"""Trash dialog: restore or permanently delete quizzes moved out of ``Data\\``."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.errors import Err, Result
from quiz_reporter.storage.quiz_store import QuizEntry, QuizStore

TRASH_COLUMNS = ("퀴즈명", "만든 날짜", "인원", "폴더")
HINT_TEXT = (
    "삭제한 퀴즈입니다. 복원하면 채점 이력으로 돌아갑니다. 영구 삭제하면 되돌릴 수 없습니다."
)
EMPTY_TEXT = "휴지통이 비어 있습니다."
UNREADABLE_DATE = "읽을 수 없음"


def _reason(failed: Err) -> str:
    return str(failed.errors[0].context["reason"])


class TrashDialog(QDialog):
    """Lists trashed quizzes; restores or purges the selected ones through the store."""

    # Emitted after a restore or purge that changed something, so the main window reloads.
    changed = Signal()

    def __init__(self, store: QuizStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._entries: tuple[QuizEntry, ...] = ()
        self._write_enabled = True
        self.setObjectName("trashDialog")
        self.setWindowTitle("휴지통")
        self.setModal(True)
        self.resize(720, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        hint = QLabel(HINT_TEXT)
        hint.setObjectName("trashHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.empty_label = QLabel(EMPTY_TEXT)
        self.empty_label.setObjectName("trashEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label, 1)

        self.table = QTableWidget(0, len(TRASH_COLUMNS))
        self.table.setObjectName("trashTable")
        self.table.setHorizontalHeaderLabels(list(TRASH_COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(64)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.restore_button = QPushButton("복원")
        self.restore_button.setObjectName("secondaryButton")
        self.purge_button = QPushButton("영구 삭제")
        self.purge_button.setObjectName("dangerButton")
        self.close_button = QPushButton("닫기")
        actions.addWidget(self.restore_button)
        actions.addStretch(1)
        actions.addWidget(self.purge_button)
        actions.addSpacing(12)
        actions.addWidget(self.close_button)
        root.addLayout(actions)

        self.restore_button.clicked.connect(self._restore)
        self.purge_button.clicked.connect(self._purge)
        self.close_button.clicked.connect(self.reject)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.refresh()

    def refresh(self) -> None:
        """Reload the trash from the store; this clears the selection."""
        self._entries = self._store.list_trash()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            self._fill_row(row, entry)
        # No current cell either, or the first one looks selected while nothing is.
        self.table.setCurrentCell(-1, -1)
        has_entries = bool(self._entries)
        self.empty_label.setVisible(not has_entries)
        self.table.setVisible(has_entries)
        self._update_buttons()

    def set_write_enabled(self, enabled: bool) -> None:
        """Read-only mode keeps the list but disables restore and purge."""
        self._write_enabled = bool(enabled)
        self._update_buttons()

    def select_rows(self, *rows: int) -> None:
        """Select whole rows, as a click or Ctrl+click would."""
        self.table.clearSelection()
        mode = self.table.selectionMode()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for row in rows:
            self.table.selectRow(row)
        self.table.setSelectionMode(mode)

    def _fill_row(self, row: int, entry: QuizEntry) -> None:
        info = entry.info
        if info is None:
            values = (entry.folder, UNREADABLE_DATE, "", entry.folder)
        else:
            values = (
                info.name,
                info.created_at.strftime("%Y-%m-%d %H:%M"),
                str(info.summary.students),
                entry.folder,
            )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            # The reason a folder can't be read shows on hover over its row.
            item.setToolTip(entry.problem)
            if column == 2:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, column, item)

    def _selected_entries(self) -> tuple[QuizEntry, ...]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return tuple(self._entries[row] for row in rows)

    def _update_buttons(self) -> None:
        enabled = self._write_enabled and bool(self.table.selectedIndexes())
        self.restore_button.setEnabled(enabled)
        self.purge_button.setEnabled(enabled)

    def _restore(self) -> None:
        entries = self._selected_entries()
        if not self._write_enabled or not entries:
            return
        self._run("복원", self._store.restore, entries)

    def _purge(self) -> None:
        entries = self._selected_entries()
        if not self._write_enabled or not entries:
            return
        answer = QMessageBox.question(
            self,
            "영구 삭제",
            f"선택한 퀴즈 {len(entries)}개를 영구 삭제할까요? 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run("영구 삭제", self._store.purge, entries)

    def _run[T](
        self,
        verb: str,
        action: Callable[[str], Result[T]],
        entries: tuple[QuizEntry, ...],
    ) -> None:
        """Apply the action to every selected folder; one failure does not stop the rest."""
        failures: list[str] = []
        changed = False
        for entry in entries:
            result = action(entry.folder)
            if isinstance(result, Err):
                failures.append(f"{entry.folder}: {_reason(result)}")
            else:
                changed = True
        if changed:
            self.changed.emit()
        if failures:
            QMessageBox.warning(
                self,
                f"{verb} 실패",
                f"다음 퀴즈를 {verb}하지 못했습니다.\n\n" + "\n".join(failures),
            )
        self.refresh()


__all__ = ["TRASH_COLUMNS", "TrashDialog"]
