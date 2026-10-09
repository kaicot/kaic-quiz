"""Saved quizzes under ``Data\\``: create, list, reopen, rebuild with a new 문항표, trash.

Every change is built in a staging folder (``Data\\.작업중-…``) and renamed into place, so a
failure never leaves a half-written quiz. Rebuilding parks the old folder as
``Data\\.교체전-<폴더>`` until the new one is in place; ``recover`` puts it back after a crash.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import quiz_reporter
from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.infrastructure.atomic_io import atomic_write_bytes, atomic_write_json
from quiz_reporter.infrastructure.io_retry import retry_copy2, retry_io
from quiz_reporter.infrastructure.paths import ManagedPaths, validate_component
from quiz_reporter.quiz.bank import QuizBank, bank_workbook_bytes, parse_bank_bytes
from quiz_reporter.quiz.grading import AnswerSheet
from quiz_reporter.quiz.pipeline import Graded, grade
from quiz_reporter.quiz.responses import KST, FormResponses, read_form_responses
from quiz_reporter.quiz.students import GradedQuiz, safe_filename
from quiz_reporter.storage.quiz_info import (
    BANK_FILENAME,
    INFO_FILENAME,
    INFO_FORMAT,
    REPORT_DIRNAME,
    RESPONSE_SUFFIXES,
    RESPONSES_STEM,
    QuizInfo,
    QuizSummary,
    read_quiz_info,
)

STAGING_PREFIX = ".작업중-"
PARKED_PREFIX = ".교체전-"
PURGING_PREFIX = ".삭제중-"
NAME_LIMIT = 40
_LOCKED = (
    "퀴즈 폴더의 파일(PDF·엑셀)이나 그 폴더를 연 탐색기 창이 열려 있습니다. 닫고 다시 시도하세요."
)

# Writes the report files of a graded quiz into the given folder.
ReportWriter = Callable[[GradedQuiz, Path], Result[Any]]


@dataclass(frozen=True, slots=True)
class QuizEntry:
    """A folder in ``Data\\`` or the trash. ``info`` is ``None`` when it can't be read."""

    folder: str
    path: Path
    info: QuizInfo | None
    problem: str = ""


@dataclass(frozen=True, slots=True)
class OpenedQuiz:
    entry: QuizEntry
    info: QuizInfo
    responses: FormResponses
    graded: Graded

    @property
    def report_dir(self) -> Path:
        return self.entry.path / REPORT_DIRNAME


def _fail(reason: str) -> Err:
    return Err(
        (
            ErrorInfo(
                "QUIZ_STORE_FAILED", "error.quiz_store_failed", None, context={"reason": reason}
            ),
        )
    )


def _os_reason(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return _LOCKED
    return f"파일을 옮기거나 저장하지 못했습니다. ({exc.strerror or exc})"


def _now() -> datetime:
    return datetime.now(KST).replace(microsecond=0)


def remove_tree(path: Path) -> None:
    def clear_readonly(function: Callable[..., object], target: str, _: object) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=clear_readonly)


def _discard(path: Path) -> None:
    """Best-effort removal; ``QuizStore.recover`` retries leftovers on the next start."""
    if not path.exists():
        return
    try:
        remove_tree(path)
    except OSError:
        pass


def _summary(graded: Graded) -> QuizSummary:
    return QuizSummary(
        len(graded.students),
        graded.flagged,
        len(graded.selection.late),
        len(graded.selection.repeats),
        len(graded.bank.items),
        graded.summary.maximum,
        graded.summary.average,
        graded.bank.complete,
    )


def graded_quiz(info: QuizInfo, folder: str, graded: Graded) -> GradedQuiz:
    """What the report writer needs."""
    return GradedQuiz(
        info.name,
        folder,
        info.graded_at.isoformat(),
        graded.bank,
        graded.students,
        graded.excluded,
    )


