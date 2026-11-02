# Screenshots

A static gallery of real Ominis 1.2.0 runs. The page and the cropped PNGs are
generated from the captured reports in [`docs/captures`](../captures), so they
can be rebuilt at any time.

| File | Shows |
| --- | --- |
| `index.html` | The whole gallery: doctor, local search, username search, StyxNet |
| `00-overview.png` | Full-page render of `index.html` at 1240 px wide |
| `01-doctor.png` | Install and TLS check |
| `02-local-search.png` | Merged DuckDuckGo + Bing results and detected profiles |
| `03-username-search.png` | 154 platform templates, confirmed profiles, signals |
| `04-styxnet.png` | StyxNet engine pool, organic results, ranked candidates |

## Build

Run from the repository root after refreshing the captures:

```sh
python docs/screenshots/build_gallery.py
```

That rewrites `index.html` from the JSON in `docs/captures/raw`. To refresh the
PNGs, render the page with headless Chrome and crop each section:

```sh
"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new ^
  --disable-gpu --hide-scrollbars --force-device-scale-factor=1 ^
  --window-size=1240,<page-height> ^
  --screenshot=docs\screenshots\00-overview.png ^
  http://127.0.0.1:8765/index.html
```

Serve the folder locally first (`python -m http.server 8765 --directory docs/screenshots`),
then measure the document height and each `section.shot` offset in the browser.
The section PNGs are cropped from `00-overview.png` with 18 px of padding above
and below.

## Notes

- No key, token, or local absolute path appears in the page or the images.
- Emoji in result titles are rendered with a fallback font stack so they do not
  show as empty boxes.
- StyxNet candidates are labelled with their source and capped at confidence 60
  unless the local registry recognises the URL.
- The page is plain HTML with inline CSS. It has no scripts, fonts, or other
  network dependencies.
