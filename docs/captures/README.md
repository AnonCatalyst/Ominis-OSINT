# Captures

Real command output and the report files it produced. Nothing here is mocked,
and nothing here contains a key, token, or absolute path from the build
machine.

These files feed [`docs/screenshots/build_gallery.py`](../screenshots/build_gallery.py),
which builds the static gallery in [`docs/screenshots`](../screenshots).

## What was run

All runs used the checkout virtual environment on Windows, Python 3.12.10,
with proxies unset (`ALL_PROXY`, `HTTP_PROXY`, `HTTPS_PROXY` cleared and
`NO_PROXY=*`). Output was redirected by `cmd` so the log holds raw UTF-8, not
the console code page.

| Capture | Command | Result |
| --- | --- | --- |
| `00-doctor.log` | `python ominis.py doctor` | Dependencies import, system TLS store, live HTTPS 200 |
| `01-local-search.log` | `python ominis.py search AnonCatalyst --max-results 20 --out docs\captures\raw\local-search --format txt,json,md` | 10 results, 7 profiles, 2 engines, proxies off |
| `02-username.log` | `python ominis.py username AnonCatalyst --quiet --all --out docs\captures\raw\username --format txt,json,md,csv` | 10 matches of 154 checked, 9 errors |
| `03-styxnet.log` | `python ominis.py search AnonCatalyst --styxnet --max-results 15 --quiet --out docs\captures\raw\styxnet --format txt,json,md` | 7 results, 14 profiles, 16 engines in 15.5 s |

The StyxNet run read its key from the local key file. The key is never printed,
and it is not present in any file here.

## Layout

```
docs/captures/
├── 00-doctor.log
├── 01-local-search.log
├── 02-username.log
├── 03-styxnet.log
└── raw/
    ├── local-search/   AnonCatalyst.{txt,json,md}
    ├── username/       username-AnonCatalyst.{txt,json,md,csv}
    └── styxnet/        AnonCatalyst.{txt,json,md}
```

## What each run shows

- **Local search.** DuckDuckGo and Bing results are merged by canonical URL, so
  the same page from both engines appears once. Mentions are counted as whole
  words. Subpages such as a GitHub repository collapse to the profile that
  owns them.
- **Username search.** Positive signals were Open Graph metadata (GitHub, X,
  YouTube, Telegram), a canonical URL (Twitch), a structured handle field
  (TikTok), and body text (GitLab, Pbase). A Russian-language "profile does not
  exist" page was rejected. The nine errors are real network failures (dead
  hosts, a TLS mismatch, a timeout), reported per URL instead of being hidden.
- **StyxNet.** One request to the WinterGate engine pool returned organic
  results plus candidate profiles. Candidates are treated as untrusted: the
  service label is capped at confidence 60 unless the local platform registry
  recognises the URL shape. The archive id is `arc_811ae4c57e4e0f85`.

## Rebuilding

Run from the repository root:

```sh
python ominis.py doctor > docs/captures/00-doctor.log 2>&1
python ominis.py search AnonCatalyst --max-results 20 --out docs/captures/raw/local-search --format txt,json,md > docs/captures/01-local-search.log 2>&1
python ominis.py username AnonCatalyst --quiet --all --out docs/captures/raw/username --format txt,json,md,csv > docs/captures/02-username.log 2>&1
python ominis.py search AnonCatalyst --styxnet --max-results 15 --quiet --out docs/captures/raw/styxnet --format txt,json,md > docs/captures/03-styxnet.log 2>&1
python docs/screenshots/build_gallery.py
```

On Windows, wrap each command in `cmd /c "..."` if you want the redirected log
to be raw UTF-8.

Live results change over time. If a rebuilt report differs from the numbers
above, update this file and the gallery together.
