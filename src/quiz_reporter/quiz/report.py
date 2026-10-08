"""Per-student quiz feedback: what was missed, why, which traps keep catching the student, and
what to review first. Pure: the caller supplies graded choices and the bank.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape

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


@dataclass(frozen=True, slots=True)
class Student:
    serial: int
    student_id: str
    name: str
    choices: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class Miss:
    item: QuizItem
    chosen: int | None

    @property
    def reason(self) -> str:
        if self.chosen is None:
            return "답을 고르지 않았습니다."
        return self.item.reasons[self.chosen - 1]

    @property
    def trap(self) -> str:
        return "" if self.chosen is None else self.item.traps[self.chosen - 1]


@dataclass(frozen=True, slots=True)
class UnitRow:
    unit: str
    mine: float
    average: float


@dataclass(frozen=True, slots=True)
class StudentReport:
    student: Student
    score: int
    maximum: int
    average: float
    units: tuple[UnitRow, ...]
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
    units = list(dict.fromkeys(item.unit for item in items if item.unit))
    unit_items = {unit: [item for item in items if item.unit == unit] for unit in units}
    class_unit = {
        unit: (
            sum(summary.correct_rate[item.number - 1] for item in unit_items[unit])
            / len(unit_items[unit])
        )
        for unit in units
    }
    reports: list[StudentReport] = []
    for student in students:
        misses = tuple(
            Miss(item, student.choices[item.number - 1])
            for item in items
            if student.choices[item.number - 1] != item.answer
        )
        right = tuple(
            item.number for item in items if student.choices[item.number - 1] == item.answer
        )
        mine = {
            unit: sum(student.choices[item.number - 1] == item.answer for item in unit_items[unit])
            / len(unit_items[unit])
            for unit in units
        }
        traps = Counter(miss.trap for miss in misses if miss.trap)
        # Weakest units first (furthest below the class), then question order.
        ordered = sorted(
            misses,
            key=lambda miss: (
                mine.get(miss.item.unit, 0) - class_unit.get(miss.item.unit, 0),
                miss.item.number,
            ),
        )
        review = tuple(dict.fromkeys(miss.item.review for miss in ordered if miss.item.review))[:3]
        reports.append(
            StudentReport(
                student,
                len(right),
                len(items),
                summary.average,
                tuple(UnitRow(unit, mine[unit], class_unit[unit]) for unit in units),
                misses,
                right,
                tuple(traps.most_common()),
                review,
            )
        )
    return tuple(reports), summary


# Palette: navy header, blue for "me", grey for the class, red for misses, green for answers.
_NAVY = "#1f3a5f"
_BLUE = "#2563eb"
_TRACK = "#e3e8f0"
_CLASS = "#9aa6b8"
_MUTED = "#6b7280"
_CARD = "#f5f7fb"
_RED, _RED_SOFT = "#b42318", "#fdecea"
_GREEN, _GREEN_SOFT = "#1e7b45", "#e8f5ee"
_ORANGE, _ORANGE_SOFT = "#b45309", "#fff4e5"
_BLUE_SOFT = "#eaf1ff"


def _bar(rate: float, color: str, height: str = "6pt") -> str:
    """A horizontal bar as a one-row table: filled part, then the empty track."""
    filled = max(0, min(100, round(rate * 100)))
    cells = []
    if filled:
        cells.append(
            f"<td width='{filled}%' bgcolor='{color}' style='font-size:{height}'>&nbsp;</td>"
        )
    if filled < 100:
        cells.append(
            f"<td width='{100 - filled}%' bgcolor='{_TRACK}' style='font-size:{height}'>&nbsp;</td>"
        )
    return f"<table width='100%' cellspacing='0' cellpadding='0'><tr>{''.join(cells)}</tr></table>"


def _chip(text: str, color: str, background: str) -> str:
    return (
        f"<span style='background-color:{background}; color:{color}; font-weight:600'>"
        f"&nbsp;{escape(text)}&nbsp;</span>"
    )


def _heading(text: str, color: str = _NAVY) -> str:
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:9px; margin-bottom:3px'>"
        f"<tr><td width='4' bgcolor='{color}'></td><td style='padding-left:6px'>"
        f"<span style='font-size:10.5pt; font-weight:700; color:{color}'>{escape(text)}</span>"
        "</td></tr></table>"
    )


def _box(content: str, accent: str, background: str) -> str:
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:3px'>"
        f"<tr><td width='4' bgcolor='{accent}'></td>"
        f"<td bgcolor='{background}' style='padding:6px 9px'>{content}</td></tr></table>"
    )


def _choice(number: int | None) -> str:
    return "무응답" if number is None else CIRCLED[number - 1]


def report_html(report: StudentReport, title: str, date: str, *, page_break: bool) -> str:
    """One student's A4 page; Qt rich text, so layout is built from tables."""
    s = report.student
    percent = report.score / report.maximum if report.maximum else 0.0
    average = report.average / report.maximum if report.maximum else 0.0
    gap = report.score - report.average
    gap_text = (
        f"<span style='color:{_GREEN}'>반 평균보다 {gap:+.1f}점</span>"
        if gap > 0.05
        else f"<span style='color:{_RED}'>반 평균보다 {gap:+.1f}점</span>"
        if gap < -0.05
        else f"<span style='color:{_MUTED}'>반 평균과 같음</span>"
    )
    parts = [f"<div style='{'page-break-before: always;' if page_break else ''}'>"]
    # Header band.
    parts.append(
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr><td bgcolor='{_NAVY}' style='padding:10px 12px'>"
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td><span style='color:white; font-size:15pt; font-weight:700'>{escape(title)}</span><br>"
        f"<span style='color:#c9d5e6; font-size:8.5pt'>{escape(date)}  ·  학생별 피드백 리포트</span></td>"
        f"<td align='right'><span style='color:white; font-size:14pt; font-weight:700'>{escape(s.name) or '이름 없음'}</span><br>"
        f"<span style='color:#c9d5e6; font-size:9pt'>{escape(s.student_id) or '학번 확인 필요'}</span></td>"
        "</tr></table></td></tr></table>"
    )
    # Score cards.
    right = ", ".join(str(n) for n in report.right) or "없음"
    parts.append(
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:8px'><tr>"
        f"<td width='36%' bgcolor='{_CARD}' style='padding:8px 10px' valign='top'>"
        f"<span style='color:{_MUTED}; font-size:8.5pt'>내 점수</span><br>"
        f"<span style='color:{_BLUE}; font-size:24pt; font-weight:700'>{report.score}</span>"
        f"<span style='font-size:11pt; color:{_MUTED}'> / {report.maximum}  ({round(percent * 100)}%)</span>"
        f"{_bar(percent, _BLUE)}</td>"
        "<td width='2%'></td>"
        f"<td width='30%' bgcolor='{_CARD}' style='padding:8px 10px' valign='top'>"
        f"<span style='color:{_MUTED}; font-size:8.5pt'>반 평균</span><br>"
        f"<span style='font-size:16pt; font-weight:700'>{report.average:.1f}</span>"
        f"<span style='color:{_MUTED}'> / {report.maximum}</span><br>{gap_text}"
        f"{_bar(average, _CLASS)}</td>"
        "<td width='2%'></td>"
        f"<td width='30%' bgcolor='{_CARD}' style='padding:8px 10px' valign='top'>"
        f"<span style='color:{_MUTED}; font-size:8.5pt'>맞힌 문항</span><br>"
        f"<span style='color:{_GREEN}; font-weight:700'>{escape(right)}</span><br>"
        f"<span style='color:{_MUTED}; font-size:8.5pt'>틀린 문항</span> "
        f"<span style='color:{_RED}; font-weight:700'>{len(report.misses)}개</span></td>"
        "</tr></table>"
    )
    # Units: my bar over the class bar.
    if report.units:
        rows = []
        for row in report.units:
            weak = row.mine + 0.2 <= row.average
            flag = _chip("복습", _RED, _RED_SOFT) if weak else ""
            rows.append(
                f"<tr><td width='24%' valign='middle'><b>{escape(row.unit)}</b></td>"
                f"<td width='46%' valign='middle'>{_bar(row.mine, _BLUE, '5pt')}"
                f"<table width='100%' cellspacing='0' cellpadding='0'><tr><td style='font-size:2pt'>&nbsp;</td></tr></table>"
                f"{_bar(row.average, _CLASS, '3pt')}</td>"
                f"<td width='18%' align='right' valign='middle'><span style='color:{_BLUE}; font-weight:700'>"
                f"나 {round(row.mine * 100)}%</span><br><span style='color:{_MUTED}; font-size:8pt'>반 "
                f"{round(row.average * 100)}%</span></td>"
                f"<td width='12%' align='center' valign='middle'>{flag}</td></tr>"
            )
        parts.append(_heading("단원별 정답률"))
        parts.append(
            "<table width='100%' cellspacing='0' cellpadding='3'>" + "".join(rows) + "</table>"
        )
    # Misses as cards.
    if report.misses:
        parts.append(_heading("틀린 문항", _RED))
        for miss in report.misses:
            item = miss.item
            answer = item.answer or 0
            chosen = (
                f"<b>{_choice(miss.chosen)}</b> {escape(item.options[miss.chosen - 1])}"
                if miss.chosen
                else "<b>무응답</b>"
            )
            trap = f" {_chip(miss.trap, _RED, _RED_SOFT)}" if miss.trap else ""
            unit = f"{_chip(item.unit, _NAVY, _BLUE_SOFT)} " if item.unit else ""
            # Why it was wrong sits last, in its own tinted box, after both answers.
            reason = (
                "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:3px'><tr>"
                f"<td bgcolor='{_RED_SOFT}' style='padding:4px 7px'>"
                f"<span style='color:{_RED}; font-weight:700'>틀린 이유</span>&nbsp;&nbsp;"
                f"<span style='color:#3f1d1d'>{escape(miss.reason)}</span></td></tr></table>"
                if miss.reason
                else ""
            )
            content = (
                f"<span style='color:{_NAVY}; font-weight:700'>{item.number}번</span>&nbsp; {unit}"
                f"{escape(item.question)}<br>"
                f"<span style='color:{_MUTED}'>내가 고른 답</span>&nbsp; {chosen}{trap}<br>"
                f"<span style='color:{_GREEN}; font-weight:700'>정답</span>&nbsp; "
                f"<span style='color:{_GREEN}; font-weight:700'>{CIRCLED[answer - 1]}</span> "
                f"<span style='color:{_GREEN}'>{escape(item.options[answer - 1])}</span>"
                f"{reason}"
            )
            parts.append(_box(content, _RED, "#fbfbfd"))
    else:
        parts.append(
            _box(
                f"<span style='color:{_GREEN}; font-size:12pt; font-weight:700'>모든 문항을 맞혔습니다. 훌륭합니다!</span>",
                _GREEN,
                _GREEN_SOFT,
            )
        )
    # Trap pattern.
    if report.traps:
        top, count = report.traps[0]
        lead = (
            f"틀린 {len(report.misses)}문항 중 <b>{count}개</b>가 "
            f"<span style='color:{_ORANGE}; font-weight:700'>{escape(top)}</span>입니다."
            if count >= 2
            else "틀린 문항을 함정 유형별로 모았습니다."
        )
        chips = " ".join(_chip(f"{trap} ×{n}", _ORANGE, "#ffe8cc") for trap, n in report.traps)
        advice = "<br>".join(
            f"<b>{escape(trap)}</b> — {escape(TRAP_ADVICE.get(trap, ''))}"
            for trap, _ in report.traps
        )
        parts.append(_heading("나의 함정 패턴", _ORANGE))
        parts.append(
            _box(
                f"{lead}<br>{chips}<br><span style='line-height:140%'>{advice}</span>",
                _ORANGE,
                _ORANGE_SOFT,
            )
        )
    # Review order.
    if report.review:
        items = "<br>".join(
            f"<span style='color:{_BLUE}; font-weight:700'>{CIRCLED[index]}</span> {escape(point)}"
            for index, point in enumerate(report.review)
        )
        parts.append(_heading("복습 우선순위", _BLUE))
        parts.append(_box(items, _BLUE, _BLUE_SOFT))
    parts.append(
        "<p align='right' style='margin-top:8px; color:#9aa3b2; font-size:7.5pt'>퀴즈 리포터 · 학생별 피드백</p>"
    )
    parts.append("</div>")
    return "".join(parts)


def reports_html(reports: tuple[StudentReport, ...], title: str, date: str) -> str:
    pages = "".join(
        report_html(report, title, date, page_break=index > 0)
        for index, report in enumerate(reports)
    )
    return f"<html><body style='font-size:9pt'>{pages}</body></html>"


__all__ = [
    "CIRCLED",
    "OPTION_COUNT",
    "TRAP_ADVICE",
    "ClassSummary",
    "Miss",
    "Student",
    "StudentReport",
    "build_reports",
    "report_html",
    "reports_html",
    "summarize",
]
