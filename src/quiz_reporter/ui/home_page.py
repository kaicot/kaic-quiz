"""홈: a big "new quiz" button and the most recent quizzes as cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.storage.quiz_info import QuizInfo
from quiz_reporter.storage.quiz_store import QuizEntry

RECENT = 6
COLUMNS = 3
_WEEKDAYS = "월화수목금토일"


def when_text(info: QuizInfo) -> str:
    moment = info.created_at
    return f"{moment:%Y-%m-%d}({_WEEKDAYS[moment.weekday()]}) {moment:%H:%M}"


def score_text(info: QuizInfo) -> str:
    summary = info.summary
    return f"평균 {summary.average:.1f} / {summary.maximum}"


def _label(text: str, name: str, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    return label


class QuizTile(QFrame):
    """One recent quiz: name, when, how many students, the class average and its reports."""

    def __init__(self, entry: QuizEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        info = entry.info
        assert info is not None
        self.folder = entry.folder
        self.setObjectName("quizTile")
        self.setMinimumWidth(240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title = _label(info.name, "tileTitle", self)
        title.setWordWrap(True)
        title.setToolTip(entry.folder)
        layout.addWidget(title)
        layout.addWidget(_label(f"{when_text(info)} · {info.summary.students}명", "tileMeta", self))
        row = QHBoxLayout()
        row.addWidget(_label(score_text(info), "tileScore", self))
        row.addStretch(1)
        badge = _label("상세 리포트" if info.summary.detailed else "기본 리포트", "tileBadge", self)
        badge.setProperty("role", "detailed" if info.summary.detailed else "basic")
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.report_button = QPushButton("통합 리포트", self)
        self.report_button.setToolTip("모든 학생을 묶은 흑백 인쇄용 PDF를 엽니다.")
        self.singles_button = QPushButton("학생별 PDF", self)
        self.singles_button.setToolTip("학생에게 한 명씩 보낼 컬러 PDF가 든 폴더를 엽니다.")
        buttons.addWidget(self.report_button)
        buttons.addWidget(self.singles_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)


class HomePage(QWidget):
    new_quiz_requested = Signal()
    report_requested = Signal(str)
    singles_requested = Signal(str)
    list_requested = Signal()
    import_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")
        self.tiles: list[QuizTile] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(22)

        hero = QVBoxLayout()
        hero.setSpacing(8)
        hero.addWidget(
            _label("구글 폼 퀴즈를 채점하고 학생마다 피드백을 만듭니다", "pageTitle", self)
        )
        intro = QLabel(
            "응답 CSV를 고르면 채점하고, 학생마다 '왜 틀렸는지' 알려 주는 PDF 리포트를 만듭니다.",
            self,
        )
        intro.setProperty("role", "hint")
        intro.setWordWrap(True)
        hero.addWidget(intro)
        root.addLayout(hero)
        self.new_quiz_button = QPushButton("＋  새 퀴즈 채점", self)
        self.new_quiz_button.setObjectName("newQuizButton")
        self.new_quiz_button.clicked.connect(self.new_quiz_requested)
        root.addWidget(self.new_quiz_button, 0, Qt.AlignmentFlag.AlignLeft)

        heading = QHBoxLayout()
        self.recent_title = _label("최근 퀴즈", "sectionTitle", self)
        heading.addWidget(self.recent_title)
        heading.addStretch(1)
        # A plain button like the ones on the cards, not a link.
        self.all_button = QPushButton("채점 이력 전체 보기  ›", self)
        self.all_button.clicked.connect(self.list_requested)
        heading.addWidget(self.all_button)
        root.addLayout(heading)

        self.grid_host = QWidget(self)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        for column in range(COLUMNS):
            self.grid.setColumnStretch(column, 1)
        root.addWidget(self.grid_host)
        self.unreadable_label = QLabel(self)
        self.unreadable_label.setProperty("role", "hint")
        self.unreadable_label.setWordWrap(True)
        root.addWidget(self.unreadable_label)

        self.empty_state = QFrame(self)
        self.empty_state.setObjectName("emptyState")
        empty = QVBoxLayout(self.empty_state)
        empty.setContentsMargins(24, 22, 24, 22)
        empty.setSpacing(8)
        empty.addWidget(_label("아직 채점한 퀴즈가 없습니다.", "sectionTitle", self.empty_state))
        start = QLabel(
            "구글 폼에서 받은 응답 CSV만 있으면 시작할 수 있습니다. 위의 '새 퀴즈 채점'을 누르세요.",
            self.empty_state,
        )
        start.setProperty("role", "hint")
        start.setWordWrap(True)
        empty.addWidget(start)
        empty.addSpacing(10)
        previous = QHBoxLayout()
        previous.addWidget(QLabel("이전 버전에서 쓰던 퀴즈가 있나요?", self.empty_state))
        self.import_button = QPushButton("이전 자료 가져오기", self.empty_state)
        self.import_button.clicked.connect(self.import_requested)
        previous.addWidget(self.import_button)
        previous.addStretch(1)
        empty.addLayout(previous)
        root.addWidget(self.empty_state)
        root.addStretch(1)
        self.set_entries(())

    def set_entries(self, entries: tuple[QuizEntry, ...]) -> None:
        """The newest quizzes as cards; with no quiz folder at all, the getting-started box."""
        for tile in self.tiles:
            self.grid.removeWidget(tile)
            tile.hide()
            tile.deleteLater()
        self.tiles = []
        readable = [entry for entry in entries if entry.info is not None]
        for index, entry in enumerate(readable[:RECENT]):
            tile = QuizTile(entry, self.grid_host)
            tile.singles_button.clicked.connect(
                lambda _=False, folder=entry.folder: self.singles_requested.emit(folder)
            )
            tile.report_button.clicked.connect(
                lambda _=False, folder=entry.folder: self.report_requested.emit(folder)
            )
            self.grid.addWidget(tile, index // COLUMNS, index % COLUMNS)
            self.tiles.append(tile)
        unreadable = len(entries) - len(readable)
        self.unreadable_label.setText(
            f"읽을 수 없는 퀴즈 폴더가 {unreadable}개 있습니다. 채점 이력에서 이유를 볼 수 있습니다."
            if unreadable
            else ""
        )
        self.unreadable_label.setVisible(bool(unreadable))
        has_any = bool(entries)
        self.empty_state.setVisible(not has_any)
        self.recent_title.setVisible(bool(readable))
        self.all_button.setVisible(has_any)
        self.grid_host.setVisible(bool(readable))

    def set_write_enabled(self, enabled: bool) -> None:
        self.new_quiz_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled)


__all__ = ["HomePage", "QuizTile", "score_text", "when_text"]
