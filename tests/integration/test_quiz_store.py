"""Saved quizzes: create, list, reopen, rebuild with a new 문항표, trash and recovery."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from quiz_reporter.errors import Err, Ok, Result
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.quiz.bank import QuizBank
from quiz_reporter.quiz.form_page import FormPage, FormQuestion
from quiz_reporter.quiz.grading import (
    bank_from_sheet,
    select,
    sheet_from_bank,
    sheet_from_form,
    sheet_from_scores,
    suggest_cutoff,
)
from quiz_reporter.quiz.responses import KST, read_form_responses
from quiz_reporter.quiz.students import GradedQuiz, students_from_selection
from quiz_reporter.storage.quiz_info import INFO_FILENAME, read_quiz_info
from quiz_reporter.storage.quiz_store import PARKED_PREFIX, STAGING_PREFIX, QuizStore
from tests.helpers.quiz_forms import QUESTIONS, form_csv, form_xlsx, full_bank

START = datetime(2026, 10, 6, 13, 20, 0, tzinfo=KST)


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _Writer:
    """Stands in for the PDF writer: one marker file per student, and what it was asked."""

    def __init__(self) -> None:
        self.calls: list[GradedQuiz] = []
        self.fail = False

    def __call__(self, quiz: GradedQuiz, folder: Path) -> Result[object]:
        self.calls.append(quiz)
        if self.fail:
            return Err(read_quiz_info(folder).errors)  # any Err will do
        (folder / "개별").mkdir(parents=True)
        (folder / "전체(인쇄용).pdf").write_bytes(b"%PDF bundle")
        for student in quiz.students:
            (folder / "개별" / f"{student.serial:03d}.pdf").write_bytes(b"%PDF")
        return Ok(None)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "Quiz-Reporter"
    root.mkdir()
    writer = _Writer()
    store = QuizStore(ManagedPaths.from_root(root), writer, app_version="1.0.0", clock=_Clock())
    csv = tmp_path / "생리 퀴즈(응답).csv"
    csv.write_bytes(form_csv())
    return store, writer, csv, root


def _cutoff(path: Path):
    responses = read_form_responses(str(path))
    assert isinstance(responses, Ok)
    return responses.value, suggest_cutoff(responses.value)


def test_a_new_quiz_keeps_its_originals_and_lists_its_summary(setup):
    store, writer, csv, root = setup
    responses, cutoff = _cutoff(csv)

    created = store.create(
        "생리 퀴즈", csv, cutoff, full_bank(), sheet_from_bank(responses, full_bank()).value
    )

    assert isinstance(created, Ok), created
    folder = created.value.path
    assert folder == root / "Data" / "261006_132001_생리 퀴즈"
    assert sorted(path.name for path in folder.iterdir()) == [
        "리포트",
        "문항표.xlsx",
        "응답원본.csv",
        "퀴즈정보.json",
    ]
    assert (folder / "응답원본.csv").read_bytes() == csv.read_bytes()
    assert len(list((folder / "리포트" / "개별").iterdir())) == 4
    info = json.loads((folder / INFO_FILENAME).read_text(encoding="utf-8"))
    assert info["name"] == "생리 퀴즈"
    assert info["source_name"] == "생리 퀴즈(응답).csv"
    assert info["cutoff"] == "2026-10-06T13:15:00+09:00"
    assert info["summary"] == {
        "students": 4,
        "flagged": 1,
        "late": 1,
        "repeats": 1,
        "questions": 3,
        "maximum": 3,
        "average": 1.5,
        "detailed": True,
    }
    assert writer.calls[0].exam_name == "생리 퀴즈"
    assert [entry.folder for entry in store.list_quizzes()] == ["261006_132001_생리 퀴즈"]
    assert not [path for path in (root / "Data").iterdir() if path.name.startswith(".")]


def test_reopening_grades_again_to_the_same_students(setup):
    store, writer, csv, _ = setup
    responses, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)

    opened = store.open(created.value.folder)

    assert isinstance(opened, Ok), opened
    expected = students_from_selection(
        select(responses, cutoff), sheet_from_bank(responses, full_bank()).value
    )
    assert opened.value.graded.students == expected
    assert opened.value.graded.bank == full_bank()
    assert [student.name for student in writer.calls[0].students] == [
        "가나",
        "다라",
        "마바",
        "사아",
    ]


def test_a_quiz_graded_from_csv_scores_reopens_from_its_saved_bank(setup):
    store, _, csv, _ = setup
    responses, cutoff = _cutoff(csv)
    sheet = sheet_from_scores(responses).value
    bank = bank_from_sheet(responses, sheet)

    created = store.create("기본형", csv, cutoff, bank, sheet)
    assert isinstance(created, Ok), created

    opened = store.open(created.value.folder)
    assert isinstance(opened, Ok), opened
    assert opened.value.graded.sheet == sheet
    assert not opened.value.info.summary.detailed


def test_a_quiz_made_from_the_public_form_page_reopens_the_same_way(setup):
    store, _, csv, _ = setup
    responses, cutoff = _cutoff(csv)
    form = FormPage("생리 퀴즈", tuple(FormQuestion(q, options) for q, options, _, _ in QUESTIONS))
    sheet = sheet_from_form(responses, tuple((q.title, q.options) for q in form.questions)).value
    bank = bank_from_sheet(responses, sheet)

    created = store.create("폼 틀", csv, cutoff, bank, sheet)

    assert isinstance(created, Ok), created
    opened = store.open(created.value.folder)
    assert isinstance(opened, Ok)
    assert opened.value.graded.sheet == sheet


def test_a_screen_sheet_that_the_bank_would_not_reproduce_is_refused(setup):
    store, _, csv, root = setup
    responses, cutoff = _cutoff(csv)
    other = sheet_from_scores(responses).value

    result = store.create("생리 퀴즈", csv, cutoff, full_bank(), other)

    assert isinstance(result, Err)
    assert "채점 기준과 문항표가 다릅니다" in result.errors[0].context["reason"]
    assert list((root / "Data").iterdir()) == []


def test_a_spreadsheet_copy_keeps_its_extension(setup, tmp_path):
    store, _, _, _ = setup
    xlsx = tmp_path / "응답.xlsx"
    xlsx.write_bytes(form_xlsx())
    responses, cutoff = _cutoff(xlsx)

    created = store.create("시트", xlsx, cutoff, full_bank())

    assert isinstance(created, Ok), created
    assert (created.value.path / "응답원본.xlsx").read_bytes() == xlsx.read_bytes()
    assert created.value.info is not None
    assert created.value.info.responses_file == "응답원본.xlsx"


def test_the_same_name_in_the_same_second_gets_a_suffix(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)
    store._clock = lambda: START  # type: ignore[method-assign]

    first = store.create("생리 퀴즈", csv, cutoff, full_bank())
    second = store.create("생리 퀴즈", csv, cutoff, full_bank())

    assert isinstance(first, Ok) and isinstance(second, Ok)
    assert second.value.folder == first.value.folder + "_2"


def test_unsafe_and_long_names_become_safe_folder_names(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)

    created = store.create('신경계: "4주차"/5주차?' + "가" * 60, csv, cutoff, full_bank())

    assert isinstance(created, Ok), created
    folder = created.value.folder
    assert folder.startswith("261006_132001_신경계_ _4주차_5주차_")
    assert len(folder) <= len("261006_132001_") + 40


def test_a_failed_report_leaves_nothing_behind(setup):
    store, writer, csv, root = setup
    _, cutoff = _cutoff(csv)
    writer.fail = True

    result = store.create("생리 퀴즈", csv, cutoff, full_bank())

    assert isinstance(result, Err)
    assert list((root / "Data").iterdir()) == []


def test_a_new_bank_rebuilds_the_reports_and_keeps_the_originals(setup):
    store, writer, csv, _ = setup
    _, cutoff = _cutoff(csv)
    full = full_bank()
    first = full.items[0]
    blank = first.__class__(
        first.number, first.unit, first.question, first.options, first.answer, "",
        first.reasons, first.traps, first.review,
    )  # fmt: skip
    created = store.create("생리 퀴즈", csv, cutoff, QuizBank((blank, *full.items[1:])))
    assert isinstance(created, Ok) and created.value.info is not None
    assert not created.value.info.summary.detailed
    folder = created.value.path
    (folder / "리포트" / "개별" / "옛것.pdf").write_bytes(b"old")
    (folder / "메모.txt").write_text("사용자가 둔 파일", encoding="utf-8")

    rebuilt = store.replace_bank(created.value.folder, full)

    assert isinstance(rebuilt, Ok), rebuilt
    assert rebuilt.value.info is not None
    assert rebuilt.value.info.summary.detailed
    assert rebuilt.value.info.created_at == created.value.info.created_at
    assert rebuilt.value.info.graded_at > created.value.info.graded_at
    assert writer.calls[-1].bank == full
    assert not (folder / "리포트" / "개별" / "옛것.pdf").exists()
    assert len(list((folder / "리포트" / "개별").iterdir())) == 4
    assert (folder / "메모.txt").read_text(encoding="utf-8") == "사용자가 둔 파일"
    assert (folder / "응답원본.csv").read_bytes() == csv.read_bytes()
    reopened = store.open(created.value.folder)
    assert isinstance(reopened, Ok)
    assert reopened.value.graded.bank == full
    assert [path.name for path in folder.parent.iterdir()] == [created.value.folder]


def test_a_bank_that_does_not_fit_the_form_changes_nothing(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    before = (created.value.path / "문항표.xlsx").read_bytes()
    wrong = QuizBank(full_bank().items[:2])

    result = store.replace_bank(created.value.folder, wrong)

    assert isinstance(result, Err)
    assert "문항 수가 다릅니다" in result.errors[0].context["reason"]
    assert (created.value.path / "문항표.xlsx").read_bytes() == before


def test_trash_restore_and_purge(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    name = created.value.folder

    deleted = store.delete(name)

    assert isinstance(deleted, Ok)
    assert store.list_quizzes() == ()
    assert [entry.folder for entry in store.list_trash()] == [name]
    assert (root / "Data" / "_휴지통" / name / "퀴즈정보.json").exists()

    restored = store.restore(name)
    assert isinstance(restored, Ok)
    assert [entry.folder for entry in store.list_quizzes()] == [name]
    assert store.list_trash() == ()

    assert isinstance(store.delete(name), Ok)
    assert isinstance(store.purge(name), Ok)
    assert store.list_trash() == ()
    assert isinstance(store.purge(name), Err)


def test_restoring_onto_a_name_in_use_adds_a_suffix(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)
    store._clock = lambda: START  # type: ignore[method-assign]
    first = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(first, Ok)
    assert isinstance(store.delete(first.value.folder), Ok)
    again = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(again, Ok) and again.value.folder == first.value.folder

    restored = store.restore(first.value.folder)

    assert isinstance(restored, Ok)
    assert restored.value.folder == first.value.folder + "_2"


def test_an_open_report_blocks_delete_and_the_quiz_stays(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)

    with open(created.value.path / "리포트" / "전체(인쇄용).pdf", "rb"):
        result = store.delete(created.value.folder)

    assert isinstance(result, Err)
    assert "열려 있습니다" in result.errors[0].context["reason"]
    assert created.value.path.is_dir()
    assert store.list_trash() == ()


def test_an_open_report_blocks_a_rebuild_and_the_old_quiz_stays(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    before = (created.value.path / "퀴즈정보.json").read_bytes()

    with open(created.value.path / "리포트" / "전체(인쇄용).pdf", "rb"):
        result = store.replace_bank(created.value.folder, full_bank())

    assert isinstance(result, Err)
    assert "열려 있습니다" in result.errors[0].context["reason"]
    assert (created.value.path / "퀴즈정보.json").read_bytes() == before
    assert [path.name for path in (root / "Data").iterdir()] == [created.value.folder]


def test_unreadable_folders_are_listed_with_the_reason(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    assert isinstance(store.create("생리 퀴즈", csv, cutoff, full_bank()), Ok)
    broken = root / "Data" / "261001_090000_망가진 퀴즈"
    broken.mkdir()
    (broken / INFO_FILENAME).write_text("{", encoding="utf-8")
    newer = root / "Data" / "261002_090000_새 버전"
    newer.mkdir()
    (newer / INFO_FILENAME).write_text(
        json.dumps({"format": 2, "app_version": "2.0.0"}), encoding="utf-8"
    )
    (root / "Data" / "_휴지통").mkdir()
    (root / "Data" / ".작업중-abcd").mkdir()

    entries = store.list_quizzes()

    assert [entry.folder for entry in entries] == [
        "261006_132001_생리 퀴즈",
        "261001_090000_망가진 퀴즈",
        "261002_090000_새 버전",
    ]
    assert "손상" in entries[1].problem
    assert "더 새 버전 퀴즈 리포터 2.0.0" in entries[2].problem


def test_recover_puts_back_a_parked_quiz_and_drops_staging(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    data = root / "Data"
    parked = data / f"{PARKED_PREFIX}{created.value.folder}"
    created.value.path.rename(parked)  # crashed between the two renames
    (data / f"{STAGING_PREFIX}dead").mkdir()

    store.recover()

    assert [path.name for path in data.iterdir()] == [created.value.folder]
    assert isinstance(store.open(created.value.folder), Ok)


def test_folder_names_from_outside_cannot_escape_data(setup):
    store, _, _, _ = setup

    assert isinstance(store.open("..\\밖"), Err)
    assert isinstance(store.delete("../밖"), Err)
    assert isinstance(store.purge("..\\..\\밖"), Err)


def test_an_open_report_blocks_purge_and_the_quiz_stays_whole(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    assert isinstance(store.delete(created.value.folder), Ok)
    trashed = store.list_trash()[0].path

    with open(trashed / "리포트" / "전체(인쇄용).pdf", "rb"):
        result = store.purge(created.value.folder)

    assert isinstance(result, Err)
    assert "열려 있습니다" in result.errors[0].context["reason"]
    assert (trashed / "문항표.xlsx").exists() and (trashed / "응답원본.csv").exists()
    assert isinstance(store.restore(created.value.folder), Ok)
    assert isinstance(store.open(created.value.folder), Ok)


def test_a_stale_parked_copy_does_not_block_a_rebuild(setup):
    store, _, csv, root = setup
    _, cutoff = _cutoff(csv)
    created = store.create("생리 퀴즈", csv, cutoff, full_bank())
    assert isinstance(created, Ok)
    stale = root / "Data" / f"{PARKED_PREFIX}{created.value.folder}"
    stale.mkdir()
    (stale / "옛것.txt").write_text("지난번 정리 실패", encoding="utf-8")

    result = store.replace_bank(created.value.folder, full_bank())

    assert isinstance(result, Ok), result
    assert [path.name for path in (root / "Data").iterdir()] == [created.value.folder]


def test_control_characters_in_a_name_become_underscores(setup):
    store, _, csv, _ = setup
    _, cutoff = _cutoff(csv)

    created = store.create("퀴즈\t1", csv, cutoff, full_bank())

    assert isinstance(created, Ok), created
    assert created.value.folder.endswith("_퀴즈_1")
