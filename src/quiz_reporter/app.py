"""Start the program: one instance per folder, checks, theme, window, update check."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

import quiz_reporter
from quiz_reporter import self_check
from quiz_reporter.infrastructure.paths import ManagedPaths, resolve_portable_root
from quiz_reporter.startup import StartupState, prepare
from quiz_reporter.storage.quiz_store import QuizStore
from quiz_reporter.ui.controller import AppController
from quiz_reporter.ui.main_window import TITLE, MainWindow
from quiz_reporter.ui.quiz_pdf import write_quiz_reports
from quiz_reporter.ui.theme import apply_theme

LOCK_NAME = ".quiz-reporter.lock"
ICON_PATH = Path(__file__).resolve().parent / "resources" / "app_icon.svg"
ALREADY_RUNNING = "퀴즈 리포터가 이 폴더에서 이미 실행 중입니다. 열려 있는 창을 쓰세요."


def _log_to_file(paths: ManagedPaths) -> None:
    try:
        paths.logs_dir.mkdir(exist_ok=True)
        handler = RotatingFileHandler(
            paths.logs_dir / "quiz-reporter.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def build(state: StartupState, version: str) -> tuple[MainWindow, AppController]:
    """The window and its controller for a prepared folder (tests use this too)."""
    store = QuizStore(state.paths, write_quiz_reports, app_version=version)
    if state.writable:
        store.recover()
    window = MainWindow(version)
    controller = AppController(window, state, store, version=version)
    return window, controller


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv
    if self_check.FLAG in arguments:
        # Hidden: used to verify a built program (see self_check). No window, no lock.
        position = arguments.index(self_check.FLAG)
        if position + 1 >= len(arguments):
            return 2
        application = QApplication(arguments[:1])
        try:
            return 0 if self_check.run(Path(arguments[position + 1])) else 1
        except Exception:  # e.g. the report path can't be written: no dialog, just a code
            return 3
        finally:
            del application
    application = QApplication(arguments)
    application.setApplicationName(TITLE)
    application.setApplicationVersion(quiz_reporter.__version__)
    apply_theme(application)
    application.setWindowIcon(QIcon(str(ICON_PATH)))
    paths = ManagedPaths.from_root(resolve_portable_root())
    lock = QLockFile(str(paths.root / LOCK_NAME))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200) and lock.error() == QLockFile.LockError.LockFailedError:
        QMessageBox.information(None, TITLE, ALREADY_RUNNING)
        return 0
    state = prepare(paths, quiz_reporter.__version__)
    if state.writable:
        _log_to_file(paths)
    logging.getLogger(__name__).info("start %s at %s", quiz_reporter.__version__, paths.root)
    window, controller = build(state, quiz_reporter.__version__)
    window.show()
    QTimer.singleShot(1500, controller.check_for_update)
    code = application.exec()
    controller.shutdown()
    lock.unlock()
    return code


__all__ = ["ALREADY_RUNNING", "LOCK_NAME", "build", "main"]
