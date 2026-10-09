"""Importing quizzes from a previous install: places, repeat runs, broken quizzes, safety."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from quiz_reporter.errors import Err, Ok, Result
from quiz_reporter.infrastructure.paths import ManagedPaths
from quiz_reporter.quiz.grading import suggest_cutoff
from quiz_reporter.quiz.responses import KST, read_form_responses
from quiz_reporter.quiz.students import GradedQuiz
from quiz_reporter.storage import data_import
from quiz_reporter.storage.data_import import (
    ImportProgress,
    ImportSummary,
    import_previous_install,
    install_root,
)
from quiz_reporter.storage.quiz_info import INFO_FILENAME
from quiz_reporter.storage.quiz_store import STAGING_PREFIX, QuizStore
from tests.helpers.quiz_forms import form_csv, full_bank

START = datetime(2026, 10, 6, 13, 20, 0, tzinfo=KST)
ACTIVE = ("퀴즈 하나", "퀴즈 둘")
TRASHED = "퀴즈 셋"


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _writer(quiz: GradedQuiz, folder: Path) -> Result[object]:
    """Stands in for the PDF writer: one marker file per student."""
    (folder / "개별").mkdir(parents=True)
    (folder / "전체(인쇄용).pdf").write_bytes(b"%PDF bundle")
    for student in quiz.students:
        (folder / "개별" / f"{student.serial:03d}.pdf").write_bytes(b"%PDF")
    return Ok(None)


def _store(root: Path) -> QuizStore:
    root.mkdir(parents=True, exist_ok=True)
    return QuizStore(ManagedPaths.from_root(root), _writer, app_version="1.0.0", clock=_Clock())


@dataclass(frozen=True)
class Installs:
    old_root: Path
    old_store: QuizStore
    new_root: Path
    new_store: QuizStore
    new_paths: ManagedPaths
    folders: dict[str, str]  # quiz title -> folder name in the old install


def _tree_hashes(root: Path) -> dict[str, str]:
    """Every file's bytes and every folder, so any change inside the old install shows up."""
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        found[key] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
    return found


def _import(installs: Installs, chosen: Path | str | None = None, progress=None):
    return import_previous_install(
        installs.old_root if chosen is None else chosen,
        installs.new_store,
        installs.new_paths,
        progress,
    )


def _failed_names(summary: ImportSummary) -> list[str]:
    return [name for name, _ in summary.failed]


@pytest.fixture
def installs(tmp_path) -> Installs:
    csv = tmp_path / "응답.csv"
    csv.write_bytes(form_csv())
    responses = read_form_responses(str(csv))
    assert isinstance(responses, Ok)
    cutoff = suggest_cutoff(responses.value)

    old_root = tmp_path / "이전 버전"
    old_store = _store(old_root)
    folders: dict[str, str] = {}
    for title in (*ACTIVE, TRASHED):
        created = old_store.create(title, csv, cutoff, full_bank())
        assert isinstance(created, Ok), created
        folders[title] = created.value.folder
    assert isinstance(old_store.delete(folders[TRASHED]), Ok)
    (old_root / "Data" / "FORMAT.json").write_text(
        json.dumps({"data_format": 1, "written_by": "4.2.0"}), encoding="utf-8"
    )
    # Things that are not quizzes: never copied.
    (old_root / "Data" / ".작업중-abcd").mkdir()
    (old_root / "Data" / "_기타").mkdir()
    (old_root / "update.json").write_text("{}", encoding="utf-8")
    (old_root / "logs").mkdir()
    (old_root / "logs" / "app.log").write_text("log", encoding="utf-8")

    new_root = tmp_path / "새 버전"
    new_store = _store(new_root)
    return Installs(
        old_root, old_store, new_root, new_store, ManagedPaths.from_root(new_root), folders
    )


def test_active_and_trashed_quizzes_arrive_in_their_own_places(installs):
    result = _import(installs)

    assert isinstance(result, Ok), result
    assert result.value == ImportSummary(2, 1, 0, ())
    new_data = installs.new_root / "Data"
    assert sorted(entry.folder for entry in installs.new_store.list_quizzes()) == sorted(
        installs.folders[title] for title in ACTIVE
    )
    for title in ACTIVE:
        opened = installs.new_store.open(installs.folders[title])
        assert isinstance(opened, Ok), opened
        assert opened.value.info.name == title
        assert len(opened.value.graded.students) == 4
    trash = installs.new_store.list_trash()
    assert [entry.folder for entry in trash] == [installs.folders[TRASHED]]
    assert trash[0].info is not None
    assert trash[0].info.name == TRASHED
    assert (trash[0].path / "리포트" / "전체(인쇄용).pdf").is_file()
    # Only quiz folders are carried over: no markers, staging, logs or update settings.
    assert sorted(path.name for path in new_data.iterdir()) == sorted(
        [*(installs.folders[title] for title in ACTIVE), "_휴지통"]
    )
    assert not (installs.new_root / "logs").exists()
    assert not (installs.new_root / "update.json").exists()


