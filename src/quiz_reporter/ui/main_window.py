"""The window frame: top menu with the status message, notice banners, the pages, and the status line."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.ui.home_page import HomePage
from quiz_reporter.ui.quiz_list_page import QuizListPage
from quiz_reporter.ui.quiz_page import QuizPage
from quiz_reporter.ui.settings_page import SettingsPage
from quiz_reporter.ui.theme import set_role

HOME, NEW_QUIZ, QUIZ_LIST, SETTINGS = "home", "new_quiz", "quiz_list", "settings"
TITLE = "퀴즈 리포터"
SUBTITLE = "구글 폼 퀴즈 채점 · 학생별 피드백"
CREDIT = "프로그램 제작 / 조승현 (kaic21@gmail.com) / v{version}"
# GNU LGPL-3.0 section 4(c): the running program shows the Qt notice next to its own credit.
NAV = ((HOME, "홈"), (NEW_QUIZ, "퀴즈 채점"), (QUIZ_LIST, "채점 이력"), (SETTINGS, "설정"))
# How long a passing message stays in the top bar.
STATUS_MS = 12_000
QT_NOTICE = "이 프로그램은 Qt for Python(PySide6)과 Qt를 GNU LGPL 3.0 조건으로 사용합니다. 저작권과 라이선스 전문은 프로그램 폴더의 THIRD_PARTY_NOTICES.txt에 있습니다."


def _scroll(widget: QWidget, parent: QWidget) -> QScrollArea:
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


class MainWindow(QMainWindow):
    page_changed = Signal(str)
    help_requested = Signal()
    download_requested = Signal()
    skip_requested = Signal()

    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(1180, 820)
        self.setMinimumSize(900, 620)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._top_bar())
        self.read_only_banner, self.read_only_label = self._banner("warning")
        layout.addWidget(self.read_only_banner)
        self.update_banner, self.update_label = self._banner("info")
        banner_row = self.update_banner.layout()
        assert isinstance(banner_row, QHBoxLayout)
        self.download_button = QPushButton("다운로드 페이지", self.update_banner)
        self.skip_button = QPushButton("이 버전 건너뛰기", self.update_banner)
        self.download_button.clicked.connect(self.download_requested)
        self.skip_button.clicked.connect(self.skip_requested)
        banner_row.addWidget(self.download_button)
        banner_row.addWidget(self.skip_button)
        layout.addWidget(self.update_banner)

        self.stack = QStackedWidget(central)
        self.home_page = HomePage()
        self.quiz_list_page = QuizListPage()
        self.settings_page = SettingsPage()
        self.quiz_page = QuizPage()
        self.quiz_page.message.connect(self.show_status)
        self._quiz_scroll = _scroll(self.quiz_page, self.stack)
        self._pages: dict[str, QWidget] = {}
        for key, page in (
            (HOME, _scroll(self.home_page, self.stack)),
            (NEW_QUIZ, self._quiz_scroll),
            (QUIZ_LIST, self.quiz_list_page),
            (SETTINGS, _scroll(self.settings_page, self.stack)),
        ):
            self.stack.addWidget(page)
            self._pages[key] = page
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.path_label = QLabel(status)
        status.addWidget(self.path_label, 1)
        self.busy_label = QLabel(status)
        self.busy_bar = QProgressBar(status)
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setFixedWidth(140)
        status.addPermanentWidget(self.busy_label)
        status.addPermanentWidget(self.busy_bar)
        self.credit_label = QLabel(CREDIT.format(version=version), status)
        self.credit_label.setToolTip(QT_NOTICE)
        status.addPermanentWidget(self.credit_label)
        self.set_busy(None)
        self.set_read_only(None)
        self.hide_update()
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, self.help_requested.emit)
        self.show_page(HOME)

    # ----- frame -------------------------------------------------------------------------

    def _top_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("topBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 0, 20, 0)
        row.setSpacing(4)
        mark = QLabel("◆", bar)
        mark.setObjectName("brandMark")
        row.addWidget(mark)
        brand = QVBoxLayout()
        brand.setContentsMargins(6, 8, 18, 8)
        brand.setSpacing(0)
        title = QLabel(TITLE, bar)
        title.setObjectName("brandTitle")
        subtitle = QLabel(SUBTITLE, bar)
        subtitle.setObjectName("brandSubtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        row.addLayout(brand)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in NAV:
            button = QPushButton(text, bar)
            button.setObjectName("navButton")
            button.setCheckable(True)
            # Keyboard focus only: a click must not leave the button looking selected.
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _=False, page=key: self.show_page(page))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            row.addWidget(button)
        row.addSpacing(18)
        self.status_message = QLabel(bar)
        self.status_message.setObjectName("topStatus")
        self.status_message.setWordWrap(True)
        # Two lines at most, so the menu bar keeps its height; the whole text is in the tooltip.
        self.status_message.setMaximumHeight(44)
        self.status_message.hide()
        row.addWidget(self.status_message, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(0)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self.clear_status)
        row.addSpacing(12)
        self.help_button = QPushButton("?", bar)
        self.help_button.setObjectName("helpButton")
        self.help_button.setToolTip("도움말 (F1)")
        self.help_button.setAccessibleName("도움말")
        self.help_button.clicked.connect(self.help_requested)
        row.addWidget(self.help_button)
        return bar

    def _banner(self, kind: str) -> tuple[QFrame, QLabel]:
        banner = QFrame(self)
        banner.setObjectName("noticeBanner")
        banner.setProperty("kind", kind)
        row = QHBoxLayout(banner)
        row.setContentsMargins(24, 8, 20, 8)
        label = QLabel(banner)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        return banner, label

    # ----- state -------------------------------------------------------------------------

    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self._pages[key])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self.page_changed.emit(key)

    def current_page(self) -> str:
        current = self.stack.currentWidget()
        return next(key for key, page in self._pages.items() if page is current)

    def replace_quiz_page(self) -> QuizPage:
        """A fresh, empty quiz page for the next new quiz."""
        old = self._quiz_scroll.takeWidget()
        self.quiz_page = QuizPage()
        self.quiz_page.message.connect(self.show_status)
        self._quiz_scroll.setWidget(self.quiz_page)
        if old is not None:
            old.deleteLater()
        self.clear_status()
        return self.quiz_page

    def show_status(self, text: str, role: str = "info", lasting: bool = False) -> None:
        """A short message next to the menu; it fades after a while unless ``lasting``."""
        self.status_message.setText(text)
        self.status_message.setToolTip(text)
        set_role(self.status_message, role)
        self.status_message.setVisible(bool(text))
        if text and not lasting:
            self._status_timer.start(STATUS_MS)
        else:
            self._status_timer.stop()

    def clear_status(self) -> None:
        self._status_timer.stop()
        self.status_message.clear()
        self.status_message.hide()

    def set_data_path(self, text: str) -> None:
        self.path_label.setText(f"저장 위치: {text}")

    def set_busy(self, text: str | None) -> None:
        self.busy_label.setText(text or "")
        self.busy_label.setVisible(bool(text))
        self.busy_bar.setVisible(bool(text))

    def set_read_only(self, reason: str | None) -> None:
        self.read_only_label.setText(reason or "")
        self.read_only_banner.setVisible(bool(reason))

    def show_update(self, version: str) -> None:
        self.update_label.setText(
            f"새 버전 v{version.lstrip('v')}이 있습니다. 새 폴더에 풀고 설정 → 이전 자료 가져오기로"
            " 퀴즈를 옮기세요."
        )
        self.update_banner.show()

    def hide_update(self) -> None:
        self.update_banner.hide()


__all__ = ["HOME", "NEW_QUIZ", "QUIZ_LIST", "SETTINGS", "MainWindow"]
