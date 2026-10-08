"""Bring the saved quizzes of a previous install over into this one ("이전 버전 자료 가져오기").

Updating means unpacking the new version into a new folder; this copies the quizzes the old
folder holds in ``Data\\`` and its trash. Every quiz is copied into a staging folder, graded there
with the normal reader, and only then renamed into place, so a broken quiz never shows up as a
half-imported one. The old folder is only read, so the user can always go back to the old version.
"""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.infrastructure.data_format import (
    DATA_FORMAT,
    FORMAT_FILENAME,
    newer_format_reason,
    read_data_format,
)
from quiz_reporter.infrastructure.io_retry import retry_io
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.storage.quiz_info import INFO_FILENAME
from quiz_reporter.storage.quiz_store import STAGING_PREFIX, QuizStore, remove_tree

_LOCKED = (
    "퀴즈 폴더의 파일(PDF·엑셀)이나 그 폴더를 연 탐색기 창이 열려 있습니다."
    " 이전 버전 프로그램을 끄고 다시 시도하세요."
)


@dataclass(frozen=True, slots=True)
class ImportProgress:
    """After each candidate: how many are handled, how many there are, and the one just handled."""

    done: int
    total: int
    folder: str


@dataclass(frozen=True, slots=True)
class ImportSummary:
    imported: int
    trashed: int
    # Already here under the same folder name (for example from an earlier import).
    skipped: int
    # (folder name, Korean reason) for each quiz that could not be brought over.
    failed: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path
    in_trash: bool

    @property
    def name(self) -> str:
        return self.path.name


def _error(code: str, reason: str) -> Err:
    return Err((ErrorInfo(code, f"error.{code.lower()}", None, context={"reason": reason}),))


