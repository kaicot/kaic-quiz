# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Quiz Reporter portable folder (onedir, no console window).

Build with tools/build-portable-folder.ps1; to run it by hand:
    .venv\\Scripts\\python -m PyInstaller --noconfirm packaging\\Quiz_Reporter.spec
"""

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

PROJECT_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821  (SPECPATH is set by PyInstaller)
SRC_ROOT = PROJECT_ROOT / "src"
ICON = PROJECT_ROOT / "packaging" / "quiz_reporter.ico"
SVG = SRC_ROOT / "quiz_reporter" / "resources" / "app_icon.svg"

VERSION = re.search(
    r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"',
    (SRC_ROOT / "quiz_reporter" / "__init__.py").read_text(encoding="utf-8"),
    re.MULTILINE,
).group(1)
NUMERIC_VERSION = tuple(int(part) for part in VERSION.split(".")) + (0,)
FOLDER_NAME = f"Quiz-Reporter-v{VERSION}"

# The only Qt modules the program uses: QtCore, QtGui (QPdfWriter, QTextDocument), QtWidgets,
# and Qt Svg for the SVG icon (qsvg image format and qsvgicon icon engine plugins). Everything
# else is left out: it is large, unused, and several add-on modules are GPL-only in the
# open-source edition. tools/verify-portable-folder.ps1 keeps the same list.
QT_KEEP = ("Core", "Gui", "Widgets", "Svg")
QT_PYTHON_KEEP = ("Core", "Gui", "Widgets")
QT_EXCLUDED_MODULES = (
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender",
    "QtAxContainer", "QtBluetooth", "QtCanvasPainter", "QtCharts", "QtConcurrent",
    "QtDBus", "QtDataVisualization", "QtDesigner", "QtGraphs", "QtGraphsWidgets",
    "QtHelp", "QtHttpServer", "QtLocation", "QtMultimedia", "QtMultimediaWidgets",
    "QtNetwork", "QtNetworkAuth", "QtNfc", "QtOpenGL", "QtOpenGLWidgets", "QtPdf",
    "QtPdfWidgets", "QtPositioning", "QtPrintSupport", "QtQml", "QtQuick",
    "QtQuick3D", "QtQuickControls2", "QtQuickTest", "QtQuickWidgets", "QtRemoteObjects",
    "QtScxml", "QtSensors", "QtSerialBus", "QtSerialPort", "QtSpatialAudio", "QtSql",
    "QtStateMachine", "QtSvgWidgets", "QtTest", "QtTextToSpeech", "QtUiTools",
    "QtVirtualKeyboard", "QtWebChannel", "QtWebEngineCore", "QtWebEngineQuick",
    "QtWebEngineWidgets", "QtWebSockets", "QtWebView", "QtXml",
)
# Files that the Qt hooks pull in through plugins although no Qt module needs them.
DROP_FILES = {
    "opengl32sw.dll",  # software OpenGL, ~20 MB; widgets and QPdfWriter do not use OpenGL
    "d3dcompiler_47.dll",
    "qpdf.dll",  # PDF image-format plugin (needs Qt6Pdf)
    "qtvirtualkeyboardplugin.dll",  # Qt Virtual Keyboard (GPL-only)
    "qtuiotouchplugin.dll",  # needs Qt6Network
}
# Whole plugin folders for features the program does not use.
DROP_PLUGIN_DIRS = {
    "designer", "multimedia", "networkinformation", "position", "qmltooling", "scxmldatamodel",
    "sensors", "sqldrivers", "texttospeech", "tls", "webview",
}
QT_FILE = re.compile(r"^Qt6?(\w+?)\.(?:dll|pyd|pyi)$", re.IGNORECASE)


def _keep(entry):
    """Keep an entry unless it is an unused Qt module, plugin, QML or translation file."""
    parts = Path(entry[0].replace("\\", "/")).parts
    name = parts[-1]
    if name.lower() in DROP_FILES:
        return False
    if "PySide6" not in parts:
        return True
    if any(part in ("qml", "translations") for part in parts[:-1]):
        return False
    if "plugins" in parts[:-1] and parts[parts.index("plugins") + 1] in DROP_PLUGIN_DIRS:
        return False
    match = QT_FILE.match(name)
    if match:
        keep = QT_PYTHON_KEEP if name.lower().endswith((".pyd", ".pyi")) else QT_KEEP
        return match.group(1) in keep
    return True


version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=NUMERIC_VERSION,
        prodvers=NUMERIC_VERSION,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,  # Windows NT
        fileType=0x1,  # application
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "041204B0",  # Korean, Unicode
                    [
                        StringStruct("CompanyName", "조승현 (Cho, Seung-Hyun)"),
                        StringStruct("FileDescription", "퀴즈 리포터 - 구글 폼 퀴즈 채점 · 학생별 피드백"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "Quiz Reporter"),
                        StringStruct(
                            "LegalCopyright",
                            "Copyright (c) 2026 조승현 (Cho, Seung-Hyun). PolyForm Noncommercial 1.0.0",
                        ),
                        StringStruct("OriginalFilename", "Quiz Reporter.exe"),
                        StringStruct("ProductName", "Quiz Reporter"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
    ],
)

analysis = Analysis(  # noqa: F821
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(SRC_ROOT)],
    binaries=[],
    # app.py loads Path(__file__).parent / "resources" / "app_icon.svg"
    datas=[(str(SVG), "quiz_reporter/resources")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        *(f"PySide6.{name}" for name in QT_EXCLUDED_MODULES),
        "tkinter", "unittest", "pydoc", "pip", "setuptools", "pkg_resources", "distutils",
        "pytest", "_pytest", "pytestqt", "mypy", "mypy_extensions", "ruff", "tests",
    ],
    noarchive=False,
)
analysis.binaries = [entry for entry in analysis.binaries if _keep(entry)]
analysis.datas = [entry for entry in analysis.datas if _keep(entry)]

pyz = PYZ(analysis.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Quiz Reporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
    version=version_info,
)
collect = COLLECT(  # noqa: F821
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=FOLDER_NAME,
)
