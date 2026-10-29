# Ominis-OSINT: Web Hunter — ARG build (10.12.2024)

An updated build of the original `Ominis-OSINT-ARG.10.12.2024` release. The
command line stays the same, so existing scripts keep working, while the
transport, parsers and defaults are fixed.

The original release stays available untouched. If you want the new modular
suite instead, use the current `v1.0.0` release on `main`.

Maintained by AnonCatalyst with the WinterGate Intelligence Collective (WIC),
an independent privacy-first collective. <https://wintergate.org>

## Install

```sh
git clone https://github.com/AnonCatalyst/Ominis-OSINT.git
cd Ominis-OSINT
git checkout Ominis-OSINT-ARG.10.12.2024-fixed
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   . .venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage

```sh
python ominis.py -q "acme corp"
python ominis.py -q "acme corp" -l en -c US -s 2025-01-01 -e 2025-12-31
python ominis.py -q "acme corp" -p 127.0.0.1:8080 --max-results 50
python ominis.py -q "acme corp" --username acme
```

Flags:

| Flag | Meaning |
| --- | --- |
| `-q`, `--query` | query text (required) |
| `-l`, `--language` | `en` / `lang_en`; normalised for Google |
| `-c`, `--country` | `US` / `countryUS`; normalised for Google |
| `-s`, `--start_date` | `YYYY-MM-DD` or `MM/DD/YYYY` |
| `-e`, `--end_date` | `YYYY-MM-DD` or `MM/DD/YYYY` |
| `-p`, `--proxy` | proxy endpoint, repeatable; **off by default** |
| `--proxy-file` | read endpoints from a file |
| `--scrape-proxies` | harvest and validate a pool first (opt-in) |
| `--engine` | `google`, `duckduckgo`, `bing`, `serpbase` |
| `--serpbase-key` | API key, or set `SERPBASE_API_KEY` |
| `--max-results` | results to keep (default `100`) |
| `--out` | output directory (default `Results`) |
| `--username` | also check the handle across `src/urls.txt` |
| `--no-verify` | skip TLS verification (not recommended) |

Results are written to `Results/<query>.txt` and `Results/<query>.json`. The
query is reduced to a safe file name, so a query cannot choose a parent
directory.

## Optional SerpBase Google leg

Without a key, `google` is scraped like the original build. Set a key and the
Google leg is served by the documented SerpBase API instead:

```sh
export SERPBASE_API_KEY=...          # PowerShell: $env:SERPBASE_API_KEY="..."
python ominis.py -q "acme corp" -l en -c US
```

The request is `POST https://api.serpbase.dev/google/search` with `X-API-Key`
and a JSON body of `q`, `page`, `gl`, `hl`. If the key is absent the scraped
path runs; if SerpBase fails, the failure is reported and the other selected
engines still run. Date filters are folded into the query for this provider.

## Proxies

Proxies are **not** required and are **not** enabled implicitly. Pass `-p`,
`--proxy-file`, or `--scrape-proxies` when you want them. TLS verification is
on unless you explicitly pass `--no-verify`.

## What changed in this build

- The original argparse interface and defaults are preserved.
- Proxies are optional; the old "no proxies, exiting" path is gone.
- Fixed `httpx` proxy wiring, removed the browser-impersonation dependency, and
  restored certificate verification by default.
- DuckDuckGo redirect links, Bing `ck/a` links and Google `/url?q=` links are
  unwrapped; ads and non-HTTP links are skipped.
- Optional SerpBase JSON provider for the Google leg.
- Safe output names; no package-local log files or committed proxy lists.
- Removed the hard-coded Python path used by the old username search.
- Fixed the `is_potential_forum` crash when a URL has no hostname.

## Licence

MIT. See [LICENSE](LICENSE). Third-party components keep their own licences.
This release is unsigned; verify the SHA-256 digest published with the release.
