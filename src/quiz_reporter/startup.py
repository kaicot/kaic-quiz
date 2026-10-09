"""Checks before the window opens: can we write here, and is the data a format we understand?"""

from __future__ import annotations

from dataclasses import dataclass

from quiz_reporter.errors import Err
from quiz_reporter.infrastructure.atomic_io import atomic_write_bytes
from quiz_reporter.infrastructure.data_format import ensure_data_format
from quiz_reporter.infrastructure.paths import ManagedPaths, is_path_writable
from quiz_reporter.infrastructure.update_check import UpdatePreferences

READ_ONLY_FOLDER = (
    "프로그램 폴더에 쓸 수 없어 읽기 전용으로 열었습니다. 채점·삭제는 할 수 없습니다."
    " 프로그램 폴더 전체를 쓰기 가능한 곳(예: D:\\퀴즈리포터)으로 옮기세요."
)


@dataclass(frozen=True, slots=True)
class StartupState:
    paths: ManagedPaths
    # Why the program opened read-only; ``None`` when it can write.
    read_only_reason: str | None
    # A problem worth telling the user that does not stop writing.
    notice: str | None = None

    @property
    def writable(self) -> bool:
        return self.read_only_reason is None


def prepare(paths: ManagedPaths, version: str) -> StartupState:
    """Create ``Data`` and its ``FORMAT.json`` when we may; otherwise say why we are read-only."""
    if not is_path_writable(paths.root):
        return StartupState(paths, READ_ONLY_FOLDER)
    data = paths.data_target()
    if isinstance(data, Err):
        return StartupState(paths, str(data.errors[0].context.get("reason") or READ_ONLY_FOLDER))
    try:
        data.value.mkdir(parents=True, exist_ok=True)
    except OSError:
        return StartupState(paths, READ_ONLY_FOLDER)
    marker = ensure_data_format(data.value, version)
    if isinstance(marker, Err):
        return StartupState(paths, str(marker.errors[0].context["reason"]))
    notice = None
    if marker.warnings:
        notice = str(marker.warnings[0].context.get("reason") or "")
    return StartupState(paths, None, notice or None)


def load_update_preferences(paths: ManagedPaths) -> UpdatePreferences:
    try:
        return UpdatePreferences.from_json(paths.update_prefs_path.read_bytes())
    except OSError:
        return UpdatePreferences()


def save_update_preferences(paths: ManagedPaths, prefs: UpdatePreferences) -> bool:
    return not isinstance(atomic_write_bytes(paths.update_prefs_path, prefs.to_json()), Err)


__all__ = [
    "READ_ONLY_FOLDER",
    "StartupState",
    "load_update_preferences",
    "prepare",
    "save_update_preferences",
]
