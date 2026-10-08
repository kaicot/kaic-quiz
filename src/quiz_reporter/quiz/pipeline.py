"""Grade a quiz from its originals: the responses, the cutoff and the question bank.

The first grading and every later rebuild (a new bank, reopening a saved quiz) go through
``grade`` so a saved quiz always reproduces the same students and reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.quiz.bank import QuizBank
from quiz_reporter.quiz.grading import AnswerSheet, Selection, select, sheet_from_bank
from quiz_reporter.quiz.report import ClassSummary, Student, StudentReport, build_reports
from quiz_reporter.quiz.responses import FormResponses
from quiz_reporter.quiz.students import excluded_rows, flagged_count, students_from_selection


@dataclass(frozen=True, slots=True)
class Graded:
    bank: QuizBank
    sheet: AnswerSheet
    selection: Selection
    students: tuple[Student, ...]
    # 시각, 학번(입력값), 이름, 이유
    excluded: tuple[tuple[str, ...], ...]
    reports: tuple[StudentReport, ...]
    summary: ClassSummary

    @property
    def flagged(self) -> int:
        return flagged_count(self.selection)


def _fail(reason: str) -> Err:
    return Err(
        (
            ErrorInfo(
                "QUIZ_GRADE_FAILED", "error.quiz_grade_failed", None, context={"reason": reason}
            ),
        )
    )


def grade(responses: FormResponses, cutoff: datetime | None, bank: QuizBank) -> Result[Graded]:
    """Check the bank against the form, keep the responses up to ``cutoff`` and grade them."""
    sheet = sheet_from_bank(responses, bank)
    if isinstance(sheet, Err):
        return sheet
    if all(answer is None for answer in sheet.value.answers):
        return _fail("정답을 아는 문항이 없습니다. 문항표에 정답을 채워 주세요.")
    selection = select(responses, cutoff)
    if not selection.kept:
        return _fail("채점할 응답이 없습니다. 마감 시각을 확인하세요.")
    students = students_from_selection(selection, sheet.value)
    reports, summary = build_reports(bank, students)
    return Ok(
        Graded(
            bank,
            sheet.value,
            selection,
            students,
            excluded_rows(selection),
            reports,
            summary,
        )
    )


__all__ = ["Graded", "grade"]