def test_a_second_run_skips_everything(installs):
    first = _import(installs)
    assert isinstance(first, Ok)
    before = _tree_hashes(installs.new_root)

    second = _import(installs)

    assert isinstance(second, Ok), second
    assert second.value == ImportSummary(0, 0, 3, ())
    assert _tree_hashes(installs.new_root) == before


def test_a_quiz_trashed_after_an_earlier_import_does_not_come_back(installs):
    first = _import(installs)
    assert isinstance(first, Ok), first
    name = installs.folders[ACTIVE[0]]
    assert isinstance(installs.new_store.delete(name), Ok)

    again = _import(installs)

    assert isinstance(again, Ok), again
    assert again.value == ImportSummary(0, 0, 3, ())
    assert not (installs.new_root / "Data" / name).exists()
    assert [entry.folder for entry in installs.new_store.list_trash()].count(name) == 1


def test_a_quiz_restored_after_an_earlier_import_is_not_trashed_again(installs):
    first = _import(installs)
    assert isinstance(first, Ok), first
    name = installs.folders[TRASHED]
    assert isinstance(installs.new_store.restore(name), Ok)

    again = _import(installs)

    assert isinstance(again, Ok), again
    assert again.value == ImportSummary(0, 0, 3, ())
    assert installs.new_store.list_trash() == ()


def test_a_broken_quiz_is_reported_and_the_others_still_arrive(installs):
    broken = installs.folders[ACTIVE[0]]
    (installs.old_root / "Data" / broken / INFO_FILENAME).write_bytes(b"{")

    result = _import(installs)

    assert isinstance(result, Ok), result
    summary = result.value
    assert (summary.imported, summary.trashed, summary.skipped) == (1, 1, 0)
    assert _failed_names(summary) == [broken]
    assert INFO_FILENAME in summary.failed[0][1]
    assert not (installs.new_root / "Data" / broken).exists()
    assert not [
        path
        for path in (installs.new_root / "Data").iterdir()
        if path.name.startswith((".", STAGING_PREFIX))
    ]
    assert [entry.folder for entry in installs.new_store.list_quizzes()] == [
        installs.folders[ACTIVE[1]]
    ]
    assert len(installs.new_store.list_trash()) == 1


def test_a_quiz_with_a_linked_folder_inside_is_not_copied(installs, tmp_path):
    outside = tmp_path / "바깥 폴더"
    outside.mkdir()
    (outside / "남의 파일.txt").write_text("퀴즈 밖의 파일", encoding="utf-8")
    linked = installs.folders[ACTIVE[0]]
    junction = installs.old_root / "Data" / linked / "연결"
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True
    )
    if made.returncode != 0:
        pytest.skip("cannot create a junction here")

    result = _import(installs)

    assert isinstance(result, Ok), result
    assert _failed_names(result.value) == [linked]
    assert "링크" in result.value.failed[0][1]
    assert not (installs.new_root / "Data" / linked).exists()
    assert result.value.imported == 1
    junction.rmdir()  # remove the link only, never the folder it points to
    assert (outside / "남의 파일.txt").exists()


def test_a_copy_error_fails_only_that_quiz_and_leaves_no_staging(installs, monkeypatch):
    locked = installs.folders[ACTIVE[1]]
    real_copytree = shutil.copytree

    def copytree(source, destination, *args, **kwargs):
        if Path(source).name == locked:
            Path(destination).mkdir()  # a partly copied folder
            (Path(destination) / "부분.bin").write_bytes(b"x")
            raise PermissionError(13, "Access is denied")
        return real_copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(data_import.shutil, "copytree", copytree)

    result = _import(installs)

    assert isinstance(result, Ok), result
    assert (result.value.imported, result.value.trashed) == (1, 1)
    assert _failed_names(result.value) == [locked]
    assert "열려 있습니다" in result.value.failed[0][1]
    assert not [
        path
        for path in (installs.new_root / "Data").iterdir()
        if path.name.startswith((".", STAGING_PREFIX))
    ]


def test_a_rename_error_is_reported_per_quiz_and_leaves_no_staging(installs, monkeypatch):
    def refuse(_operation, **_):
        raise OSError(5, "disk trouble")

    monkeypatch.setattr(data_import, "retry_io", refuse)

    result = _import(installs)

    assert isinstance(result, Ok), result
    assert (result.value.imported, result.value.trashed) == (0, 0)
    assert len(result.value.failed) == 3
    assert "disk trouble" in result.value.failed[0][1]
    assert [path.name for path in (installs.new_root / "Data").iterdir()] in ([], ["_휴지통"])
    assert not list((installs.new_root / "Data" / "_휴지통").glob("*"))


