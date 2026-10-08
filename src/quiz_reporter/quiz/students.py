"""Turn the kept form responses into graded students, in the order every output lists them."""

from __future__ import annotations

import re
from dataclasses import dataclass

from quiz_reporter.quiz.bank import QuizBank
from quiz_reporter.quiz.grading import AnswerSheet, Selection, choice_numbers, valid_student_id
from quiz_reporter.quiz.report import Student
from quiz_reporter.quiz.responses import FormResponse

LATE_REASON = "마감 뒤 응답(복습)"
REPEAT_REASON = "같은 학번의 두 번째 이후 응답"
_FILENAME_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass(frozen=True, slots=True)
class GradedQuiz:
    exam_name: str
    folder_name: str
    graded_at: str | None
    bank: QuizBank
    students: tuple[Student, ...]
    # 시각, 학번(입력값), 이름, 이유
    excluded: tuple[tuple[str, ...], ...]


def safe_filename(text: str) -> str:
    return _FILENAME_UNSAFE.sub("_", text).strip(" .") or "퀴즈"


def _when(row: FormResponse) -> str:
    return row.submitted_at.strftime("%m/%d %H:%M:%S") if row.submitted_at else "시각 없음"


def students_from_selection(selection: Selection, sheet: AnswerSheet) -> tuple[Student, ...]:
    """Each kept response as a student; IDs that are not 8 digits are left blank.

    Sorted 가나다 by name, then by student ID; numbered from 1 in that order.
    """
    raw = [
        Student(
            position,
            row.student_id if valid_student_id(row.student_id) else "",
            row.name,
            choice_numbers(row, sheet),
        )
        for position, row in enumerate(selection.kept)
    ]
    ordered = sorted(
        raw, key=lambda s: (not s.name, s.name, not s.student_id, s.student_id, s.serial)
    )
    return tuple(
        Student(serial, s.student_id, s.name, s.choices) for serial, s in enumerate(ordered, 1)
    )


def flagged_count(selection: Selection) -> int:
    """Kept responses whose typed ID is not 8 digits."""
    return sum(not valid_student_id(row.student_id) for row in selection.kept)


def excluded_rows(selection: Selection) -> tuple[tuple[str, ...], ...]:
    """The responses left out: late ones first, then repeats."""
    late = [(_when(row), row.student_id, row.name, LATE_REASON) for row in selection.late]
    repeats = [(_when(row), row.student_id, row.name, REPEAT_REASON) for row in selection.repeats]
    return tuple(late + repeats)


__all__ = [
    "LATE_REASON",
    "REPEAT_REASON",
    "GradedQuiz",
    "excluded_rows",
    "flagged_count",
    "safe_filename",
    "students_from_selection",
]
