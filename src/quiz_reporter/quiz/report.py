"""Per-student quiz feedback: what was missed, why, which traps keep catching the student, and
what to review first. Pure: the caller supplies graded choices and the bank.

Two looks share one layout: color for the PDF a student gets, and a grey-scale look for the
bundle teachers print in bulk (marks and weight instead of color, no wide tinted areas).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape

from quiz_reporter.palette import TOKENS
from quiz_reporter.quiz.bank import OPTION_COUNT, QuizBank, QuizItem

CIRCLED = "①②③④⑤"
TRAP_ADVICE = {
    "개념 혼동": "비슷한 두 개념의 차이를 표로 나란히 정리해 보세요.",
    "용어 혼동": "헷갈린 용어끼리 짝지어 뜻과 위치를 정리해 보세요.",
    "방향·순서 혼동": "과정의 방향과 순서를 화살표 그림으로 그려 보세요.",
    "수치 혼동": "자주 나오는 수치는 암기 카드로 따로 정리해 보세요.",
    "부분만 맞음": "보기의 모든 부분이 맞는지 끝까지 확인하는 습관을 들이세요.",
    "반대 개념": "증가/감소, 촉진/억제처럼 반대 짝을 함께 외워 보세요.",
    "지나친 일반화": "'모든', '항상' 같은 말이 나오면 예외가 없는지 따져 보세요.",
    "사례 적용 오류": "개념을 실제 사례에 적용하는 문제를 더 풀어 보세요.",
}
# Questions per row on the result strip.
STRIP_COLUMNS = 15
# Body text size: small enough that a student who missed most questions still fits on one A4.
BODY_PT = 8.5


@dataclass(frozen=True, slots=True)
class Student:
    serial: int
    # Blank when the typed ID is not 8 digits; ``typed_id`` keeps what was typed.
    student_id: str
    name: str
    choices: tuple[int | None, ...]
    typed_id: str = ""


@dataclass(frozen=True, slots=True)
class Miss:
    item: QuizItem
    chosen: int | None
    # Share of the class that got this question right.
    class_rate: float = 0.0

    @property
    def reason(self) -> str:
        if self.chosen is None:
            return "답을 고르지 않았습니다."
        return self.item.reasons[self.chosen - 1]

    @property
    def trap(self) -> str:
        return "" if self.chosen is None else self.item.traps[self.chosen - 1]


@dataclass(frozen=True, slots=True)
class Mark:
    """One graded question on the student's result strip."""

    number: int
    correct: bool
    class_rate: float


@dataclass(frozen=True, slots=True)
class StudentReport:
    student: Student
    score: int
    maximum: int
    average: float
    marks: tuple[Mark, ...]
    misses: tuple[Miss, ...]
    right: tuple[int, ...]
    traps: tuple[tuple[str, int], ...]
    review: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassSummary:
    students: int
    average: float
    maximum: int
    # Per question: correct rate and how many chose each option (1..5).
    correct_rate: tuple[float, ...]
    option_counts: tuple[tuple[int, ...], ...]
    trap_counts: tuple[tuple[str, int], ...]


def _graded(bank: QuizBank) -> tuple[QuizItem, ...]:
    return tuple(item for item in bank.items if item.answer is not None)


def summarize(bank: QuizBank, students: tuple[Student, ...]) -> ClassSummary:
    items = _graded(bank)
    rates: list[float] = []
    counts: list[tuple[int, ...]] = []
    traps: Counter[str] = Counter()
    for item in bank.items:
        index = item.number - 1
        chosen = [student.choices[index] for student in students]
        counts.append(tuple(sum(choice == number for choice in chosen) for number in range(1, 6)))
        if item.answer is None:
            rates.append(0.0)
            continue
        rates.append(
            sum(choice == item.answer for choice in chosen) / len(students) if students else 0.0
        )
        for choice in chosen:
            if choice is not None and choice != item.answer and item.traps[choice - 1]:
                traps[item.traps[choice - 1]] += 1
    scores = [
        sum(student.choices[item.number - 1] == item.answer for item in items)
        for student in students
    ]
    return ClassSummary(
        len(students),
        sum(scores) / len(scores) if scores else 0.0,
        len(items),
        tuple(rates),
        tuple(counts),
        tuple(traps.most_common()),
    )


