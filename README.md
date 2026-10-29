# Ominis-OSINT: Web Hunter — legacy 0.5.x

The original interactive build, kept alive for people who prefer the guided
prompts over the new `v1.0.0` subcommand suite. The prompts and result layout
are the same; proxies are now optional and the transport/parsers are fixed.

The original releases remain available untouched. For the new modular suite,
use `v1.0.0` on `main`.

Maintained by AnonCatalyst with the WinterGate Intelligence Collective (WIC),
an independent privacy-first collective. <https://wintergate.org>

## Install

```sh
git clone https://github.com/AnonCatalyst/Ominis-OSINT.git
cd Ominis-OSINT
git checkout v0.5.0
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   . .venv/bin/activate
python -m pip install -r requirements.txt
python ominis.py
```

## Usage

Run `python ominis.py` and answer the prompts:

1. Query text.
2. Language (optional, e.g. `en`).
3. Country (optional, e.g. `US`).
4. Start and end dates (optional, `YYYY-MM-DD`).
5. **Use proxies?** Defaults to **no**. If you answer `y`, the tool harvests and
   validates a pool before searching; if none validate, it continues directly.
6. After the search you can run a username check across `ominis_src/urls.txt`.

Reports are written to `Results/`:

- `Results/<query>_dual-engine_results.txt`
- `Results/<query>_dual-engine_results.json`
- `Results/username-<name>_results.txt`

`<query>` is reduced to letters, digits, `.`, `-` and `_`, at most 60
characters, so it cannot choose a parent directory.

## Optional SerpBase engine

The legacy build searches DuckDuckGo and Bing. Set a SerpBase key and it adds a
Google results API leg as a third engine:

```sh
export SERPBASE_API_KEY=...          # PowerShell: $env:SERPBASE_API_KEY="..."
python ominis.py
```

The request is `POST https://api.serpbase.dev/google/search` with `X-API-Key`
and a JSON body of `q`, `page`, `gl`, `hl`. No key means no API call and no
extra dependency. Date filters are folded into the query for that provider.

## What changed in 0.5.0

- Proxies are opt-in and off by default; TLS verification is on.
- Fixed `httpx` proxy wiring and removed `fake_useragent`.
- DuckDuckGo redirects and Bing `ck/a` links are unwrapped; ads are skipped.
- Optional SerpBase Google leg.
- Safe output names; no package-local logs or committed proxy list.
- Username checks use `httpx` instead of `requests-html`, with the hard-coded
  interpreter path removed.
- Fixed `is_potential_forum` when a URL has no hostname.

## Licence

MIT. See [LICENSE](LICENSE).

This build is not code-signed. See [CODE_SIGNING.md](CODE_SIGNING.md) for
the SHA-256 verification steps and why there is no self-signed
certificate. The WinterGate names and logos are covered by
[TRADEMARKS.md](TRADEMARKS.md), not by the MIT licence. This release is unsigned; verify the SHA-256 digest
published with the release.
