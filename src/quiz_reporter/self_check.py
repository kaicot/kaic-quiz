"""``Quiz Reporter.exe --self-check <result.json>``: prove a built program works, then exit.

Grades a tiny built-in quiz (synthetic students only) in a temporary folder, writes the reports
and the result workbook, rebuilds it once, and records each check in ``result.json``. Packaging
is where fonts, the PDF writer or the Excel library can go missing; tests run from source can't
see that. Nothing is shown and nothing outside the temporary folder is touched.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import quiz_reporter
from quiz_reporter.errors import Err, Ok
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.quiz.bank import QuizBank, QuizItem
from quiz_reporter.quiz.grading import suggest_cutoff
from quiz_reporter.quiz.responses import read_form_responses
from quiz_reporter.startup import prepare
from quiz_reporter.storage.quiz_store import QuizStore, ReportWriter

FLAG = "--self-check"
# Fonts with Hangul glyphs (Windows and common free ones); any other font would print boxes.
KOREAN_FONTS = (
    "Malgun", "Gulim", "Dotum", "Batang", "Gungsuh", "Nanum",
    "NotoSansKR", "NotoSansCJK", "NotoSerifKR", "SourceHanSans",
)  # fmt: skip
# (question, options, answer); synthetic content only.
_QUESTIONS = (
    ("가상 문항 1: 셋 중 가장 큰 수는?", ("1", "2", "3", "4", "5"), 5),
    ("가상 문항 2: 짝수는?", ("1", "3", "4", "5", "7"), 3),
)
# (minutes after start, student ID, name, choices); a repeat and a late answer are left out.
_ROWS = (
    (0, "20260001", "가나", (5, 3)),
    (1, "20260002", "다라", (4, 3)),
    (2, "20260003", "마바", (5, 1)),
    (3, "20260002", "다라", (5, 3)),
    (60 * 26, "20260004", "복습", (5, 3)),
)
_START = datetime(2026, 10, 6, 13, 0, 0)


def _stamp(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return (
        f"{moment:%Y/%m/%d} {hour}:{moment:%M:%S} {'오후' if moment.hour >= 12 else '오전'} GMT+9"
    )


def _form_csv() -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream)
    header = ["타임스탬프", "총점", "이름", "학번"]
    for question, _, _ in _QUESTIONS:
        header += [question, f"{question}[점수]", f"{question}[의견]"]
    writer.writerow(header)
    for minutes, student_id, name, choices in _ROWS:
        line = [_stamp(_START + timedelta(minutes=minutes)), "", name, student_id]
        for choice, (_, options, answer) in zip(choices, _QUESTIONS, strict=True):
            line += [options[choice - 1], f"{1 if choice == answer else 0:.2f} / 1", ""]
        writer.writerow(line)
    return stream.getvalue().encode("utf-8")


def _bank() -> QuizBank:
    items = []
    for number, (question, options, answer) in enumerate(_QUESTIONS, 1):
        reasons = tuple(
            "" if i + 1 == answer else f"보기{i + 1}은 가상 오답입니다." for i in range(5)
        )
        traps = tuple("" if i + 1 == answer else "개념 혼동" for i in range(5))
        items.append(
            QuizItem(
                number, "가상 단원", question, options, answer, "가상 해설", reasons, traps, "복습"
            )
        )
    return QuizBank(tuple(items))


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def _fonts(data: bytes) -> list[str]:
    names = re.findall(rb"/BaseFont\s*/([A-Za-z0-9+#_-]+)", data)
    return sorted({name.decode("ascii", "replace") for name in names})


def run(report: Path, writer: ReportWriter | None = None) -> bool:
    """Run every check and write ``report``; ``True`` when all passed."""
    if writer is None:
        from quiz_reporter.ui.quiz_pdf import write_quiz_reports

        writer = write_quiz_reports
    chosen: ReportWriter = writer
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    try:
        work = Path(tempfile.mkdtemp(prefix="quiz-reporter-self-check-"))
    except OSError as exc:
        check("temporary folder", False, str(exc))
        return _finish(report, checks)
    try:
        root = work / "Quiz-Reporter"
        root.mkdir()
        state = prepare(ManagedPaths.from_root(root), quiz_reporter.__version__)
        check(
            "data folder and format marker",
            state.writable and (root / "Data" / "FORMAT.json").is_file(),
        )
        source = work / "가상 퀴즈(응답).csv"
        source.write_bytes(_form_csv())
        responses = read_form_responses(str(source))
        if not check("read the response CSV", isinstance(responses, Ok)):
            return _finish(report, checks)
        assert isinstance(responses, Ok)
        store = QuizStore(state.paths, chosen, app_version=quiz_reporter.__version__)
        created = store.create("가상 퀴즈", source, suggest_cutoff(responses.value), _bank())
        if not check("grade and save", isinstance(created, Ok), _reason(created)):
            return _finish(report, checks)
        assert isinstance(created, Ok)
        folder = created.value.path
        data = (folder / "리포트" / "전체(인쇄용).pdf").read_bytes()
        pages = _pdf_pages(data)
        check("bundle PDF, one page per student", pages == 3, f"pages={pages}")
        singles = list((folder / "리포트" / "개별").glob("*.pdf"))
        check("one PDF per student", len(singles) == 3, f"files={len(singles)}")
        fonts = _fonts(data)
        korean = any(name in font for font in fonts for name in KOREAN_FONTS)
        check("a Korean font is embedded", korean, ", ".join(fonts))

        from openpyxl import load_workbook

        book = load_workbook(folder / "채점결과.xlsx", read_only=True)
        try:
            names = list(book.sheetnames)
            first = [
                row for row in book["채점결과"].iter_rows(min_row=4, max_row=6, values_only=True)
            ]
        finally:
            book.close()
        check("result workbook sheets", names[:2] == ["채점결과", "문항 분석"], ", ".join(names))
        check(
            "result workbook scores",
            [line[3] for line in first] == [2, 1, 1],
            str([line[3] for line in first]),
        )
        rebuilt = store.replace_bank(created.value.folder, _bank())
        check("rebuild with a 문항표", isinstance(rebuilt, Ok), _reason(rebuilt))
        deleted = store.delete(created.value.folder)
        check("delete to trash", isinstance(deleted, Ok), _reason(deleted))
        restored = store.restore(created.value.folder)
        check("restore from trash", isinstance(restored, Ok), _reason(restored))
    except Exception as exc:  # recorded, never raised: the caller only reads the report
        check("no unexpected error", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return _finish(report, checks)


def _reason(result: object) -> str:
    return str(result.errors[0].context.get("reason", "")) if isinstance(result, Err) else ""


def _finish(report: Path, checks: list[dict[str, object]]) -> bool:
    passed = all(item["ok"] for item in checks)
    payload = {
        "version": quiz_reporter.__version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "passed": passed,
        "checks": checks,
    }
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return passed


__all__ = ["FLAG", "run"]
