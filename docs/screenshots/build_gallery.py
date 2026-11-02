"""Build the static verification gallery from real captured runs.

Run from the repository root:

    python docs/screenshots/build_gallery.py

The source data lives in ``docs/captures``. No key, token, or local absolute
path is read into the page: the JSON reports contain only public results.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CAPTURES = ROOT / "docs" / "captures"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def terminal(lines: list[str], note: str = "") -> str:
    body = "\n".join(esc(line) for line in lines)
    caption = f'<p class="caption">{esc(note)}</p>' if note else ""
    return f'<pre class="term"><code>{body}</code></pre>{caption}'


def result_rows(results: list[dict], limit: int = 5) -> str:
    rows = []
    for item in results[:limit]:
        rows.append(
            "<tr>"
            f"<td class=\"rank\">{int(item.get('position') or 0)}</td>"
            f"<td><span class=\"engine\">{esc(item.get('engine'))}</span>"
            f"<strong>{esc(item.get('title'))}</strong>"
            f"<a href=\"{esc(item.get('url'))}\">{esc(item.get('url'))}</a></td>"
            f"<td class=\"snippet\">{esc(item.get('snippet'))[:180]}</td>"
            "</tr>")
    return "".join(rows)


def profile_rows(profiles: list[dict]) -> str:
    rows = []
    for profile in profiles:
        confidence = esc(profile.get("confidence"))
        title = esc(profile.get("title"))
        source = esc(profile.get("source"))
        extra = ""
        if title:
            extra += f"<span class=\"title\">{title}</span>"
        if source:
            extra += f"<span class=\"source\">{source}</span>"
        rows.append(
            "<tr>"
            f"<td><strong>{esc(profile.get('platform'))}</strong>"
            f"<span class=\"category\">{esc(profile.get('category'))}</span></td>"
            f"<td><a href=\"{esc(profile.get('profile_url'))}\">"
            f"{esc(profile.get('profile_url'))}</a>{extra}</td>"
            f"<td class=\"confidence\">{confidence}</td>"
            "</tr>")
    return "".join(rows)


def metric(label: str, value: object) -> str:
    return (f'<div class="metric"><span class="value">{esc(value)}</span>'
            f'<span class="label">{esc(label)}</span></div>')


def username_rows(payload: dict) -> str:
    rows = []
    for hit in payload.get("profiles", []):
        rows.append(
            "<tr>"
            f"<td><strong>{esc(hit.get('platform'))}</strong></td>"
            f"<td><span class=\"reason\">{esc(hit.get('match'))}</span></td>"
            f"<td><a href=\"{esc(hit.get('url'))}\">{esc(hit.get('url'))}</a>"
            f"<span class=\"title\">{esc(hit.get('title'))}</span></td>"
            f"<td class=\"confidence\">{esc(hit.get('confidence'))}</td>"
            "</tr>")
    return "".join(rows)


def build() -> str:
    doctor = (CAPTURES / "00-doctor.log").read_text(encoding="utf-8").splitlines()
    local = load(CAPTURES / "raw" / "local-search" / "AnonCatalyst.json")
    user = load(CAPTURES / "raw" / "username" / "username-AnonCatalyst.json")
    styx = load(CAPTURES / "raw" / "styxnet" / "AnonCatalyst.json")

    local_summary = local["summary"]
    user_checked = user["checked"]
    user_found = user["found"]
    styx_summary = styx["summary"]
    styx_meta = styx_summary.get("styxnet_meta", {})

    sections = f"""
<section class="shot" id="shot-doctor">
  <header class="shot-head">
    <p class="eyebrow">01 &middot; Install check</p>
    <h2>Doctor</h2>
    <p class="lede">Dependencies, TLS store, and a live HTTPS request.</p>
  </header>
  <div class="command"><span class="prompt">PS&gt;</span>
    <code>python -m ominis_src.cli doctor</code></div>
  {terminal(doctor)}
</section>

<section class="shot" id="shot-search">
  <header class="shot-head">
    <p class="eyebrow">02 &middot; Local search</p>
    <h2>DuckDuckGo + Bing, deduplicated</h2>
    <p class="lede">Canonical URLs merge duplicate engine hits; mentions are
    counted as whole words; subpages collapse to the parent profile.</p>
  </header>
  <div class="command"><span class="prompt">PS&gt;</span>
    <code>ominis search AnonCatalyst --max-results 20
    --format txt,json,md</code></div>
  <div class="metrics">
    {metric("results", local_summary["results"])}
    {metric("profiles", local_summary["profiles"])}
    {metric("proxies", "off")}
    {metric("engines", "2")}
  </div>
  <div class="mentions">Mentions:
    {" &nbsp; ".join(f"<b>{esc(k)}</b> &times;{esc(v)}" for k, v in local_summary["mentions"].items())}
  </div>
  <h3>Top results</h3>
  <table class="results"><thead><tr><th>#</th><th>Result</th><th>Snippet</th></tr></thead>
  <tbody>{result_rows(local["results"])}</tbody></table>
  <h3>Detected profiles</h3>
  <table class="profiles"><thead><tr><th>Platform</th><th>Profile</th><th>Conf.</th></tr></thead>
  <tbody>{profile_rows(local["profiles"])}</tbody></table>
  <p class="caption">Report files: {esc(local_summary["results"])} results and
  {esc(local_summary["profiles"])} profiles, written as txt, json, and md.</p>
