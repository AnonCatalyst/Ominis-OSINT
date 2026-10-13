import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]


def test_transport_extras_match_both_installation_paths():
    requirements = [Requirement(line.split("#", 1)[0].strip()) for line in (ROOT / "requirements.txt").read_text().splitlines()
                    if line and not line.startswith("#")]
    httpx = next(req for req in requirements if req.name == "httpx")
    assert {"http2", "socks"}.issubset(httpx.extras)
    captured = {}
    from unittest.mock import patch
    with patch("setuptools.setup", lambda **kwargs: captured.update(kwargs)):
        exec(compile((ROOT / "setup.py").read_text(), "setup.py", "exec"), {"__name__": "audit_setup"})
    installed = next(Requirement(req) for req in captured["install_requires"]
                     if Requirement(req).name == "httpx")
    assert {"http2", "socks"}.issubset(installed.extras)
    assert installed.specifier.contains("0.28.1")
    assert not installed.specifier.contains("0.28.0")


def test_wheel_excludes_stale_modules_and_imports_outside_checkout(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".venv", "venv"))
    dist = tmp_path / "dist"
    build = subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                            "--outdir", str(dist)], cwd=source, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any(name.startswith("src/") for name in names), names
        for name in ["ominis.py", "ominis_src/tools_handler.py", "ominis_src/proxy_handler.py",
                     "ominis_src/social_platforms.json", "ominis_src/urls.txt"]:
            assert archive.read(name) == (ROOT / name).read_bytes()

    installed = tmp_path / "installed"
    install = subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "install",
                              "--no-index", "--no-deps", "--no-compile",
                              "--target", str(installed), str(wheel)], capture_output=True, text=True)
    assert install.returncode == 0, install.stdout + install.stderr
    env = os.environ.copy()
    env["PYTHONPATH"] = str(installed)
    smoke = subprocess.run([sys.executable, "-c", """
import pathlib, ssl, sys
original = ssl._create_default_https_context
import ominis
from ominis_src import tools_handler
assert ssl._create_default_https_context is original
assert pathlib.Path(tools_handler.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
import h2, socksio
""", str(installed)], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
