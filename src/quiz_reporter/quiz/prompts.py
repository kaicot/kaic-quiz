"""Requests for the AI: write a quiz, fill in a bank skeleton, fix reported problems.

Only questions, options and answers ever go into these texts; never student names or IDs.
The AI may answer with an .xlsx file or with a tab-separated table, which the app can paste.
"""

from __future__ import annotations

import csv
import io
import re

from quiz_reporter.quiz.bank import BANK_HEADERS, BANK_SHEET, READABLE_LIMIT, TRAP_TYPES, QuizBank

_TRAPS = "\n".join(f"  - {name}: {meaning}" for name, meaning in TRAP_TYPES)
_FORMAT = f"""[출력 형식 — 반드시 지켜 주세요]
- 시트 이름 '{BANK_SHEET}'인 .xlsx 파일로 주세요. 파일을 만들 수 없으면, 아래 열 이름을 첫 줄로
  하는 '탭으로 구분한 표(TSV)'를 코드 블록 하나에 넣어 주세요. 칸 안에서 줄을 바꾸지 마세요.
- 열(이 순서 그대로): {", ".join(BANK_HEADERS)}
- 번호: 1부터 차례로. 정답: 1~5 숫자 하나.
- 문제·보기1~5: 구글 폼에 그대로 올릴 글자. 보기는 서로 다르게, 번호(①, 1.)를 붙이지 않음.
- 해설: 정답이 왜 맞는지 1~2문장(아래 '쉬운 말' 규칙을 따름).
- 오답이유1~5: 그 보기를 고른 학생에게 왜 틀렸는지 알려 주는 말. 정답 보기의 칸은 비워 둡니다.
  학생이 리포트에서 그대로 읽으므로 반드시 '쉬운 말' 규칙을 지킵니다.
- 쉬운 말 규칙(해설·오답이유):
  - 대학 1학년이 한 번 읽고 바로 알아듣게, 1~2문장 {READABLE_LIMIT}자 이내로 씁니다.
  - 어려운 한자어와 전문용어는 쉬운 말로 풀어 씁니다. 꼭 필요한 용어는 처음 한 번만 괄호로 뜻을 붙입니다.
  - '~입니다', '~예요' 같은 부드러운 존댓말로, 학생을 탓하지 않습니다.
  - 무엇을 헷갈렸는지와 맞는 내용이 무엇인지를 짧게 짚습니다.
  - 이중부정, 긴 꾸밈말, 번역투('~에 있어서', '~를 통해')는 쓰지 않습니다.
  - 좋은 예: "방실결절은 신호를 잠깐 늦춰 주는 곳이에요. 신호를 처음 만드는 곳은 동방결절입니다."
- 함정유형1~5: 정답이 아닌 보기마다 아래 목록에서 하나만 골라 그대로 적습니다. 정답 보기의 칸은 비움.
{_TRAPS}
- 복습포인트: 이 문항을 틀린 학생이 다시 봐야 할 핵심 개념 한 줄.
- 단원: 교재의 장·절 이름(짧게)."""


def _table(bank: QuizBank) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(BANK_HEADERS)
    for item in bank.items:
        writer.writerow(
            [
                item.number,
                item.unit,
                item.question,
                *item.options,
                "" if item.answer is None else item.answer,
                item.explanation,
                *item.reasons,
                *item.traps,
                item.review,
            ]
        )
    return stream.getvalue()


def completion_request(
    bank: QuizBank | None, problems: str = "", previous: str | None = None
) -> str:
    """One prompt for every follow-up: fill the empty columns and fix whatever the check found.

    ``bank`` is the table as the app holds it; ``previous`` is the AI's last answer when it could
    not be read at all. ``problems`` lists what the app's check found, if anything.
    """
    table = _table(bank) if bank is not None else (previous or "")
    fixes = f"\n\n[프로그램이 찾은 고칠 점]\n{problems}" if problems else ""
    return f"""아래는 5지선다 퀴즈의 문항표입니다. 문제와 보기 글자는 구글 폼과 같아야 하니 절대 바꾸지
말고, 비어 있는 칸(단원, 정답(비어 있으면), 해설, 오답이유, 함정유형, 복습포인트)을 모두 채우고
고칠 점이 있으면 함께 고쳐서, 같은 형식의 전체 문항표로 돌려주세요. 이미 적힌 정답은 그대로 둡니다.{fixes}

{_FORMAT}

[현재 문항표(TSV)]
```
{table}```"""


def bank_text(bank: QuizBank) -> str:
    return _table(bank)


_MARKDOWN_RULE = re.compile(r"^\s*\|?\s*:?-{2,}")


def rows_from_text(text: str) -> list[tuple[object, ...]]:
    """A table pasted from an AI chat: tab-separated (TSV) or a markdown ``| a | b |`` table."""
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    lines = [line for line in lines if not line.strip().startswith("```")]
    if not lines:
        return []
    if any("\t" in line for line in lines):
        return [tuple(row) for row in csv.reader(io.StringIO("\n".join(lines)), delimiter="\t")]
    rows: list[tuple[object, ...]] = []
    for line in lines:
        if _MARKDOWN_RULE.match(line):
            continue
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        rows.append(tuple(cell.strip() for cell in stripped.split("|")))
    return rows


__all__ = [
    "bank_text",
    "completion_request",
    "rows_from_text",
]
