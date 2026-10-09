"""Print quiz reports to PDF with Qt's own PDF writer: one grey-scale bundle to print, and one
color file per student to send.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

from quiz_reporter.errors import Err, ErrorInfo, Ok, Result
from quiz_reporter.quiz.report import (
    StudentReport,
    build_reports,
    page_html,
    report_html,
    reports_html,
)
from quiz_reporter.quiz.students import GradedQuiz, safe_filename

_FONT = "Malgun Gothic"


def _print(html: str, path: Path) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(14, 12, 14, 12),
            QPageLayout.Unit.Millimeter,
        )
    )
    writer.setResolution(300)
    writer.setTitle(path.stem)
    document = QTextDocument()
    # Lay out on the PDF device so point sizes mean real points on paper.
    document.documentLayout().setPaintDevice(writer)
    document.setDefaultFont(QFont(_FONT, 9))
    document.setHtml(html)
    layout = writer.pageLayout().paintRectPixels(writer.resolution())
    document.setPageSize(QSizeF(layout.width(), layout.height()))
    document.print_(writer)


def single_names(reports: tuple[StudentReport, ...], title: str, day: str) -> tuple[str, ...]:
    """``이름_학번_yymmdd_퀴즈.pdf`` for each student; a repeated name gets `` (2)``, `` (3)``…

    ``day`` is YYYY-MM-DD (the quiz day); blank leaves the date out.
    """
    stamp = day[2:4] + day[5:7] + day[8:10] if len(day) >= 10 else ""
    seen: dict[str, int] = {}
    names: list[str] = []
    for report in reports:
        student = report.student
        parts = [student.name or "이름없음", student.student_id or "학번확인필요"]
        parts += [stamp] if stamp else []
        stem = safe_filename("_".join([*parts, title]))
        key = stem.casefold()
        seen[key] = seen.get(key, 0) + 1
        names.append(f"{stem} ({seen[key]}).pdf" if seen[key] > 1 else f"{stem}.pdf")
    return tuple(names)


def write_report_pdfs(
    reports: tuple[StudentReport, ...],
    title: str,
    date: str,
    folder: Path,
    *,
    numbered: bool = True,
) -> tuple[Path, tuple[Path, ...]]:
    """``<folder>/전체(인쇄용).pdf`` in grey scale and ``<folder>/개별/<이름>_<학번>_<yymmdd>_<퀴즈>.pdf``
    in color. ``date`` is the quiz day, YYYY-MM-DD.
    """
    folder.mkdir(parents=True, exist_ok=True)
    single = folder / "개별"
    single.mkdir(exist_ok=True)
    bundle = folder / "전체(인쇄용).pdf"
    _print(reports_html(reports, title, date, numbered=numbered, mono=True), bundle)
    files: list[Path] = []
    for report, name in zip(reports, single_names(reports, title, date), strict=True):
        target = single / name
        _print(
            page_html(report_html(report, title, date, page_break=False, numbered=numbered)), target
        )
        files.append(target)
    return bundle, tuple(files)


@dataclass(frozen=True, slots=True)
class QuizReportSummary:
    folder: str
    students: int
    detailed: bool
    bundle: str


def write_quiz_reports(quiz: GradedQuiz, folder: Path) -> Result[QuizReportSummary]:
    """Write the bundle and one PDF per student into ``folder``."""
    if not quiz.students:
        return Err(
            (
                ErrorInfo(
                    "QUIZ_REPORT_FAILED",
                    "error.quiz_report_failed",
                    None,
                    context={"reason": "리포트를 만들 학생이 없습니다."},
                ),
            )
        )
    reports, _ = build_reports(quiz.bank, quiz.students)
    # The day the quiz was taken, not the day of grading; unknown when no answer has a time.
    date = quiz.taken_on
    try:
        bundle, _ = write_report_pdfs(
            reports, quiz.exam_name, date, folder, numbered=not quiz.bank.response_order
        )
    except OSError as exc:
        return Err(
            (
                ErrorInfo(
                    "QUIZ_REPORT_FAILED",
                    "error.quiz_report_failed",
                    None,
                    context={"reason": f"리포트를 저장하지 못했습니다. ({exc.strerror or exc})"},
                ),
            )
        )
    return Ok(QuizReportSummary(str(folder), len(reports), quiz.bank.complete, str(bundle)))


__all__ = ["QuizReportSummary", "single_names", "write_quiz_reports", "write_report_pdfs"]
