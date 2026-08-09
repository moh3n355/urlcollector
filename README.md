# urlcollector

License: MIT

`urlcollector` runs `waybackurls` and then `gau` against a target domain and merges the results into a single URL list, with optional deduplication and noise filtering. Wraps two well-known recon tools instead of reimplementing them.

## Resources

- [Usage](#usage)
- [Flags](#flags)
- [Requirements](#requirements)
- [Installation](#installation)

## Usage

Examples:
```
$ python3 urlcollector.py example.com
$ python3 urlcollector.py example.com --thread 50
$ python3 urlcollector.py example.com --uro
$ python3 urlcollector.py example.com --nice
$ python3 urlcollector.py example.com -o urls.txt
$ python3 urlcollector.py example.com --thread 100 --uro --nice -o urls.txt
```

To display the help for the tool use the `-h` flag:
```
$ python3 urlcollector.py -h
```

## Flags

| Flag | Description | Example |
|---|---|---|
| `--thread` | number of threads passed to gau | `urlcollector.py example.com --thread 50` |
| `--parallel` | Run waybackurls and gau concurrently instead of sequentially | `urlcollector.py example.com ----parallel` |
| `--uro` | dedupe/normalize the final URL list with uro (if not set, duplicates are kept) | `urlcollector.py example.com --uro` |
| `--nice` | strip URLs ending in noisy static extensions (js, css, images, fonts, archives, etc.) | `urlcollector.py example.com --nice` |
| `-o`, `--output` | filename to write the final results to | `urlcollector.py example.com -o urls.txt` |
| `-h`, `--help` | show help and exit | `urlcollector.py -h` |

## Requirements

`urlcollector` is a wrapper — it needs the following binaries available in `$PATH`:

- [`waybackurls`](https://github.com/tomnomnom/waybackurls)
- [`gau`](https://github.com/lc/gau)
- [`uro`](https://github.com/s0md3v/uro) — only required if you pass `--uro`

If any required tool is missing, `urlcollector.py` prints the exact install command for it and **exits without running anything**, so partial/incomplete results are never produced.

## Installation

From source:
```
$ git clone https://github.com/YOUR_USERNAME/urlcollector.git
$ cd urlcollector
$ python3 urlcollector.py -h
```

Install the underlying tools:
```
$ go install github.com/tomnomnom/waybackurls@latest
$ go install github.com/lc/gau/v2/cmd/gau@latest
$ pip install uro
```

> If `go install` fails with a `403` from `proxy.golang.org`, your network may be blocking Go's default module proxy. Retry with:
> ```
> $ GOPROXY=direct GOSUMDB=off go install github.com/lc/gau/v2/cmd/gau@latest
> ```
