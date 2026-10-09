"""Trash dialog: list, restore and purge quizzes through a real QuizStore (synthetic data)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QAbstractItemView, QMessageBox

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.quiz.grading import suggest_cutoff
from quiz_reporter.quiz.responses import KST, read_form_responses
from quiz_reporter.quiz.students import GradedQuiz
from quiz_reporter.storage.quiz_info import INFO_FILENAME
from quiz_reporter.storage.quiz_store import QuizStore
from quiz_reporter.ui.trash_dialog import TrashDialog
from tests.helpers.quiz_forms import form_csv, full_bank

START = datetime(2026, 10, 6, 13, 20, 0, tzinfo=KST)


class _Clock:
    """Each save moves one second on, so the newest quiz is the last one saved."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _Writer:
    """Stands in for the PDF writer: one marker file per student."""

    def __call__(self, quiz: GradedQuiz, folder: Path) -> Result[object]:
        (folder / "개별").mkdir(parents=True)
        (folder / "전체(인쇄용).pdf").write_bytes(b"%PDF bundle")
        for student in quiz.students:
            (folder / "개별" / f"{student.serial:03d}.pdf").write_bytes(b"%PDF")
        return Ok(None)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Quiz-Reporter"
    folder.mkdir()
    return folder


@pytest.fixture
def store(root: Path) -> QuizStore:
    return QuizStore(ManagedPaths.from_root(root), _Writer(), app_version="1.0.0", clock=_Clock())


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "생리 퀴즈(응답).csv"
    path.write_bytes(form_csv())
    return path


@pytest.fixture
def dialog(qtbot, store: QuizStore) -> TrashDialog:
    window = TrashDialog(store)
    qtbot.addWidget(window)
    return window


def _save(store: QuizStore, csv: Path, name: str) -> str:
    responses = read_form_responses(str(csv))
    assert isinstance(responses, Ok)
    created = store.create(name, csv, suggest_cutoff(responses.value), full_bank())
    assert isinstance(created, Ok), created
    return created.value.folder


def _trashed(store: QuizStore, csv: Path, *names: str) -> list[str]:
    """Save quizzes in the given order, then move each of them to the trash."""
    folders = [_save(store, csv, name) for name in names]
    for folder in folders:
        assert isinstance(store.delete(folder), Ok)
    return folders


def _row_of(dialog: TrashDialog, folder: str) -> int:
    for row in range(dialog.table.rowCount()):
        if dialog.table.item(row, 3).text() == folder:
            return row
    raise AssertionError(f"{folder} is not in the table")


def _record_answers(monkeypatch, answer: QMessageBox.StandardButton) -> list[tuple]:
    calls: list[tuple] = []

    def fake_question(*args, **kwargs):
        calls.append(args)
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    return calls


def _record_warnings(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    def fake_warning(*args, **kwargs):
        calls.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(fake_warning))
    return calls


def test_rows_list_the_newest_first_with_name_date_and_students(dialog, store, csv_path):
    _trashed(store, csv_path, "생리 퀴즈", "호흡 퀴즈", "내분비 퀴즈")

    dialog.refresh()

    table = dialog.table
    assert [table.horizontalHeaderItem(c).text() for c in range(4)] == [
        "퀴즈명",
        "만든 날짜",
        "인원",
        "폴더",
    ]
    assert table.rowCount() == 3
    assert [table.item(row, 0).text() for row in range(3)] == [
        "내분비 퀴즈",
        "호흡 퀴즈",
        "생리 퀴즈",
    ]
    assert table.item(0, 1).text() == "2026-10-06 13:20"
    assert table.item(0, 2).text() == "4"
    assert table.item(0, 3).text().startswith("261006_132003_내분비 퀴즈")
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert dialog.empty_label.isHidden()
    assert not table.isHidden()


def test_restore_moves_the_selected_quiz_back_and_emits_changed(dialog, store, csv_path):
    _trashed(store, csv_path, "생리 퀴즈", "호흡 퀴즈")
    dialog.refresh()
    row = _row_of(dialog, "261006_132001_생리 퀴즈")
    dialog.select_rows(row)
    changed: list[bool] = []
    dialog.changed.connect(lambda: changed.append(True))

    dialog.restore_button.click()

    assert changed == [True]

    assert [entry.folder for entry in store.list_quizzes()] == ["261006_132001_생리 퀴즈"]
    assert [entry.folder for entry in store.list_trash()] == ["261006_132002_호흡 퀴즈"]
    assert dialog.table.rowCount() == 1
    assert not dialog.restore_button.isEnabled()