</section>

<section class="shot" id="shot-username">
  <header class="shot-head">
    <p class="eyebrow">03 &middot; Username search</p>
    <h2>154 platform templates</h2>
    <p class="lede">Metadata, canonical links, and structured handles are used
    as positive signals; login walls and soft 404s are rejected.</p>
  </header>
  <div class="command"><span class="prompt">PS&gt;</span>
    <code>ominis username AnonCatalyst --all --format txt,json,md,csv</code></div>
  <div class="metrics">
    {metric("checked", user_checked)}
    {metric("matches", user_found)}
    {metric("errors", len(user.get("errors", [])))}
    {metric("formats", "4")}
  </div>
  <h3>Confirmed profiles</h3>
  <table class="profiles"><thead><tr><th>Platform</th><th>Signal</th><th>Profile</th><th>Conf.</th></tr></thead>
  <tbody>{username_rows(user)}</tbody></table>
  <p class="caption">TikTok was confirmed from its structured <code>uniqueId</code>,
  Twitch from its canonical URL, and YouTube through the modern
  <code>@handle</code> template. A Russian-language soft 404 was rejected.</p>
</section>

<section class="shot" id="shot-styxnet">
  <header class="shot-head">
    <p class="eyebrow">04 &middot; StyxNet</p>
    <h2>WinterGate engine pool</h2>
    <p class="lede">One switch, <code>--styxnet</code>. Results and username
    candidates keep the same report shape as local search.</p>
  </header>
  <div class="command"><span class="prompt">PS&gt;</span>
    <code>ominis search AnonCatalyst --styxnet --max-results 15
    --format txt,json,md</code></div>
  <div class="metrics">
    {metric("results", styx_summary["results"])}
    {metric("profiles", styx_summary["profiles"])}
    {metric("engines", styx_meta.get("engines", "?"))}
    {metric("elapsed", f"{styx_meta.get('elapsed_ms', 0)} ms")}
  </div>
  <h3>Top results</h3>
  <table class="results"><thead><tr><th>#</th><th>Result</th><th>Snippet</th></tr></thead>
  <tbody>{result_rows(styx["results"], limit=4)}</tbody></table>
  <h3>Ranked profiles</h3>
  <table class="profiles"><thead><tr><th>Platform</th><th>Profile</th><th>Conf.</th></tr></thead>
  <tbody>{profile_rows(styx["profiles"])}</tbody></table>
  <p class="caption">Archive id <code>{esc(styx_meta.get("archive_id"))}</code>.
  No proxies, no local engine fallback. StyxNet profiles are untrusted
  candidates: the service label is capped at confidence 60 unless the local
  registry recognises the URL shape.</p>
