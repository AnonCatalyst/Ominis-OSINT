# Changelog

Notable changes to the Ominis command line suite and the Ominis Investigation
Workstation. The command line engine and the workstation are separate
downloads; each entry names both versions when they shipped together.

The full list of older releases and their assets is on the
[GitHub releases page](https://github.com/AnonCatalyst/Ominis-OSINT/releases).

## 1.2.7 / Workstation 1.0.7 - 2026-11-09

### Added

- Search and username results on the command line now report the same detection
  depth as the workstation. Each profile row carries its handle, category,
  confidence, detecting signal, and lead strength, and each report summarizes
  verified leads and results that resolve to a profile. The console and the
  `txt`, `json`, `csv`, and `md` writers all include the new fields, so
  `--format none` still prints them.
- Search enriches records the page scan did not reach, and merges detection
  depth when a duplicate profile appears, instead of keeping whichever record
  arrived first.
- `ominis doctor` reports whether a StyxNet key is ready and which source
  supplied it, without printing the key.

### Changed

- A StyxNet key can come from `--styxnet-key`, `STYXNET_ACCESS_KEY`,
  `OMINIS_STYXNET_KEY`, `~/.config/ominis/styxnet-key.txt`
  (`%USERPROFILE%\.config\ominis\styxnet-key.txt` on Windows), or
  `%APPDATA%\ominis\styxnet-key.txt` when the first file is absent. A key from
  any of these is sufficient; no other configuration is required, and
  `--styxnet` remains the switch that routes the search.

## 1.2.6 / Workstation 1.0.6 - 2026-11-08

### Fixed

- `ominis username --urls FILE` prints one clear line and exits 2 when the
  platform list is missing, unreadable, or contains no URLs. A missing file
  used to raise a `FileNotFoundError` traceback; an empty file used to report
  success after checking nothing.
- `ominis search --proxy ...` validates the endpoint before any request. An
  unsupported scheme or malformed value now exits 2 with a clear message,
  matching the username command, instead of a per-engine warning and exit 1.
- `ominis proxy harvest --out` rejects an existing directory before
  downloading, and a write failure prints one error line instead of a
  traceback.

## 1.2.5 / Workstation 1.0.5 - 2026-11-08

### Fixed

- Windows input files saved with a UTF-8 BOM (Notepad, PowerShell) are read
  correctly. A BOM no longer breaks the first platform URL, the first proxy
  endpoint, or a saved StyxNet key.
- `ominis username` exits non-zero when every checked platform failed, such as
  with a dead proxy. It used to report success with no matches.
- An `--out` path that is an existing file is rejected before the network run
  instead of crashing with a raw traceback afterwards. A report write failure
  now prints one error line.
- An explicitly supplied `--proxy-file` with no endpoints is a usage error
  instead of silently searching without a proxy.
- A reversed `--since`/`--until` range is a usage error instead of a silent
  empty search.
- Username checks no longer print a phantom Windows asyncio traceback
  (`_ProactorBasePipeTransport._call_connection_lost`) when a site resets a
  pooled connection. The site itself is still reported normally.

### Documentation

- The README now shows one current release summary and links here for history
  instead of stacking every version on the project page.

## 1.2.4 / Workstation 1.0.4 - 2026-11-07

### Fixed

- The Windows asyncio proactor no longer prints an `ERROR` traceback when a
  checked site resets a pooled socket during username checks. Only that
  callback is ignored; other loop errors still surface.

## 1.2.3 / Workstation 1.0.3 - 2026-11-07

### Fixed

- Explicit proxy runs work in the windowed workstation. The legacy
  "enable proxy rotation display?" prompt tried to read standard input, which
  a windowed build does not have. Non-interactive callers keep the display off
  and use the proxy; a terminal user can still opt in.
- A leading `@` is accepted in username checks and is treated as notation,
  so `ominis username @AnonCatalyst` checks `AnonCatalyst`. Unsafe names are
  still rejected.
- Workstation executable metadata reports the same version in the fixed and
  string fields.

## 1.2.2 / Workstation 1.0.2 - 2026-11-05

This is the full suite. It is published alongside the patched original
(`v0.5.0`) so anyone relying on the old layout can keep it.

### Added

- Page inspection: the default scan pass fetches the top results and records
  what each page itself proves: metadata, canonical URL, structured handle
  fields, redirect target, and visible text. Reports carry HTTP status, final
  URL, signal, and detail per row, and profiles inherit that evidence.
  `--no-scan-pages` turns it off; `--scan-limit` caps it.
- Raw-only output: `--format none` prints results and writes no report files.
  The workstation has a matching "Save report files" switch.
- Optional StyxNet search through `--styxnet`, using WinterGate's engine pool.
- Real filters: language, country, and date ranges are passed to each engine
  instead of being accepted and ignored.
- Optional SerpBase-compatible results API for the Google leg.
- Report formats: `txt`, `json`, `csv`, and `md`, with file names that are safe
  for any query.
- A scriptable CLI with subcommands, exit codes, and a `doctor` check.

### Changed

- Environment proxies are opt-in. `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`
  are ignored unless `--use-env-proxy` is passed, so a stale value cannot
  empty every engine.
- Canonical URLs collapse duplicate engine hits, engines are paged in
  lockstep, search plumbing is filtered out, and mentions are counted as whole
  words, including multi-word queries.
- Username checks read Open Graph metadata, canonical links, and structured
  handle fields, so valid TikTok, Twitch, and YouTube profiles are found
  without trusting a footer mention or a soft 404.
- Deep detection keeps the curated platform registry, the original wide
  `social_platforms.json` table, and generic Discourse/Fediverse/forum rules.
- Username checks share one HTTPX client instead of starting a Chromium
  session per URL.

## Earlier releases

Versions before 1.2.2 are documented on the
[GitHub releases page](https://github.com/AnonCatalyst/Ominis-OSINT/releases).