def test_a_newer_data_format_is_refused_and_nothing_is_copied(installs):
    (installs.old_root / "Data" / "FORMAT.json").write_text(
        json.dumps({"data_format": 2, "written_by": "9.0.0"}), encoding="utf-8"
    )

    result = _import(installs)

    assert isinstance(result, Err)
    assert result.errors[0].code == "IMPORT_SOURCE_NEWER"
    assert "9.0.0" in str(result.errors[0].context["reason"])
    new_data = installs.new_root / "Data"
    assert not new_data.exists() or list(new_data.iterdir()) == []


def test_a_missing_format_marker_is_fine(installs):
    (installs.old_root / "Data" / "FORMAT.json").unlink()

    result = _import(installs)

    assert isinstance(result, Ok), result
    assert result.value.imported == 2


def test_the_current_install_is_refused(installs):
    (installs.new_root / "Data").mkdir()
    for chosen in (
        installs.new_root,
        installs.new_root / "Data",
        Path(str(installs.new_root).upper()),
    ):
        result = _import(installs, chosen)

        assert isinstance(result, Err), chosen
        assert result.errors[0].code == "IMPORT_SOURCE_SAME"
        assert result.errors[0].message_key == "error.import_source_same"
    assert list((installs.new_root / "Data").iterdir()) == []


def test_choosing_the_old_data_folder_works_like_choosing_the_program_folder(installs):
    chosen = installs.old_root / "Data"
    assert install_root(chosen) == installs.old_root
    assert install_root(installs.old_root) == installs.old_root

    result = _import(installs, str(chosen))

    assert isinstance(result, Ok), result
    assert result.value == ImportSummary(2, 1, 0, ())


def test_a_random_folder_is_refused(installs, tmp_path):
    random_folder = tmp_path / "아무 폴더"
    (random_folder / "Data").mkdir(parents=True)
    (random_folder / "Data" / "메모.txt").write_text("not a quiz", encoding="utf-8")
    empty = tmp_path / "빈 폴더"
    empty.mkdir()

    for chosen in (random_folder, empty, tmp_path / "없는 폴더"):
        assert install_root(chosen) is None
        result = _import(installs, chosen)

        assert isinstance(result, Err), chosen
        assert result.errors[0].code == "IMPORT_SOURCE_INVALID"
        assert result.errors[0].message_key == "error.import_source_invalid"
    assert not (installs.new_root / "Data").exists()


def test_the_old_install_is_unchanged_afterwards(installs):
    broken = installs.folders[ACTIVE[0]]
    (installs.old_root / "Data" / broken / INFO_FILENAME).write_bytes(b"{")
    before = _tree_hashes(installs.old_root)

    first = _import(installs)
    second = _import(installs)

    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert first.value.imported == 1
    assert _tree_hashes(installs.old_root) == before


def test_progress_is_reported_once_per_candidate(installs):
    # One of the three is already here, so skipped quizzes are reported too.
    first = _import(installs)
    assert isinstance(first, Ok)
    shutil.rmtree(installs.new_root / "Data" / installs.folders[ACTIVE[1]])
    seen: list[ImportProgress] = []

    result = _import(installs, progress=seen.append)

    assert isinstance(result, Ok), result
    assert result.value == ImportSummary(1, 0, 2, ())
    names = [installs.folders[title] for title in (*ACTIVE, TRASHED)]
    assert seen == [
        ImportProgress(1, 3, min(names[:2])),
        ImportProgress(2, 3, max(names[:2])),
        ImportProgress(3, 3, names[2]),
    ]


def test_an_install_without_quizzes_to_import_gives_an_empty_summary(installs):
    for title in (*ACTIVE, TRASHED):
        folder = installs.folders[title]
        path = installs.old_root / "Data" / folder
        shutil.rmtree(path if path.exists() else installs.old_root / "Data" / "_휴지통" / folder)
    seen: list[ImportProgress] = []

    result = _import(installs, progress=seen.append)

    assert isinstance(result, Ok), result
    assert result.value == ImportSummary(0, 0, 0, ())
    assert seen == []


def test_an_old_install_kept_inside_the_new_program_folder_can_be_chosen(installs):
    nested = installs.new_root / "예전 버전"
    shutil.copytree(installs.old_root, nested)

    result = _import(installs, nested)

    assert isinstance(result, Ok), result
    assert (result.value.imported, result.value.trashed) == (2, 1)


def test_choosing_the_folder_that_holds_both_versions_imports_the_old_one(installs, tmp_path):
    # D:\퀴즈리포터\ with the old and the new program folders side by side.
    result = _import(installs, tmp_path)

    assert isinstance(result, Ok), result
    assert (result.value.imported, result.value.trashed) == (2, 1)


def test_two_old_versions_in_the_chosen_folder_ask_which_one(installs, tmp_path):
    shutil.copytree(installs.old_root, tmp_path / "더 이전 버전")

    result = _import(installs, tmp_path)

    assert isinstance(result, Err)
    assert result.errors[0].code == "IMPORT_SOURCE_AMBIGUOUS"
    assert "2개" in result.errors[0].context["reason"]