</section>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ominis 1.2.0 verification gallery</title>
<style>
  :root {{
    --ink: #dbe7ff;
    --muted: #8fa3c8;
    --line: #223352;
    --panel: #0d1730;
    --panel-2: #101d3b;
    --glow: #58e1ff;
    --ember: #ffb45c;
    --green: #7ef0b2;
    --bg: #070d1b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 36px; width: 1240px;
    background:
      radial-gradient(900px 500px at 85% -10%, #16305c 0%, transparent 60%),
      radial-gradient(700px 400px at -10% 100%, #2a1533 0%, transparent 55%),
      var(--bg);
    color: var(--ink);
    font: 15px/1.55 "Segoe UI", system-ui, sans-serif;
  }}
  .hero {{ padding: 18px 4px 30px; border-bottom: 1px solid var(--line); }}
  .brand {{ display: flex; align-items: center; gap: 14px; }}
  .mark {{
    width: 44px; height: 44px; border-radius: 12px;
    background: linear-gradient(145deg, #1c3f78, #0b1730);
    border: 1px solid #2d5a9e; display: grid; place-items: center;
    color: var(--glow); font-weight: 700; letter-spacing: .5px;
    box-shadow: 0 0 24px #1b4f8a66;
  }}
  .brand small {{ color: var(--muted); display: block; letter-spacing: .12em;
    text-transform: uppercase; font-size: 10px; }}
  .brand b {{ font-size: 19px; letter-spacing: .02em; }}
  h1 {{ font-size: 38px; line-height: 1.1; margin: 26px 0 10px;
    letter-spacing: -.02em; }}
  h1 span {{ color: var(--glow); }}
  .hero p {{ color: var(--muted); max-width: 820px; margin: 0; }}
  .badges {{ display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }}
  .badge {{ border: 1px solid var(--line); background: #0b1428;
    padding: 5px 11px; border-radius: 999px; color: var(--muted);
    font-size: 12px; }}
  .shot {{ padding: 34px 0 30px; border-bottom: 1px solid var(--line); }}
  .eyebrow {{ margin: 0 0 6px; color: var(--ember); font-size: 11px;
    letter-spacing: .16em; text-transform: uppercase; font-weight: 600; }}
  h2 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: -.01em; }}
  .lede {{ margin: 0 0 18px; color: var(--muted); max-width: 900px; }}
  h3 {{ margin: 24px 0 9px; font-size: 13px; text-transform: uppercase;
    letter-spacing: .1em; color: var(--glow); }}
  .command {{ display: flex; gap: 10px; align-items: baseline;
    background: #0a1326; border: 1px solid var(--line);
    border-bottom: 0; border-radius: 12px 12px 0 0; padding: 12px 14px;
    font: 13px/1.4 "Cascadia Code", Consolas, monospace; color: #bfd4ff;
    overflow-wrap: anywhere; }}
  .prompt {{ color: var(--ember); font-weight: 700; }}
  .term {{ margin: 0; padding: 16px; overflow: hidden;
    background: #070f21; border: 1px solid var(--line); border-radius: 0 0 12px 12px;
    color: #c9d8f5; font: 12.5px/1.6 "Cascadia Code", Consolas, monospace;
    white-space: pre-wrap; word-break: break-word; }}
  .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 10px; margin: 18px 0 4px; }}
  .metric {{ background: var(--panel); border: 1px solid var(--line);
    border-radius: 12px; padding: 13px 15px; }}
  .metric .value {{ display: block; font-size: 25px; font-weight: 700;
    color: var(--green); letter-spacing: -.02em; }}
  .metric .label {{ color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: .1em; }}
  .mentions {{ margin: 13px 0 2px; padding: 10px 13px; border-radius: 10px;
    background: #0b1428; border: 1px solid var(--line); color: var(--muted);
    font-size: 12.5px; }}
  .mentions b {{ color: var(--ink); }}
  table {{ width: 100%; border-collapse: collapse; margin: 4px 0 0;
    font-size: 12.5px; }}
  th {{ text-align: left; color: var(--muted); font-size: 10.5px;
    letter-spacing: .1em; text-transform: uppercase;
    border-bottom: 1px solid var(--line); padding: 7px 9px; }}
  td {{ vertical-align: top; padding: 9px; border-bottom: 1px solid #17243f; }}
  tr:last-child td {{ border-bottom: 0; }}
  td.rank {{ color: var(--muted); width: 26px; }}
  td.confidence {{ width: 52px; color: var(--green); font-weight: 700;
    text-align: right; }}
  .engine {{ display: inline-block; margin-right: 8px; padding: 1px 7px;
    border-radius: 999px; background: #132849; color: var(--glow);
    border: 1px solid #234a7d; font-size: 10px; text-transform: uppercase;
    letter-spacing: .06em; }}
  strong {{ display: block; font-weight: 600;
    font-family: "Segoe UI", "Leelawadee UI", "Cambria Math",
      "Segoe UI Symbol", sans-serif; font-synthesis: none; }}
  a {{ color: #8db8ff; text-decoration: none; overflow-wrap: anywhere; }}
  .snippet {{ color: var(--muted); width: 46%; }}
  .category, .source, .reason {{ display: inline-block; margin-left: 7px;
    padding: 1px 7px; border-radius: 999px; background: #0f1c36;
    border: 1px solid var(--line); color: var(--muted); font-size: 10px; }}
  .reason {{ margin-left: 0; color: var(--green); border-color: #1f5b45; }}
  .title {{ display: block; color: var(--muted); font-size: 11.5px;
    margin-top: 2px; }}
  .source {{ color: var(--ember); border-color: #5a3a1e; }}
  .caption {{ color: var(--muted); font-size: 12px; margin: 12px 0 0; }}
  .caption code, .lede code {{ color: var(--glow); font-family:
    "Cascadia Code", Consolas, monospace; font-size: .92em; }}
  footer {{ padding: 26px 4px 4px; color: var(--muted); font-size: 12px;
    display: flex; justify-content: space-between; gap: 20px; }}
  footer b {{ color: var(--ink); }}
</style>
</head>
<body>
  <div class="hero">
    <div class="brand">
      <div class="mark">WI</div>
      <div><b>WinterGate Intelligence Collective</b>
        <small>Ominis OSINT &middot; verification gallery</small></div>
    </div>
    <h1>Ominis <span>1.2.0</span><br>real runs, real reports</h1>
    <p>Every panel below is generated from the captured JSON reports in
    <code>docs/captures</code>. No mocked data, no proxy pool, and no
    credentials are included.</p>
    <div class="badges">
      <span class="badge">MIT licensed</span>
      <span class="badge">Windows &middot; Python 3.12.10</span>
      <span class="badge">Unsigned artifacts</span>
      <span class="badge">wintergate.org</span>
    </div>
  </div>
  {sections}
  <footer>
    <span><b>Ominis OSINT 1.2.0</b> &middot; maintained by AnonCatalyst with
    the WinterGate Intelligence Collective.</span>
    <span>Captures: 2026-11-02 &middot; source reports in
    <code>docs/captures</code></span>
  </footer>
</body>
</html>
"""


def main() -> None:
    page = HERE / "index.html"
    page.write_text(build(), encoding="utf-8")
    print(page)


if __name__ == "__main__":
    main()
