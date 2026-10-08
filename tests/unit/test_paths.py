from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from quiz_reporter.errors import Err, Ok
from quiz_reporter.infrastructure import paths as paths_module
from quiz_reporter.infrastructure.paths import ManagedPaths, resolve_portable_root


def test_resolve_portable_root_uses_injected_source_entry(tmp_path: Path) -> None:
    entry = tmp_path / "source" / "main.py"

    assert resolve_portable_root(frozen=False, source_entry=entry) == entry.parent.resolve()


def test_resolve_portable_root_uses_injected_executable_when_frozen(tmp_path: Path) -> None:
    executable = tmp_path / "package" / "Quiz_Reporter.exe"

    assert resolve_portable_root(frozen=True, executable=executable) == executable.parent.resolve()


def test_resolve_portable_root_uses_runtime_entry_when_not_injected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = tmp_path / "runtime" / "main.py"
    monkeypatch.setattr(paths_module.sys, "argv", [str(entry)])

    assert resolve_portable_root(frozen=False) == entry.parent.resolve()


def test_resolve_portable_root_uses_runtime_executable_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "packaged" / "Quiz_Reporter.exe"
    monkeypatch.setattr(paths_module.sys, "executable", str(executable))

    assert resolve_portable_root(frozen=True) == executable.parent.resolve()


def test_managed_paths_stay_beneath_portable_root(tmp_path: Path) -> None:
    paths = ManagedPaths.from_root(tmp_path / "portable")
    paths.root.mkdir()

    data = paths.data_path("quiz", "answers.json")
    trash = paths.trash_path("quiz")

    assert paths.data_dir == (paths.root / "Data").resolve()
    assert paths.trash_dir == (paths.root / "Data" / "_휴지통").resolve()
    assert paths.update_prefs_path == paths.root / "update.json"
    assert isinstance(data, Ok)
    assert data.value.is_relative_to(paths.root)
    assert isinstance(trash, Ok)
    assert trash.value == (paths.root / "Data" / "_휴지통" / "quiz").resolve()


@pytest.mark.parametrize(
    "component", ["..", "child/grandchild", "child\\grandchild", "C:drive", "name."]
)
def test_data_path_rejects_unsafe_components(tmp_path: Path, component: str) -> None:
    result = ManagedPaths.from_root(tmp_path).data_path(component)

    assert isinstance(result, Err)
    assert result.errors[0].code == "INVALID_MANAGED_PATH"


@pytest.mark.parametrize(
    "component",
    ["data\x00", "AUX.backup", "answers.json:stream", r"\\server\share", "name "],
)
def test_data_path_rejects_portable_windows_filename_hazards(
    tmp_path: Path, component: str
) -> None:
    result = ManagedPaths.from_root(tmp_path).data_path(component)

    assert isinstance(result, Err)
    assert result.errors[0].code == "INVALID_MANAGED_PATH"


@pytest.mark.parametrize("component", ["..", "child/grandchild", "NUL.log"])
def test_trash_path_rejects_unsafe_components(tmp_path: Path, component: str) -> None:
    result = ManagedPaths.from_root(tmp_path).trash_path(component)

    assert isinstance(result, Err)
    assert result.errors[0].code == "INVALID_MANAGED_PATH"


def test_managed_paths_reject_escaping_symlink_entries(tmp_path: Path) -> None:
    root = tmp_path / "portable"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "Data"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EPERM} or getattr(exc, "winerror", None) == 1314:
            pytest.skip(f"directory symlinks require unavailable host privileges: {exc}")
        raise

    result = ManagedPaths.from_root(root).data_path("session.json")

    assert isinstance(result, Err)
    assert result.errors[0].code == "MANAGED_PATH_INVALID"


def test_managed_paths_reject_reparse_point_managed_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = ManagedPaths.from_root(tmp_path)
    monkeypatch.setattr(
        paths_module,
        "_is_reparse_point",
        lambda path: path == paths.data_dir,
    )

    result = paths.data_path("session.json")

    assert isinstance(result, Err)
    assert result.errors[0].code == "MANAGED_PATH_INVALID"