def test_purge_asks_first_and_no_leaves_the_quiz_in_the_trash(
    dialog, store, csv_path, monkeypatch, qtbot
):
    (folder,) = _trashed(store, csv_path, "생리 퀴즈")
    dialog.refresh()
    dialog.select_rows(0)
    asked = _record_answers(monkeypatch, QMessageBox.StandardButton.No)
    changed: list[bool] = []
    dialog.changed.connect(lambda: changed.append(True))

    dialog.purge_button.click()

    title, text = asked[0][1], asked[0][2]
    assert title == "영구 삭제"
    assert text == "선택한 퀴즈 1개를 영구 삭제할까요? 되돌릴 수 없습니다."
    assert asked[0][4] == QMessageBox.StandardButton.No
    assert [entry.folder for entry in store.list_trash()] == [folder]
    assert changed == []


def test_purge_yes_removes_the_quiz_and_emits_changed(dialog, store, csv_path, monkeypatch, root):
    (folder,) = _trashed(store, csv_path, "생리 퀴즈")
    dialog.refresh()
    dialog.select_rows(0)
    _record_answers(monkeypatch, QMessageBox.StandardButton.Yes)
    changed: list[bool] = []
    dialog.changed.connect(lambda: changed.append(True))

    dialog.purge_button.click()

    assert store.list_trash() == ()
    assert not (root / "Data" / "_휴지통" / folder).exists()
    assert changed == [True]
    assert dialog.table.rowCount() == 0


def test_an_unreadable_folder_shows_the_reason_and_can_still_be_purged(
    dialog, store, csv_path, monkeypatch, root
):
    _trashed(store, csv_path, "생리 퀴즈")
    broken = root / "Data" / "_휴지통" / "261001_090000_망가진 퀴즈"
    broken.mkdir()
    (broken / INFO_FILENAME).write_text("{", encoding="utf-8")
    dialog.refresh()

    row = _row_of(dialog, "261001_090000_망가진 퀴즈")
    assert dialog.table.item(row, 0).text() == "261001_090000_망가진 퀴즈"
    assert dialog.table.item(row, 1).text() == "읽을 수 없음"
    assert dialog.table.item(row, 2).text() == ""
    assert "손상" in dialog.table.item(row, 0).toolTip()

    dialog.select_rows(row)
    _record_answers(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog.purge_button.click()

    assert [entry.folder for entry in store.list_trash()] == ["261006_132001_생리 퀴즈"]
    assert not broken.exists()


def test_a_failed_restore_shows_the_reason_and_the_other_quiz_is_still_restored(
    dialog, store, csv_path, monkeypatch
):
    failing, working = _trashed(store, csv_path, "생리 퀴즈", "호흡 퀴즈")
    real_restore = store.restore

    def restore(folder: str):
        if folder == failing:
            return Err(
                (
                    ErrorInfo(
                        "QUIZ_STORE_FAILED",
                        "error.quiz_store_failed",
                        None,
                        context={"reason": "파일이 잠겨 있습니다."},
                    ),
                )
            )
        return real_restore(folder)

    monkeypatch.setattr(store, "restore", restore)
    warnings = _record_warnings(monkeypatch)
    dialog.refresh()
    dialog.select_rows(0, 1)

    dialog.restore_button.click()

    assert len(warnings) == 1
    assert f"{failing}: 파일이 잠겨 있습니다." in warnings[0][2]
    assert working not in warnings[0][2]
    assert [entry.folder for entry in store.list_quizzes()] == [working]
    assert [entry.folder for entry in store.list_trash()] == [failing]
    assert [dialog.table.item(row, 3).text() for row in range(dialog.table.rowCount())] == [failing]


def test_buttons_need_a_selection_and_write_access(dialog, store, csv_path):
    _trashed(store, csv_path, "생리 퀴즈")
    dialog.refresh()

    assert not dialog.restore_button.isEnabled()
    assert not dialog.purge_button.isEnabled()

    dialog.select_rows(0)
    assert dialog.restore_button.isEnabled()
    assert dialog.purge_button.isEnabled()

    dialog.set_write_enabled(False)
    assert not dialog.restore_button.isEnabled()
    assert not dialog.purge_button.isEnabled()

    dialog.set_write_enabled(True)
    assert dialog.restore_button.isEnabled()
    assert dialog.purge_button.isEnabled()


def test_the_action_buttons_have_their_style_names(dialog):
    assert dialog.restore_button.objectName() == "secondaryButton"
    assert dialog.purge_button.objectName() == "dangerButton"


def test_an_empty_trash_shows_the_empty_label(dialog):
    dialog.refresh()

    assert dialog.empty_label.text() == "휴지통이 비어 있습니다."
    assert not dialog.empty_label.isHidden()
    assert dialog.table.rowCount() == 0
    assert dialog.table.isHidden()
    assert not dialog.restore_button.isEnabled()
    assert not dialog.purge_button.isEnabled()


def test_the_dialog_is_titled_and_modal(dialog):
    assert dialog.windowTitle() == "휴지통"
    assert dialog.isModal()
    assert dialog.width() == 720 and dialog.height() == 420
