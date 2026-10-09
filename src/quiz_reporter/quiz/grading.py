"""Turn form responses into graded answers: the class-time window, first submissions, and the
option number each answer text stands for.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.quiz.bank import OPTION_COUNT, QuizBank, QuizItem, normalize
from quiz_reporter.quiz.responses import KST, FormResponse, FormResponses

# Answers more than this far apart belong to different sittings (class vs. later review).
SITTING_GAP = timedelta(minutes=30)
_ID = re.compile(r"\d{8}")


@dataclass(frozen=True, slots=True)
class Selection:
    kept: tuple[FormResponse, ...]
    late: tuple[FormResponse, ...]
    repeats: tuple[FormResponse, ...]
    cutoff: datetime | None


@dataclass(frozen=True, slots=True)
class Sitting:
    """Answers with no gap over ``SITTING_GAP`` between them: one class, or one later review."""

    start: datetime
    end: datetime
    answers: int


def sittings(responses: FormResponses) -> tuple[Sitting, ...]:
    times = sorted(row.submitted_at for row in responses.rows if row.submitted_at is not None)
    groups: list[list[datetime]] = []
    for moment in times:
        if groups and moment - groups[-1][-1] <= SITTING_GAP:
            groups[-1].append(moment)
        else:
            groups.append([moment])
    return tuple(Sitting(group[0], group[-1], len(group)) for group in groups)


def suggest_cutoff(responses: FormResponses) -> datetime | None:
    """The end of the busiest sitting, or ``None`` when every answer belongs to one sitting."""
    found = sittings(responses)
    if len(found) <= 1:
        return None
    return max(found, key=lambda sitting: sitting.answers).end


def quiz_day(selection: Selection) -> date | None:
    """The day the quiz was taken: the day most kept answers were sent (Korea time)."""
    days = Counter(
        row.submitted_at.astimezone(KST).date() for row in selection.kept if row.submitted_at
    )
    if not days:
        return None
    return max(days, key=lambda day: (days[day], -day.toordinal()))


def _whole_second(moment: datetime) -> datetime:
    return moment.replace(microsecond=0)


def select(responses: FormResponses, cutoff: datetime | None) -> Selection:
    """Answers up to ``cutoff``; a student who answered twice counts with the first answer."""
    ordered = sorted(
        responses.rows,
        key=lambda row: (row.submitted_at is None, row.submitted_at or datetime.min, row.row),
    )
    late = tuple(
        row
        for row in ordered
        if cutoff is not None
        and row.submitted_at is not None
        and _whole_second(row.submitted_at) > _whole_second(cutoff)
    )
    window = [row for row in ordered if row not in late]
    kept: list[FormResponse] = []
    repeats: list[FormResponse] = []
    seen: set[str] = set()
    for row in window:
        key = row.student_id
        if key and key in seen:
            repeats.append(row)
            continue
        if key:
            seen.add(key)
        kept.append(row)
    return Selection(tuple(kept), late, tuple(repeats), cutoff)


def valid_student_id(text: str) -> bool:
    return _ID.fullmatch(text) is not None


def _problem(reason: str) -> ErrorInfo:
    return ErrorInfo(
        "QUIZ_MATCH_FAILED", "error.quiz_match_failed", None, context={"reason": reason}
    )


@dataclass(frozen=True, slots=True)
class AnswerSheet:
    """Each question's option texts (1..5) and its answer, as used for grading."""

    options: tuple[tuple[str, ...], ...]
    answers: tuple[int | None, ...]
    # Options numbered as answers appeared in the responses (from CSV scores).
    from_responses: bool = False


def sheet_from_bank(responses: FormResponses, bank: QuizBank) -> Result[AnswerSheet]:
    """Check the form against the bank: same questions in the same order, every answer an option."""
    problems: list[str] = []
    if len(bank.items) != len(responses.questions):
        problems.append(
            f"문항 수가 다릅니다: 응답 파일 {len(responses.questions)}문항, 문항표"
            f" {len(bank.items)}문항."
        )
    for index, (title, item) in enumerate(zip(responses.questions, bank.items, strict=False), 1):
        if normalize(title) != normalize(item.question):
            problems.append(
                f"{index}번 문항의 문제 글자가 폼과 다릅니다. 폼: '{title[:60]}' / 문항표:"
                f" '{item.question[:60]}'"
            )
    if not problems:
        for index, item in enumerate(bank.items):
            known = {normalize(option) for option in item.options}
            unknown = sorted(
                {
                    row.answers[index]
                    for row in responses.rows
                    if row.answers[index] and normalize(row.answers[index]) not in known
                }
            )
            for text in unknown[:3]:
                problems.append(
                    f"{item.number}번 문항: 응답 '{text[:60]}'이(가) 문항표 보기에 없습니다."
                )
    if problems:
        return Err(tuple(_problem(text) for text in problems))
    return Ok(
        AnswerSheet(
            tuple(tuple(item.options) for item in bank.items),
            tuple(item.answer for item in bank.items),
            bank.response_order,
        )
    )


