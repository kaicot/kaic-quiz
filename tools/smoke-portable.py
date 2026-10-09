"""Run a built Quiz Reporter folder from a fresh copy and check how it behaves.

    .venv\\Scripts\\python tools\\smoke-portable.py [FOLDER | ZIP]

Without an argument the newest dist\\Quiz-Reporter-v* folder of this repository is used. The
built folder is never started in place: it is copied to a new folder under %TEMP% (a zip is
extracted there), so the release stays free of Data, logs and lock files. Nothing from the
repository is imported; only PySide6's QLockFile is used to look at the lock.

Checks: ``--self-check`` passes in the frozen program; a normal start (offscreen) keeps running,
writes Data\\FORMAT.json and logs\\quiz-reporter.log next to the EXE, holds the lock file, and
leaves no Quiz Reporter folder in %APPDATA% or %LOCALAPPDATA%. Exit code 0 when all pass.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

EXE_NAME = "Quiz Reporter.exe"
SELF_CHECK_TIMEOUT = 300
START_WAIT = 6.0
START_LIMIT = 40.0
REPO = Path(__file__).resolve().parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    return bool(ok)


def newest_release() -> Path:
    candidates = [path for path in (REPO / "dist").glob("Quiz-Reporter-v*") if path.is_dir()]
    if not candidates:
        raise SystemExit("No dist\\Quiz-Reporter-v* folder found; build first or pass a path.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def copy_release(source: Path, work: Path) -> Path:
    """A fresh copy of the release folder under ``work``; a zip is extracted instead."""
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            archive.extractall(work)
        folders = [path for path in work.iterdir() if path.is_dir()]
        if len(folders) != 1:
            raise SystemExit(f"Expected one folder in the zip, found {len(folders)}.")
        return folders[0]
    target = work / source.name
    shutil.copytree(source, target, symlinks=True)
    return target


def app_data_names() -> set[str]:
    names: set[str] = set()
    for variable in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base and Path(base).is_dir():
            names.update(f"{variable}/{entry.name}" for entry in Path(base).iterdir())
    return names


def quiz_named(names: set[str]) -> list[str]:
    return sorted(name for name in names if re.search(r"quiz|퀴즈", name, re.IGNORECASE))


def run_self_check(folder: Path, work: Path) -> None:
    report = work / "self-check.json"
    # No QT_QPA_PLATFORM: the real Windows platform has the system fonts the PDFs need.
    env = {key: value for key, value in os.environ.items() if key != "QT_QPA_PLATFORM"}
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [str(folder / EXE_NAME), "--self-check", str(report)],
            cwd=folder,
            env=env,
            timeout=SELF_CHECK_TIMEOUT,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        check("self-check finishes", False, f"no result after {SELF_CHECK_TIMEOUT} s")
        return
    seconds = time.monotonic() - started
    check("self-check exits with 0", completed.returncode == 0, f"exit={completed.returncode}")
    if not report.is_file():
        check("self-check wrote its result file", False, f"{seconds:.1f} s")
        return
    payload = json.loads(report.read_text(encoding="utf-8"))
    check("self-check passed", payload.get("passed") is True, f"{seconds:.1f} s")
    check("self-check ran frozen", payload.get("frozen") is True)
    expected = re.search(r"-v(\d+\.\d+\.\d+)", folder.name)
    if expected:
        check(
            "self-check version matches the folder",
            payload.get("version") == expected.group(1),
            str(payload.get("version")),
        )
    for item in payload.get("checks", []):
        check(
            f"self-check: {item.get('name')}", item.get("ok") is True, str(item.get("detail", ""))
        )
    check(
        "self-check left no Data or logs beside the EXE",
        not (folder / "Data").exists() and not (folder / "logs").exists(),
    )


def run_normal_start(folder: Path) -> None:
    from PySide6.QtCore import QLockFile  # only to look at the lock; no bundle code is imported

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    process = subprocess.Popen([str(folder / EXE_NAME)], cwd=folder, env=env)
    try:
        format_file = folder / "Data" / "FORMAT.json"
        log_file = folder / "logs" / "quiz-reporter.log"
        deadline = time.monotonic() + START_LIMIT
        time.sleep(START_WAIT)
        while time.monotonic() < deadline and not (format_file.is_file() and log_file.is_file()):
            if process.poll() is not None:
                break
            time.sleep(0.5)
        alive = process.poll() is None
        check(
            "normal start keeps running",
            alive,
            "" if alive else f"exited with {process.returncode}",
        )
        check("Data\\FORMAT.json is written beside the EXE", format_file.is_file())
        check("logs\\quiz-reporter.log is written beside the EXE", log_file.is_file())
        if log_file.is_file():
            text = log_file.read_text(encoding="utf-8", errors="replace")
            check(
                "log names this folder as the portable root",
                folder.name in text and ": start " in text,
            )
        lock_path = folder / ".quiz-reporter.lock"
        check("lock file exists", lock_path.is_file())
        probe = QLockFile(str(lock_path))
        probe.setStaleLockTime(0)
        held = (
            alive
            and not probe.tryLock(100)
            and probe.error() == QLockFile.LockError.LockFailedError
        )
        if not held and alive:
            probe.unlock()
        check("the running program holds the lock (a second start would be refused)", held)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)


def remove_tree(path: Path) -> None:
    for attempt in range(10):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.5 * (attempt + 1))
    shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else newest_release()
    if not source.exists():
        print(f"Not found: {source}")
        return 2
    work = Path(tempfile.mkdtemp(prefix="quiz-reporter-smoke-"))
    if REPO in work.parents:
        print("The temporary folder must be outside the repository.")
        return 2
    try:
        before = app_data_names()
        folder = copy_release(source, work)
        check("the exe is in the copy", (folder / EXE_NAME).is_file(), str(folder))
        if (folder / EXE_NAME).is_file():
            run_self_check(folder, work)
            run_normal_start(folder)
        added = quiz_named(app_data_names() - before)
        check(
            "nothing named Quiz/퀴즈 was added under APPDATA or LOCALAPPDATA",
            not added,
            ", ".join(added),
        )
    finally:
        remove_tree(work)
    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'OK  ' if ok else 'FAIL'} {name.ljust(width)}  {detail}".rstrip())
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
