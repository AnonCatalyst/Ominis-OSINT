# Ominis Investigation Workstation

A native Windows desktop application for the Ominis engine. It is a real Qt
window built with PySide6 — **not a browser page, not a local web server, and
not an Electron shell**. There is no embedded browser: search results, profile
checks, StyxNet runs, and reports all happen inside one desktop window.

- Workstation version: **1.0.0**
- Bundled engine: **Ominis 1.2.1**
- Platform: Windows 10/11, 64-bit
- License: MIT

![Workstation overview](screenshots/01-overview.png)

## Download

The release asset is `Ominis-Workstation-1.0.0-win64.zip`. Unpack it and run
`OminisWorkstation.exe`. There is no installer. The only things written outside
the folder are the reports you ask for, the optional StyxNet key file, and
window preferences in the registry.

The build is **unsigned**. Windows SmartScreen may show a warning for an
unknown publisher. No code signing is claimed; see `CODE_SIGNING.md` in the
repository for why.

SHA-256 digests for every release asset are published with the release.

## Three modes

| Mode | What it does |
|---|---|
| **Web search** | Scrapes DuckDuckGo and Bing locally, or calls SerpBase when a key is set. Results are canonicalised and profiles are detected from the URLs. |
| **Username** | Checks a handle against the shipped platform templates over HTTPS and confirms a profile from page metadata, canonical links, redirects, structured data, or visible page content. |
| **StyxNet** | Sends one request to WinterGate's engine pool. Organic results and candidate profiles come back together. Candidate confidence is capped until you open the profile. |

StyxNet replaces the local engines for that run and falls back to them if the
service errors. It is optional and never enabled by default.

### Access to StyxNet

Access is free right now and will stay free for the foreseeable future. Join
the WinterGate Discord and ask for a key:

<https://discord.gg/tu5CynxjZq>

The key is stored in `~/.config/ominis/styxnet-key.txt` (or
`%USERPROFILE%\.config\ominis\styxnet-key.txt`) with the file permissions
tightened to the current account. An existing key in
`%APPDATA%\ominis\styxnet-key.txt` is also accepted. Settings never display the
key again; it shows only whether a key is saved and how many characters it has.
You can also use `STYXNET_ACCESS_KEY` or `OMINIS_STYXNET_KEY` if you prefer
environment variables. Client-side limits (one search at a time, 20 per hour,
100 per day, 10 seconds between searches, 200 engines per request) are enforced
by the engine, not by the window, so they hold across terminals too.

## Detection signals

Every profile row says **how** it was detected. The same vocabulary is used in
the results table, the profile table, and the inspector.

| Signal | Meaning | Strength |
|---|---|---|
| **Page metadata** | The page title or Open Graph metadata named the handle at a word boundary. | Strong |
| **Canonical URL** | The page's canonical URL points at the handle, which a soft 404 would not do. | Strong |
| **Redirect** | The template URL redirected to the handle's profile instead of a not-found page. | Strong |
| **Structured data** | JSON-LD or another structured block named the handle. | Strong |
| **Page content** | The handle appears in visible profile content, not a footer mention. | Medium |
| **URL pattern** | The URL shape matched the curated platform registry. The page was not inspected. | Medium |
| **StyxNet candidate** | Returned by StyxNet. Unverified until you open it. | Candidate |
| **No match** | The page loaded but nothing matched the handle. | None |
| **Request error** | The check did not complete. Neither a match nor a confirmed absence. | Error |

The interface carries the same information visually:

- a **Signal** column with a colour per detection type;
- a tinted confidence cell and a numeric confidence, with `—` when the host has
  no registry confidence;
- a **◆** mark on search results that resolve to a detected profile;
- **✓** for found username checks, **✗** for errors, **·** for checked misses;
- an inspector with a confidence meter, the signal in plain language, and a
  reminder that StyXNet results are leads, not proof;
- **Help → Detection signals** (or F1) for the full reference, with the same
  explanation used in the tooltips and the inspector.

Rows are tinted by the strength of the evidence. A checked miss stays neutral,
so confirmed rows stand out. Links open in your default system browser; the
workstation never embeds a web view.

Confidence is not a probability. It reflects the strength of the signal and
the registry entry for that host. Treat anything below 70 as a lead to verify.

## Screenshots

All images are rendered by Qt itself from captured runs. The payloads in
[`captures/`](captures) come from real JSON reports in
[`../captures`](../captures); nothing here is mocked or drawn in a browser.

| | |
|---|---|
| ![Welcome](screenshots/00-welcome.png) | ![Results](screenshots/02-results.png) |
| ![Profiles](screenshots/03-profiles.png) | ![Username checks](screenshots/06-username-checks.png) |
| ![StyxNet](screenshots/07-styxnet-overview.png) | ![Detection signals](screenshots/12-signals.png) |

More: [username profiles](screenshots/05-username-profiles.png),
[StyxNet profiles](screenshots/08-styxnet-profiles.png),
[settings](screenshots/09-settings.png), [about](screenshots/10-about.png),
[environment check](screenshots/11-doctor.png).

> StyxNet's organic result lane returned no rows on 2026-11-03 while candidate
> profiles still came back. The StyxNet screenshots therefore replay the
> verified 2026-11-02 capture and are labelled from that run. The live
> behaviour is recorded in [`../captures`](../captures).

## Reports

Every finished run writes the formats selected in the case panel (`txt`,
`json`, `md`, and optionally `csv`) to the chosen folder. The default is
`Documents\Ominis Cases`. **Open report folder** opens the last run's folder.

Reports are plain files. Nothing is uploaded anywhere. The StyxNet key is never
written into a report.

## Proxies

Proxies are optional and off by default. The workstation never downloads or
validates a proxy list on its own. If your machine has `HTTP_PROXY`,
`HTTPS_PROXY`, or `ALL_PROXY` set, the underlying HTTP client may honour them;
**Environment check** shows whether they are set, without printing their
values (they can contain credentials).

## Run from source

Python 3.10 or newer:

```sh
python -m pip install -r requirements.txt
python -m pip install PySide6
python ominis_workstation.py
```

or:

```sh
python -m ominis_workstation
```

Verify a build without touching the network:

```sh
python -m ominis_workstation --smoke build-smoke.txt
```

The smoke report checks the window, icon, stylesheet, tabs, and imports, and
exits non-zero if the window itself did not come up. Add a `.png` path to save
a render of the window instead.

## Build the executable

On Windows, in the repository root:

```sh
python -m pip install PyInstaller
pyinstaller --noconfirm --clean workstation.spec
```

The result is `dist\OminisWorkstation.exe`, with the Qt runtime, the Ominis
engine, and both detection tables inside. The spec excludes Qt WebEngine on
purpose: there is no browser in this application.

## Tests

The headless Qt tests cover payload mapping, detection labels, default sort
order, the inspector, mode synchronisation, and key handling:

```sh
python -m pytest tests/test_workstation.py -q
```

The full suite covers the command line engine:

```sh
python -m pytest -q
```

## Identity and licence

MIT licensed. Maintained by [AnonCatalyst](https://github.com/AnonCatalyst) with
the [WinterGate Intelligence Collective](https://wintergate.org). The
collective is independent and unincorporated. This project is not affiliated
with any platform it checks.

Use it on your own presence or with permission. Ominis only reads public pages,
but a search can still be intrusive. You are responsible for the law, the
site's terms, and the people whose data you touch.
