# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the NFL Blitz Mod Suite.

Build from the repository root:

    pyinstaller packaging/nfl_blitz_suite.spec

Produces a single executable in ``dist/``. On Windows that is
``NFLBlitzModSuite.exe``.

PyInstaller does not cross-compile: a Windows .exe must be built on Windows.
``.github/workflows/windows-build.yml`` does exactly that on a hosted runner,
so a Windows binary can be produced without owning a Windows machine.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent

# Read-only data the application needs at runtime. core/paths.py resolves
# these through sys._MEIPASS when frozen.
datas = [
    (str(ROOT / "games"), "games"),
    (str(ROOT / "docs"), "docs"),
    (str(ROOT / "README.md"), "."),
]

# Qt pulls in a lot that a desktop tool of this shape never touches; dropping
# it roughly halves the download without changing behaviour.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNetwork",
    "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtWebSockets",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtRemoteObjects",
    "tkinter", "unittest", "pytest", "setuptools", "pip",
    "matplotlib", "scipy", "pandas", "IPython",
]

# The suite loads its own subpackages dynamically in places, so collect them.
hiddenimports = (
    collect_submodules("core")
    + collect_submodules("editors")
    + collect_submodules("tools")
    + collect_submodules("ui")
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NFLBlitzModSuite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # No console window: this is a GUI application.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