def build_reports(
    bank: QuizBank, students: tuple[Student, ...]
) -> tuple[tuple[StudentReport, ...], ClassSummary]:
    summary = summarize(bank, students)
    items = _graded(bank)
    reports: list[StudentReport] = []
    for student in students:
        marks = tuple(
            Mark(
                item.number,
                student.choices[item.number - 1] == item.answer,
                summary.correct_rate[item.number - 1],
            )
            for item in items
        )
        misses = tuple(
            Miss(item, student.choices[item.number - 1], summary.correct_rate[item.number - 1])
            for item in items
            if student.choices[item.number - 1] != item.answer
        )
        right = tuple(mark.number for mark in marks if mark.correct)
        traps = Counter(miss.trap for miss in misses if miss.trap)
        # Review first what most of the class got right: the gaps quickest to close.
        ordered = sorted(misses, key=lambda miss: (-miss.class_rate, miss.item.number))
        review = tuple(dict.fromkeys(miss.item.review for miss in ordered if miss.item.review))[:3]
        reports.append(
            StudentReport(
                student,
                len(right),
                len(items),
                summary.average,
                marks,
                misses,
                right,
                tuple(traps.most_common()),
                review,
            )
        )
    return tuple(reports), summary


@dataclass(frozen=True, slots=True)
class _Look:
    mono: bool
    ink: str
    muted: str
    brand: str
    brand_soft: str
    score_bar: str
    track: str
    klass: str
    card: str
    rule: str
    red: str
    red_soft: str
    green: str
    green_soft: str
    green_strong: str
    orange: str
    orange_soft: str
    orange_chip: str
    reason: str
    wrong_cell: str
    # Width of the left rule on boxes, in pixels.
    accent: int


# Color, for the PDF a student gets: the app theme. Teal frames the page and marks "me"; green,
# red and amber keep their meanings (right, wrong, trap).
COLOR = _Look(
    mono=False,
    ink=TOKENS.text,
    muted=TOKENS.muted,
    brand=TOKENS.primary,
    brand_soft=TOKENS.primary_soft,
    score_bar=TOKENS.primary,
    track="#E6ECEA",
    klass="#9AA5B1",
    card=TOKENS.window,
    rule=TOKENS.border,
    red=TOKENS.error,
    red_soft=TOKENS.error_soft,
    green=TOKENS.success,
    green_soft="#E8F5EE",
    green_strong="#166534",
    orange=TOKENS.warning,
    orange_soft=TOKENS.warning_soft,
    orange_chip="#FFE8CC",
    reason="#3F1D1D",
    wrong_cell=TOKENS.error_soft,
    accent=4,
)
# Grey scale, for the bundle printed in bulk: black and dark grey text on white, rules instead
# of tinted boxes, ✕ and weight for wrong answers. Only the small wrong cells and bars are grey.
MONO = _Look(
    mono=True,
    ink="#111111",
    muted="#404040",
    brand="#111111",
    brand_soft="#FFFFFF",
    score_bar="#404040",
    track="#E0E0E0",
    klass="#8C8C8C",
    card="#FFFFFF",
    rule="#111111",
    red="#111111",
    red_soft="#FFFFFF",
    green="#111111",
    green_soft="#FFFFFF",
    green_strong="#111111",
    orange="#111111",
    orange_soft="#FFFFFF",
    orange_chip="#FFFFFF",
    reason="#111111",
    wrong_cell="#D9D9D9",
    accent=2,
)

# (label, text, background) pairs drawn on the page; tests hold them to WCAG AA.
REPORT_TEXT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("ink on white", COLOR.ink, "#FFFFFF"),
    ("muted on card", COLOR.muted, COLOR.card),
    ("muted on white", COLOR.muted, "#FFFFFF"),
    ("brand on white", COLOR.brand, "#FFFFFF"),
    ("brand on card", COLOR.brand, COLOR.card),
    ("brand on brand soft", COLOR.brand, COLOR.brand_soft),
    ("green on card", COLOR.green, COLOR.card),
    ("green on white", COLOR.green, "#FFFFFF"),
    ("red on card", COLOR.red, COLOR.card),
    ("red on red soft", COLOR.red, COLOR.red_soft),
    ("reason text on red soft", COLOR.reason, COLOR.red_soft),
    ("amber on amber soft", COLOR.orange, COLOR.orange_soft),
    ("amber on amber chip", COLOR.orange, COLOR.orange_chip),
    ("strong green on green soft", COLOR.green_strong, COLOR.green_soft),
    ("grey: ink on white", MONO.ink, "#FFFFFF"),
    ("grey: muted on white", MONO.muted, "#FFFFFF"),
    ("grey: ink on wrong cell", MONO.ink, MONO.wrong_cell),
)


