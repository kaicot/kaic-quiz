"""문항표 바꿔 다시 만들기: choose a new 문항표 for a saved quiz and check it fits the form."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.errors import Err
from quiz_reporter.quiz.bank import (
    QuizBank,
    parse_bank,
    problems_text,
    read_bank,
    readability_notes,
)
from quiz_reporter.quiz.grading import sheet_from_bank
from quiz_reporter.quiz.prompts import rows_from_text
from quiz_reporter.quiz.responses import FormResponses
from quiz_reporter.ui.theme import set_role


class BankDialog(QDialog):
    """Accepts only a 문항표 whose questions and options match the quiz's form."""

    def __init__(
        self,
        quiz_name: str,
        responses: FormResponses,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("문항표 바꿔 다시 만들기")
        self.setModal(True)
        self.resize(640, 420)
        self._responses = responses
        self.bank: QuizBank | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)
        heading = QLabel(f"{quiz_name}", self)
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        hint = QLabel(
            "새 문항표로 다시 채점하고 리포트를 새로 만듭니다. 응답과 마감 시각은 처음 그대로입니다."
            " 문제와 보기는 폼과 글자까지 같아야 합니다. 지금 문항표는 이 퀴즈 폴더의 문항표.xlsx에 있습니다.",
            self,
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        row = QHBoxLayout()
        self.load_button = QPushButton("문항표 파일 불러오기", self)
        self.paste_button = QPushButton("문항표 클립보드에서 붙여넣기", self)
        for button in (self.load_button, self.paste_button):
            row.addWidget(button)
        row.addStretch(1)
        root.addLayout(row)
        self.status_label = QLabel("새 문항표를 불러오거나 붙여 넣으세요.", self)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.problems_box = QPlainTextEdit(self)
        self.problems_box.setObjectName("quizProblems")
        self.problems_box.setReadOnly(True)
        self.problems_box.hide()
        root.addWidget(self.problems_box, 1)
        root.addStretch(0)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("취소", self)
        self.rebuild_button = QPushButton("다시 만들기", self)
        self.rebuild_button.setObjectName("primaryActionButton")
        self.rebuild_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.rebuild_button)
        root.addLayout(buttons)

        self.load_button.clicked.connect(self._load_file)
        self.paste_button.clicked.connect(lambda: self.paste(QApplication.clipboard().text()))
        self.cancel_button.clicked.connect(self.reject)
        self.rebuild_button.clicked.connect(self.accept)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "문항표 엑셀 선택", "", "Excel 통합 문서 (*.xlsx)"
        )
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        self._check(parse_bank(path, require_feedback=False), Path(path).name)

    def paste(self, text: str) -> None:
        rows = rows_from_text(text)
        if not rows:
            self._problem("복사한 내용에서 표를 찾지 못했습니다. AI가 준 표 전체를 복사하세요.")
            return
        self._check(read_bank(rows, require_feedback=False), "붙여 넣은 문항표")

    def _check(self, result: object, label: str) -> None:
        if isinstance(result, Err):
            self._problem(problems_text(result.errors))
            return
        bank = getattr(result, "value", None)
        if not isinstance(bank, QuizBank):
            return
        fits = sheet_from_bank(self._responses, bank)
        if isinstance(fits, Err):
            self._problem("이 퀴즈의 폼과 맞지 않습니다.\n" + problems_text(fits.errors))
            return
        self.bank = bank
        missing = [
            item.number for item in bank.items if item.answer is None or not item.has_feedback
        ]
        notes = [*readability_notes(bank)]
        if missing:
            notes.insert(
                0, f"빈 칸이 있는 문항: {', '.join(map(str, missing))}번 (그 문항은 기본 리포트)"
            )
        self.problems_box.setPlainText("\n".join(f"- {note}" for note in notes))
        self.problems_box.setVisible(bool(notes))
        kind = "상세 리포트" if bank.complete else "일부 기본 리포트"
        self.status_label.setText(f"{label}: {len(bank.items)}문항, 폼과 맞습니다 · {kind}")
        set_role(self.status_label, "success")
        self.rebuild_button.setEnabled(True)

    def _problem(self, text: str) -> None:
        self.bank = None
        self.problems_box.setPlainText(text)
        self.problems_box.show()
        self.status_label.setText("이 문항표로는 다시 만들 수 없습니다. 아래 내용을 고치세요.")
        set_role(self.status_label, "warning")
        self.rebuild_button.setEnabled(False)


__all__ = ["BankDialog"]
