# UTF-8
#
# PyInstaller spec for the Ominis Investigation Workstation.
#
#     pyinstaller --noconfirm --clean workstation.spec
#
# The result is a single OminisWorkstation.exe that contains the Qt runtime,
# the Ominis engine, and the two detection tables. Build on Windows.

from pathlib import Path

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "ominis_src" / "urls.txt"), "ominis_src"),
    (str(ROOT / "ominis_src" / "social_platforms.json"), "ominis_src"),
    (str(ROOT / "ominis_workstation" / "assets"), "ominis_workstation/assets"),
]

a = Analysis(
    [str(ROOT / "ominis_workstation.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OminisWorkstation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "ominis_workstation" / "assets" / "icon.ico"),
    version=str(ROOT / "ominis_workstation" / "assets" / "version_info.txt"),
)
