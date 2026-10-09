"""The help window and its manual: every section reachable, search works, labels match the UI."""

from __future__ import annotations

import html
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractSlider, QPushButton

from quiz_reporter.quiz.bank import BANK_HEADERS, TRAP_NAMES
from quiz_reporter.ui import help_content
from quiz_reporter.ui.help_content import PAGE_SECTIONS, SECTIONS, help_html
from quiz_reporter.ui.help_dialog import HelpDialog
from quiz_reporter.ui.quiz_page import QuizPage

_BUTTON = re.compile(r"<span class='btn'>\[(.*?)\]</span>")


@pytest.fixture
def dialog(qtbot) -> HelpDialog:
    window = HelpDialog()
    qtbot.addWidget(window)
    return window


def _current_key(window: HelpDialog) -> str:
    item = window.toc.currentItem()
    assert item is not None
    return str(item.data(Qt.ItemDataRole.UserRole))


def _section_html(key: str) -> str:
    """The HTML of one section: from its anchor up to the next section's anchor."""
    text = help_html()
    start = text.index(f"<a name='{key}'>")
    keys = [section.key for section in SECTIONS]
    position = keys.index(key)
    end = text.index(f"<a name='{keys[position + 1]}'>") if position + 1 < len(keys) else len(text)
    return text[start:end]


def test_window_basics(qtbot, dialog: HelpDialog) -> None:
    dialog.show()

    assert dialog.windowTitle() == "도움말"
    assert not dialog.isModal()
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()


def test_every_section_has_an_anchor_and_a_toc_entry(dialog: HelpDialog) -> None:
    text = help_html()

    assert dialog.toc.count() == len(SECTIONS)
    assert [index for _, index in dialog._section_starts] == list(range(len(SECTIONS)))
    for row, section in enumerate(SECTIONS):
        assert f"<a name='{section.key}'>{section.title}</a>" in text
        item = dialog.toc.item(row)
        assert item is not None
        assert item.text() == section.title
        assert item.data(Qt.ItemDataRole.UserRole) == section.key
    assert len({section.key for section in SECTIONS}) == len(SECTIONS)


def test_in_page_links_point_at_existing_sections() -> None:
    keys = {section.key for section in SECTIONS}
    targets = set(re.findall(r"href='#([^']+)'", help_html()))

    assert targets
    assert targets <= keys


def test_page_sections_map_to_existing_sections() -> None:
    keys = {section.key for section in SECTIONS}

    assert set(PAGE_SECTIONS) == {"home", "new_quiz", "quiz_list", "settings"}
    assert set(PAGE_SECTIONS.values()) <= keys


def test_show_section_selects_and_scrolls_to_it(dialog: HelpDialog) -> None:
    dialog.show()
    bar = dialog.browser.verticalScrollBar()
    assert bar.maximum() > 0

    positions = []
    for section in SECTIONS[:-1]:
        dialog.show_section(section.key)
        assert _current_key(dialog) == section.key
        positions.append(bar.value())

    assert positions == sorted(positions)
    assert positions[-1] > positions[0]

    dialog.show_section("trouble")
    assert _current_key(dialog) == "trouble"
    assert bar.value() >= positions[-1]

    dialog.show_section("no_such_section")
    assert _current_key(dialog) == "trouble"


def test_toc_click_scrolls_and_scrolling_moves_the_toc(dialog: HelpDialog) -> None:
    dialog.show()
    bar = dialog.browser.verticalScrollBar()

    dialog.toc.setCurrentRow(3)
    assert bar.value() > 0

    bar.triggerAction(QAbstractSlider.SliderAction.SliderToMinimum)
    assert dialog.toc.currentRow() == 0

    bar.triggerAction(QAbstractSlider.SliderAction.SliderToMaximum)
    assert dialog.toc.currentRow() > 3


