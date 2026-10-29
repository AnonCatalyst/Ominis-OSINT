# Contributing to Ominis-OSINT

Thanks for helping. Ominis is a privacy-first, fully open-source OSINT helper.
The project has no paid tier, no account and no licence check; contributions are
held to the same standard as the maintainers' own changes.

## Ground rules

- Be civil. Read `CODE_OF_CONDUCT.md`.
- Only query public sources, and only in ways you are allowed to. Do not add
  credential stuffing, login bypasses, paywall bypasses or scraping of private
  data.
- Never commit secrets. That includes API keys, tokens, cookies, proxy lists and
  personal data. Use environment variables or a local file that `.gitignore`
  covers.
- Proxies stay **optional and off by default**. The default path must work
  without Tor, a proxy subscription or an API key.
- Keep the runtime small: `httpx`, `beautifulsoup4`, `lxml`, `tqdm`,
  `fake-useragent` and the standard library. Test tooling belongs in
  `requirements-test.txt`.

## Development setup

```sh
git clone https://github.com/AnonCatalyst/Ominis-OSINT.git
cd Ominis-OSINT
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   . .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The suite is offline and deterministic. It must pass on Python 3.10, 3.11 and
3.12. Add tests for every bug fix and for new parsers or flags. Tests must not
call the network; use the existing fakes in `tests/`.

Manual checks:

```sh
python ominis.py search "example query" --engine duckduckgo,bing --max-results 5
python ominis.py username example --limit 5
```

## Style

- Standard library first; avoid new dependencies unless there is no reasonable
  alternative. Explain the need in the pull request.
- Keep functions small and typed where practical. This code targets Python 3.10.
- No shell interpolation of user input. Pass values through arguments or
  environment variables.
- Write output through `ominis_src/report.py` so filenames stay sanitised.
- Do not log credentials, query strings or result URLs at INFO level.

## Pull requests

1. Fork, branch from `main`, and keep the change focused.
2. Run `python -m pytest -q` and, if you touched packaging,
   `python -m build --wheel`.
3. Describe what changed and why, plus the commands you used to verify it.
4. Link the issue if one exists. Draft pull requests are welcome.
5. CI must be green. A maintainer will review; small, clear commits are easier
   to review than one large rewrite.

By contributing you agree that your work is licensed under the MIT licence in
`LICENSE`.
