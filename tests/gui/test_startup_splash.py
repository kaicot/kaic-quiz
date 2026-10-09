"""The splash: up at once, with the program's name, and gone when the window shows."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow

from quiz_reporter.startup_splash import ICON_PATH, LOADING, create_splash, show_splash


def test_the_splash_shows_and_steps_aside_for_the_window(qtbot):
    application, splash = show_splash([])
    qtbot.addWidget(splash)

    assert splash.isVisible()
    assert not splash.pixmap().isNull()
    assert splash.accessibleDescription() == LOADING
    assert not application.windowIcon().isNull()

    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    splash.finish(window)
    qtbot.waitUntil(lambda: not splash.isVisible(), timeout=3000)


def test_the_icon_file_is_there():
    assert ICON_PATH.is_file()
    assert not QIcon(str(ICON_PATH)).isNull()
    assert create_splash(QIcon(str(ICON_PATH))).pixmap().width() > 0