def _bar(rate: float, color: str, track: str, height: str = "5pt") -> str:
    """A horizontal bar as a one-row table: filled part, then the empty track."""
    filled = max(0, min(100, round(rate * 100)))
    cells = []
    if filled:
        cells.append(
            f"<td width='{filled}%' bgcolor='{color}' style='font-size:{height}'>&nbsp;</td>"
        )
    if filled < 100:
        cells.append(
            f"<td width='{100 - filled}%' bgcolor='{track}' style='font-size:{height}'>&nbsp;</td>"
        )
    return f"<table width='100%' cellspacing='0' cellpadding='0'><tr>{''.join(cells)}</tr></table>"


def _chip(text: str, color: str, background: str, look: _Look) -> str:
    if look.mono:
        return f"<span style='color:{look.ink}; font-weight:700'>[{escape(text)}]</span>"
    return (
        f"<span style='background-color:{background}; color:{color}; font-weight:600'>"
        f"&nbsp;{escape(text)}&nbsp;</span>"
    )


def _heading(text: str, color: str) -> str:
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:7px; margin-bottom:2px'>"
        f"<tr><td width='4' bgcolor='{color}'></td><td style='padding-left:6px'>"
        f"<span style='font-size:10.5pt; font-weight:700; color:{color}'>{escape(text)}</span>"
        "</td></tr></table>"
    )


def _box(content: str, accent: str, background: str, look: _Look) -> str:
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:2px'>"
        f"<tr><td width='{look.accent}' bgcolor='{accent}'></td>"
        f"<td bgcolor='{background}' style='padding:4px 8px'>{content}</td></tr></table>"
    )


def _card(content: str, width: str, look: _Look) -> str:
    if look.mono:
        return (
            f"<td width='{width}' valign='top'><table width='100%' cellspacing='0' cellpadding='0'>"
            f"<tr><td width='{look.accent}' bgcolor='{look.rule}'></td>"
            f"<td style='padding:4px 9px'>{content}</td></tr></table></td>"
        )
    return (
        f"<td width='{width}' bgcolor='{look.card}' style='padding:6px 10px' valign='top'>"
        f"{content}</td>"
    )


def _choice(number: int | None) -> str:
    return "무응답" if number is None else CIRCLED[number - 1]


def _percent(rate: float) -> str:
    return f"{round(rate * 100)}%"


def _strip(marks: tuple[Mark, ...], look: _Look) -> str:
    """Mine (○/✕) over the class's correct rate, one column per question."""
    blocks = []
    for start in range(0, len(marks), STRIP_COLUMNS):
        chunk = marks[start : start + STRIP_COLUMNS]
        width = min(100, 13 + 6 * len(chunk))
        label = f"<td width='{round(1300 / width)}%' style='color:{look.muted}'>"
        numbers = "".join(
            f"<td align='center' style='color:{look.muted}'>{mark.number}</td>" for mark in chunk
        )
        mine = "".join(
            f"<td align='center' bgcolor='{look.green_soft}' style='color:{look.green_strong}'>○</td>"
            if mark.correct
            else f"<td align='center' bgcolor='{look.wrong_cell}'"
            f" style='color:{look.red}; font-weight:700'>✕</td>"
            for mark in chunk
        )
        rates = "".join(
            f"<td align='center' style='color:{look.muted}; font-size:8pt'>"
            f"{_percent(mark.class_rate)}</td>"
            for mark in chunk
        )
        blocks.append(
            f"<table width='{width}%' cellspacing='1' cellpadding='2' style='margin-top:2px'>"
            f"<tr>{label}문항</td>{numbers}</tr>"
            f"<tr>{label}<b style='color:{look.ink}'>나</b></td>{mine}</tr>"
            f"<tr>{label}반 정답률</td>{rates}</tr></table>"
        )
    return "".join(blocks)


