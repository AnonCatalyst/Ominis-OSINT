"""Command line parsing and exit codes."""

import pytest

from ominis_src import cli, config, username


def test_search_parser_defaults_keep_proxies_off():
    args = cli.build_parser().parse_args(["search", "acme", "corp"])
    assert args.command == "search"
    assert args.query == ["acme", "corp"]
    assert args.engine == config.DEFAULT_ENGINES
    assert args.proxy == []
    assert args.proxy_file is None
    assert args.format == ("txt", "json")
    assert args.max_results == 50
    assert args.no_verify is False


def test_search_parser_accepts_filters_and_repeated_proxies():
    args = cli.build_parser().parse_args([
        "search", "acme", "--engine", "bing,serpbase", "--lang", "en",
        "--country", "US", "--since", "2026-01-01", "--until", "2026-02-01",
        "--max-results", "10", "--format", "json,md", "--timeout", "5",
        "--proxy", "127.0.0.1:8080", "--proxy", "socks5://127.0.0.1:1080"])
    assert args.engine == ("bing", "serpbase")
    assert args.lang == "en"
    assert args.country == "US"
    assert args.max_results == 10
    assert args.format == ("json", "md")
    assert args.timeout == 5.0
    assert args.proxy == ["127.0.0.1:8080", "socks5://127.0.0.1:1080"]


@pytest.mark.parametrize("argv", [
    ["search", "acme", "--engine", "google"],
    ["search", "acme", "--format", "xml"],
    ["search", "acme", "--max-results", "0"],
    ["username"],
    ["proxy"],
])
def test_bad_arguments_exit_with_usage(argv):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(argv)
    assert exc.value.code == 2


def test_username_parser_defaults():
    args = cli.build_parser().parse_args(["username", "acme"])
    assert args.username == "acme"
    assert args.concurrency == 8
    assert args.all is False
    assert args.urls is None


def test_gather_proxies_combines_arguments_and_file(tmp_path):
    path = tmp_path / "proxies.txt"
    path.write_text("127.0.0.1:8080\n", encoding="utf-8")
    args = cli.build_parser().parse_args([
        "search", "acme", "--proxy", "127.0.0.1:9090",
        "--proxy-file", str(path)])
    assert cli._gather_proxies(args) == (
        "127.0.0.1:9090", "127.0.0.1:8080")


def test_no_command_prints_help_and_returns_usage(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main([]) == cli.EXIT_USAGE
    assert "usage: ominis" in capsys.readouterr().out


def test_version_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "Ominis OSINT" in capsys.readouterr().out


def test_username_command_writes_a_report(monkeypatch, tmp_path, capsys):
    outcome = username.UsernameReport(username="acme", hits=[
        username.Hit(username="acme", url="https://a.example/acme", status=200,
                     title="Acme", matched=True)])

    async def fake_run(*args, **kwargs):
        return outcome

    written = {}

    def fake_write(report, out_dir, formats):
        written["out_dir"] = out_dir
        written["formats"] = formats
        return {"txt": str(tmp_path / "username-acme.txt")}

    monkeypatch.setattr(cli.username_mod, "run", fake_run)
    monkeypatch.setattr(cli.username_mod, "write", fake_write)
    code = cli.main(["username", "acme", "--out", str(tmp_path),
                     "--format", "json"])
    assert code == cli.EXIT_OK
    assert written == {"out_dir": str(tmp_path), "formats": ("json",)}
    assert "1 match(es) out of 1 checked." in capsys.readouterr().out


def test_search_command_returns_success_for_results(monkeypatch, tmp_path, capsys):
    from ominis_src import engines, report

    outcome = report.SearchReport(query="acme", records=[
        report.SearchRecord(title="A", url="https://a.example/",
                            engine="duckduckgo", position=1)])

    async def fake_run(settings, progress):
        assert settings.proxies == ()
        return outcome

    monkeypatch.setattr(cli.search, "run", fake_run)
    monkeypatch.setattr(cli.search, "write",
                        lambda result, settings: {"txt": str(tmp_path / "acme.txt")})
    code = cli.main(["search", "acme", "--quiet", "--out", str(tmp_path)])
    assert code == cli.EXIT_OK
    assert "1 result(s), 0 social profile(s)." in capsys.readouterr().out


def test_search_command_fails_only_when_every_engine_failed(monkeypatch, tmp_path):
    from ominis_src import report

    outcome = report.SearchReport(query="acme", errors=["duckduckgo: blocked",
                                                        "bing: blocked"])

    async def fake_run(settings, progress):
        return outcome

    monkeypatch.setattr(cli.search, "run", fake_run)
    monkeypatch.setattr(cli.search, "write", lambda result, settings: {})
    assert cli.main(["search", "acme", "--quiet", "--out", str(tmp_path)]) == cli.EXIT_ERROR


def test_invalid_date_is_reported_as_a_usage_error(monkeypatch, tmp_path, capsys):
    assert cli.main(["search", "acme", "--since", "31-01-2026",
                     "--out", str(tmp_path)]) == cli.EXIT_USAGE
    assert "YYYY-MM-DD" in capsys.readouterr().err
