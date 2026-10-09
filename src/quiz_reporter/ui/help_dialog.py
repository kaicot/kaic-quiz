"""Help window: table of contents on the left, the manual on the right, a search box on top."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.ui.help_content import HELP_STYLESHEET, SECTIONS, help_html


class HelpDialog(QDialog):
    """The manual; the window keeps no state beyond the shown document and the reader's place."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("helpDialog")
        self.setWindowTitle("도움말")
        self.setMinimumSize(760, 560)
        self.resize(1020, 720)
        self.setModal(False)
        self._section_starts: list[tuple[int, int]] = []
        self._syncing = False
        self._wanted_key: str | None = None

        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("helpSearch")
        self.search_edit.setPlaceholderText("도움말에서 찾기 (예: 마감, 문항표, 휴지통)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("도움말 검색")
        self.previous_button = QPushButton("이전 찾기")
        self.previous_button.setObjectName("helpPreviousButton")
        self.search_button = QPushButton("다음 찾기")
        self.search_button.setObjectName("helpSearchButton")
        self.search_status = QLabel()
        self.search_status.setObjectName("helpSearchStatus")
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.previous_button)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.search_status)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.toc = QListWidget()
        self.toc.setObjectName("helpToc")
        self.toc.setAccessibleName("도움말 목차")
        for section in SECTIONS:
            self.toc.addItem(section.title)
            item = self.toc.item(self.toc.count() - 1)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole, section.key)
        self.browser = QTextBrowser()
        self.browser.setObjectName("helpBrowser")
        self.browser.setOpenExternalLinks(True)
        self.browser.setOpenLinks(True)
        splitter.addWidget(self.toc)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 790])
        root.addWidget(splitter, 1)
        buttons = QDialogButtonBox(self)
        close = buttons.addButton("닫기", QDialogButtonBox.ButtonRole.RejectRole)
        close.setObjectName("helpCloseButton")
        buttons.rejected.connect(self.close)
        root.addWidget(buttons)

        self.browser.document().setDefaultStyleSheet(HELP_STYLESHEET)
        self.browser.setHtml(help_html())
        self._section_starts = self._find_section_starts()

        self.toc.currentRowChanged.connect(self._toc_chosen)
        self.search_edit.textChanged.connect(lambda _: self.find_next(from_start=True))
        self.search_edit.returnPressed.connect(self.find_next)
        self.search_button.clicked.connect(lambda: self.find_next())
        self.previous_button.clicked.connect(lambda: self.find_previous())
        self.browser.verticalScrollBar().valueChanged.connect(self._sync_toc)
        self.browser.verticalScrollBar().actionTriggered.connect(lambda _: self._reader_scrolled())
        self.toc.setCurrentRow(0)

    def _find_section_starts(self) -> list[tuple[int, int]]:
        """Character positions of each section heading, in TOC order."""
        titles = {section.title: index for index, section in enumerate(SECTIONS)}
        starts: list[tuple[int, int]] = []
        block = self.browser.document().begin()
        while block.isValid():
            index = titles.get(block.text().strip())
            if index is not None and block.blockFormat().headingLevel() == 2:
                starts.append((block.position(), index))
            block = block.next()
        return sorted(starts)

    def show_section(self, key: str) -> None:
        """Select ``key`` in the table of contents and scroll the manual to it."""
        for row in range(self.toc.count()):
            item = self.toc.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self._syncing = True
                self.toc.setCurrentRow(row)
                self._syncing = False
                self._wanted_key = key
                self.browser.scrollToAnchor(key)
                return

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # The layout only has its final size once the window is shown.
        if self._wanted_key is not None:
            self.browser.scrollToAnchor(self._wanted_key)

    def _toc_chosen(self, row: int) -> None:
        if self._syncing or not 0 <= row < len(SECTIONS):
            return
        self._wanted_key = SECTIONS[row].key
        self.browser.scrollToAnchor(self._wanted_key)

    def _reader_scrolled(self) -> None:
        """The reader moved the page by hand; the table of contents follows it again."""
        self._wanted_key = None
        self._sync_toc()

    def _sync_toc(self) -> None:
        # A chosen section stays selected even when it is too close to the end to reach the top.
        if not self._section_starts or self._wanted_key is not None:
            return
        position = self.browser.cursorForPosition(
            self.browser.viewport().rect().topLeft()
        ).position()
        row = 0
        for start, index in self._section_starts:
            if start <= position + 1:
                row = index
        if row != self.toc.currentRow():
            self._syncing = True
            self.toc.setCurrentRow(row)
            self._syncing = False

    def _search(self, backward: bool, from_edge: bool) -> bool:
        text = self.search_edit.text().strip()
        if not text:
            self.search_status.setText("")
            return False
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        edge = QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
        if from_edge:
            self.browser.moveCursor(edge)
        found = self.browser.find(text, flags)
        if not found:
            self.browser.moveCursor(edge)
            found = self.browser.find(text, flags)
        self.search_status.setText("" if found else "찾는 말이 없습니다")
        return found

    def find_next(self, from_start: bool = False) -> bool:
        """Select the next match of the search text, wrapping to the top once."""
        return self._search(backward=False, from_edge=from_start)

    def find_previous(self) -> bool:
        """Select the previous match of the search text, wrapping to the bottom once."""
        return self._search(backward=True, from_edge=False)


__all__ = ["HelpDialog"]
