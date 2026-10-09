"""퀴즈: grade a Google Forms quiz and make feedback reports.

The page reads files and checks the question bank itself (instant, no I/O beyond the chosen
files). Reading a public form page and grading/writing reports are handed to the controller,
which runs them off the GUI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quiz_reporter.errors import Err, Ok
from quiz_reporter.quiz.bank import (
    QuizBank,
    parse_bank,
    problems_text,
    read_bank,
    readability_notes,
)
from quiz_reporter.quiz.form_page import FormPage
from quiz_reporter.quiz.grading import (
    AnswerSheet,
    Selection,
    bank_from_sheet,
    select,
    sheet_from_bank,
    sheet_from_form,
    sheet_from_scores,
    suggest_cutoff,
)
from quiz_reporter.quiz.prompts import bank_text, completion_request, rows_from_text
from quiz_reporter.quiz.responses import KST, FormResponses, read_form_responses
from quiz_reporter.ui.theme import set_role


@dataclass(frozen=True, slots=True)
class QuizRunRequest:
    exam_name: str
    responses_path: Path
    cutoff: datetime | None
    sheet: AnswerSheet
    bank: QuizBank


def _step(
    parent: QWidget, number: int, title: str, hint: str
) -> tuple[QFrame, QVBoxLayout, QLabel]:
    """A step card: numbered circle, title, a status badge on the right, and one hint line."""
    card = QFrame(parent)
    card.setObjectName("quizCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(10)
    header = QHBoxLayout()
    header.setSpacing(10)
    circle = QLabel(str(number), card)
    circle.setObjectName("quizStepNumber")
    circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    heading = QLabel(title, card)
    heading.setObjectName("quizStepTitle")
    badge = QLabel(card)
    badge.setObjectName("quizBadge")
    header.addWidget(circle)
    header.addWidget(heading)
    header.addStretch()
    header.addWidget(badge)
    layout.addLayout(header)
    note = QLabel(hint, card)
    note.setProperty("role", "hint")
    note.setWordWrap(True)
    layout.addWidget(note)
    return card, layout, badge


def _panel(parent: QWidget, title: str) -> tuple[QFrame, QVBoxLayout]:
    """A tinted box inside a step."""
    panel = QFrame(parent)
    panel.setObjectName("quizPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    heading = QLabel(title, panel)
    heading.setObjectName("quizPanelTitle")
    layout.addWidget(heading)
    return panel, layout


def _set_badge(badge: QLabel, text: str, role: str) -> None:
    badge.setText(text)
    set_role(badge, role)


class QuizPage(QWidget):
    form_fetch_requested = Signal(str)
    run_requested = Signal(object)
    # (text, role) for the window's status message next to the menu
    message = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("quizPage")
        self._bank: QuizBank | None = None
        self._bank_problems: str = ""
        self._last_bank_text: str | None = None
        self._responses: FormResponses | None = None
        self._responses_path: Path | None = None
        self._form: FormPage | None = None
        self._write_enabled = True
        self._busy = False
        self.last_copied = ""
        self.last_status = ""
        self._check_failed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)
        title = QLabel("새 퀴즈 채점", self)
        title.setObjectName("quizPageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "구글 폼으로 본 5지선다 퀴즈를 채점하고, 학생마다 틀린 이유를 알려 주는 리포트를 만듭니다.",
            self,
        )
        subtitle.setProperty("role", "hint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # 1. 학생 응답
        card, layout, self.responses_badge = _step(
            self,
            1,
            "학생 응답",
            "구글 폼의 응답 탭에서 '응답 다운로드(.csv)'로 받은 파일을 고르세요. 연결된 스프레드시트(.xlsx)도"
            " 됩니다.",
        )
        file_row = QHBoxLayout()
        self.responses_button = QPushButton("응답 파일 선택", card)
        self.responses_button.setObjectName("quizResponsesButton")
        self.responses_label = QLabel("아직 고르지 않았습니다.", card)
        self.responses_label.setWordWrap(True)
        file_row.addWidget(self.responses_button)
        file_row.addSpacing(6)
        file_row.addWidget(self.responses_label, 1)
        layout.addLayout(file_row)
        panel, inner = _panel(card, "채점할 응답")
        name_row = QHBoxLayout()
        name_label = QLabel("퀴즈 이름", panel)
        name_label.setMinimumWidth(70)
        self.name_edit = QLineEdit(panel)
        self.name_edit.setPlaceholderText("채점 이력에 이 이름으로 남습니다")
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit, 1)
        inner.addLayout(name_row)
        cutoff_row = QHBoxLayout()
        self.cutoff_check = QCheckBox("이 시각 뒤 응답은 제외 (나중에 복습으로 다시 푼 것)", panel)
        self.cutoff_edit = QDateTimeEdit(panel)
        self.cutoff_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.cutoff_edit.setCalendarPopup(False)
        self.cutoff_edit.setDateTime(QDateTime.currentDateTime())
        cutoff_row.addWidget(self.cutoff_check)
        cutoff_row.addWidget(self.cutoff_edit)
        cutoff_row.addStretch()
        inner.addLayout(cutoff_row)
        self.cutoff_hint = QLabel(
            "마감은 프로그램이 제안합니다: 응답 시각을 30분 넘게 비는 틈으로 나눠, 응답이 가장 많이"
            " 몰린 시간대(수업 시간)의 마지막 응답 시각입니다. 그 뒤 응답(다음 날 복습 등)은 빠집니다."
            " 시간대가 하나뿐이면 제안하지 않습니다. 시각은 직접 고칠 수 있고, 체크를 끄면 모두 채점합니다.",
            panel,
        )
        self.cutoff_hint.setProperty("role", "hint")
        self.cutoff_hint.setWordWrap(True)
        inner.addWidget(self.cutoff_hint)
        self.selection_label = QLabel("", panel)
        self.selection_label.setObjectName("quizSelectionLabel")
        self.selection_label.setWordWrap(True)
        inner.addWidget(self.selection_label)
        layout.addWidget(panel)
        root.addWidget(card)

        # 2. 정답·해설 (문항표)
        card, layout, self.bank_badge = _step(
            self,
            2,
            "정답·해설 (문항표)",
            "이미 본 구글 폼 퀴즈의 정답과 해설(틀린 이유)을 만듭니다. 폼 주소로 틀을 만들고 AI에게 해설을"
            " 맡기세요. 건너뛰면 점수와 정답만 담은 기본 리포트가 나갑니다.",
        )
        self.xlsx_notice = QLabel(
            "스프레드시트(xlsx) 응답에는 정답 표시가 없어 추가 작업이 필요합니다. 아래 '가'에서 폼 주소로"
            " 틀을 만든 뒤, '나'에서 AI에게 정답과 해설을 함께 받아 넣으세요. (구글 폼 응답 탭에서 CSV로"
            " 받으면 정답이 자동으로 들어갑니다.)",
            card,
        )
        self.xlsx_notice.setProperty("role", "warning")
        self.xlsx_notice.setWordWrap(True)
        self.xlsx_notice.hide()
        layout.addWidget(self.xlsx_notice)
        form_panel, form_inner = _panel(card, "가. 폼 주소로 정답/해설 만들기")
        form_row = QHBoxLayout()
        self.form_edit = QLineEdit(form_panel)
        self.form_edit.setPlaceholderText("구글 폼 주소 https://docs.google.com/forms/…")
        form_row.addWidget(self.form_edit, 1)
        self.form_button = QPushButton("폼 주소로 정답/해설 만들기", form_panel)
        self.form_button.setObjectName("quizFormButton")
        form_row.addWidget(self.form_button)
        form_inner.addLayout(form_row)
        self.form_status = QLabel(form_panel)
        self.form_status.setWordWrap(True)
        self.form_status.hide()
        form_inner.addWidget(self.form_status)
        form_hint = QLabel(
            "학생이 푼 폼의 주소를 붙여 넣으세요. 문제와 보기는 폼에서, 정답은 ① 응답 CSV에서 가져와"
            " 문항표 틀을 만듭니다. 해설은 아래 '나'에서 AI에게 받습니다.",
            form_panel,
        )
        form_hint.setProperty("role", "hint")
        form_hint.setWordWrap(True)
        form_inner.addWidget(form_hint)
        layout.addWidget(form_panel)

        result_panel, result_inner = _panel(card, "나. AI에게 정답/해설 받기 (AI가 준 문항표 넣기)")
        ai_steps = QLabel(
            "① '해설 만들기 프롬프트 복사'를 누르고 → ② AI 대화창에 붙여 넣은 뒤 → ③ AI가 준 표를"
            " 복사해 '문항표 클립보드에서 붙여넣기'를 누르세요. AI가 엑셀 파일로 주면 '문항표 파일"
            " 불러오기'를 씁니다. 빈 정답도 AI가 채웁니다.",
            result_panel,
        )
        ai_steps.setProperty("role", "hint")
        ai_steps.setWordWrap(True)
        result_inner.addWidget(ai_steps)
        load_row = QHBoxLayout()
        self.bank_file_button = QPushButton("문항표 파일 불러오기", result_panel)
        self.bank_file_button.setToolTip("AI가 엑셀 파일(.xlsx)로 준 문항표를 고릅니다.")
        self.bank_paste_button = QPushButton("문항표 클립보드에서 붙여넣기", result_panel)
        self.bank_paste_button.setToolTip(
            "AI가 대화창에 표로 답했을 때, 그 표를 복사(Ctrl+C)한 뒤 누릅니다."
        )
        self.copy_complete_button = QPushButton("해설 만들기 프롬프트 복사", result_panel)
        self.copy_complete_button.setToolTip(
            "지금 문항표와 고칠 점을 담아, 빈 칸을 채우고 어려운 문장을 쉽게 고치게 하는 프롬프트를"
            " 복사합니다."
        )
        load_row.addWidget(self.copy_complete_button)
        load_row.addWidget(self.bank_paste_button)
        load_row.addWidget(self.bank_file_button)
        load_row.addStretch()
        result_inner.addLayout(load_row)
        self.bank_label = QLabel("아직 문항표가 없습니다.", result_panel)
        self.bank_label.setObjectName("quizBankLabel")
        self.bank_label.setWordWrap(True)
        result_inner.addWidget(self.bank_label)
        self.problems_box = QPlainTextEdit(result_panel)
        self.problems_box.setObjectName("quizProblems")
        self.problems_box.setReadOnly(True)
        self.problems_box.setMaximumHeight(110)
        self.problems_box.hide()
        result_inner.addWidget(self.problems_box)
        layout.addWidget(result_panel)
        root.addWidget(card)

        # 3. 채점과 리포트
        card, layout, self.run_badge = _step(
            self,
            3,
            "채점하고 리포트 만들기",
            "누르면 퀴즈가 채점 이력에 저장되고, 인쇄용 묶음 PDF · 학생별 PDF · 채점결과 엑셀이"
            " 만들어집니다. 저장할 폴더는 고르지 않아도 됩니다.",
        )
        run_row = QHBoxLayout()
        self.run_button = QPushButton("채점하고 리포트 만들기", card)
        self.run_button.setObjectName("primaryActionButton")
        self.run_button.setMinimumHeight(40)
        run_row.addWidget(self.run_button)
        run_row.addStretch()
        layout.addLayout(run_row)
        root.addWidget(card)
        root.addStretch()
        self.form_button.clicked.connect(self._request_form)
        self.bank_file_button.clicked.connect(self._load_bank_file)
        self.bank_paste_button.clicked.connect(self._paste_bank)
        self.copy_complete_button.clicked.connect(self._copy_completion_prompt)
        self.responses_button.clicked.connect(self._pick_responses)
        self.cutoff_check.toggled.connect(lambda _: self._refresh())
        self.cutoff_edit.dateTimeChanged.connect(lambda _: self._refresh())
        self.run_button.clicked.connect(self._run)
        self._refresh()

    # ----- state shown to the controller and tests -----
    @property
    def bank(self) -> QuizBank | None:
        return self._bank

    @property
    def responses(self) -> FormResponses | None:
        return self._responses

    def set_write_enabled(self, enabled: bool) -> None:
        self._write_enabled = bool(enabled)
        self._refresh()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._refresh()

    def has_input(self) -> bool:
        """Whether leaving this page for a fresh one would throw away the teacher's work."""
        return (
            self._responses is not None
            or self._bank is not None
            or bool(self.form_edit.text().strip())
        )

    def set_status(self, text: str, role: str = "info") -> None:
        self.last_status = text
        self.message.emit(text, role)

    # ----- ① bank -----
    def _copy(self, text: str, what: str) -> None:
        self.last_copied = text
        QApplication.clipboard().setText(text)
        self.set_status(f"{what}를 복사했습니다. AI 대화창에 붙여 넣으세요.")

    def _form_message(self, text: str, role: str = "hint") -> None:
        self.form_status.setText(text)
        set_role(self.form_status, role)
        self.form_status.setVisible(bool(text))

    def _request_form(self) -> None:
        address = self.form_edit.text().strip()
        if not address:
            self._form_message("폼 주소를 붙여 넣으세요.", "warning")
            return
        self._form_message("폼을 읽는 중입니다…")
        self.form_fetch_requested.emit(address)

    def set_form_page(self, result: object) -> None:
        """The controller's answer to ``form_fetch_requested``."""
        if isinstance(result, Err):
            self._form_message(problems_text(result.errors).removeprefix("- "), "warning")
            return
        if isinstance(result, Ok):
            result = result.value
        if not isinstance(result, FormPage):
            self._form_message("폼을 읽지 못했습니다. 주소를 확인하세요.", "warning")
            return
        self._form = result
        if not self.name_edit.text().strip() and result.title:
            self.name_edit.setText(result.title)
        self._build_skeleton()

    def _build_skeleton(self) -> None:
        """Questions and options from the form, answers from the CSV when it has [점수]."""
        form, responses = self._form, self._responses
        if form is None:
            return
        if responses is None:
            self._form_message(
                f"폼에서 {len(form.questions)}문항을 읽었습니다. ① 응답 파일을 고르면 틀을 만듭니다."
            )
            return
        questions = tuple((question.title, question.options) for question in form.questions)
        sheet = sheet_from_form(responses, questions)
        if isinstance(sheet, Err):
            self._form_message(
                "이 폼과 응답 파일이 맞지 않습니다. 아래 고칠 점을 보세요.", "warning"
            )
            self.show_problems(problems_text(sheet.errors))
            return
        skeleton = bank_from_sheet(responses, sheet.value)
        self._set_bank(skeleton, "폼에서 만든 문항표 틀")
        self._form = None
        count = len(sheet.value.answers)
        known = sum(answer is not None for answer in sheet.value.answers)
        if known == count:
            message = (
                f"폼에서 {count}문항 틀을 만들었습니다(정답 포함). 이제 '나'에서"
                " '해설 만들기 프롬프트 복사'로 AI에게 해설을 받으세요."
            )
        elif known == 0:
            message = (
                f"폼에서 {count}문항 틀을 만들었습니다. 응답 파일에 정답 정보가 없어 정답 칸이 비어"
                " 있습니다. '나'에서 AI에게 정답과 해설을 함께 받으세요."
            )
        else:
            message = (
                f"폼에서 {count}문항 틀을 만들었습니다. 정답은 {known}문항만 채웠습니다. '나'에서 AI에게"
                " 나머지 정답과 해설을 받으세요."
            )
        self._form_message(message, "success")

    def _load_bank_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "문항표 엑셀 선택", "", "Excel 통합 문서 (*.xlsx)"
        )
        if path:
            self.load_bank(path)

    def load_bank(self, path: str) -> None:
        result = parse_bank(path, require_feedback=False)
        self._accept_bank(result, Path(path).name)

    def _paste_bank(self) -> None:
        self.paste_bank(QApplication.clipboard().text())

    def paste_bank(self, text: str) -> None:
        rows = rows_from_text(text)
        if not rows:
            self.show_problems(
                "복사한 내용에서 표를 찾지 못했습니다. AI가 준 표 전체를 복사하세요."
            )
            return
        self._last_bank_text = text
        self._accept_bank(read_bank(rows, require_feedback=False), "붙여 넣은 문항표")

    def _accept_bank(self, result: object, label: str) -> None:
        if isinstance(result, Err):
            self.show_problems(problems_text(result.errors))
            return
        if isinstance(result, Ok) and isinstance(result.value, QuizBank):
            self._set_bank(result.value, label)

    def _set_bank(self, bank: QuizBank, label: str) -> None:
        self._check_failed = False
        self._bank = bank
        self._last_bank_text = bank_text(bank)
        missing = [
            item.number for item in bank.items if item.answer is None or not item.has_feedback
        ]
        notes = readability_notes(bank)
        lines = []
        if missing:
            lines.append(
                f"- 빈 칸이 있는 문항: {', '.join(str(n) for n in missing)}번 (정답·해설·오답이유·함정유형·"
                "복습포인트를 채워야 함)"
            )
        lines.extend(f"- {note}" for note in notes)
        self._bank_problems = "\n".join(lines)
        if lines:
            self.problems_box.setPlainText(self._bank_problems)
            self.problems_box.show()
        else:
            self.problems_box.hide()
        if missing:
            summary = "빈 칸이 있어 그 문항은 기본 리포트로 나갑니다."
        elif notes:
            summary = f"학생이 읽기에 긴 문장 {len(notes)}개 · '해설 만들기 프롬프트 복사'로 쉽게 고칠 수 있습니다."
        else:
            summary = "해설과 오답 이유 모두 있음"
        self.bank_label.setText(f"문항표: {label}, {len(bank.items)}문항 · {summary}")
        self._refresh()

    def show_problems(self, text: str) -> None:
        self._check_failed = True
        self._bank_problems = text
        self.problems_box.setPlainText(text)
        self.problems_box.show()
        self.set_status(
            "문항표에 고칠 점이 있습니다. 2단계 '나'의 목록을 보세요.",
            "warning",
        )
        self._refresh()

    def _copy_completion_prompt(self) -> None:
        if self._bank is None and not self._bank_problems:
            return
        # After a failed check, hand back the AI's own last answer with the problems.
        bank = None if self._check_failed else self._bank
        self._copy(
            completion_request(bank, self._bank_problems, self._last_bank_text),
            "해설 만들기 프롬프트",
        )

    # ----- ② responses -----
    def _pick_responses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "구글 폼 응답 선택", "", "구글 폼 응답 (*.csv *.xlsx)"
        )
        if path:
            self.load_responses(path)

    def load_responses(self, path: str) -> None:
        result = read_form_responses(path)
        if isinstance(result, Err):
            self.responses_label.setText(problems_text(result.errors))
            self._responses = None
            self._responses_path = None
            self.xlsx_notice.hide()
            self._refresh()
            return
        responses = result.value
        self._responses = responses
        self.xlsx_notice.setVisible(not responses.has_item_scores)
        self._responses_path = Path(path)
        stem = Path(path).stem.replace("(응답)", "").strip()
        if not self.name_edit.text().strip():
            self.name_edit.setText(stem)
        cutoff = suggest_cutoff(responses)
        blocked = self.cutoff_check.blockSignals(True)
        self.cutoff_check.setChecked(cutoff is not None)
        self.cutoff_check.blockSignals(blocked)
        moment = cutoff or max(
            (row.submitted_at for row in responses.rows if row.submitted_at), default=None
        )
        if moment is not None:
            local = moment.astimezone(KST)
            blocked = self.cutoff_edit.blockSignals(True)
            self.cutoff_edit.setDateTime(
                QDateTime(
                    local.year, local.month, local.day, local.hour, local.minute, local.second
                )
            )
            self.cutoff_edit.blockSignals(blocked)
        kind = (
            "문항별 정답 여부 있음"
            if responses.has_item_scores
            else "문항별 정답 여부 없음(문항표 필요)"
        )
        self.responses_label.setText(
            f"{Path(path).name}: 응답 {len(responses.rows)}건, {len(responses.questions)}문항 · {kind}"
        )
        if self._form is not None:
            self._build_skeleton()
        self._refresh()

    def _cutoff(self) -> datetime | None:
        if not self.cutoff_check.isChecked():
            return None
        value = self.cutoff_edit.dateTime()
        date, time = value.date(), value.time()
        return datetime(
            date.year(),
            date.month(),
            date.day(),
            time.hour(),
            time.minute(),
            time.second(),
            tzinfo=KST,
        )

    def current_selection(self) -> Selection | None:
        if self._responses is None:
            return None
        return select(self._responses, self._cutoff())

    def _describe(self, selection: Selection) -> str:
        times = [row.submitted_at for row in selection.kept if row.submitted_at]
        span = ""
        if times:
            first, last = min(times).astimezone(KST), max(times).astimezone(KST)
            span = f" ({first:%m/%d %H:%M}~{last:%H:%M})"
        parts = [f"채점할 응답 {len(selection.kept)}명{span}"]
        if selection.late:
            parts.append(f"마감 뒤 {len(selection.late)}건 제외")
        if selection.repeats:
            parts.append(f"같은 학번 두 번째 응답 {len(selection.repeats)}건 제외")
        flagged = sum(
            1
            for row in selection.kept
            if not (row.student_id.isdigit() and len(row.student_id) == 8)
        )
        if flagged:
            parts.append(f"학번이 8자리 숫자가 아닌 응답 {flagged}건(결과에 노랗게 표시)")
        return " · ".join(parts)

    # ----- ③ run -----
    def answer_sheet(self) -> tuple[AnswerSheet, QuizBank] | Err:
        responses = self._responses
        if responses is None:
            return Err(())
        if self._bank is not None:
            sheet = sheet_from_bank(responses, self._bank)
            return sheet if isinstance(sheet, Err) else (sheet.value, self._bank)
        scored = sheet_from_scores(responses)
        if isinstance(scored, Err):
            return scored
        return scored.value, bank_from_sheet(responses, scored.value)

    def _run(self) -> None:
        if self._responses is None or self._responses_path is None:
            self.set_status("먼저 ① 응답 파일을 고르세요.", "warning")
            return
        prepared = self.answer_sheet()
        if isinstance(prepared, Err):
            self.show_problems(problems_text(prepared.errors))
            return
        sheet, bank = prepared
        name = self.name_edit.text().strip() or "퀴즈"
        self.run_requested.emit(
            QuizRunRequest(
                name,
                self._responses_path,
                self._cutoff(),
                sheet,
                bank,
            )
        )

    def _update_badges(self, selection: Selection | None) -> None:
        if selection is None:
            _set_badge(self.responses_badge, "응답 없음", "idle")
        else:
            _set_badge(self.responses_badge, f"{len(selection.kept)}명 채점", "ok")
        bank = self._bank
        if bank is None:
            _set_badge(self.bank_badge, "없음 · 기본 리포트", "idle")
        elif not bank.complete:
            missing = sum(1 for item in bank.items if item.answer is None or not item.has_feedback)
            _set_badge(self.bank_badge, f"빈 칸 {missing}문항", "warn")
        elif self._bank_problems:
            _set_badge(self.bank_badge, "고칠 문장 있음", "warn")
        else:
            _set_badge(self.bank_badge, f"완성 · {len(bank.items)}문항", "ok")
        ready = selection is not None and bool(selection.kept)
        _set_badge(self.run_badge, "준비됨" if ready else "응답 필요", "ok" if ready else "idle")

    def _refresh(self) -> None:
        idle = not self._busy
        self.copy_complete_button.setEnabled(self._bank is not None or bool(self._bank_problems))
        self.form_button.setEnabled(idle)
        self.cutoff_edit.setEnabled(self.cutoff_check.isChecked())
        selection = self.current_selection()
        self.selection_label.setText(
            "응답 파일을 고르면 여기에 채점할 학생 수가 나옵니다."
            if selection is None
            else self._describe(selection)
        )
        self._update_badges(selection)
        self.run_button.setEnabled(
            idle and self._write_enabled and selection is not None and bool(selection.kept)
        )
        self.responses_button.setEnabled(idle)


__all__ = ["QuizPage", "QuizRunRequest"]
