"""Table headers and rows leave room for Korean text under the app theme (no clipped glyphs)."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QTableWidget

from quiz_reporter.ui.quiz_list_page import QuizListPage
from quiz_reporter.ui.theme import apply_theme


@pytest.fixture
def themed(qapp):
    apply_theme(qapp)
    yield qapp
    qapp.setStyleSheet("")


def _check(table: QTableWidget) -> None:
    table.setRowCount(1)
    table.show()
    QApplication.processEvents()
    header = table.horizontalHeader()
    text = QFontMetrics(header.font()).height()
    # The space left inside the header (after its own border and padding) must fit the
    # label plus the section padding; this was 23 px for 28 px needed when labels clipped.
    assert header.viewport().height() >= text + 14, (header.viewport().height(), text)
    assert table.rowHeight(0) >= QFontMetrics(table.font()).height() + 12
    for column in range(table.columnCount()):
        label = table.horizontalHeaderItem(column).text()
        assert header.sectionSize(column) >= QFontMetrics(header.font()).horizontalAdvance(label)


def test_quiz_list_table_has_room(themed, qtbot):
    page = QuizListPage()
    qtbot.addWidget(page)
    _check(page.table)


def test_trash_table_has_room(themed, qtbot, tmp_path):
    from quiz_reporter.infrastructure.paths import ManagedPaths
    from quiz_reporter.storage.quiz_store import QuizStore
    from quiz_reporter.ui.trash_dialog import TrashDialog

    store = QuizStore(ManagedPaths.from_root(tmp_path), lambda quiz, folder: None)  # type: ignore[arg-type,return-value]
    dialog = TrashDialog(store)
    qtbot.addWidget(dialog)
    _check(dialog.table)
