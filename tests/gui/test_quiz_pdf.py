"""Reports print to one bundle, one PDF per student and the analysis workbook."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from quiz_reporter.errors import Err, Ok
from quiz_reporter.quiz.grading import select, sheet_from_bank, suggest_cutoff
from quiz_reporter.quiz.responses import read_form_responses
from quiz_reporter.quiz.students import GradedQuiz, excluded_rows, students_from_selection
from quiz_reporter.ui.quiz_pdf import export_quiz_reports
from tests.helpers.quiz_forms import form_csv, full_bank


def _quiz(tmp_path: Path) -> GradedQuiz:
    path = tmp_path / "퀴즈.csv"
    path.write_bytes(form_csv())
    responses = read_form_responses(str(path))
    assert isinstance(responses, Ok)
    bank = full_bank()
    sheet = sheet_from_bank(responses.value, bank)
    assert isinstance(sheet, Ok)
    selection = select(responses.value, suggest_cutoff(responses.value))
    students = students_from_selection(selection, sheet.value)
    return GradedQuiz(
        "생리 퀴즈",
        "261006_131100_생리 퀴즈",
        "2026-10-06T13:20:00",
        bank,
        students,
        excluded_rows(selection),
    )


def test_every_student_gets_a_pdf_and_the_bundle_and_analysis_are_written(qapp, tmp_path):
    exported = export_quiz_reports(_quiz(tmp_path), str(tmp_path / "out"))

    assert isinstance(exported, Ok), exported
    summary = exported.value
    folder = Path(summary.folder)
    assert summary.students == 4 and summary.detailed
    assert Path(summary.bundle).stat().st_size > 0
    singles = sorted(path.name for path in (folder / "개별").iterdir())
    assert singles == [
        "001_20260001_가나.pdf",
        "002_20260002_다라.pdf",
        "003_20260003_마바.pdf",
        "004_학번확인필요_사아.pdf",
    ]
    workbook = openpyxl.load_workbook(summary.analysis, read_only=True)
    try:
        assert workbook.sheetnames
    finally:
        workbook.close()


def test_a_quiz_without_students_is_refused(qapp, tmp_path):
    quiz = _quiz(tmp_path)
    empty = GradedQuiz(quiz.exam_name, quiz.folder_name, None, quiz.bank, (), ())

    result = export_quiz_reports(empty, str(tmp_path / "out"))

    assert isinstance(result, Err)
    assert result.errors[0].context["reason"] == "리포트를 만들 학생이 없습니다."
