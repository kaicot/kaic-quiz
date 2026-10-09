"""``퀴즈정보.json``: what a saved quiz folder holds and the summary the lists show.

A quiz folder keeps only its originals (the response file copy, the cutoff and the 문항표);
students and reports are graded again from them. The summary here is a cache for the lists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result

INFO_FORMAT = 1
INFO_FILENAME = "퀴즈정보.json"
BANK_FILENAME = "문항표.xlsx"
RESPONSES_STEM = "응답원본"
RESPONSE_SUFFIXES = (".csv", ".xlsx")
REPORT_DIRNAME = "리포트"
# Where the options' order (and so their numbers) came from: the form itself (a 문항표 or
# the public form page) or only the order answers first appeared in the responses.
FORM_ORDER, RESPONSE_ORDER = "form", "responses"
_KEYS = {
    "format",
    "app_version",
    "name",
    "created_at",
    "graded_at",
    "source_name",
    "responses_file",
    "cutoff",
    "option_order",
    "summary",
}
_SUMMARY_KEYS = {
    "students",
    "flagged",
    "late",
    "repeats",
    "questions",
    "maximum",
    "average",
    "detailed",
}


@dataclass(frozen=True, slots=True)
class QuizSummary:
    students: int
    # Kept responses whose typed ID is not 8 digits.
    flagged: int
    late: int
    repeats: int
    questions: int
    # Questions with a known answer: the full score.
    maximum: int
    average: float
    # Every question has feedback (explanation, reasons, traps).
    detailed: bool


@dataclass(frozen=True, slots=True)
class QuizInfo:
    format: int
    app_version: str
    name: str
    created_at: datetime
    graded_at: datetime
    source_name: str
    responses_file: str
    cutoff: datetime | None
    option_order: str
    summary: QuizSummary

    @property
    def numbered(self) -> bool:
        """Option numbers match the form, so reports may show ①~⑤."""
        return self.option_order == FORM_ORDER

    def to_json(self) -> dict[str, object]:
        summary = self.summary
        return {
            "format": self.format,
            "app_version": self.app_version,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "graded_at": self.graded_at.isoformat(),
            "source_name": self.source_name,
            "responses_file": self.responses_file,
            "cutoff": None if self.cutoff is None else self.cutoff.isoformat(),
            "option_order": self.option_order,
            "summary": {
                "students": summary.students,
                "flagged": summary.flagged,
                "late": summary.late,
                "repeats": summary.repeats,
                "questions": summary.questions,
                "maximum": summary.maximum,
                "average": round(summary.average, 4),
                "detailed": summary.detailed,
            },
        }

    @staticmethod
    def from_json(value: Any) -> QuizInfo:
        """Strict reader: unknown or missing keys and wrong types raise ``ValueError``."""
        if not isinstance(value, dict) or set(value) != _KEYS:
            raise ValueError("quiz info keys")
        summary = value["summary"]
        if not isinstance(summary, dict) or set(summary) != _SUMMARY_KEYS:
            raise ValueError("quiz summary keys")
        cutoff = value["cutoff"]
        return QuizInfo(
            _integer(value["format"]),
            _text(value["app_version"]),
            _text(value["name"]),
            _moment(value["created_at"]),
            _moment(value["graded_at"]),
            _text(value["source_name"]),
            _responses_file(value["responses_file"]),
            None if cutoff is None else _moment(cutoff),
            _choice_of(value["option_order"], (FORM_ORDER, RESPONSE_ORDER)),
            QuizSummary(
                _integer(summary["students"]),
                _integer(summary["flagged"]),
                _integer(summary["late"]),
                _integer(summary["repeats"]),
                _integer(summary["questions"]),
                _integer(summary["maximum"]),
                _number(summary["average"]),
                _flag(summary["detailed"]),
            ),
        )


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError("expected a nonnegative number")
    return float(value)


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("expected a boolean")
    return value


def _text(value: object) -> str:
    if type(value) is not str:
        raise ValueError("expected text")
    return value


def _choice_of(value: object, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError("unexpected value")
    return str(value)


def _moment(value: object) -> datetime:
    moment = datetime.fromisoformat(_text(value))
    if moment.tzinfo is None:
        raise ValueError("time without a time zone")
    return moment


def _responses_file(value: object) -> str:
    name = _text(value)
    if name not in {RESPONSES_STEM + suffix for suffix in RESPONSE_SUFFIXES}:
        raise ValueError("unexpected response file name")
    return name


def _fail(reason: str) -> Err:
    return Err(
        (
            ErrorInfo(
                "QUIZ_INFO_UNREADABLE",
                "error.quiz_info_unreadable",
                None,
                context={"reason": reason},
            ),
        )
    )


def read_quiz_info(folder: Path) -> Result[QuizInfo]:
    """The folder's ``퀴즈정보.json``; an error says in Korean why the quiz can't be read."""
    try:
        raw = (folder / INFO_FILENAME).read_bytes()
    except FileNotFoundError:
        return _fail(f"{INFO_FILENAME}이 없습니다.")
    except OSError as exc:
        return _fail(f"{INFO_FILENAME}을 읽을 수 없습니다. ({exc.strerror or exc})")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail(f"{INFO_FILENAME}이 손상되었습니다.")
    found = value.get("format") if isinstance(value, dict) else None
    if type(found) is int and found > INFO_FORMAT:
        version = value.get("app_version")
        made_by = f" {version}" if isinstance(version, str) else ""
        return _fail(f"더 새 버전 퀴즈 리포터{made_by}에서 만든 퀴즈입니다. 새 버전으로 여세요.")
    try:
        return Ok(QuizInfo.from_json(value))
    except ValueError:
        return _fail(f"{INFO_FILENAME}의 내용이 올바르지 않습니다.")


__all__ = [
    "BANK_FILENAME",
    "FORM_ORDER",
    "RESPONSE_ORDER",
    "INFO_FILENAME",
    "INFO_FORMAT",
    "REPORT_DIRNAME",
    "RESPONSES_STEM",
    "RESPONSE_SUFFIXES",
    "QuizInfo",
    "QuizSummary",
    "read_quiz_info",
]
