"""Reports print to one bundle and one PDF per student; the workbooks live elsewhere."""

from __future__ import annotations

from pathlib import Path

from quiz_reporter.errors import Err, Ok
from quiz_reporter.quiz.grading import select, sheet_from_bank, suggest_cutoff
from quiz_reporter.quiz.responses import read_form_responses
from quiz_reporter.quiz.students import GradedQuiz, excluded_rows, students_from_selection
from quiz_reporter.ui.quiz_pdf import write_quiz_reports
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


def test_every_student_gets_a_pdf_and_the_bundle_is_written(qapp, tmp_path):
    exported = write_quiz_reports(_quiz(tmp_path), tmp_path / "리포트")

    assert isinstance(exported, Ok), exported
    summary = exported.value
    folder = Path(summary.folder)
    assert folder == tmp_path / "리포트"
    assert summary.students == 4 and summary.detailed
    assert Path(summary.bundle).stat().st_size > 0
    singles = sorted(path.name for path in (folder / "개별").iterdir())
    assert singles == [
        "001_20260001_가나.pdf",
        "002_20260002_다라.pdf",
        "003_20260003_마바.pdf",
        "004_학번확인필요_사아.pdf",
    ]
    assert sorted(path.name for path in folder.iterdir()) == ["개별", "전체(인쇄용).pdf"]


def test_a_quiz_without_students_is_refused(qapp, tmp_path):
    quiz = _quiz(tmp_path)
    empty = GradedQuiz(quiz.exam_name, quiz.folder_name, None, quiz.bank, (), ())

    result = write_quiz_reports(empty, tmp_path / "리포트")

    assert isinstance(result, Err)
    assert result.errors[0].context["reason"] == "리포트를 만들 학생이 없습니다."
