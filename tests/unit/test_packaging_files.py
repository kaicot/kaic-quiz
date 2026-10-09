"""The release tooling names the right files and agrees with itself. Nothing is built here."""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

import quiz_reporter

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "Quiz_Reporter.spec"
NOTICES = ROOT / "packaging" / "generate_third_party_notices.py"
BUILD = ROOT / "tools" / "build-portable-folder.ps1"
VERIFY = ROOT / "tools" / "verify-portable-folder.ps1"
SMOKE = ROOT / "tools" / "smoke-portable.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def quoted(text: str, start: str, end: str, quote: str) -> list[str]:
    """The quoted words between two markers, e.g. a tuple or set literal."""
    begin = text.index(start) + len(start)
    return re.findall(rf"{quote}([^{quote}]+){quote}", text[begin : text.index(end, begin)])


def test_all_release_files_exist():
    for path in (SPEC, NOTICES, BUILD, VERIFY, SMOKE, ROOT / "packaging" / "quiz_reporter.ico"):
        assert path.is_file(), path
    assert (ROOT / "packaging" / "licenses" / "LGPL-3.0.txt").is_file()
    assert (ROOT / "packaging" / "licenses" / "GPL-3.0.txt").is_file()
    assert (ROOT / "packaging" / "quiz_reporter.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_packaging_folder_is_not_a_python_package():
    # A packaging/__init__.py would shadow the PyPI "packaging" library that pytest imports.
    assert not (ROOT / "packaging" / "__init__.py").exists()


@pytest.mark.parametrize("path", [SPEC, NOTICES, SMOKE])
def test_python_files_parse(path: Path):
    ast.parse(read(path), filename=str(path))


def test_spec_names_the_program_and_its_data():
    spec = read(SPEC)
    assert 'name="Quiz Reporter"' in spec
    assert "console=False" in spec
    assert "exclude_binaries=True" in spec  # onedir
    assert 'PROJECT_ROOT / "main.py"' in spec
    assert "quiz_reporter.ico" in spec
    assert "app_icon.svg" in spec
    assert '"quiz_reporter/resources"' in spec  # where app.py looks for the icon
    assert 'f"Quiz-Reporter-v{VERSION}"' in spec
    for text in (
        "Quiz Reporter.exe",
        "조승현 (Cho, Seung-Hyun)",
        "퀴즈 리포터 - 구글 폼 퀴즈 채점 · 학생별 피드백",
        "Copyright (c) 2026 조승현 (Cho, Seung-Hyun). PolyForm Noncommercial 1.0.0",
    ):
        assert text in spec


def test_spec_reads_the_package_version():
    spec = read(SPEC)
    assert "__init__.py" in spec
    match = re.search(r"^__version__\s*=\s*\"(\d+\.\d+\.\d+)\"", spec, re.MULTILINE)
    assert match is None  # the spec reads it; it does not hard-code one
    assert re.fullmatch(r"\d+\.\d+\.\d+", quiz_reporter.__version__)


def test_spec_and_verify_agree_on_qt_modules_and_dropped_files():
    spec, verify = read(SPEC), read(VERIFY)
    keep_dll = quoted(spec, "QT_KEEP = (", ")", '"')
    keep_pyd = quoted(spec, "QT_PYTHON_KEEP = (", ")", '"')
    assert keep_dll == quoted(verify, "$QtKeepDll = @(", ")", "'")
    assert keep_pyd == quoted(verify, "$QtKeepPyd = @(", ")", "'")
    assert set(keep_pyd) <= set(keep_dll) >= {"Core", "Gui", "Widgets"}
    assert quoted(spec, "DROP_FILES = {", "}", '"') == quoted(
        verify, "$DroppedFiles = @(", ")", "'"
    )
    assert quoted(spec, "DROP_PLUGIN_DIRS = {", "}", '"') == quoted(
        verify, "$DroppedPluginDirs = @(", ")", "'"
    )


def test_spec_excludes_unused_qt_and_keeps_the_used_ones():
    spec = read(SPEC)
    excluded = quoted(spec, "QT_EXCLUDED_MODULES = (", ")", '"')
    for name in (
        "QtWebEngineCore",
        "QtQuick",
        "QtQml",
        "Qt3DCore",
        "QtCharts",
        "QtDataVisualization",
        "QtMultimedia",
        "QtNetwork",
        "QtSql",
        "QtTest",
        "QtBluetooth",
        "QtSerialPort",
        "QtPositioning",
        "QtSensors",
        "QtVirtualKeyboard",
        "QtDesigner",
        "QtHelp",
        "QtPdf",
        "QtPdfWidgets",
    ):
        assert name in excluded, name
    for used in ("QtCore", "QtGui", "QtWidgets"):
        assert used not in excluded


def test_verify_checks_what_the_release_must_and_must_not_contain():
    verify = read(VERIFY)
    assert verify.isascii()
    for text in (
        "Quiz Reporter.exe",
        "_internal",
        "LICENSE.md",
        "THIRD_PARTY_NOTICES.txt",
        "app_icon.svg",
        "qwindows.dll",
        "qsvg.dll",
        "GPL-only",
        "Data",
        "update.json",
        ".quiz-reporter.lock",
        ".csv",
        ".xlsx",
        ".pdf",
        "FileVersion",
        "ProductVersion",
        ".sha256",
        "exit 1",
    ):
        assert text in verify, text
    assert "-Folder" in verify
    assert "-Zip" in verify


def test_build_script_names_the_outputs_and_refuses_to_overwrite():
    build = read(BUILD)
    assert build.isascii()
    for text in (
        "Quiz-Reporter-v$version",
        "-windows.zip",
        ".sha256",
        "LICENSE.md",
        "THIRD_PARTY_NOTICES.txt",
        "generate_third_party_notices.py",
        "Quiz_Reporter.spec",
        "verify-portable-folder.ps1",
        "ReparsePoint",
        "will not be replaced",
        "$DistRoot",
        "$WorkRoot",
    ):
        assert text in build, text
    assert "'dist'" in build
    assert "'build'" in build


def test_smoke_script_checks_the_frozen_program():
    smoke = read(SMOKE)
    for text in (
        "--self-check",
        "QT_QPA_PLATFORM",
        "QLockFile",
        "FORMAT.json",
        "quiz-reporter.log",
        "APPDATA",
        "LOCALAPPDATA",
        "tempfile.mkdtemp",
        "Quiz Reporter.exe",
    ):
        assert text in smoke, text
    assert "frozen" in smoke


def test_notices_cover_every_bundled_package(tmp_path: Path):
    module_spec = importlib.util.spec_from_file_location("third_party_notices", NOTICES)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    written = module.write_notices(tmp_path / "THIRD_PARTY_NOTICES.txt")
    text = written.read_text(encoding="utf-8")

    assert "LGPL-3.0" in text
    assert "https://download.qt.io" in text
    assert "https://code.qt.io/cgit/pyside/pyside-setup.git" in text
    assert "6.11.2" in text
    assert "_internal" in text  # where users can replace the Qt DLLs
    assert "openpyxl" in text and "et-xmlfile" in text
    assert "MIT License" in text or "Permission is hereby granted" in text
    assert "PyInstaller" in text
    assert "Python Software Foundation" in text
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in text
    assert "LicenseRef-Qt-Commercial" not in text
