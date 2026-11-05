"""Command line parsing and exit codes."""

import pytest

from ominis_src import cli, config, username

_ENV_NAMES = (
    "OMINIS_ENGINES", "OMINIS_LANGUAGE", "OMINIS_COUNTRY", "OMINIS_SINCE",
    "OMINIS_UNTIL", "OMINIS_MAX_RESULTS", "OMINIS_PROXY_POOL",
    "OMINIS_TIMEOUT", "OMINIS_FORMATS", "OMINIS_OUTPUT_DIR", "OMINIS_STYXNET",
    "OMINIS_STYXNET_KEY", "OMINIS_STYXNET_ENDPOINT",
    "OMINIS_STYXNET_ENGINES", "OMINIS_STYXNET_SCOPES", "SERPBASE_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_ominis_environment(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_search_parser_defaults_keep_proxies_off():
    args = cli.build_parser().parse_args(["search", "acme", "corp"])
    assert args.command == "search"
    assert args.query == ["acme", "corp"]
    assert args.engine == config.DEFAULT_ENGINES
    assert args.proxy is None
    assert args.proxy_file is None
    assert args.format == ("txt", "json")
    assert args.max_results == 50
    assert args.no_verify is False


def test_search_parser_styxnet_defaults_are_off():
    args = cli.build_parser().parse_args(["search", "acme"])
    assert args.styxnet is False
    assert args.styxnet_key == ""
    assert args.styxnet_engines == 35
    assert args.styxnet_scopes == ("surface", "onion", "deep")


def test_search_parser_accepts_styxnet_options():
    args = cli.build_parser().parse_args([
        "search", "acme", "--styxnet", "--styxnet-key", "sgn_test",
        "--styxnet-engines", "12", "--styxnet-scopes", "surface,deep"])
    assert args.styxnet is True
    assert args.styxnet_key == "sgn_test"
    assert args.styxnet_engines == 12
    assert args.styxnet_scopes == ("surface", "deep")


@pytest.mark.parametrize("argv", [
    ["search", "acme", "--styxnet-engines", "0"],
    ["search", "acme", "--styxnet-engines", "201"],
    ["search", "acme", "--styxnet-scopes", "surface,clearnet"],
])
def test_bad_styxnet_arguments_exit_with_usage(argv):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(argv)
    assert exc.value.code == 2


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


def test_documented_environment_variables_are_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("OMINIS_ENGINES", "bing")
    monkeypatch.setenv("OMINIS_LANGUAGE", "en")
    monkeypatch.setenv("OMINIS_COUNTRY", "US")
    monkeypatch.setenv("OMINIS_SINCE", "2026-01-01")
    monkeypatch.setenv("OMINIS_UNTIL", "2026-02-01")
    monkeypatch.setenv("OMINIS_MAX_RESULTS", "7")
    monkeypatch.setenv("OMINIS_TIMEOUT", "7.5")
    monkeypatch.setenv("OMINIS_FORMATS", "json,md")
    monkeypatch.setenv("OMINIS_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OMINIS_STYXNET", "1")
    monkeypatch.setenv("OMINIS_STYXNET_ENGINES", "9")
    monkeypatch.setenv("OMINIS_STYXNET_SCOPES", "surface")

    args = cli.build_parser().parse_args(["search", "acme"])
    assert args.engine == ("bing",)
    assert args.lang == "en"
    assert args.country == "US"
    assert args.since == "2026-01-01"
    assert args.until == "2026-02-01"
    assert args.max_results == 7
    assert args.timeout == 7.5
    assert args.format == ("json", "md")
    assert args.out == str(tmp_path)
    assert args.styxnet is True
    assert args.styxnet_engines == 9
    assert args.styxnet_scopes == ("surface",)

    # An explicit argument always wins over the environment.
    args = cli.build_parser().parse_args([
        "search", "acme", "--engine", "duckduckgo", "--max-results", "3",
        "--no-styxnet", "--styxnet-engines", "4"])
    assert args.engine == ("duckduckgo",)
    assert args.max_results == 3
    assert args.styxnet is False
    assert args.styxnet_engines == 4


def test_invalid_environment_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("OMINIS_ENGINES", "google")
    monkeypatch.setenv("OMINIS_MAX_RESULTS", "many")
    monkeypatch.setenv("OMINIS_TIMEOUT", "soon")
    monkeypatch.setenv("OMINIS_FORMATS", "xml")
    monkeypatch.setenv("OMINIS_STYXNET_ENGINES", "lots")
    monkeypatch.setenv("OMINIS_STYXNET_SCOPES", "clearnet")
    args = cli.build_parser().parse_args(["search", "acme"])
    assert args.engine == config.DEFAULT_ENGINES
    assert args.max_results == 50
    assert args.timeout == 15.0
    assert args.format == ("txt", "json")
    assert args.styxnet_engines == 35
    assert args.styxnet_scopes == ("surface", "onion", "deep")


def test_proxy_pool_environment_is_used_only_without_cli_proxies(monkeypatch):
    monkeypatch.setenv("OMINIS_PROXY_POOL",
                       "127.0.0.1:8080, socks5://127.0.0.1:1080")
    args = cli.build_parser().parse_args(["search", "acme"])
    assert cli._gather_proxies(args) == (
        "127.0.0.1:8080", "socks5://127.0.0.1:1080")
    args = cli.build_parser().parse_args([
        "search", "acme", "--proxy", "127.0.0.1:9090"])
    assert cli._gather_proxies(args) == ("127.0.0.1:9090",)


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

    def fake_write(report, out_dir, formats, include_all=False):
        written["out_dir"] = out_dir
        written["formats"] = formats
        written["include_all"] = include_all
        return {"txt": str(tmp_path / "username-acme.txt")}

    monkeypatch.setattr(cli.username_mod, "run", fake_run)
    monkeypatch.setattr(cli.username_mod, "write", fake_write)
    code = cli.main(["username", "acme", "--out", str(tmp_path),
                     "--format", "json", "--all"])
    assert code == cli.EXIT_OK
    assert written == {"out_dir": str(tmp_path), "formats": ("json",),
                       "include_all": True}
    assert "1 match(es) out of 1 checked." in capsys.readouterr().out


def test_print_hit_can_show_checked_platforms(capsys):
    hit = username.Hit(username="acme", url="https://a.example/acme", status=404)
    cli._print_hit(hit, show_all=True)
    assert "[checked] https://a.example/acme - HTTP 404" in capsys.readouterr().out


def test_configure_stdio_uses_utf8_and_replaces_unprintable_glyphs(monkeypatch):
    class Stream:
        def __init__(self):
            self.calls = []

        def reconfigure(self, **kwargs):
            self.calls.append(kwargs)

    out, err = Stream(), Stream()
    monkeypatch.setattr(cli.sys, "stdout", out)
    monkeypatch.setattr(cli.sys, "stderr", err)
    cli._configure_stdio()
    assert out.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert err.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_configure_stdio_tolerates_wrapped_streams(monkeypatch):
    class Wrapped:
        def reconfigure(self, **kwargs):
            raise ValueError("not supported")

    monkeypatch.setattr(cli.sys, "stdout", Wrapped())
    cli._configure_stdio()  # must not raise


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
    assert ("1 result(s), 0 social profile(s), 0 page match(es)."
            in capsys.readouterr().out)


def test_search_command_uses_styxnet_settings(monkeypatch, tmp_path, capsys):
    from ominis_src import report

    captured = {}

    async def fake_run(settings, progress):
        captured["settings"] = settings
        return report.SearchReport(query="acme")

    monkeypatch.setattr(cli.search, "run", fake_run)
    monkeypatch.setattr(cli.search, "write", lambda result, settings: {})
    code = cli.main([
        "search", "acme", "--quiet", "--out", str(tmp_path), "--styxnet",
        "--styxnet-key", "sgn_test", "--styxnet-engines", "7",
        "--styxnet-scopes", "surface"])
    assert code == cli.EXIT_OK
    settings = captured["settings"]
    assert settings.styxnet is True
    assert settings.styxnet_key == "sgn_test"
    assert settings.styxnet_engines == 7
    assert settings.styxnet_scopes == ("surface",)
    assert "Searching via StyxNet" in capsys.readouterr().out


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
