#!/usr/bin/env python3
"""
urlcollector.py

Collects historical URLs for a target using:
  1. The Wayback Machine CDX API directly (manual, reliable pagination
     with retry/backoff -- does NOT rely on the waybackurls binary,
     which silently drops most pages on large domains).
  2. gau (Common Crawl + OTX + Wayback).

Results are deduplicated and optionally normalized/filtered.

Usage:
    python3 urlcollector.py example.com
    python3 urlcollector.py example.com --threads 10
    python3 urlcollector.py example.com --no-subs
    python3 urlcollector.py example.com --nice
    python3 urlcollector.py example.com --strict-nice
    python3 urlcollector.py example.com --exclude-ext .pdf,.zip
    python3 urlcollector.py example.com --ext-only .js,.json,.php
    python3 urlcollector.py example.com --uro
    python3 urlcollector.py example.com --only-200
    python3 urlcollector.py example.com --dates
    python3 urlcollector.py example.com --parallel -o urls.txt
"""

import argparse
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

CDX_BASE = "http://web.archive.org/cdx/search/cdx"

REQUIRED_TOOLS = {
    "gau": "go install github.com/lc/gau/v2/cmd/gau@latest",
}

OPTIONAL_TOOLS = {
    "uro": "pip install uro",
}

# Extensions that are almost never useful for bug hunting (binary/media/fonts).
# Filtered by default when --nice is passed.
HARD_NOISE = {
    ".css", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".ico",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".bmp", ".tif", ".tiff", ".webp",
    ".mp3", ".mp4", ".mov", ".wmv", ".flv", ".ogg", ".ogv", ".webm",
    ".m4a", ".m4p",
}

