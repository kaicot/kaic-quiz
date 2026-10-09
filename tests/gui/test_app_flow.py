"""The whole program on a temporary folder: grade, list, rebuild, trash, import, update, help."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from quiz_reporter.errors import Err, ErrorInfo, Ok
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.infrastructure.update_check import ReleaseInfo
from quiz_reporter.quiz.prompts import bank_text
from quiz_reporter.startup import StartupState, load_update_preferences, prepare
from quiz_reporter.storage.quiz_store import QuizStore
from quiz_reporter.ui import controller as controller_module
from quiz_reporter.ui.controller import AppController
from quiz_reporter.ui.home_page import QuizTile
from quiz_reporter.ui.main_window import HOME, NEW_QUIZ, QUIZ_LIST, SETTINGS, MainWindow
from quiz_reporter.ui.quiz_pdf import write_quiz_reports
from tests.helpers.quiz_forms import form_csv, full_bank

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


class App:
    def __init__(self, qtbot, root: Path, *, release=None, read_only: str | None = None):
        root.mkdir(parents=True, exist_ok=True)
        paths = ManagedPaths.from_root(root)
        state = prepare(paths, "1.0.0")
        if read_only:
            state = StartupState(paths, read_only)
        self.paths = paths
        self.opened: list[str] = []
        self.finished: list[tuple[str, str]] = []
        self.releases = [release] if release else []
        self.window = MainWindow("1.0.0")
        qtbot.addWidget(self.window)
        self.store = QuizStore(paths, write_quiz_reports, app_version="1.0.0")
        self.controller = AppController(
            self.window,
            state,
            self.store,
            version="1.0.0",
            open_target=lambda target: self.opened.append(target) or True,
            fetch_release=self._release,
            now=lambda: NOW,
        )
        # The "done" box is modal; record it instead.
        self.controller._finished = lambda entry, headline: self.finished.append(  # type: ignore[method-assign]
            (entry.folder, headline)
        )
        self.qtbot = qtbot

    def _release(self, version: str):
        if not self.releases:
            return Err(
                (
                    ErrorInfo(
                        "UPDATE_CHECK_FAILED",
                        "error.update_check_failed",
                        None,
                        context={"reason": "오프라인"},
                    ),
                )
            )
        return Ok(self.releases[0])

    def wait(self) -> None:
        self.qtbot.waitUntil(
            lambda: not self.controller.runner.busy and not self.controller.network.busy,
            timeout=30000,
        )

    def grade(self, csv: Path, name: str = "생리 퀴즈") -> None:
        self.controller.new_quiz()
        page = self.window.quiz_page
        page.load_responses(str(csv))
        page.name_edit.setText(name)
        page.paste_bank(bank_text(full_bank()))
        assert page.run_button.isEnabled()
        page.run_button.click()
        self.wait()


@pytest.fixture
def csv(tmp_path) -> Path:
    path = tmp_path / "생리 퀴즈(응답).csv"
    path.write_bytes(form_csv())
    return path


def test_a_new_quiz_lands_on_home_and_in_the_list(qtbot, tmp_path, csv):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    assert app.window.home_page.empty_state.isVisibleTo(app.window.home_page)

    app.grade(csv)

    assert app.window.current_page() == HOME
    assert [folder for folder, _ in app.finished] == [app.store.list_quizzes()[0].folder]
    tiles = app.window.home_page.tiles
    assert len(tiles) == 1
    app.controller.refresh()  # replaced cards must not linger behind the new ones
    home = app.window.home_page
    assert [t for t in home.findChildren(QuizTile) if t.isVisibleTo(home)] == home.tiles
    tiles = home.tiles
    assert not app.window.home_page.empty_state.isVisibleTo(app.window.home_page)
    folder = app.store.list_quizzes()[0].path
    assert (folder / "리포트" / "전체(인쇄용).pdf").stat().st_size > 0
    assert len(list((folder / "리포트" / "개별").iterdir())) == 4

    tiles[0].report_button.click()
    assert app.opened == [str(folder / "리포트" / "전체(인쇄용).pdf")]

    app.window.show_page(QUIZ_LIST)
    listing = app.window.quiz_list_page
    assert listing.table.rowCount() == 1
    assert listing.table.item(0, 1).text() == "생리 퀴즈"
    assert listing.table.item(0, 2).text() == "4명"
    listing.table.selectRow(0)
    listing.folder_button.click()
    assert app.opened[-1] == str(folder)


def test_starting_a_new_quiz_gives_an_empty_page(qtbot, tmp_path, csv):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    app.grade(csv)

    app.controller.new_quiz()

    assert app.window.current_page() == NEW_QUIZ
    assert app.window.quiz_page.responses is None
    assert not app.window.quiz_page.run_button.isEnabled()
    app.window.back_button.click()
    assert app.window.current_page() == HOME


def test_rebuild_delete_and_restore_from_the_list(qtbot, tmp_path, csv, monkeypatch):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    app.grade(csv)
    entry = app.store.list_quizzes()[0]

    class _Dialog:
        def __init__(self, name, responses, current, parent):
            self.bank = full_bank()

        def exec(self):
            return 1

    monkeypatch.setattr(controller_module, "BankDialog", _Dialog)
    app.controller.rebuild(entry.folder)
    app.wait()
    assert app.finished[-1] == (entry.folder, "리포트를 다시 만들었습니다")
    rebuilt = app.store.list_quizzes()[0]
    assert rebuilt.info is not None and entry.info is not None
    assert rebuilt.info.graded_at >= entry.info.graded_at

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    app.controller.delete(entry.folder)
    assert app.store.list_quizzes() == ()
    assert app.window.quiz_list_page.table.rowCount() == 0
    assert [e.folder for e in app.store.list_trash()] == [entry.folder]
    assert app.window.home_page.empty_state.isVisibleTo(app.window.home_page)


def test_a_failed_grading_stays_on_the_page_with_the_reason(qtbot, tmp_path, csv, monkeypatch):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    monkeypatch.setattr(
        app.store,
        "create",
        lambda *a, **k: Err(
            (
                ErrorInfo(
                    "QUIZ_STORE_FAILED",
                    "error.quiz_store_failed",
                    None,
                    context={"reason": "디스크가 가득 찼습니다."},
                ),
            )
        ),
    )

    app.grade(csv)

    assert app.window.current_page() == NEW_QUIZ
    assert "디스크가 가득 찼습니다." in app.window.quiz_page.problems_box.toPlainText()
    assert app.finished == []


def test_read_only_mode_explains_why_and_blocks_writing(qtbot, tmp_path):
    app = App(qtbot, tmp_path / "Quiz-Reporter", read_only="쓸 수 없는 폴더입니다.")

    assert app.window.read_only_banner.isVisibleTo(app.window)
    assert app.window.read_only_label.text() == "쓸 수 없는 폴더입니다."
    assert not app.window.home_page.new_quiz_button.isEnabled()
    assert not app.window.settings_page.import_button.isEnabled()
    assert not app.window.quiz_page.run_button.isEnabled()


def test_a_newer_release_shows_the_banner_and_skipping_remembers_it(qtbot, tmp_path):
    release = ReleaseInfo("v1.1.0", "https://github.com/kaicot/kaic-quiz/releases/tag/v1.1.0", None)
    app = App(qtbot, tmp_path / "Quiz-Reporter", release=release)

    app.controller.check_for_update()
    app.wait()

    assert app.window.update_banner.isVisibleTo(app.window)
    assert "v1.1.0" in app.window.update_label.text()
    app.window.download_button.click()
    assert app.opened[-1] == release.page_url
    app.window.skip_button.click()
    assert not app.window.update_banner.isVisibleTo(app.window)
    prefs = load_update_preferences(app.paths)
    assert prefs.skipped_version == "v1.1.0" and prefs.last_checked is not None

    app.controller.prefs = app.controller.prefs.__class__(True, None, "v1.1.0")
    app.controller.check_for_update()
    app.wait()
    assert not app.window.update_banner.isVisibleTo(app.window)


def test_checking_by_hand_reports_the_result_even_offline(qtbot, tmp_path):
    app = App(qtbot, tmp_path / "Quiz-Reporter")

    app.window.settings_page.check_now_button.click()
    app.wait()

    assert "오프라인" in app.window.settings_page.update_result.text()
    app.releases = [
        ReleaseInfo("v1.0.0", "https://github.com/kaicot/kaic-quiz/releases/latest", None)
    ]
    app.window.settings_page.check_now_button.click()
    app.wait()
    assert "최신" in app.window.settings_page.update_result.text()


def test_turning_the_update_check_off_is_saved(qtbot, tmp_path):
    app = App(qtbot, tmp_path / "Quiz-Reporter")

    app.window.settings_page.update_check.setChecked(False)

    assert load_update_preferences(app.paths).enabled is False
    saved = json.loads(app.paths.update_prefs_path.read_text(encoding="utf-8"))
    assert saved["enabled"] is False


def test_importing_a_previous_install_from_settings(qtbot, tmp_path, csv):
    old = App(qtbot, tmp_path / "old")
    old.grade(csv, "예전 퀴즈")
    app = App(qtbot, tmp_path / "new")

    app.controller.import_from(str(tmp_path / "old"))
    app.wait()

    result = app.window.settings_page.import_result.text()
    assert "퀴즈 1개를 가져왔습니다." in result
    assert [entry.info.name for entry in app.store.list_quizzes() if entry.info] == ["예전 퀴즈"]
    assert len(app.window.home_page.tiles) == 1


def test_help_opens_at_the_current_page(qtbot, tmp_path):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    app.window.show_page(SETTINGS)

    app.controller.show_help()

    dialog = app.controller.help_dialog
    assert dialog is not None and dialog.isVisible()
    qtbot.addWidget(dialog)


def test_startup_marks_the_data_folder_and_refuses_newer_data(tmp_path):
    root = tmp_path / "Quiz-Reporter"
    root.mkdir()
    paths = ManagedPaths.from_root(root)

    state = prepare(paths, "1.0.0")

    assert state.writable
    marker = json.loads((root / "Data" / "FORMAT.json").read_text(encoding="utf-8"))
    assert marker["data_format"] == 1
    (root / "Data" / "FORMAT.json").write_text(
        json.dumps({"data_format": 2, "written_by": "2.0.0"}), encoding="utf-8"
    )
    newer = prepare(paths, "1.0.0")
    assert not newer.writable
    assert "더 새 버전 퀴즈 리포터 2.0.0" in (newer.read_only_reason or "")


def test_a_form_page_that_arrives_after_starting_over_is_ignored(qtbot, tmp_path):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    app.controller.new_quiz()
    first = app.window.quiz_page
    gate: list[object] = []
    app.controller._fetch_form = lambda address: (gate.append(address), "late result")[1]
    seen: list[object] = []
    first.set_form_page = seen.append  # type: ignore[method-assign]

    first.form_fetch_requested.emit("https://docs.google.com/forms/d/e/x/viewform")
    app.controller.new_quiz()  # the user starts over before the answer comes back
    app.wait()

    assert gate and seen == []
    assert app.window.quiz_page is not first


def test_import_waits_for_a_running_job(qtbot, tmp_path, monkeypatch):
    app = App(qtbot, tmp_path / "Quiz-Reporter")
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    picked: list[str] = []
    monkeypatch.setattr(
        controller_module.QFileDialog,
        "getExistingDirectory",
        lambda *a, **k: picked.append("asked") or str(tmp_path),
    )
    release = []
    app.controller.runner.run(lambda: release.append(1), lambda _: None)
    assert not app.window.settings_page.import_button.isEnabled()

    app.controller.choose_import()

    assert warned and "끝난 뒤" in warned[0]
    assert picked == []
    app.wait()
    assert app.window.settings_page.import_button.isEnabled()


def test_the_form_address_builds_a_skeleton_through_the_controller(qtbot, tmp_path, csv):
    """The controller hands the fetched form (an Ok result) to the page, which uses it."""
    from quiz_reporter.quiz.form_page import FormPage, FormQuestion
    from tests.helpers.quiz_forms import QUESTIONS

    app = App(qtbot, tmp_path / "Quiz-Reporter")
    form = FormPage("생리 퀴즈", tuple(FormQuestion(q, options) for q, options, _, _ in QUESTIONS))
    app.controller._fetch_form = lambda address: Ok(form)
    app.controller.new_quiz()
    page = app.window.quiz_page
    page.load_responses(str(csv))
    page.form_edit.setText("https://docs.google.com/forms/d/e/abc/viewform?usp=dialog")

    page.form_button.click()
    app.wait()

    assert page.bank is not None and len(page.bank.items) == 3
    assert [item.answer for item in page.bank.items] == [3, 2, 3]
    assert "틀을 만들었습니다" in page.form_status.text()
    assert page.form_status.isVisibleTo(page)
