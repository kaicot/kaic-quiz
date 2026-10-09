"""The 퀴즈 page: responses, cutoff, bank checks, AI requests and the run request."""

from __future__ import annotations

from quiz_reporter.errors import Ok
from quiz_reporter.quiz.bank import bank_workbook_bytes
from quiz_reporter.quiz.form_page import FormPage, FormQuestion
from quiz_reporter.quiz.prompts import bank_text
from quiz_reporter.ui.quiz_page import QuizPage, QuizRunRequest
from tests.helpers.quiz_forms import QUESTIONS, form_csv, form_xlsx, full_bank


def _page(qtbot, tmp_path, data=None, name="생리 퀴즈(응답).csv") -> QuizPage:
    page = QuizPage()
    qtbot.addWidget(page)
    path = tmp_path / name
    path.write_bytes(form_csv() if data is None else data)
    page.load_responses(str(path))
    return page


def test_responses_suggest_a_cutoff_and_describe_the_selection(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)

    assert page.name_edit.text() == "생리 퀴즈"
    assert page.cutoff_check.isChecked()
    text = page.selection_label.text()
    assert "채점할 응답 4명" in text
    assert "마감 뒤 1건 제외" in text
    assert "두 번째 응답 1건 제외" in text
    assert "8자리 숫자가 아닌 응답 1건" in text
    assert page.run_button.isEnabled()

    page.cutoff_check.setChecked(False)
    assert "채점할 응답 5명" in page.selection_label.text()


def test_a_pasted_ai_table_becomes_the_bank_and_problems_can_go_back_to_the_ai(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)

    page.paste_bank("```\n" + bank_text(full_bank()) + "```")

    assert page.bank == full_bank()
    assert "해설과 오답 이유 모두 있음" in page.bank_label.text()
    page.copy_complete_button.click()
    assert "비어 있는 칸" in page.last_copied
    assert "[프로그램이 찾은 고칠 점]" not in page.last_copied

    broken = bank_text(full_bank()).replace("\t수치 혼동\t", "\t숫자 실수\t", 1)
    page.paste_bank(broken)
    assert "목록에 없습니다" in page.problems_box.toPlainText()
    page.copy_complete_button.click()
    request = page.last_copied
    assert "[프로그램이 찾은 고칠 점]" in request
    # The AI gets its own last table back, with the problem in it.
    assert "숫자 실수" in request


def test_a_bank_file_with_blanks_is_accepted_but_said_to_give_basic_reports(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    bank = full_bank()
    item = bank.items[0]
    blank = item.__class__(
        item.number, item.unit, item.question, item.options, item.answer, "", item.reasons,
        item.traps, item.review,
    )  # fmt: skip
    path = tmp_path / "문항표.xlsx"
    path.write_bytes(bank_workbook_bytes(bank.__class__((blank, *bank.items[1:]))))

    page.load_bank(str(path))

    assert "빈 칸이 있어" in page.bank_label.text()
    assert "1번" in page.problems_box.toPlainText()
    page.copy_complete_button.click()
    assert "비어 있는 칸" in page.last_copied


def test_the_form_page_and_csv_make_a_skeleton_with_answers(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    form = FormPage("생리 퀴즈", tuple(FormQuestion(q, options) for q, options, _, _ in QUESTIONS))

    page.set_form_page(form)

    assert page.bank is not None
    assert [item.answer for item in page.bank.items] == [3, 2, 3]
    assert page.bank.items[2].options == QUESTIONS[2][1]  # all five, in form order
    assert "빈 칸이 있어" in page.bank_label.text()


def test_the_spreadsheet_without_a_bank_explains_what_is_missing(qtbot, tmp_path):
    page = _page(qtbot, tmp_path, form_xlsx(), "응답.xlsx")
    requests = []
    page.run_requested.connect(requests.append)

    page.run_button.click()

    assert requests == []
    assert "문항별 정답 여부가 없습니다" in page.problems_box.toPlainText()


def test_running_hands_the_file_cutoff_and_bank_to_the_controller(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    page.paste_bank(bank_text(full_bank()))
    requests = []
    page.run_requested.connect(requests.append)

    page.run_button.click()

    assert len(requests) == 1
    request = requests[0]
    assert isinstance(request, QuizRunRequest)
    assert request.exam_name == "생리 퀴즈"
    assert request.responses_path == tmp_path / "생리 퀴즈(응답).csv"
    assert request.cutoff is not None and (request.cutoff.hour, request.cutoff.minute) == (
        13,
        15,
    )
    assert request.bank == full_bank()


def test_running_is_blocked_without_write_access(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    assert page.run_button.isEnabled()

    page.set_write_enabled(False)

    assert not page.run_button.isEnabled()


def test_form_errors_are_shown(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    from quiz_reporter.quiz.form_page import fetch_form_page

    page.set_form_page(fetch_form_page("not a url"))

    assert "구글 폼 주소가 아닙니다" in page.status_label.text()
    assert isinstance(Ok(1), Ok)
