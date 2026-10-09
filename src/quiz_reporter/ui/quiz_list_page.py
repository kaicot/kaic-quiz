"""퀴즈 목록: every saved quiz in a table, with what can be done to the selected one."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, SignalInstance
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.storage.quiz_store import QuizEntry
from quiz_reporter.ui.home_page import when_text
from quiz_reporter.ui.theme import TOKENS

COLUMNS = ("날짜", "퀴즈명", "인원", "평균", "리포트")


class QuizListPage(QWidget):
    report_requested = Signal(str)
    folder_requested = Signal(str)
    rebuild_requested = Signal(str)
    delete_requested = Signal(str)
    trash_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("quizListPage")
        self._entries: tuple[QuizEntry, ...] = ()
        self._write_enabled = True
        self._busy = False
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(14)
        title = QLabel("퀴즈 목록", self)
        title.setObjectName("pageTitle")
        root.addWidget(title)
        hint = QLabel("퀴즈를 고르고 아래 버튼을 누르세요. 두 번 누르면 리포트가 열립니다.", self)
        hint.setProperty("role", "hint")
        root.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setObjectName("quizTable")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(64)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._refresh)
        self.table.cellDoubleClicked.connect(lambda row, _column: self._open_report(row))
        root.addWidget(self.table, 1)
        self.empty_label = QLabel("저장된 퀴즈가 없습니다. 홈에서 '새 퀴즈 채점'을 누르세요.", self)
        self.empty_label.setProperty("role", "hint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label, 1)
        self.problem_label = QLabel(self)
        self.problem_label.setProperty("role", "warning")
        self.problem_label.setWordWrap(True)
        root.addWidget(self.problem_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.report_button = QPushButton("리포트 열기", self)
        self.folder_button = QPushButton("폴더 열기", self)
        self.rebuild_button = QPushButton("문항표 바꿔 다시 만들기", self)
        self.delete_button = QPushButton("삭제", self)
        self.delete_button.setObjectName("dangerButton")
        self.trash_button = QPushButton("휴지통 보기", self)
        for button in (self.report_button, self.folder_button, self.rebuild_button):
            actions.addWidget(button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.trash_button)
        root.addLayout(actions)
        self.report_button.clicked.connect(lambda: self._emit(self.report_requested))
        self.folder_button.clicked.connect(lambda: self._emit(self.folder_requested))
        self.rebuild_button.clicked.connect(lambda: self._emit(self.rebuild_requested))
        self.delete_button.clicked.connect(lambda: self._emit(self.delete_requested))
        self.trash_button.clicked.connect(self.trash_requested)
        self.set_entries(())

    @property
    def entries(self) -> tuple[QuizEntry, ...]:
        return self._entries

    def set_entries(self, entries: tuple[QuizEntry, ...]) -> None:
        selected = self.selected()
        self._entries = entries
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            info = entry.info
            if info is None:
                values = ("", entry.folder, "", "", "읽을 수 없음")
            else:
                summary = info.summary
                values = (
                    when_text(info),
                    info.name,
                    f"{summary.students}명",
                    f"{summary.average:.1f} / {summary.maximum}",
                    "상세" if summary.detailed else "기본",
                )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if info is None:
                    item.setForeground(QColor(TOKENS.disabled))
                    item.setToolTip(entry.problem)
                else:
                    item.setToolTip(entry.folder)
                self.table.setItem(row, column, item)
        self.table.setVisible(bool(entries))
        self.empty_label.setVisible(not entries)
        if selected is None or not self.select_folder(selected.folder):
            self.table.setCurrentCell(-1, -1)
        self._refresh()

    def select_folder(self, folder: str) -> bool:
        for row, entry in enumerate(self._entries):
            if entry.folder == folder:
                self.table.selectRow(row)
                return True
        return False

    def selected(self) -> QuizEntry | None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        return self._entries[min(rows)] if rows else None

    def set_write_enabled(self, enabled: bool) -> None:
        self._write_enabled = bool(enabled)
        self._refresh()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._refresh()

    def _emit(self, signal: SignalInstance) -> None:
        entry = self.selected()
        if entry is not None:
            signal.emit(entry.folder)

    def _open_report(self, row: int) -> None:
        if 0 <= row < len(self._entries) and self._entries[row].info is not None:
            self.report_requested.emit(self._entries[row].folder)

    def _refresh(self) -> None:
        entry = self.selected()
        readable = entry is not None and entry.info is not None
        writing = self._write_enabled and not self._busy
        self.report_button.setEnabled(readable)
        self.folder_button.setEnabled(entry is not None)
        self.rebuild_button.setEnabled(readable and writing)
        self.delete_button.setEnabled(entry is not None and writing)
        self.trash_button.setEnabled(not self._busy)
        problem = entry.problem if entry is not None and entry.info is None else ""
        self.problem_label.setText(f"이 폴더를 읽을 수 없습니다: {problem}" if problem else "")
        self.problem_label.setVisible(bool(problem))


__all__ = ["COLUMNS", "QuizListPage"]
