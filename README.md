# urlcollector

License: MIT

`urlcollector` fetches historical URLs for a target domain from the **Wayback Machine CDX API directly** (with manual, reliable pagination and retry/backoff) and merges them with results from `gau`, into a single URL list, with optional deduplication and noise filtering.

> **Why not `waybackurls`?** On larger domains, `waybackurls` can silently drop the vast majority of results due to how it handles CDX pagination — it exits with code `0` and no error, but returns a tiny fraction of the actual data. `urlcollector` talks to the CDX API directly, fetches every page itself, and explicitly reports any page that fails after retries instead of failing silently.

## Resources

- [Usage](#usage)
- [Flags](#flags)
- [Requirements](#requirements)
- [Installation](#installation)

## Usage

Examples:
```
$ python3 urlcollector.py example.com
$ python3 urlcollector.py example.com --threads 50
$ python3 urlcollector.py example.com --uro
$ python3 urlcollector.py example.com --nice
$ python3 urlcollector.py example.com --strict-nice --exclude-ext .pdf,.zip
$ python3 urlcollector.py example.com --ext-only .js,.json,.php
$ python3 urlcollector.py example.com --no-subs
$ python3 urlcollector.py example.com --only-200
$ python3 urlcollector.py example.com --dates
$ python3 urlcollector.py example.com --no-source
$ python3 urlcollector.py example.com -o urls.txt
$ python3 urlcollector.py example.com --threads 100 --uro --nice --parallel -o urls.txt
```

To display the help for the tool use the `-h` flag:
```
$ python3 urlcollector.py -h
```

## Flags

| Flag | Description | Example |
|---|---|---|
| `--threads` | parallel workers for CDX page fetching **and** thread count passed to `gau` (default: `10`) | `urlcollector.py example.com --threads 50` |
| `--timeout` | per-request timeout in seconds for each CDX page (default: `30`) | `urlcollector.py example.com --timeout 60` |
| `--retries` | retry attempts per CDX page before giving up (default: `3`) | `urlcollector.py example.com --retries 5` |
| `--delay` | base backoff delay in seconds between retries, doubles each attempt (default: `1.0`) | `urlcollector.py example.com --delay 2` |
| `--no-subs` | do **not** include subdomains (default: subdomains are included) | `urlcollector.py example.com --no-subs` |
| `--only-200` | only keep records with HTTP status `200` | `urlcollector.py example.com --only-200` |
| `--dates` | prefix each CDX URL with its capture timestamp (tab-separated) | `urlcollector.py example.com --dates` |
| `--nice` | strip URLs ending in **hard-noise** extensions (fonts, images, audio, video) | `urlcollector.py example.com --nice` |
| `--strict-nice` | like `--nice`, but also strips **soft-noise** extensions (`.js`, `.json`, `.pdf`, `.txt`, `.xml`, `.zip`, `.doc(x)`, `.ppt(x)`, `.scss`) | `urlcollector.py example.com --strict-nice` |
| `--exclude-ext` | extra extensions to exclude on top of `--nice`/`--strict-nice` | `urlcollector.py example.com --exclude-ext .pdf,.zip` |
| `--ext-only` | keep **only** URLs with these extensions (overrides all other filtering) | `urlcollector.py example.com --ext-only .js,.json,.php` |
| `--uro` | deep-normalize/dedupe the final URL list with `uro` (a basic dedup always runs regardless) | `urlcollector.py example.com --uro` |
| `--no-source` | skip `gau` entirely and only use the Wayback CDX API | `urlcollector.py example.com --no-source` |
| `--parallel` | run the CDX fetch and `gau` concurrently instead of sequentially | `urlcollector.py example.com --parallel` |
| `-o`, `--output` | filename to write the final results to | `urlcollector.py example.com -o urls.txt` |
| `-h`, `--help` | show help and exit | `urlcollector.py -h` |

`.js` and `.json` are deliberately **kept by default** — they're a common source of exposed endpoints, secrets, and configs. Use `--strict-nice` if you specifically want them stripped too.

## Requirements

`urlcollector` talks to the Wayback CDX API itself using only Python's standard library — no `waybackurls` binary needed. It still wraps `gau` for its Common Crawl / OTX coverage:

- [`gau`](https://github.com/lc/gau)
- [`uro`](https://github.com/s0md3v/uro) — only required if you pass `--uro`

If any required tool is missing, `urlcollector.py` prints the exact install command for it and **exits without running anything**, so partial/incomplete results are never produced.

If some CDX pages fail even after all retries, `urlcollector.py` will say so explicitly on stderr (page numbers included) instead of silently returning an incomplete list.

## Installation

From source:
```
$ git clone https://github.com/moh3n355/urlcollector.git
$ cd urlcollector
$ python3 urlcollector.py -h
```

Install the underlying tools:
```
$ go install github.com/lc/gau/v2/cmd/gau@latest
$ pip install uro
```

> If `go install` fails with a `403` from `proxy.golang.org`, your network may be blocking Go's default module proxy. Retry with:
> ```
> $ GOPROXY=direct GOSUMDB=off go install github.com/lc/gau/v2/cmd/gau@latest
> ```
