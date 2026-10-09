"""The student page: one A4 sheet for a usual result, the quiz day on top, color and grey looks."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from quiz_reporter.quiz.bank import QuizBank, QuizItem
from quiz_reporter.quiz.grading import Selection, quiz_day, sittings
from quiz_reporter.quiz.report import COLOR, Student, build_reports, report_html, reports_html
from quiz_reporter.quiz.responses import KST, FormResponse, FormResponses
from quiz_reporter.ui.quiz_pdf import _print, single_names

TRAPS = ("개념 혼동", "용어 혼동", "방향·순서 혼동", "수치 혼동", "반대 개념")


def _bank(count: int = 10) -> QuizBank:
    """Synthetic questions about as long as a real class quiz."""
    items = []
    for number in range(1, count + 1):
        answer = number % 5 + 1
        options = tuple(
            f"가상 개념 {number}-{index}에 대한 설명으로, 보기 글자는 이 정도 길이입니다"
            for index in range(1, 6)
        )
        reasons = tuple(
            ""
            if index == answer
            else f"보기 {index}은 가상 개념 {number}의 다른 면을 설명합니다. 학생이 자주 헷갈리는"
            " 지점이라 한 줄 반 정도 되는 이유를 씁니다."
            for index in range(1, 6)
        )
        traps = tuple("" if index == answer else TRAPS[index - 1] for index in range(1, 6))
        items.append(
            QuizItem(
                number,
                f"가상 단원 {number}",
                f"가상 개념 {number}에 대한 설명으로 옳은 것은? 문제 글도 실제 퀴즈처럼 한 줄을 넘깁니다.",
                options,
                answer,
                f"{number}번 해설",
                reasons,
                traps,
                f"가상 개념 {number}의 핵심 정리",
            )
        )
    return QuizBank(tuple(items))


def _students(bank: QuizBank, wrong: int) -> tuple[Student, ...]:
    """The first student misses ``wrong`` questions; classmates miss a few each."""
    answers = [item.answer for item in bank.items]
    first = tuple(
        (answer % 5) + 1 if index < wrong else answer
        for index, answer in enumerate(answers)
        if answer
    )
    others = tuple(
        Student(
            serial,
            f"2026000{serial}",
            name,
            tuple(
                (answer % 5) + 1 if (index + serial) % 3 == 0 else answer
                for index, answer in enumerate(answers)
                if answer
            ),
        )
        for serial, name in ((2, "다라"), (3, "마바"), (4, "사아"))
    )
    return (Student(1, "20260001", "가나", first), *others)


def _pages(path: Path) -> int:
    found = re.findall(rb"/Count\s+(\d+)", path.read_bytes())
    assert found
    return max(int(value) for value in found)


def test_five_misses_out_of_ten_fit_on_one_page_in_both_looks(qapp, tmp_path):
    bank = _bank()
    reports, _ = build_reports(bank, _students(bank, wrong=5))
    report = reports[0]
    assert len(report.misses) == 5

    color, grey = tmp_path / "color.pdf", tmp_path / "grey.pdf"
    _print(reports_html((report,), "가상 퀴즈", "2026-10-06"), color)
    _print(reports_html((report,), "가상 퀴즈", "2026-10-06", mono=True), grey)

    assert _pages(color) == 1
    assert _pages(grey) == 1


def test_the_header_shows_the_quiz_day_and_the_strip_every_question(qapp):
    bank = _bank(20)
    reports, summary = build_reports(bank, _students(bank, wrong=3))
    report = reports[0]

    html = report_html(report, "가상 퀴즈", "2026-10-06", page_break=False)

    assert "2026-10-06 응시" in html
    assert "단원별 정답률" not in html
    assert "문항별 결과" in html
    assert html.count("반 정답률") == 2  # 20 questions: two rows of 15 and 5
    assert [mark.correct for mark in report.marks[:4]] == [False, False, False, True]
    assert report.marks[0].class_rate == summary.correct_rate[0]
    assert "가 맞힘)" in html
    no_day = report_html(report, "가상 퀴즈", "", page_break=False)
    assert "응시" not in no_day and "학생별 피드백 리포트" in no_day


def test_the_grey_look_uses_no_theme_color(qapp):
    bank = _bank()
    reports, _ = build_reports(bank, _students(bank, wrong=5))

    color = reports_html(reports, "가상 퀴즈", "2026-10-06")
    grey = reports_html(reports, "가상 퀴즈", "2026-10-06", mono=True)

    for tint in (COLOR.brand, COLOR.red, COLOR.green, COLOR.orange, COLOR.red_soft):
        assert tint in color
        assert tint not in grey, tint
    assert "✕" in grey and "[개념 혼동" in grey


def test_review_starts_with_what_most_of_the_class_got_right(qapp):
    bank = _bank()
    reports, _ = build_reports(bank, _students(bank, wrong=5))
    report = reports[0]
    rates = {miss.item.review: miss.class_rate for miss in report.misses}

    assert [rates[point] for point in report.review] == sorted(
        (rates[point] for point in report.review), reverse=True
    )


def test_student_files_are_named_name_id_day_quiz(qapp):
    bank = _bank(3)
    students = (
        Student(1, "20260001", "가나", (1, 1, 1)),
        Student(2, "", "다라", (1, 1, 1), typed_id="2026"),
        Student(3, "", "다라", (2, 2, 2), typed_id="20"),
    )
    reports, _ = build_reports(bank, students)

    names = single_names(reports, "생리: 퀴즈", "2026-10-06")

    assert names == (
        "가나_20260001_261006_생리_ 퀴즈.pdf",
        "다라_학번확인필요_261006_생리_ 퀴즈.pdf",
        "다라_학번확인필요_261006_생리_ 퀴즈 (2).pdf",
    )
    assert single_names(reports[:1], "퀴즈", "") == ("가나_20260001_퀴즈.pdf",)


def _response(row: int, moment: datetime) -> FormResponse:
    return FormResponse(row, moment, f"2026000{row}", "가나", (), ())


def test_the_quiz_day_is_the_day_most_answers_came_in():
    start = datetime(2026, 10, 6, 13, 11, tzinfo=KST)
    rows = tuple(_response(index, start + timedelta(minutes=index)) for index in range(1, 6))
    late = _response(9, datetime(2026, 10, 7, 21, 0, tzinfo=KST))
    selection = Selection((*rows, late), (), (), None)

    assert str(quiz_day(selection)) == "2026-10-06"
    assert quiz_day(Selection((), (), (), None)) is None


def test_sittings_split_on_gaps_longer_than_half_an_hour():
    start = datetime(2026, 10, 6, 13, 11, tzinfo=KST)
    moments = [start, start + timedelta(minutes=9), start + timedelta(hours=8)]
    responses = FormResponses(
        "응답.csv", (), tuple(_response(index, moment) for index, moment in enumerate(moments, 1))
    )

    found = sittings(responses)

    assert [(sitting.start, sitting.end, sitting.answers) for sitting in found] == [
        (moments[0], moments[1], 2),
        (moments[2], moments[2], 1),
    ]