def test_search_selects_a_match_and_says_when_there_is_none(dialog: HelpDialog) -> None:
    dialog.search_edit.setText("문항표")

    assert dialog.browser.textCursor().selectedText() == "문항표"
    first = dialog.browser.textCursor().position()
    assert dialog.find_next()
    assert dialog.browser.textCursor().position() != first
    assert dialog.search_status.text() == ""

    dialog.search_edit.setText("없는말없는말")
    assert dialog.search_status.text() == "찾는 말이 없습니다"
    assert not dialog.find_next()
    assert not dialog.find_previous()


def test_find_next_and_previous_walk_the_matches_and_wrap(dialog: HelpDialog) -> None:
    word = "휴지통"
    count = dialog.browser.document().toPlainText().count(word)
    assert count > 2
    dialog.search_edit.setText(word)
    positions = [dialog.browser.textCursor().position()]
    for _ in range(count - 1):
        assert dialog.find_next()
        positions.append(dialog.browser.textCursor().position())

    assert positions == sorted(set(positions))
    assert len(positions) == count

    # One more step wraps to the first match.
    assert dialog.find_next()
    assert dialog.browser.textCursor().position() == positions[0]

    # Going back from the first match wraps to the last one, then walks backwards.
    assert dialog.find_previous()
    assert dialog.browser.textCursor().position() == positions[-1]
    assert dialog.find_previous()
    assert dialog.browser.textCursor().position() == positions[-2]


def test_buttons_quoted_in_the_manual_exist_on_the_quiz_page(qtbot) -> None:
    page = QuizPage()
    qtbot.addWidget(page)
    labels = {button.text() for button in page.findChildren(QPushButton)}

    for key in ("new_quiz", "question_bank"):
        quoted = [html.unescape(label) for label in _BUTTON.findall(_section_html(key))]
        assert quoted, key
        assert set(quoted) <= labels, (key, set(quoted) - labels)
    # The prompts the manual explains are the page's own buttons.
    quoted_all = {
        html.unescape(label)
        for key in ("new_quiz", "question_bank")
        for label in _BUTTON.findall(_section_html(key))
    }
    assert {"폼 주소로 정답/해설 만들기", "해설 만들기 프롬프트 복사"} <= quoted_all


def test_the_bank_columns_and_trap_types_come_from_the_bank_module() -> None:
    section = html.unescape(_section_html("question_bank"))

    assert ", ".join(BANK_HEADERS) in section
    for name in TRAP_NAMES:
        assert name in section


def test_every_section_has_text_and_example_ids_are_fake() -> None:
    for section in SECTIONS:
        assert len(re.sub(r"<[^>]+>", "", _section_html(section.key))) > 120, section.key
    for number in re.findall(r"\d{8}", help_html()):
        assert number.startswith("2026000"), number


def test_the_stylesheet_has_the_fixed_palette_and_font() -> None:
    sheet = help_content.HELP_STYLESHEET

    assert "Malgun Gothic" in sheet
    for color in ("#1F2933", "#0F766E", "#E6F4F1", "#FFF7E6", "#8A4B00", "#D9E2EC"):
        assert color in sheet


def test_the_qt_lgpl_notice_is_shown_while_running(qtbot):
    from quiz_reporter.ui.help_content import help_html
    from quiz_reporter.ui.main_window import QT_NOTICE, MainWindow

    window = MainWindow("1.0.0")
    qtbot.addWidget(window)

    assert "LGPL" in window.credit_label.toolTip()
    assert window.credit_label.toolTip() == QT_NOTICE
    assert "THIRD_PARTY_NOTICES.txt" in help_html()


def test_the_last_section_is_the_program_information():
    import quiz_reporter
    from quiz_reporter.ui.help_content import SECTIONS, help_html

    assert SECTIONS[-1].key == "about"
    html = help_html()
    about = html.split("name='about'", 1)[1]
    for expected in (
        quiz_reporter.__version__,
        "조승현",
        "kaic21@gmail.com",
        "PolyForm Noncommercial",
        "LGPL",
        "THIRD_PARTY_NOTICES.txt",
        "github.com/kaicot/kaic-quiz",
    ):
        assert expected in about, expected
