#!/usr/bin/env python3
"""
urlcollector.py

Runs waybackurls, then gau, against a target and combines the results.

Usage:
    python3 urlcollector.py example.com
    python3 urlcollector.py example.com --thread 50
    python3 urlcollector.py example.com --uro
    python3 urlcollector.py example.com --nice
    python3 urlcollector.py example.com -o urls.txt
    python3 urlcollector.py example.com --thread 50 --uro --nice -o urls.txt
"""

import argparse
import shutil
import subprocess
import sys

REQUIRED_TOOLS = {
    "waybackurls": "go install github.com/tomnomnom/waybackurls@latest",
    "gau": "go install github.com/lc/gau/v2/cmd/gau@latest",
}

OPTIONAL_TOOLS = {
    "uro": "pip install uro",
}

# noise extensions to strip out with --nice
NOISE_EXTENSIONS = [
    '.json', '.js', '.fnt', '.ogg', '.css', '.jpg', '.jpeg', '.png', '.svg',
    '.img', '.gif', '.exe', '.mp4', '.flv', '.pdf', '.doc', '.ogv', '.webm',
    '.wmv', '.webp', '.mov', '.mp3', '.m4a', '.m4p', '.ppt', '.pptx', '.scss',
    '.tif', '.tiff', '.ttf', '.otf', '.woff', '.woff2', '.bmp', '.ico',
    '.eot', '.htc', '.swf', '.rtf', '.image', '.rf', '.txt', '.xml', '.zip',
]


def good_url(url: str) -> bool:
    """Return False if the url ends with a noise extension (before query string)."""
    path = url.split('?', 1)[0].split('#', 1)[0]
    return not any(path.lower().endswith(ext) for ext in NOISE_EXTENSIONS)


def check_tools(need_uro: bool) -> None:
    missing = []

    for tool, install_cmd in REQUIRED_TOOLS.items():
        if shutil.which(tool) is None:
            missing.append((tool, install_cmd))

    if need_uro and shutil.which("uro") is None:
        missing.append(("uro", OPTIONAL_TOOLS["uro"]))

    if missing:
        print("[!] Missing required tool(s). Nothing was run.\n", file=sys.stderr)
        for tool, install_cmd in missing:
            print(f"  - {tool}\n      install with: {install_cmd}\n", file=sys.stderr)
        sys.exit(1)


def run_waybackurls(target: str) -> list[str]:
    result = subprocess.run(
        ["waybackurls", target],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[!] waybackurls exited with an error:\n{result.stderr}", file=sys.stderr)
    return [line for line in result.stdout.splitlines() if line.strip()]


def run_gau(target: str, threads: int | None) -> list[str]:
    cmd = ["gau", target]
    if threads is not None:
        cmd += ["--threads", str(threads)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] gau exited with an error:\n{result.stderr}", file=sys.stderr)
    return [line for line in result.stdout.splitlines() if line.strip()]


def start_waybackurls(target: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["waybackurls", target],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def start_gau(target: str, threads: int | None) -> subprocess.Popen:
    cmd = ["gau", target]
    if threads is not None:
        cmd += ["--threads", str(threads)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def collect(proc: subprocess.Popen, name: str) -> list[str]:
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        print(f"[!] {name} exited with an error:\n{stderr}", file=sys.stderr)
    return [line for line in stdout.splitlines() if line.strip()]


def run_uro(urls: list[str]) -> list[str]:
    result = subprocess.run(
        ["uro"],
        input="\n".join(urls),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[!] uro exited with an error:\n{result.stderr}", file=sys.stderr)
        return urls
    return [line for line in result.stdout.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Collect URLs for a target via waybackurls + gau."
    )
    parser.add_argument("url", help="Target domain/URL to collect URLs for")
    parser.add_argument(
        "--thread", type=int, default=None,
        help="Thread count passed to gau (--threads)"
    )
    parser.add_argument(
        "--uro", action="store_true",
        help="Deduplicate/normalize the final URL list with uro. If not set, duplicates are kept."
    )
    parser.add_argument(
        "--nice", action="store_true",
        help="Strip URLs ending in noisy static extensions (js, css, images, fonts, archives, etc.)"
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="Save the final URL list to FILE (in addition to printing it)"
    )
    parser.add_argument(
        "--parallel", action="store_true",
        help="Run waybackurls and gau at the same time instead of one after the other"
    )

    args = parser.parse_args()

    check_tools(need_uro=args.uro)

    if args.parallel:
        print(f"[*] Running waybackurls + gau on {args.url} in parallel ...", file=sys.stderr)
        wb_proc = start_waybackurls(args.url)
        gau_proc = start_gau(args.url, args.thread)
        urls = collect(wb_proc, "waybackurls") + collect(gau_proc, "gau")
    else:
        print(f"[*] Running waybackurls on {args.url} ...", file=sys.stderr)
        urls = run_waybackurls(args.url)

        print(f"[*] Running gau on {args.url} ...", file=sys.stderr)
        urls += run_gau(args.url, args.thread)

    if args.nice:
        before = len(urls)
        urls = [u for u in urls if good_url(u)]
        print(f"[*] --nice filtered {before - len(urls)} noisy URL(s)", file=sys.stderr)

    if args.uro:
        before = len(urls)
        urls = run_uro(urls)
        print(f"[*] --uro removed {before - len(urls)} duplicate URL(s)", file=sys.stderr)

    print(f"[*] {len(urls)} URL(s) collected\n", file=sys.stderr)

    output_text = "\n".join(urls)
    print(output_text)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text + ("\n" if urls else ""))
        print(f"\n[*] Saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
