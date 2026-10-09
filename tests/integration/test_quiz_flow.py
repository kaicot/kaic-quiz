"""A Google Forms quiz end to end: responses -> graded students -> feedback reports."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from quiz_reporter.errors import Err, Ok
from quiz_reporter.quiz.bank import QuizBank, bank_workbook_bytes, parse_bank_bytes
from quiz_reporter.quiz.grading import (
    AnswerSheet,
    Selection,
    bank_from_sheet,
    select,
    sheet_from_bank,
    sheet_from_scores,
    suggest_cutoff,
)
from quiz_reporter.quiz.report import build_reports
from quiz_reporter.quiz.responses import read_form_responses
from quiz_reporter.quiz.students import (
    GradedQuiz,
    excluded_rows,
    flagged_count,
    students_from_selection,
)
from tests.helpers.quiz_forms import START, form_csv, form_xlsx, full_bank


def _grade(name: str, selection: Selection, sheet: AnswerSheet, bank: QuizBank) -> GradedQuiz:
    return GradedQuiz(
        name,
        name,
        None,
        bank,
        students_from_selection(selection, sheet),
        excluded_rows(selection),
    )


def _responses(tmp_path: Path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    read = read_form_responses(str(path))
    assert isinstance(read, Ok)
    return read.value


def test_the_class_sitting_is_kept_first_tries_count_and_late_answers_are_left_out(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())

    cutoff = suggest_cutoff(responses)
    selection = select(responses, cutoff)

    assert len(responses.rows) == 6 and responses.has_item_scores
    assert cutoff is not None and cutoff.hour == 13 and cutoff.minute == 15
    assert [row.name for row in selection.kept] == ["가나", "다라", "마바", "사아"]
    assert [row.name for row in selection.repeats] == ["다라"]
    assert [row.name for row in selection.late] == ["복습"]
    # The first try of 다라 is kept (2, 3, 3), not the second (3, 2, 3).
    assert selection.kept[1].answers[0].startswith("히스다발")


def test_a_bank_drives_grading_and_the_reports_explain_each_miss(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    bank = full_bank()
    sheet = sheet_from_bank(responses, bank)
    assert isinstance(sheet, Ok)
    selection = select(responses, suggest_cutoff(responses))

    quiz = _grade("생리 퀴즈1", selection, sheet.value, bank)

    assert (len(quiz.students), flagged_count(selection)) == (4, 1)
    assert (len(selection.late), len(selection.repeats)) == (1, 1)
    assert quiz.exam_name == "생리 퀴즈1"
    assert quiz.bank == bank
    assert len(quiz.excluded) == 2
    by_name = {student.name: student for student in quiz.students}
    assert by_name["가나"].choices == (3, 2, 3)
    assert by_name["다라"].choices == (2, 3, 3)
    assert by_name["사아"].student_id == ""  # seven digits are not an ID
    reports, summary = build_reports(quiz.bank, quiz.students)
    report = next(item for item in reports if item.student.name == "다라")
    assert (report.score, report.maximum) == (1, 3)
    assert [miss.item.number for miss in report.misses] == [1, 2]
    assert report.misses[0].trap == "방향·순서 혼동"
    assert report.misses[0].reason == "보기2을 고르면 방향·순서 혼동입니다."
    assert report.traps[0][1] == 1
    assert report.review[0].endswith("핵심 정리")
    assert summary.students == 4
    assert summary.option_counts[0] == (1, 1, 2, 0, 0)


def test_without_a_bank_the_csv_scores_give_the_answers(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    sheet = sheet_from_scores(responses)
    assert isinstance(sheet, Ok)
    bank = bank_from_sheet(responses, sheet.value)

    quiz = _grade("기본형", select(responses, suggest_cutoff(responses)), sheet.value, bank)

    reports, _ = build_reports(quiz.bank, quiz.students)
    assert sorted(report.score for report in reports) == [0, 1, 2, 3]
    # The basic report still names the right option text.
    miss = next(report for report in reports if report.score == 0).misses[0]
    assert miss.item.options[miss.item.answer - 1].startswith("동방결절")


def test_the_spreadsheet_needs_a_bank_and_its_numeric_ids_come_back(tmp_path):
    responses = _responses(tmp_path, "응답.xlsx", form_xlsx())

    assert not responses.has_item_scores
    assert isinstance(sheet_from_scores(responses), Err)
    assert responses.rows[0].student_id == "20260001"
    assert responses.rows[0].submitted_at is not None
    assert responses.rows[0].submitted_at.replace(tzinfo=None) == START
    assert isinstance(sheet_from_bank(responses, full_bank()), Ok)


def test_a_bank_that_differs_from_the_form_is_explained(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    bank = full_bank()
    changed = bank.items[0].__class__(
        1, "x", "다른 문제", bank.items[0].options, 3, "", ("",) * 5, ("",) * 5, ""
    )
    other = bank.__class__((changed, *bank.items[1:]))

    result = sheet_from_bank(responses, other)

    assert isinstance(result, Err)
    assert "1번 문항의 문제 글자가 폼과 다릅니다" in result.errors[0].context["reason"]


def test_the_bank_workbook_round_trips_and_lists_every_problem(tmp_path):
    bank = full_bank()
    assert parse_bank_bytes(bank_workbook_bytes(bank)) == Ok(bank)

    workbook = openpyxl.load_workbook(__import__("io").BytesIO(bank_workbook_bytes(bank)))
    sheet = workbook["문항표"]
    sheet["I2"] = 9  # 정답
    sheet["P3"] = "엉뚱한 유형"  # 함정유형1 of question 2
    sheet["K2"] = None  # 오답이유1 of question 1
    stream = __import__("io").BytesIO()
    workbook.save(stream)

    problems = parse_bank_bytes(stream.getvalue())

    assert isinstance(problems, Err)
    reasons = [error.context["reason"] for error in problems.errors]
    assert any(reason.startswith("1번 문항: 정답은 1~5") for reason in reasons)
    assert any("2번 문항: 함정유형1 '엉뚱한 유형'" in reason for reason in reasons)


def test_students_are_listed_by_name_then_id_and_excluded_rows_say_why(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    sheet = sheet_from_scores(responses)
    assert isinstance(sheet, Ok)
    selection = select(responses, suggest_cutoff(responses))

    students = students_from_selection(selection, sheet.value)
    excluded = excluded_rows(selection)

    assert [(s.serial, s.name) for s in students] == [
        (1, "가나"),
        (2, "다라"),
        (3, "마바"),
        (4, "사아"),
    ]
    assert [row[1:] for row in excluded] == [
        ("1234", "복습", "마감 뒤 응답(복습)"),
        ("20260002", "다라", "같은 학번의 두 번째 이후 응답"),
    ]


def test_a_report_without_form_numbers_shows_option_text_only(tmp_path):
    from quiz_reporter.quiz.report import report_html

    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    sheet = sheet_from_scores(responses)
    assert isinstance(sheet, Ok)
    bank = bank_from_sheet(responses, sheet.value)
    quiz = _grade("기본형", select(responses, suggest_cutoff(responses)), sheet.value, bank)
    reports, _ = build_reports(quiz.bank, quiz.students)
    report = next(item for item in reports if item.misses)

    numbered = report_html(report, "기본형", "2026-10-06", page_break=False)
    plain = report_html(report, "기본형", "2026-10-06", page_break=False, numbered=False)

    assert any(mark in numbered for mark in "①②③④⑤")
    miss = report.misses[0]
    chosen_text = miss.item.options[miss.chosen - 1]
    assert chosen_text in plain
    body = plain.split("틀린 문항", 1)[1].split("복습 우선순위", 1)[0]
    assert not any(mark in body for mark in "①②③④⑤")


def test_a_response_order_bank_round_trips_through_its_workbook(tmp_path):
    responses = _responses(tmp_path, "퀴즈.csv", form_csv())
    sheet = sheet_from_scores(responses)
    assert isinstance(sheet, Ok) and sheet.value.from_responses
    bank = bank_from_sheet(responses, sheet.value)
    assert bank.response_order

    again = parse_bank_bytes(bank_workbook_bytes(bank), require_feedback=False)

    assert again == Ok(bank)
    assert sheet_from_bank(responses, bank) == Ok(sheet.value)
    assert not parse_bank_bytes(bank_workbook_bytes(full_bank())).value.response_order


def test_a_damaged_workbook_is_explained_not_raised(tmp_path):
    from quiz_reporter.quiz.bank import parse_bank

    broken = tmp_path / "문항표.xlsx"
    broken.write_bytes(b"not a workbook")
    responses = tmp_path / "응답.xlsx"
    responses.write_bytes(b"not a workbook")

    assert isinstance(parse_bank(str(broken)), Err)
    assert isinstance(read_form_responses(str(responses)), Err)


def test_the_cutoff_keeps_a_response_in_its_last_second_despite_milliseconds():
    """Spreadsheets keep milliseconds; the deadline shown on screen has whole seconds."""
    from datetime import datetime

    from quiz_reporter.quiz.responses import KST, FormResponse, FormResponses

    last = datetime(2026, 10, 6, 13, 28, 14, 512000, tzinfo=KST)
    late = datetime(2026, 10, 7, 9, 0, 0, tzinfo=KST)
    rows = tuple(
        FormResponse(index, moment, f"2026000{index}", name, ("a",), (None,))
        for index, (moment, name) in enumerate(((last, "가나"), (late, "다라")), 1)
    )
    responses = FormResponses("시트", ("문항",), rows)

    on_screen = last.replace(microsecond=0)  # what the deadline field can hold

    selection = select(responses, on_screen)
    assert [row.name for row in selection.kept] == ["가나"]
    assert [row.name for row in selection.late] == ["다라"]