def _os_reason(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return _LOCKED
    if isinstance(exc, shutil.Error):
        return "파일을 복사하지 못했습니다."
    return f"파일을 복사하거나 옮기지 못했습니다. ({exc.strerror or exc})"


def _has_quiz_info(base: Path) -> bool:
    try:
        return any((path / INFO_FILENAME).is_file() for path in base.iterdir() if path.is_dir())
    except OSError:
        return False


def _looks_like_install(root: Path) -> bool:
    """A ``Data`` folder that has the format marker or at least one quiz in it or its trash."""
    data = ManagedPaths.from_root(root).data_dir
    if not data.is_dir():
        return False
    return (
        (data / FORMAT_FILENAME).is_file()
        or _has_quiz_info(data)
        or _has_quiz_info(ManagedPaths.from_root(root).trash_dir)
    )


def install_root(chosen: str | Path) -> Path | None:
    """The previous install's folder for what the user picked: the folder or its ``Data``."""
    path = Path(chosen)
    for candidate in (path, path.parent):
        if _looks_like_install(candidate):
            return candidate
    return None


def _same_folder(left: Path, right: Path) -> bool:
    try:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()
    except OSError:
        return False


def _candidates(source: ManagedPaths) -> list[_Candidate]:
    found: list[_Candidate] = []
    for base, in_trash in ((source.data_dir, False), (source.trash_dir, True)):
        try:
            folders = sorted(path for path in base.iterdir() if path.is_dir())
        except FileNotFoundError:
            continue
        for path in folders:
            if not path.name.startswith((".", "_")):
                found.append(_Candidate(path, in_trash))
    return found


def _failure_reason(result: Err) -> str:
    return str(result.errors[0].context.get("reason") or "퀴즈를 읽을 수 없습니다.")


def _has_link(folder: Path) -> bool:
    """A symlink or junction anywhere in the quiz folder (copying would follow it outside)."""
    if folder.is_symlink() or folder.is_junction():
        return True
    for parent, directories, files in folder.walk():
        for name in (*directories, *files):
            entry = parent / name
            if entry.is_symlink() or entry.is_junction():
                return True
    return False


def _bring_over(candidate: _Candidate, data: Path, target: Path, store: QuizStore) -> str | None:
    """Copy one quiz via ``data`` staging into ``target``; ``None`` on success, else the reason."""
    try:
        if _has_link(candidate.path):
            return "퀴즈 폴더 안에 바로가기 링크(연결된 폴더)가 있어 가져오지 않았습니다."
    except OSError as exc:
        return _os_reason(exc)
    staging = data / f"{STAGING_PREFIX}{secrets.token_hex(4)}"
    try:
        shutil.copytree(candidate.path, staging)
        checked = store.check_folder(staging)
        if isinstance(checked, Err):
            return _failure_reason(checked)
        target.mkdir(parents=True, exist_ok=True)
        retry_io(lambda: staging.rename(target / candidate.name))
    except OSError as exc:
        return _os_reason(exc)
    finally:
        if staging.exists():
            try:
                remove_tree(staging)
            except OSError:
                pass  # ``QuizStore.recover`` drops a leftover staging folder on the next start.
    return None


def import_previous_install(
    chosen: str | Path,
    store: QuizStore,
    paths: ManagedPaths,
    progress: Callable[[ImportProgress], None] | None = None,
) -> Result[ImportSummary]:
    """Copy the quizzes (and trashed quizzes) of a previous install into this one.

    A folder that is already here under the same name is skipped, so running it again after a
    partial failure is safe. One quiz that can't be brought over is listed in ``failed`` and the
    rest still arrive. Nothing is ever written inside the old folder.
    """
    chosen_path = Path(chosen)
    # The program folder itself, or its Data folder (which may still be empty).
    if _same_folder(chosen_path, paths.root) or _same_folder(chosen_path, paths.data_dir):
        return _error(
            "IMPORT_SOURCE_SAME",
            "지금 쓰고 있는 프로그램 폴더입니다. 이전 버전 프로그램 폴더를 고르세요.",
        )
    source_root = install_root(chosen_path)
    if source_root is None:
        return _error(
            "IMPORT_SOURCE_INVALID",
            "퀴즈 리포터 폴더가 아닙니다. 이전 버전 프로그램이 있는 폴더(Data 폴더가 들어 있는"
            " 폴더)를 고르세요.",
        )
    if _same_folder(source_root, paths.root):
        return _error(
            "IMPORT_SOURCE_SAME",
            "지금 쓰고 있는 프로그램 폴더입니다. 이전 버전 프로그램 폴더를 고르세요.",
        )
    source = ManagedPaths.from_root(source_root)
    marker = read_data_format(source.data_dir)
    if isinstance(marker, Err):
        return marker
    if marker.value is not None and marker.value.data_format > DATA_FORMAT:
        return _error("IMPORT_SOURCE_NEWER", newer_format_reason(marker.value))

    data = paths.data_target()
    if isinstance(data, Err):
        return data
    trash = paths.trash_target()
    if isinstance(trash, Err):
        return trash
    try:
        candidates = _candidates(source)
    except OSError as exc:
        return _error("IMPORT_FAILED", f"이전 폴더를 읽을 수 없습니다. ({exc.strerror or exc})")

    try:
        data.value.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error("IMPORT_FAILED", _os_reason(exc))
    imported = trashed = skipped = 0
    failed: list[tuple[str, str]] = []
    for index, candidate in enumerate(candidates, start=1):
        target = trash.value if candidate.in_trash else data.value
        # Already here, active or trashed (the user may have moved it since an earlier import).
        if (data.value / candidate.name).exists() or (trash.value / candidate.name).exists():
            skipped += 1
        elif (reason := _bring_over(candidate, data.value, target, store)) is not None:
            failed.append((candidate.name, reason))
        elif candidate.in_trash:
            trashed += 1
        else:
            imported += 1
        if progress is not None:
            progress(ImportProgress(index, len(candidates), candidate.name))
    return Ok(ImportSummary(imported, trashed, skipped, tuple(failed)))


__all__ = [
    "ImportProgress",
    "ImportSummary",
    "import_previous_install",
    "install_root",
]