class QuizStore:
    def __init__(
        self,
        paths: ManagedPaths,
        writer: ReportWriter,
        *,
        app_version: str = quiz_reporter.__version__,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._paths = paths
        self._writer = writer
        self._version = app_version
        self._clock = clock

    # ----- reading -------------------------------------------------------------------------

    def list_quizzes(self) -> tuple[QuizEntry, ...]:
        """Newest first; folders whose 퀴즈정보.json can't be read come last."""
        return self._entries(self._paths.data_dir)

    def list_trash(self) -> tuple[QuizEntry, ...]:
        return self._entries(self._paths.trash_dir)

    def _entries(self, base: Path) -> tuple[QuizEntry, ...]:
        try:
            folders = sorted(path for path in base.iterdir() if path.is_dir())
        except OSError:
            return ()
        entries: list[QuizEntry] = []
        for path in folders:
            if path.name.startswith((".", "_")):
                continue
            read = read_quiz_info(path)
            if isinstance(read, Err):
                entries.append(
                    QuizEntry(path.name, path, None, str(read.errors[0].context["reason"]))
                )
            else:
                entries.append(QuizEntry(path.name, path, read.value))
        readable = sorted(
            (entry for entry in entries if entry.info is not None),
            key=lambda entry: (entry.info.created_at if entry.info else _now(), entry.folder),
            reverse=True,
        )
        broken = [entry for entry in entries if entry.info is None]
        return tuple(readable + broken)

    def open(self, folder: str) -> Result[OpenedQuiz]:
        """Read a saved quiz and grade it again from its originals."""
        path = self._paths.data_path(folder)
        if isinstance(path, Err):
            return path
        return self._open_at(path.value)

    def check_folder(self, path: Path) -> Result[OpenedQuiz]:
        """Grade a quiz folder anywhere (such as one being imported) without moving it."""
        return self._open_at(path)

    def _open_at(self, path: Path, bank: QuizBank | None = None) -> Result[OpenedQuiz]:
        info = read_quiz_info(path)
        if isinstance(info, Err):
            return info
        responses = read_form_responses(str(path / info.value.responses_file))
        if isinstance(responses, Err):
            return responses
        if bank is None:
            try:
                data = (path / BANK_FILENAME).read_bytes()
            except OSError as exc:
                return _fail(f"{BANK_FILENAME}을 읽을 수 없습니다. ({exc.strerror or exc})")
            parsed = parse_bank_bytes(data, require_feedback=False)
            if isinstance(parsed, Err):
                return parsed
            bank = parsed.value
        graded = grade(responses.value, info.value.cutoff, bank)
        if isinstance(graded, Err):
            return graded
        entry = QuizEntry(path.name, path, info.value)
        return Ok(OpenedQuiz(entry, info.value, responses.value, graded.value))

    # ----- writing -------------------------------------------------------------------------

    def create(
        self,
        name: str,
        responses_path: Path,
        cutoff: datetime | None,
        bank: QuizBank,
        sheet: AnswerSheet | None = None,
    ) -> Result[QuizEntry]:
        """Save a new quiz: copy the response file, grade it, write the 문항표 and reports.

        ``sheet`` is what the screen graded with; the saved quiz must grade the same way.
        """
        suffix = responses_path.suffix.lower()
        if suffix not in RESPONSE_SUFFIXES:
            return _fail("응답 파일은 구글 폼의 CSV나 xlsx여야 합니다.")
        created = self._clock()
        title = name.strip() or "퀴즈"
        base = f"{created:%y%m%d_%H%M%S}_{safe_filename(title)[:NAME_LIMIT].strip(' .')}"
        if isinstance(valid := validate_component(base, field_path="quiz"), Err):
            return valid
        data = self._ready(self._paths.data_target())
        if isinstance(data, Err):
            return data
        staging = self._new_staging(data.value)
        if isinstance(staging, Err):
            return staging
        try:
            copied = staging.value / f"{RESPONSES_STEM}{suffix}"
            retry_copy2(responses_path, copied)
            responses = read_form_responses(str(copied))
            if isinstance(responses, Err):
                return responses
            graded = grade(responses.value, cutoff, bank)
            if isinstance(graded, Err):
                return graded
            if sheet is not None and sheet != graded.value.sheet:
                return _fail("화면의 채점 기준과 문항표가 다릅니다. 문항표를 다시 불러오세요.")
            folder = self._unique(data.value, base)
            info = QuizInfo(
                INFO_FORMAT,
                self._version,
                title,
                created,
                created,
                responses_path.name,
                copied.name,
                cutoff,
                _summary(graded.value),
            )
            written = self._write(staging.value, info, folder, graded.value)
            if isinstance(written, Err):
                return written
            retry_io(lambda: staging.value.rename(data.value / folder))
        except OSError as exc:
            return _fail(_os_reason(exc))
        finally:
            _discard(staging.value)
        return Ok(QuizEntry(folder, data.value / folder, info))

    def replace_bank(self, folder: str, bank: QuizBank) -> Result[QuizEntry]:
        """Grade a saved quiz again with ``bank`` and replace its 문항표 and reports."""
        path = self._paths.data_path(folder)
        if isinstance(path, Err):
            return path
        current = self._open_at(path.value, bank)
        if isinstance(current, Err):
            return current
        opened = current.value
        info = replace(
            opened.info,
            app_version=self._version,
            graded_at=self._clock(),
            summary=_summary(opened.graded),
        )
        data = path.value.parent
        staging = self._new_staging(data)
        if isinstance(staging, Err):
            return staging
        parked = data / f"{PARKED_PREFIX}{folder}"
        try:
            for item in path.value.iterdir():
                if item.name in {REPORT_DIRNAME, BANK_FILENAME, INFO_FILENAME}:
                    continue
                if item.is_dir():
                    shutil.copytree(item, staging.value / item.name)
                else:
                    retry_copy2(item, staging.value / item.name)
            written = self._write(staging.value, info, folder, opened.graded)
            if isinstance(written, Err):
                return written
            if parked.exists():
                # Left over from an earlier rebuild whose cleanup failed; the quiz itself
                # is still in place, so the parked copy is stale.
                remove_tree(parked)
            retry_io(lambda: path.value.rename(parked))
            try:
                retry_io(lambda: staging.value.rename(path.value))
            except OSError:
                retry_io(lambda: parked.rename(path.value))
                raise
        except OSError as exc:
            return _fail(_os_reason(exc))
        finally:
            _discard(staging.value)
        _discard(parked)
        return Ok(QuizEntry(folder, path.value, info))

    def delete(self, folder: str) -> Result[QuizEntry]:
        """Move a quiz to ``Data\\_휴지통``."""
        source = self._paths.data_path(folder)
        if isinstance(source, Err):
            return source
        trash = self._ready(self._paths.trash_target())
        if isinstance(trash, Err):
            return trash
        return self._move(source.value, trash.value)

    def restore(self, folder: str) -> Result[QuizEntry]:
        """Move a quiz back from the trash; a name already in use gets ``_2``."""
        source = self._paths.trash_path(folder)
        if isinstance(source, Err):
            return source
        data = self._ready(self._paths.data_target())
        if isinstance(data, Err):
            return data
        return self._move(source.value, data.value)

    def purge(self, folder: str) -> Result[None]:
        """Delete a quiz in the trash for good."""
        target = self._paths.trash_path(folder)
        if isinstance(target, Err):
            return target
        if not target.value.is_dir():
            return _fail("휴지통에 그 퀴즈가 없습니다.")
        # Rename first: it fails cleanly while a file is open, so the quiz is never left
        # half deleted.
        doomed = target.value.with_name(f"{PURGING_PREFIX}{secrets.token_hex(4)}")
        try:
            retry_io(lambda: target.value.rename(doomed))
        except OSError as exc:
            return _fail(_os_reason(exc))
        _discard(doomed)
        return Ok(None)

    def recover(self) -> None:
        """After a crash: put back a parked quiz whose rebuild never finished, drop staging
        and half-purged trash."""
        leftovers: list[Path] = []
        for base in (self._paths.data_dir, self._paths.trash_dir):
            try:
                leftovers.extend(path for path in base.iterdir() if path.is_dir())
            except OSError:
                continue
        for path in leftovers:
            try:
                if path.name.startswith(PARKED_PREFIX):
                    original = path.with_name(path.name[len(PARKED_PREFIX) :])
                    if original.exists():
                        remove_tree(path)
                    else:
                        path.rename(original)
                elif path.name.startswith((STAGING_PREFIX, PURGING_PREFIX)):
                    remove_tree(path)
            except OSError:
                continue

    # ----- helpers -------------------------------------------------------------------------

    def _ready(self, target: Result[Path]) -> Result[Path]:
        if isinstance(target, Err):
            return target
        try:
            target.value.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _fail(_os_reason(exc))
        return target

    @staticmethod
    def _new_staging(data: Path) -> Result[Path]:
        staging = data / f"{STAGING_PREFIX}{secrets.token_hex(4)}"
        try:
            staging.mkdir()
        except OSError as exc:
            return _fail(_os_reason(exc))
        return Ok(staging)

    @staticmethod
    def _unique(base_dir: Path, name: str) -> str:
        candidate, number = name, 2
        while (base_dir / candidate).exists():
            candidate = f"{name}_{number}"
            number += 1
        return candidate

    def _write(self, folder: Path, info: QuizInfo, name: str, graded: Graded) -> Result[None]:
        bank = atomic_write_bytes(folder / BANK_FILENAME, bank_workbook_bytes(graded.bank))
        if isinstance(bank, Err):
            return bank
        reports = self._writer(graded_quiz(info, name, graded), folder / REPORT_DIRNAME)
        if isinstance(reports, Err):
            return reports
        # Written last: a folder without it is never listed as a finished quiz.
        return atomic_write_json(folder / INFO_FILENAME, info.to_json())

    def _move(self, source: Path, target_dir: Path) -> Result[QuizEntry]:
        if not source.is_dir():
            return _fail("그 퀴즈 폴더가 없습니다.")
        name = self._unique(target_dir, source.name)
        target = target_dir / name
        try:
            retry_io(lambda: source.rename(target))
        except OSError as exc:
            return _fail(_os_reason(exc))
        read = read_quiz_info(target)
        if isinstance(read, Err):
            return Ok(QuizEntry(name, target, None, str(read.errors[0].context["reason"])))
        return Ok(QuizEntry(name, target, read.value))


__all__ = [
    "NAME_LIMIT",
    "PARKED_PREFIX",
    "PURGING_PREFIX",
    "STAGING_PREFIX",
    "OpenedQuiz",
    "QuizEntry",
    "QuizStore",
    "ReportWriter",
    "graded_quiz",
    "remove_tree",
]
