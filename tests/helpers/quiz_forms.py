"""Synthetic Google Forms quizzes shaped like real downloads (no real students)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from openpyxl import Workbook

from quiz_reporter.quiz.bank import QuizBank, QuizItem

QUESTIONS = (
    (
        "심장의 전도계에서 흥분이 시작되는 곳은?",
        (
            "방실결절, 심방과 심실 사이",
            "히스다발, 심실중격 위쪽",
            "동방결절, 우심방 벽",
            "푸르키녜섬유, 심실벽 안쪽",
            "좌심방, 폐정맥 입구",
        ),
        3,
        "심장 생리",
    ),
    (
        "들숨 때 일어나는 변화로 옳은 것은?",
        (
            "가로막 이완, 흉강 부피 감소",
            "가로막 수축, 흉강 부피 증가",
            "가로막 수축, 폐포 압력 증가",
            "바깥갈비사이근 이완, 흉강 부피 증가",
            "가로막 이완, 폐포 압력 감소",
        ),
        2,
        "호흡 생리",
    ),
    (
        "정상 성인의 안정 시 공복 혈당 범위로 가장 가까운 것은?",
        ("-10~10 mg/dL", "30~50 mg/dL", "70~100 mg/dL", "200~250 mg/dL", "+400 mg/dL 이상"),
        3,
        "내분비",
    ),
)
TRAPS = ("수치 혼동", "방향·순서 혼동", "개념 혼동", "반대 개념", "부분만 맞음")
START = datetime(2026, 10, 6, 13, 11, 0)

# (minutes after start, student id as typed, name, chosen option per question)
ROWS = (
    (0, "20260001", "가나", (3, 2, 3)),
    (1, "20260002", "다라", (2, 3, 3)),
    (2, "20260003", "마바", (1, 1, 2)),
    (3, "2026004", "사아", (3, 2, 2)),  # seven digits: flagged
    (4, "20260002", "다라", (3, 2, 3)),  # second try in class: first one counts
    (60 * 26, "1234", "복습", (3, 2, 3)),  # next day, self-study
)


def _stamp(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    meridiem = "오후" if moment.hour >= 12 else "오전"
    return f"{moment:%Y/%m/%d} {hour}:{moment:%M:%S} {meridiem} GMT+9"


def form_csv(rows=ROWS) -> bytes:
    """The form's own CSV in quiz mode: answer, [점수] and [의견] per question."""
    stream = io.StringIO()
    writer = csv.writer(stream)
    header = [
        "타임스탬프",
        "총점",
        "이름",
        "이름[점수]",
        "이름[의견]",
        "학번",
        "학번[점수]",
        "학번[의견]",
    ]
    for question, _, _, _ in QUESTIONS:
        header += [question, f"{question}[점수]", f"{question}[의견]"]
    writer.writerow(header)
    for minutes, student_id, name, choices in rows:
        right = [
            choice == answer for choice, (_, _, answer, _) in zip(choices, QUESTIONS, strict=True)
        ]
        line = [
            _stamp(START + timedelta(minutes=minutes)),
            f"{sum(right):.2f} / {len(QUESTIONS) + 2}",
        ]
        line += [name, "-- / 1", "", student_id, "-- / 1", ""]
        for choice, ok, (_, options, _, _) in zip(choices, right, QUESTIONS, strict=True):
            line += [options[choice - 1], f"{1 if ok else 0:.2f} / 1", ""]
        writer.writerow(line)
    return stream.getvalue().encode("utf-8")


def form_xlsx(rows=ROWS) -> bytes:
    """The linked spreadsheet: total score only, IDs as numbers."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "설문지 응답 시트1"
    sheet.append(
        ["타임스탬프", "점수", "이름", "학번", *(question for question, _, _, _ in QUESTIONS)]
    )
    for minutes, student_id, name, choices in rows:
        right = sum(
            choice == answer for choice, (_, _, answer, _) in zip(choices, QUESTIONS, strict=True)
        )
        identifier: object = float(student_id) if student_id.isdigit() else student_id
        sheet.append(
            [
                START + timedelta(minutes=minutes),
                float(right),
                name,
                identifier,
                *(
                    options[choice - 1]
                    for choice, (_, options, _, _) in zip(choices, QUESTIONS, strict=True)
                ),
            ]
        )
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def full_bank() -> QuizBank:
    items = []
    for number, (question, options, answer, unit) in enumerate(QUESTIONS, 1):
        reasons = tuple(
            "" if index + 1 == answer else f"보기{index + 1}을 고르면 {TRAPS[index]}입니다."
            for index in range(5)
        )
        traps = tuple("" if index + 1 == answer else TRAPS[index] for index in range(5))
        items.append(
            QuizItem(
                number,
                unit,
                question,
                options,
                answer,
                f"{number}번 해설",
                reasons,
                traps,
                f"{unit} 핵심 정리",
            )
        )
    return QuizBank(tuple(items))