def sheet_from_scores(responses: FormResponses) -> Result[AnswerSheet]:
    """Without a bank: options in the order students chose them, answers from [점수] columns.

    Questions nobody answered correctly have no known answer and are left out of grading.
    """
    if not responses.has_item_scores:
        return Err(
            (
                _problem(
                    "이 응답 파일에는 문항별 정답 여부가 없습니다(구글 스프레드시트 xlsx)."
                    " 문항표를 고르거나, 구글 폼에서 받은 CSV를 쓰세요."
                ),
            )
        )
    options: list[tuple[str, ...]] = []
    answers: list[int | None] = []
    problems: list[str] = []
    for index in range(len(responses.questions)):
        seen: list[str] = []
        right: set[str] = set()
        for row in responses.rows:
            text = row.answers[index]
            if text and text not in seen:
                seen.append(text)
            if text and row.correct[index]:
                right.add(text)
        if len(seen) > OPTION_COUNT:
            problems.append(
                f"{index + 1}번 문항에 서로 다른 응답이 {len(seen)}가지입니다(5지선다가 아님)."
            )
            continue
        if len(right) > 1:
            problems.append(f"{index + 1}번 문항에서 정답 처리된 응답이 여러 가지입니다.")
            continue
        options.append(tuple(seen) + ("",) * (OPTION_COUNT - len(seen)))
        answers.append(seen.index(right.pop()) + 1 if right else None)
    if problems:
        return Err(tuple(_problem(text) for text in problems))
    return Ok(AnswerSheet(tuple(options), tuple(answers), from_responses=True))


def sheet_from_form(
    responses: FormResponses, questions: tuple[tuple[str, tuple[str, ...]], ...]
) -> Result[AnswerSheet]:
    """Options in the form's own order (from its public page); answers from [점수] when present.

    ``questions`` holds each form question's title and options. Without [점수] columns the
    answers stay empty for the AI to fill in the 문항표.
    """
    problems: list[str] = []
    if len(questions) != len(responses.questions):
        problems.append(
            f"폼의 객관식 문항 수({len(questions)})와 응답 파일의 문항 수"
            f"({len(responses.questions)})가 다릅니다. 같은 폼의 주소와 응답인지 확인하세요."
        )
        return Err(tuple(_problem(text) for text in problems))
    options_out: list[tuple[str, ...]] = []
    answers: list[int | None] = []
    for index, ((title, options), answered_title) in enumerate(
        zip(questions, responses.questions, strict=True)
    ):
        if normalize(title) != normalize(answered_title):
            problems.append(f"{index + 1}번 문항의 제목이 폼과 응답 파일에서 다릅니다.")
            continue
        if len(options) != OPTION_COUNT:
            problems.append(f"{index + 1}번 문항의 보기가 {len(options)}개입니다(5지선다가 아님).")
            continue
        normalized = [normalize(option) for option in options]
        right = {
            normalize(row.answers[index])
            for row in responses.rows
            if row.answers[index] and row.correct[index]
        }
        if len(right) > 1:
            problems.append(f"{index + 1}번 문항에서 정답 처리된 응답이 여러 가지입니다.")
            continue
        correct_text = next(iter(right), None)
        answer = normalized.index(correct_text) + 1 if correct_text in normalized else None
        options_out.append(tuple(options))
        answers.append(answer)
    if problems:
        return Err(tuple(_problem(text) for text in problems))
    return Ok(AnswerSheet(tuple(options_out), tuple(answers)))


def bank_from_sheet(responses: FormResponses, sheet: AnswerSheet, units: str = "") -> QuizBank:
    """A bank holding only questions, options and answers (feedback columns empty)."""
    empty = ("",) * OPTION_COUNT
    return QuizBank(
        tuple(
            QuizItem(number, units, title, options, answer, "", empty, empty, "")
            for number, (title, options, answer) in enumerate(
                zip(responses.questions, sheet.options, sheet.answers, strict=True), 1
            )
        ),
        response_order=sheet.from_responses,
    )


def choice_numbers(row: FormResponse, sheet: AnswerSheet) -> tuple[int | None, ...]:
    """The option number of each answer, ``None`` for a blank."""
    numbers: list[int | None] = []
    for text, options in zip(row.answers, sheet.options, strict=True):
        if not text:
            numbers.append(None)
            continue
        wanted = normalize(text)
        found = next(
            (index + 1 for index, option in enumerate(options) if normalize(option) == wanted),
            None,
        )
        numbers.append(found)
    return tuple(numbers)


__all__ = [
    "AnswerSheet",
    "SITTING_GAP",
    "Selection",
    "Sitting",
    "bank_from_sheet",
    "choice_numbers",
    "quiz_day",
    "select",
    "sheet_from_bank",
    "sheet_from_scores",
    "sittings",
    "suggest_cutoff",
    "valid_student_id",
]
