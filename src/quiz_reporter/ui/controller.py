"""Connects the pages to the quiz store; slow work runs off the GUI thread."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from quiz_reporter.errors import Err, Ok, Result
from quiz_reporter.infrastructure.update_check import (
    RELEASES_PAGE_URL,
    ReleaseInfo,
    fetch_latest_release,
    is_newer,
    now_text,
)
from quiz_reporter.quiz.bank import problems_text
from quiz_reporter.quiz.form_page import fetch_form_page
from quiz_reporter.startup import StartupState, load_update_preferences, save_update_preferences
from quiz_reporter.storage.data_import import ImportProgress, ImportSummary, import_previous_install
from quiz_reporter.storage.quiz_info import REPORT_DIRNAME
from quiz_reporter.storage.quiz_store import QuizEntry, QuizStore
from quiz_reporter.ui.bank_dialog import BankDialog
from quiz_reporter.ui.help_content import PAGE_SECTIONS
from quiz_reporter.ui.help_dialog import HelpDialog
from quiz_reporter.ui.main_window import HOME, NEW_QUIZ, QUIZ_LIST, MainWindow
from quiz_reporter.ui.quiz_page import QuizPage, QuizRunRequest
from quiz_reporter.ui.trash_dialog import TrashDialog
from quiz_reporter.ui.workers import TaskRunner

BUNDLE_NAME = "전체(인쇄용).pdf"
SINGLES_DIRNAME = "개별"


def open_with_system(target: str) -> bool:
    """Open a file, a folder or a web page the way Explorer would."""
    url = QUrl(target) if target.startswith("https://") else QUrl.fromLocalFile(target)
    return QDesktopServices.openUrl(url)


def reason_of(result: Err) -> str:
    return problems_text(result.errors).removeprefix("- ")


class _ImportRelay(QObject):
    """Carries import progress from the worker thread to the GUI thread."""

    progress = Signal(int, int)


class AppController(QObject):
    def __init__(
        self,
        window: MainWindow,
        state: StartupState,
        store: QuizStore,
        *,
        version: str,
        open_target: Callable[[str], bool] = open_with_system,
        fetch_release: Callable[[str], Result[ReleaseInfo]] = fetch_latest_release,
        fetch_form: Callable[[str], object] = fetch_form_page,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(window)
        self.window = window
        self.state = state
        self.store = store
        self.version = version
        self._open = open_target
        self._fetch_release = fetch_release
        self._fetch_form = fetch_form
        self._now = now
        self.runner = TaskRunner(self)
        self.network = TaskRunner(self)
        self.prefs = load_update_preferences(state.paths)
        self.release: ReleaseInfo | None = None
        self.help_dialog: HelpDialog | None = None
        self._import_relay = _ImportRelay(self)
        self._import_relay.progress.connect(window.settings_page.set_import_progress)

        writable = state.writable
        notices = [text for text in (state.read_only_reason, state.notice) if text]
        window.set_read_only("\n".join(notices) or None)
        window.set_data_path(str(state.paths.data_dir))
        window.settings_page.set_data_path(str(state.paths.data_dir))
        window.settings_page.set_update_enabled(self.prefs.enabled)
        for page in (window.home_page, window.quiz_list_page, window.settings_page):
            page.set_write_enabled(writable)
        self._wire_quiz_page(window.quiz_page)

        home, listing, settings = window.home_page, window.quiz_list_page, window.settings_page
        home.new_quiz_requested.connect(self.new_quiz)
        home.report_requested.connect(self.open_report)
        home.singles_requested.connect(self.open_singles)
        home.list_requested.connect(lambda: window.show_page(QUIZ_LIST))
        home.import_requested.connect(self.choose_import)
        listing.report_requested.connect(self.open_report)
        listing.singles_requested.connect(self.open_singles)
        listing.folder_requested.connect(self.open_folder)
        listing.rebuild_requested.connect(self.rebuild)
        listing.delete_requested.connect(self.delete)
        listing.trash_requested.connect(self.show_trash)
        settings.open_data_requested.connect(self.open_data_folder)
        settings.update_toggled.connect(self.set_update_enabled)
        settings.check_now_requested.connect(lambda: self.check_for_update(manual=True))
        settings.import_requested.connect(self.choose_import)
        window.help_requested.connect(self.show_help)
        window.download_requested.connect(self.open_download_page)
        window.skip_requested.connect(self.skip_release)
        window.page_changed.connect(
            lambda key: self.refresh() if key in (HOME, QUIZ_LIST) else None
        )
        self.runner.busy_changed.connect(self._busy)
        self.refresh()

    # ----- lists ---------------------------------------------------------------------------

    def refresh(self) -> tuple[QuizEntry, ...]:
        entries = self.store.list_quizzes()
        self.window.home_page.set_entries(entries)
        self.window.quiz_list_page.set_entries(entries)
        return entries

    def _busy(self, busy: bool) -> None:
        self.window.quiz_page.set_busy(busy)
        self.window.quiz_list_page.set_busy(busy)
        free = self.state.writable and not busy
        self.window.home_page.import_button.setEnabled(free)
        self.window.settings_page.import_button.setEnabled(free)
        if not busy:
            self.window.set_busy(None)
            self.window.clear_status()

    def _warn(self, title: str, text: str) -> None:
        QMessageBox.warning(self.window, title, text)

    # ----- new quiz ------------------------------------------------------------------------

    def _wire_quiz_page(self, page: QuizPage) -> None:
        page.set_write_enabled(self.state.writable)
        page.run_requested.connect(self.run_quiz)
        page.form_fetch_requested.connect(self.fetch_form)

    def new_quiz(self) -> None:
        """Home's '새 퀴즈 채점': a fresh page, unless the teacher wants to go on with the open one."""
        if not self.runner.busy and (not self.window.quiz_page.has_input() or self._start_over()):
            self._fresh_quiz_page()
        self.window.show_page(NEW_QUIZ)

    def _fresh_quiz_page(self) -> None:
        self._wire_quiz_page(self.window.replace_quiz_page())

    def _start_over(self) -> bool:
        box = QMessageBox(self.window)
        box.setWindowTitle("새 퀴즈 채점")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("채점하던 퀴즈가 있습니다. 이어서 할까요, 새로 시작할까요?")
        box.setInformativeText("새로 시작하면 지금 고른 응답 파일과 문항표가 화면에서 빠집니다.")
        resume = box.addButton("이어서 하기", QMessageBox.ButtonRole.RejectRole)
        box.addButton("새로 시작", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(resume)
        box.exec()
        return box.clickedButton() is not resume

    def fetch_form(self, address: str) -> None:
        page = self.window.quiz_page

        def done(result: object) -> None:
            # The user may have started another new quiz meanwhile; that page never asked.
            if page is self.window.quiz_page:
                page.set_form_page(result)

        if not self.network.run(lambda: self._fetch_form(address), done):
            page.set_status("다른 확인이 끝난 뒤 다시 누르세요.", "warning")

    def run_quiz(self, request: QuizRunRequest) -> None:
        page = self.window.quiz_page

        def work() -> Result[QuizEntry]:
            return self.store.create(
                request.exam_name,
                request.responses_path,
                request.cutoff,
                request.bank,
                request.sheet,
            )

        def done(result: object) -> None:
            if isinstance(result, Err):
                page.show_problems(problems_text(result.errors))
                page.set_status("채점하지 못했습니다. 2단계의 고칠 점을 보세요.", "error")
                return
            assert isinstance(result, Ok)
            entry = result.value
            self._fresh_quiz_page()  # the next visit to 퀴즈 채점 starts clean
            self.window.show_page(HOME)  # refreshes the lists
            self._finished(entry, "채점을 마쳤습니다")

        if self.runner.run(work, done):
            self.window.set_busy("채점하고 리포트를 만드는 중입니다…")
            self.window.show_status("채점하고 리포트를 만드는 중입니다…", lasting=True)

    def _finished(self, entry: QuizEntry, headline: str) -> None:
        info = entry.info
        detail = ""
        if info is not None:
            kind = "상세 리포트" if info.summary.detailed else "기본 리포트"
            detail = f"\n{info.summary.students}명 · 평균 {info.summary.average:.1f} / {info.summary.maximum} · {kind}"
        box = QMessageBox(self.window)
        box.setWindowTitle("퀴즈 리포터")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"{headline}: {info.name if info else entry.folder}{detail}")
        box.setInformativeText(
            "통합 리포트는 흑백 인쇄용, 학생별 PDF는 학생에게 보낼 컬러 파일입니다."
        )
        report = box.addButton("통합 리포트 열기", QMessageBox.ButtonRole.AcceptRole)
        singles = box.addButton("학생별 PDF 폴더", QMessageBox.ButtonRole.ActionRole)
        folder = box.addButton("퀴즈 폴더", QMessageBox.ButtonRole.ActionRole)
        box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is report:
            self.open_report(entry.folder)
        elif box.clickedButton() is singles:
            self.open_singles(entry.folder)
        elif box.clickedButton() is folder:
            self.open_folder(entry.folder)

    # ----- one saved quiz ------------------------------------------------------------------

    def _folder(self, folder: str) -> Path | None:
        path = self.state.paths.data_path(folder)
        return None if isinstance(path, Err) else path.value

    def open_report(self, folder: str) -> None:
        path = self._folder(folder)
        bundle = None if path is None else path / REPORT_DIRNAME / BUNDLE_NAME
        if bundle is None or not bundle.is_file():
            self._warn(
                "리포트 열기",
                "리포트 파일이 없습니다. 채점 이력에서 '문항표 바꿔 다시 만들기'로 다시 만드세요.",
            )
            return
        self._open(str(bundle))

    def open_singles(self, folder: str) -> None:
        path = self._folder(folder)
        singles = None if path is None else path / REPORT_DIRNAME / SINGLES_DIRNAME
        if singles is None or not singles.is_dir():
            self._warn(
                "학생별 PDF",
                "학생별 PDF가 없습니다. 채점 이력에서 '문항표 바꿔 다시 만들기'로 다시 만드세요.",
            )
            return
        self._open(str(singles))

    def open_folder(self, folder: str) -> None:
        path = self._folder(folder)
        if path is not None and path.is_dir():
            self._open(str(path))

    def open_data_folder(self) -> None:
        self._open(str(self.state.paths.data_dir))

    def rebuild(self, folder: str) -> None:
        opened = self.store.open(folder)
        if isinstance(opened, Err):
            self._warn("문항표 바꿔 다시 만들기", reason_of(opened))
            return
        quiz = opened.value
        dialog = BankDialog(quiz.info.name, quiz.responses, self.window)
        if not dialog.exec() or dialog.bank is None:
            return
        bank = dialog.bank

        def done(result: object) -> None:
            if isinstance(result, Err):
                self._warn("문항표 바꿔 다시 만들기", reason_of(result))
                return
            assert isinstance(result, Ok)
            self.refresh()
            self.window.quiz_list_page.select_folder(folder)
            self._finished(result.value, "리포트를 다시 만들었습니다")

        if self.runner.run(lambda: self.store.replace_bank(folder, bank), done):
            self.window.set_busy("리포트를 다시 만드는 중입니다…")

    def delete(self, folder: str) -> None:
        entry = next((e for e in self.window.quiz_list_page.entries if e.folder == folder), None)
        name = entry.info.name if entry is not None and entry.info is not None else folder
        answer = QMessageBox.question(
            self.window,
            "삭제",
            f"'{name}'을(를) 휴지통으로 옮길까요? 휴지통에서 복원할 수 있습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.store.delete(folder)
        if isinstance(result, Err):
            self._warn("삭제", reason_of(result))
        self.refresh()

    def show_trash(self) -> None:
        dialog = TrashDialog(self.store, self.window)
        dialog.set_write_enabled(self.state.writable and not self.runner.busy)
        dialog.changed.connect(self.refresh)
        dialog.exec()

    # ----- settings ------------------------------------------------------------------------

    def choose_import(self) -> None:
        if self.runner.busy:
            self._warn("이전 자료 가져오기", "지금 하는 작업이 끝난 뒤 다시 누르세요.")
            return
        folder = QFileDialog.getExistingDirectory(self.window, "이전 버전 프로그램 폴더 선택")
        if folder:
            self.window.show_page("settings")
            self.import_from(folder)

    def import_from(self, folder: str) -> None:
        settings = self.window.settings_page
        relay = self._import_relay

        def progress(step: ImportProgress) -> None:
            relay.progress.emit(step.done, step.total)

        def done(result: object) -> None:
            settings.set_importing(False)
            if isinstance(result, Err):
                settings.set_import_result(reason_of(result), "error")
                return
            assert isinstance(result, Ok) and isinstance(result.value, ImportSummary)
            settings.set_import_result(*_import_message(result.value))
            self.refresh()

        def work() -> object:
            return import_previous_install(folder, self.store, self.state.paths, progress)

        if self.runner.run(work, done):
            settings.set_importing(True)
            settings.set_import_result("")
            self.window.set_busy("이전 자료를 가져오는 중입니다…")

    def set_update_enabled(self, enabled: bool) -> None:
        self.prefs = replace(self.prefs, enabled=enabled)
        save_update_preferences(self.state.paths, self.prefs)
        if not enabled:
            self.window.hide_update()

    def check_for_update(self, *, manual: bool = False) -> None:
        if not manual and not (self.state.writable and self.prefs.due(self._now())):
            return
        settings = self.window.settings_page

        def done(result: object) -> None:
            settings.set_checking(False)
            if self.state.writable:
                self.prefs = replace(self.prefs, last_checked=now_text(self._now()))
                save_update_preferences(self.state.paths, self.prefs)
            if isinstance(result, Err):
                if manual:
                    settings.set_update_result(reason_of(result), "warning")
                return
            assert isinstance(result, Ok)
            release = result.value
            if not is_newer(release.version, self.version):
                if manual:
                    settings.set_update_result(
                        f"지금 쓰는 v{self.version}이 최신입니다.", "success"
                    )
                return
            # A version the user skipped is still shown when they ask by hand.
            if manual or release.version != self.prefs.skipped_version:
                self.release = release
                self.window.show_update(release.version)
            if manual:
                version = release.version.lstrip("v")
                settings.set_update_result(f"새 버전 v{version}이 있습니다.", "success")

        if self.network.run(lambda: self._fetch_release(self.version), done):
            settings.set_checking(True)

    def open_download_page(self) -> None:
        url = self.release.page_url if self.release is not None else RELEASES_PAGE_URL
        self._open(url)

    def skip_release(self) -> None:
        if self.release is not None:
            self.prefs = replace(self.prefs, skipped_version=self.release.version)
            save_update_preferences(self.state.paths, self.prefs)
        self.window.hide_update()

    # ----- help ----------------------------------------------------------------------------

    def show_help(self) -> None:
        if self.help_dialog is None:
            self.help_dialog = HelpDialog(self.window)
        self.help_dialog.show_section(PAGE_SECTIONS.get(self.window.current_page(), "home"))
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    def shutdown(self) -> None:
        self.runner.wait()
        self.network.wait(6000)


def _import_message(summary: ImportSummary) -> tuple[str, str]:
    parts = [f"퀴즈 {summary.imported}개"]
    if summary.trashed:
        parts.append(f"휴지통 {summary.trashed}개")
    text = f"{', '.join(parts)}를 가져왔습니다."
    if summary.skipped:
        text += f" 이미 있는 {summary.skipped}개는 건너뛰었습니다."
    if summary.failed:
        lines = "\n".join(f"- {name}: {reason}" for name, reason in summary.failed)
        return f"{text}\n가져오지 못한 퀴즈 {len(summary.failed)}개:\n{lines}", "warning"
    if not (summary.imported or summary.trashed or summary.skipped):
        return "가져올 퀴즈가 없었습니다.", "hint"
    return text, "success"


__all__ = ["AppController", "open_with_system", "reason_of"]
