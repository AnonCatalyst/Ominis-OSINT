# Ominis-OSINT: Web Hunter

### 🚧 Project Status: Active Development
> **Status:** In Progress  
> **Estimated Completion:** 1-3 days
> 
> **Notice:** This project is currently in its final development cycle. During this sprint, our focus is strictly on resolving existing reported bugs. Thank you for your support!


Discover online mentions of a query or username, and map the social profiles
and forums that surface with them. Ominis searches public web results, reports
what it finds, and gets out of the way.

MIT licensed. Maintained by [AnonCatalyst](https://github.com/AnonCatalyst) with
the [WinterGate Intelligence Collective](https://wintergate.org).

> **Use it on your own presence or with permission.** Ominis only reads public
> pages, but a search can still be intrusive. You are responsible for the law,
> the site's terms, and the people whose data you touch.

## Version 1.0

This is the full suite. It is published alongside the patched original
(`v0.5.0`) so anyone relying on the old layout can keep it. Highlights:

- **Proxies are off by default.** No proxy list is downloaded or validated
  unless you ask for it.
- **Real filters.** Language, country, and date ranges are passed to each
  engine instead of being accepted and ignored.
- **Optional results API.** Set `SERPBASE_API_KEY` and the Google leg goes
  through a SerpBase-compatible JSON API; leave it unset and the scrapers run
  as before.
- **No browser download.** Username checks share one HTTPX client instead of
  starting a `requests_html` Chromium session per URL.
- **Reports in four formats.** `txt`, `json`, `csv`, and `md`, with file names
  that are safe for any query.
- **A real CLI.** Scriptable subcommands, exit codes, and a `doctor` check.

## Install

```sh
git clone https://github.com/AnonCatalyst/Ominis-OSINT
cd Ominis-OSINT
python -m pip install -r requirements.txt
```

Or install the package:

```sh
python -m pip install Ominis-OSINT
```

Python 3.10 or newer is required.

## Use

### Search

```sh
python ominis.py search "acme corp" --country US --lang en --max-results 40
```

Results are written to `Results/` (override with `--out`). Choose formats with
`--format txt,json,csv,md`.

Filters:

```sh
python ominis.py search "acme corp" --since 2025-01-01 --until 2025-12-31
```

Engines are `duckduckgo`, `bing`, and `serpbase`. The first two are scraped.
`serpbase` needs a key:

```sh
export SERPBASE_API_KEY=...            # PowerShell: $env:SERPBASE_API_KEY="..."
python ominis.py search "acme corp" --engine duckduckgo,serpbase
```

With a key, the Google leg is a JSON API call. Without one, the engine is
skipped with a clear message and the scraped engines still run. The API is
`POST https://api.serpbase.dev/google/search` with the key in `X-API-Key` and a
JSON body of `q`, `page`, `gl`, `hl`. Override the endpoint in
`ominis_src/config.py` if you use a compatible provider. Date filters are folded
into the query for this provider (`after:YYYY/MM/DD before:YYYY/MM/DD`), so the
other engines keep their native date parameters.

### Username search

```sh
python ominis.py username acme --format txt,json,md
```

The platform list lives in `ominis_src/urls.txt`, one URL template per line.
`--urls FILE` points at your own list. Checks run concurrently (default 8),
each with its own timeout. `--all` records non-matches too.

### Proxies (opt-in)

```sh
python ominis.py proxy harvest --limit 50
python ominis.py search "acme corp" --proxy-file config/valid_proxies.txt
```

`proxy harvest` downloads candidates, validates them, and writes the working
pool. Nothing else in Ominis calls it. You can also pass endpoints directly:

```sh
python ominis.py search "acme corp" --proxy 127.0.0.1:8080 --proxy socks5://127.0.0.1:1080
```

Bare `host:port` entries are HTTP proxies. `http://`, `https://`, `socks5://`,
and `socks5h://` URLs are accepted, including authenticated forms. Credentials
are redacted from console output and error logs. An explicit pool is never
silently bypassed: if every proxy fails, the request fails.

TLS verification is on. For a private CA set `SSL_CERT_FILE` (HTTPX and aiohttp
both honour it). `--no-verify` exists for debugging and is not recommended.

### Guided mode

`python ominis.py` with no arguments walks through a search and offers a
username check at the end. Every prompt has a default; proxies default to off.

### Health check

```sh
python ominis.py doctor
```

## Try it from GitHub Actions

The **Ominis demo** workflow runs a search or username check on GitHub's
runners and uploads the report as an artifact. No clone, no install:

1. Open **Actions → Ominis demo → Run workflow**.
2. Pick `search`, `username`, or `both`, and fill in the query.
3. Download `ominis-results` when it finishes.

It uses `contents: read`, passes inputs through environment variables rather
than interpolating them into shell code, and does not use sudo or Tor.

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `OMINIS_ENGINES` | comma-separated engine list | `duckduckgo,bing` |
| `OMINIS_LANGUAGE` | language code, e.g. `en` | none |
| `OMINIS_COUNTRY` | country code, e.g. `US` | none |
| `OMINIS_SINCE`, `OMINIS_UNTIL` | `YYYY-MM-DD` bounds | none |
| `OMINIS_MAX_RESULTS` | total results to keep | `50` |
| `OMINIS_PROXY_POOL` | comma-separated proxy endpoints | off |
| `SERPBASE_API_KEY` | optional results API key | none |
| `OMINIS_OUTPUT_DIR` | report directory | `Results` |
| `OMINIS_FORMATS` | `txt,json,csv,md` | `txt,json` |
| `OMINIS_TIMEOUT` | seconds per request | `15` |

Arguments win over environment variables. The tool never writes secrets to
disk.

## Output

| File | Contents |
| --- | --- |
| `Results/<query>.txt` | human-readable results and summary |
| `Results/<query>.json` | summary, results, profiles |
| `Results/<query>.csv` | one row per result |
| `Results/<query>.md` | Markdown brief |
| `Results/username-<name>.<ext>` | username matches and errors |

`<query>` is a slug: letters, digits, `.`, `-` and `_` only, at most 60
characters. `../../notes` becomes `notes`, so a query can never choose the
directory a report is written to.

## Development

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The suite is offline. Transport tests run against loopback proxies and locally
generated certificates; engine and report tests parse fixed fixtures. CI runs
the same command on Python 3.10, 3.11, and 3.12. CodeQL runs through the
repository default setup, with dependency updates from
`.github/dependabot.yml`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, style, and pull-request
expectations, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community rules.

Layout:

```
ominis.py              entry point (delegates to ominis_src.cli)
ominis_src/
  cli.py               subcommands and arguments
  config.py            settings, environment, proxy files
  engines.py           DuckDuckGo, Bing, SerpBase, parsers
  search.py            orchestration, de-duplication, reports
  username.py          profile checks
  report.py            safe file names and writers
  proxy_handler.py     opt-in harvesting and validation
  wizard.py            guided first run
  tools_handler.py     legacy scraping API (kept for compatibility)
  utils.py             mentions, profiles, forums
tests/                 offline tests
```

## Security

- Reports are plain text; do not paste them into public issues if they contain
  personal data.
- Proxy endpoints are untrusted input. The parser rejects malformed entries and
  never logs credentials.
- Please report vulnerabilities privately: see [SECURITY.md](SECURITY.md) or use
  the repository's Security tab. Never open a public issue with a live key.
- No API key, token or proxy credential is written to disk by the tool.

## Licence

MIT. See [LICENSE](LICENSE). This release is not code-signed; see
[CODE_SIGNING.md](CODE_SIGNING.md) for the SHA-256 verification steps and why
there is no self-signed certificate. The WinterGate names and logos are covered
by [TRADEMARKS.md](TRADEMARKS.md), not by the MIT licence.