# Extensions that CAN contain useful info (JS endpoints/secrets, JSON configs,
# document metadata) -- only filtered if --strict-nice is explicitly passed.
SOFT_NOISE = {
    ".js", ".json", ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".txt", ".xml", ".zip", ".scss",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def check_tools(need_uro: bool) -> None:
    missing = []
    for tool, install_cmd in REQUIRED_TOOLS.items():
        if shutil.which(tool) is None:
            missing.append((tool, install_cmd))
    if need_uro and shutil.which("uro") is None:
        missing.append(("uro", OPTIONAL_TOOLS["uro"]))
    if missing:
        log("[!] Missing required tool(s). Nothing was run.\n")
        for tool, install_cmd in missing:
            log(f"  - {tool}\n      install with: {install_cmd}\n")
        sys.exit(1)


# --------------------------------------------------------------------------
# Wayback CDX API (manual, reliable pagination)
# --------------------------------------------------------------------------

def _cdx_url(target: str, with_subs: bool, only_200: bool, with_dates: bool) -> str:
    scope = f"*.{target}/*" if with_subs else f"{target}/*"
    fl = "timestamp,original" if with_dates else "original"
    params = {
        "url": scope,
        "output": "text",
        "fl": fl,
        "collapse": "urlkey",
    }
    if only_200:
        params["filter"] = "statuscode:200"
    return CDX_BASE + "?" + urllib.parse.urlencode(params, safe="*")


def _fetch(url: str, timeout: int, retries: int, delay: float, label: str) -> str | None:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "urlcollector/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                backoff = delay * (2 ** (attempt - 1))
                log(f"[!] {label}: attempt {attempt}/{retries} failed ({e}), retrying in {backoff:.1f}s ...")
                time.sleep(backoff)
    log(f"[!] {label}: giving up after {retries} attempts ({last_err})")
    return None


def get_num_pages(target: str, with_subs: bool, timeout: int, retries: int, delay: float) -> int | None:
    scope = f"*.{target}/*" if with_subs else f"{target}/*"
    url = CDX_BASE + "?" + urllib.parse.urlencode({"url": scope, "showNumPages": "true"}, safe="*")
    text = _fetch(url, timeout, retries, delay, "showNumPages")
    if text is None:
        return None
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        log(f"[!] Unexpected showNumPages response: {text!r}")
        return None


def run_cdx(
    target: str,
    with_subs: bool,
    threads: int,
    timeout: int,
    retries: int,
    delay: float,
    only_200: bool,
    with_dates: bool,
) -> list[str]:
    num_pages = get_num_pages(target, with_subs, timeout, retries, delay)
    if num_pages is None:
        log("[!] Could not determine CDX page count. Skipping archive.org collection.")
        return []

    log(f"[*] CDX reports {num_pages} page(s) for {target} (subs={with_subs})")

    base_scope = f"*.{target}/*" if with_subs else f"{target}/*"
    fl = "timestamp,original" if with_dates else "original"

    def build_page_url(page: int) -> str:
        params = {
            "url": base_scope,
            "output": "text",
            "fl": fl,
            "collapse": "urlkey",
            "page": str(page),
        }
        if only_200:
            params["filter"] = "statuscode:200"
        return CDX_BASE + "?" + urllib.parse.urlencode(params, safe="*")

    urls: list[str] = []
    failed_pages: list[int] = []

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        future_to_page = {
            pool.submit(_fetch, build_page_url(p), timeout, retries, delay, f"page {p}"): p
            for p in range(num_pages)
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            text = future.result()
            if text is None:
                failed_pages.append(page)
                continue
            lines = [line for line in text.splitlines() if line.strip()]
            urls.extend(lines)

    if failed_pages:
        log(f"[!] WARNING: {len(failed_pages)}/{num_pages} page(s) failed permanently: "
            f"{sorted(failed_pages)} -- results are INCOMPLETE for these pages.")
    else:
        log(f"[*] All {num_pages} CDX page(s) fetched successfully ({len(urls)} raw line(s)).")

    return urls


# --------------------------------------------------------------------------
# gau
# --------------------------------------------------------------------------

def start_gau(target: str, threads: int | None, with_subs: bool) -> subprocess.Popen:
    cmd = ["gau", target]
    if threads is not None:
        cmd += ["--threads", str(threads)]
    if with_subs:
        cmd += ["--subs"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def collect(proc: subprocess.Popen, name: str) -> list[str]:
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        log(f"[!] {name} exited with an error:\n{stderr}")
    return [line for line in stdout.splitlines() if line.strip()]


def run_gau(target: str, threads: int | None, with_subs: bool) -> list[str]:
    proc = start_gau(target, threads, with_subs)
    return collect(proc, "gau")


# --------------------------------------------------------------------------
# Filtering / dedup helpers
# --------------------------------------------------------------------------

def _path_ext(url: str) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0]
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def apply_nice_filters(
    urls: list[str],
    strict: bool,
    exclude_ext: set[str],
    ext_only: set[str],
) -> list[str]:
    if ext_only:
        kept = [u for u in urls if _path_ext(u) in ext_only]
        log(f"[*] --ext-only kept {len(kept)}/{len(urls)} URL(s) matching {sorted(ext_only)}")
        return kept

    noise = set(HARD_NOISE)
    if strict:
        noise |= SOFT_NOISE
    noise |= exclude_ext

    kept = [u for u in urls if _path_ext(u) not in noise]
    log(f"[*] Noise filtering removed {len(urls) - len(kept)} URL(s) "
        f"(strict={strict}, extra_excluded={sorted(exclude_ext) if exclude_ext else '-'})")
    return kept


def run_uro(urls: list[str]) -> list[str]:
    result = subprocess.run(["uro"], input="\n".join(urls), capture_output=True, text=True)
    if result.returncode != 0:
        log(f"[!] uro exited with an error:\n{result.stderr}")
        return urls
    return [line for line in result.stdout.splitlines() if line.strip()]


def parse_ext_list(raw: str | None) -> set[str]:
    if not raw:
        return set()
    out = set()
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = "." + item
        out.add(item)
    return out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Collect URLs for a target via a manually-paginated Wayback CDX fetch + gau."
    )
    parser.add_argument("url", help="Target domain to collect URLs for")

    parser.add_argument("--threads", type=int, default=10,
                         help="Parallel workers for CDX page fetching AND thread count passed to gau (default: 10)")
    parser.add_argument("--timeout", type=int, default=30,
                         help="Per-request timeout in seconds for CDX pages (default: 30)")
    parser.add_argument("--retries", type=int, default=3,
                         help="Retry attempts per CDX page before giving up (default: 3)")
    parser.add_argument("--delay", type=float, default=1.0,
                         help="Base backoff delay in seconds between retries (default: 1.0, doubles each retry)")

    parser.add_argument("--no-subs", action="store_true",
                         help="Do NOT include subdomains (default: subdomains included)")
    parser.add_argument("--only-200", action="store_true",
                         help="Only keep records with HTTP status 200")
    parser.add_argument("--dates", action="store_true",
                         help="Prefix each CDX URL with its capture timestamp (tab-separated)")

    parser.add_argument("--nice", action="store_true",
                         help="Strip URLs ending in hard-noise extensions (fonts/images/audio/video)")
    parser.add_argument("--strict-nice", action="store_true",
                         help="Like --nice, but also strips soft-noise extensions (.js, .json, .pdf, .txt, .xml, ...)")
    parser.add_argument("--exclude-ext", metavar="EXT,EXT,...",
                         help="Extra extensions to exclude on top of --nice/--strict-nice, e.g. .pdf,.zip")
    parser.add_argument("--ext-only", metavar="EXT,EXT,...",
                         help="Keep ONLY these extensions (overrides all other filtering), e.g. .js,.json,.php")

    parser.add_argument("--uro", action="store_true",
                         help="Deep-normalize/dedupe the final URL list with uro")
    parser.add_argument("--no-source", action="store_true",
                         help="Skip gau entirely and only use the Wayback CDX API")
    parser.add_argument("--parallel", action="store_true",
                         help="Run CDX fetching and gau at the same time instead of sequentially")

    parser.add_argument("-o", "--output", metavar="FILE",
                         help="Save the final URL list to FILE (in addition to printing it)")

    args = parser.parse_args()

    if args.dates and (args.nice or args.strict_nice or args.exclude_ext or args.ext_only):
        log("[!] --dates changes the line format (timestamp<TAB>url); "
            "extension-based filters will not match correctly. Proceed with caution.")

    check_tools(need_uro=args.uro)

    with_subs = not args.no_subs
    exclude_ext = parse_ext_list(args.exclude_ext)
    ext_only = parse_ext_list(args.ext_only)

    cdx_urls: list[str] = []
    gau_urls: list[str] = []

    if args.parallel and not args.no_source:
        log(f"[*] Running CDX fetch + gau on {args.url} in parallel ...")
        with ThreadPoolExecutor(max_workers=2) as pool:
            cdx_future = pool.submit(
                run_cdx, args.url, with_subs, args.threads, args.timeout,
                args.retries, args.delay, args.only_200, args.dates,
            )
            gau_future = pool.submit(run_gau, args.url, args.threads, with_subs)
            cdx_urls = cdx_future.result()
            gau_urls = gau_future.result()
    else:
        log(f"[*] Fetching archive.org CDX for {args.url} ...")
        cdx_urls = run_cdx(
            args.url, with_subs, args.threads, args.timeout,
            args.retries, args.delay, args.only_200, args.dates,
        )
        if not args.no_source:
            log(f"[*] Running gau on {args.url} ...")
            gau_urls = run_gau(args.url, args.threads, with_subs)

    log(f"[*] CDX: {len(cdx_urls)} line(s), gau: {len(gau_urls)} line(s)")

    # Always dedupe the raw combined set for free (cheap, always safe).
    urls = list(dict.fromkeys(cdx_urls + gau_urls))
    log(f"[*] {len(urls)} unique URL(s) after basic merge/dedup")

    if args.nice or args.strict_nice or args.exclude_ext or args.ext_only:
        urls = apply_nice_filters(urls, args.strict_nice, exclude_ext, ext_only)

    if args.uro:
        before = len(urls)
        urls = run_uro(urls)
        log(f"[*] --uro normalized/removed {before - len(urls)} additional duplicate(s)")

    log(f"[*] {len(urls)} URL(s) collected\n")

    output_text = "\n".join(urls)
    print(output_text)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text + ("\n" if urls else ""))
        log(f"\n[*] Saved to {args.output}")


if __name__ == "__main__":
    main()