def report_html(
    report: StudentReport,
    title: str,
    date: str,
    *,
    page_break: bool,
    numbered: bool = True,
    mono: bool = False,
) -> str:
    """One student's A4 page; Qt rich text, so layout is built from tables.

    ``date`` is the day the quiz was taken (blank when unknown). ``numbered=False`` leaves out
    ①~⑤ when they would not match the form's option numbers. ``mono`` is the grey-scale look.
    """
    look = MONO if mono else COLOR
    s = report.student
    percent = report.score / report.maximum if report.maximum else 0.0
    average = report.average / report.maximum if report.maximum else 0.0
    gap = report.score - report.average
    gap_text = (
        f"<span style='color:{look.green}'>반 평균보다 {gap:+.1f}점</span>"
        if gap > 0.05
        else f"<span style='color:{look.red}'>반 평균보다 {gap:+.1f}점</span>"
        if gap < -0.05
        else f"<span style='color:{look.muted}'>반 평균과 같음</span>"
    )
    parts = [f"<div style='{'page-break-before: always;' if page_break else ''}'>"]
    # Header: a thin rule over the title and the student, then a hairline.
    student_id = (
        f"<span style='color:{look.muted}; font-size:9pt'>{escape(s.student_id)}</span>"
        if s.student_id
        else f"<span style='color:{look.red}; font-size:9pt; font-weight:700'>학번 확인 필요</span>"
    )
    subtitle = f"{escape(date)} 응시  ·  학생별 피드백 리포트" if date else "학생별 피드백 리포트"
    parts.append(
        "<table width='100%' cellspacing='0' cellpadding='0'>"
        f"<tr><td colspan='2' bgcolor='{look.brand}' style='font-size:3pt'>&nbsp;</td></tr>"
        "<tr><td style='padding:6px 2px 5px 2px'>"
        f"<span style='color:{look.ink}; font-size:15pt; font-weight:700'>{escape(title)}</span><br>"
        f"<span style='color:{look.muted}; font-size:8.5pt'>{subtitle}</span>"
        "</td><td align='right' style='padding:6px 2px 5px 2px'>"
        f"<span style='color:{look.ink}; font-size:14pt; font-weight:700'>{escape(s.name) or '이름 없음'}"
        f"</span><br>{student_id}</td></tr>"
        f"<tr><td colspan='2' bgcolor='{look.rule}' style='font-size:1pt'>&nbsp;</td></tr>"
        "</table>"
    )
    # Score cards.
    right = ", ".join(str(n) for n in report.right) or "없음"
    mine = (
        f"<span style='color:{look.muted}; font-size:8.5pt'>내 점수</span><br>"
        f"<span style='color:{look.brand}; font-size:20pt; font-weight:700'>{report.score}</span>"
        f"<span style='font-size:11pt; color:{look.muted}'> / {report.maximum}"
        f"  ({round(percent * 100)}%)</span>{_bar(percent, look.score_bar, look.track)}"
    )
    klass = (
        f"<span style='color:{look.muted}; font-size:8.5pt'>반 평균</span><br>"
        f"<span style='color:{look.ink}; font-size:14pt; font-weight:700'>{report.average:.1f}</span>"
        f"<span style='color:{look.muted}'> / {report.maximum}</span>&nbsp; {gap_text}"
        f"{_bar(average, look.klass, look.track)}"
    )
    counts = (
        f"<span style='color:{look.muted}; font-size:8.5pt'>맞힌 문항</span><br>"
        f"<span style='color:{look.green}; font-weight:700'>{escape(right)}</span><br>"
        f"<span style='color:{look.muted}; font-size:8.5pt'>틀린 문항</span> "
        f"<span style='color:{look.red}; font-weight:700'>{len(report.misses)}개</span>"
    )
    parts.append(
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:6px'><tr>"
        + _card(mine, "36%", look)
        + "<td width='2%'></td>"
        + _card(klass, "30%", look)
        + "<td width='2%'></td>"
        + _card(counts, "30%", look)
        + "</tr></table>"
    )
    # Every question at a glance: mine against the class.
    if report.marks:
        parts.append(_heading("문항별 결과", look.brand))
        parts.append(_strip(report.marks, look))
    # Misses as cards.
    if report.misses:
        parts.append(_heading("틀린 문항", look.red))
        for miss in report.misses:
            item = miss.item
            answer = item.answer or 0
            chosen = (
                (f"<b>{_choice(miss.chosen)}</b> " if numbered else "")
                + escape(item.options[miss.chosen - 1])
                if miss.chosen
                else "<b>무응답</b>"
            )
            trap = f" {_chip(miss.trap, look.red, look.red_soft, look)}" if miss.trap else ""
            unit = f"{_chip(item.unit, look.brand, look.brand_soft, look)} " if item.unit else ""
            rate = (
                f"&nbsp; <span style='color:{look.muted}; font-size:8pt'>"
                f"(반 {_percent(miss.class_rate)}가 맞힘)</span>"
            )
            # Why it was wrong comes last, after both answers, on its own line.
            reason = (
                "<br>"
                + (
                    f"<span style='color:{look.ink}; font-weight:700'>▶ 틀린 이유</span>"
                    if look.mono
                    else _chip("틀린 이유", look.red, look.red_soft, look)
                )
                + f"&nbsp; <span style='color:{look.reason}'>{escape(miss.reason)}</span>"
                if miss.reason
                else ""
            )
            content = (
                f"<span style='color:{look.ink}; font-weight:700'>{item.number}번</span>&nbsp; {unit}"
                f"<span style='color:{look.ink}'>{escape(item.question)}</span>{rate}<br>"
                f"<span style='color:{look.muted}'>내가 고른 답</span>&nbsp; "
                f"<span style='color:{look.ink}'>{chosen}</span>{trap}<br>"
                f"<span style='color:{look.green}; font-weight:700'>정답</span>&nbsp; "
                + (
                    f"<span style='color:{look.green}; font-weight:700'>{CIRCLED[answer - 1]}</span> "
                    if numbered
                    else ""
                )
                + f"<span style='color:{look.green}'>{escape(item.options[answer - 1])}</span>"
                f"{reason}"
            )
            parts.append(_box(content, look.red, "#FFFFFF", look))
    else:
        parts.append(
            _box(
                f"<span style='color:{look.green_strong}; font-size:12pt; font-weight:700'>"
                "모든 문항을 맞혔습니다. 훌륭합니다!</span>",
                look.green,
                look.green_soft,
                look,
            )
        )
    # Trap pattern.
    if report.traps:
        top, count = report.traps[0]
        lead = (
            f"틀린 {len(report.misses)}문항 중 <b>{count}개</b>가 "
            f"<span style='color:{look.orange}; font-weight:700'>{escape(top)}</span>입니다."
            if count >= 2
            else f"틀린 {len(report.misses)}문항의 함정이 저마다 다릅니다. 유형마다 정리법을 보세요."
        )
        # One line per trap: how often it caught the student, then how to fix it.
        advice = "<br>".join(
            f"{_chip(f'{trap} ×{n}', look.orange, look.orange_chip, look)}&nbsp; "
            f"{escape(TRAP_ADVICE.get(trap, ''))}"
            for trap, n in report.traps
        )
        parts.append(_heading("나의 함정 패턴", look.orange))
        parts.append(
            _box(
                f"<span style='color:{look.ink}'>{lead}<br>"
                f"<span style='line-height:135%'>{advice}</span></span>",
                look.orange,
                look.orange_soft,
                look,
            )
        )
    # Review order.
    if report.review:
        items = "<br>".join(
            f"<span style='color:{look.brand}; font-weight:700'>{CIRCLED[index]}</span> "
            f"<span style='color:{look.ink}'>{escape(point)}</span>"
            for index, point in enumerate(report.review)
        )
        parts.append(_heading("복습 우선순위", look.brand))
        parts.append(_box(items, look.brand, look.brand_soft, look))
    parts.append("</div>")
    return "".join(parts)


def reports_html(
    reports: tuple[StudentReport, ...],
    title: str,
    date: str,
    *,
    numbered: bool = True,
    mono: bool = False,
) -> str:
    pages = "".join(
        report_html(report, title, date, page_break=index > 0, numbered=numbered, mono=mono)
        for index, report in enumerate(reports)
    )
    return page_html(pages)


def page_html(body: str) -> str:
    """The document around one or more student pages."""
    return f"<html><body style='font-size:{BODY_PT}pt'>{body}</body></html>"


__all__ = [
    "CIRCLED",
    "COLOR",
    "MONO",
    "OPTION_COUNT",
    "STRIP_COLUMNS",
    "TRAP_ADVICE",
    "ClassSummary",
    "Mark",
    "Miss",
    "Student",
    "StudentReport",
    "build_reports",
    "page_html",
    "report_html",
    "reports_html",
    "summarize",
]
