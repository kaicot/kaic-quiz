"""설정: where the data lives, the new-version notice, and importing a previous install."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.ui.theme import set_role


def _card(parent: QWidget, title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(8)
    heading = QLabel(title, card)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    note = QLabel(hint, card)
    note.setProperty("role", "hint")
    note.setWordWrap(True)
    layout.addWidget(note)
    return card, layout


def _set_role(label: QLabel, text: str, role: str) -> None:
    label.setText(text)
    set_role(label, role)
    label.setVisible(bool(text))


class SettingsPage(QWidget):
    open_data_requested = Signal()
    update_toggled = Signal(bool)
    check_now_requested = Signal()
    import_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(16)
        title = QLabel("설정", self)
        title.setObjectName("pageTitle")
        root.addWidget(title)

        card, layout = _card(
            self,
            "1. 저장 위치",
            "퀴즈는 모두 프로그램 폴더 안의 Data 폴더에 저장됩니다. 위치는 바꿀 수 없습니다."
            " 다른 곳에 두려면 프로그램을 끄고 프로그램 폴더 전체를 옮기세요.",
        )
        row = QHBoxLayout()
        self.data_path_label = QLabel(card)
        self.data_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.data_path_label.setWordWrap(True)
        row.addWidget(self.data_path_label, 1)
        self.open_data_button = QPushButton("폴더 열기", card)
        self.open_data_button.clicked.connect(self.open_data_requested)
        row.addWidget(self.open_data_button)
        layout.addLayout(row)
        root.addWidget(card)

        card, layout = _card(
            self,
            "2. 새 버전 안내",
            "켜 두면 하루 한 번 GitHub에서 새 버전이 있는지 확인해 화면 위쪽에 알려 줍니다."
            " 보내는 정보는 프로그램 버전 번호뿐이고, 자동으로 설치하지 않습니다.",
        )
        row = QHBoxLayout()
        self.update_check = QCheckBox("하루 한 번 새 버전 확인", card)
        self.update_check.toggled.connect(self.update_toggled)
        row.addWidget(self.update_check)
        row.addStretch(1)
        self.check_now_button = QPushButton("지금 확인", card)
        self.check_now_button.clicked.connect(self.check_now_requested)
        row.addWidget(self.check_now_button)
        layout.addLayout(row)
        self.update_result = QLabel(card)
        self.update_result.setWordWrap(True)
        self.update_result.hide()
        layout.addWidget(self.update_result)
        root.addWidget(card)

        card, layout = _card(
            self,
            "3. 이전 자료 가져오기",
            "새 버전을 새 폴더에 풀었다면, 예전 프로그램 폴더를 골라 퀴즈와 휴지통을 가져옵니다."
            " 퀴즈마다 확인한 뒤 복사하며 예전 폴더는 바꾸지 않습니다. 이미 있는 퀴즈는 건너뜁니다.",
        )
        row = QHBoxLayout()
        self.import_button = QPushButton("이전 자료 가져오기", card)
        self.import_button.clicked.connect(self.import_requested)
        row.addWidget(self.import_button)
        self.import_progress = QProgressBar(card)
        self.import_progress.setTextVisible(False)
        self.import_progress.hide()
        row.addWidget(self.import_progress, 1)
        row.addStretch(1)
        layout.addLayout(row)
        self.import_result = QLabel(card)
        self.import_result.setWordWrap(True)
        self.import_result.hide()
        layout.addWidget(self.import_result)
        root.addWidget(card)
        root.addStretch(1)

    def set_data_path(self, text: str) -> None:
        self.data_path_label.setText(text)

    def set_update_enabled(self, enabled: bool) -> None:
        blocked = self.update_check.blockSignals(True)
        self.update_check.setChecked(enabled)
        self.update_check.blockSignals(blocked)

    def set_update_result(self, text: str, role: str = "hint") -> None:
        _set_role(self.update_result, text, role)

    def set_checking(self, checking: bool) -> None:
        self.check_now_button.setEnabled(not checking)
        self.check_now_button.setText("확인하는 중…" if checking else "지금 확인")

    def set_import_progress(self, done: int, total: int) -> None:
        self.import_progress.setMaximum(max(total, 1))
        self.import_progress.setValue(done)

    def set_importing(self, importing: bool) -> None:
        self.import_button.setEnabled(not importing)
        self.import_progress.setVisible(importing)
        if importing:
            self.import_progress.setValue(0)

    def set_import_result(self, text: str, role: str = "success") -> None:
        _set_role(self.import_result, text, role)

    def set_write_enabled(self, enabled: bool) -> None:
        self.import_button.setEnabled(enabled)
        self.update_check.setEnabled(enabled)


__all__ = ["SettingsPage"]
