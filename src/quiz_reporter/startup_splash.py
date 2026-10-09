"""The first thing on screen: a splash shown before the rest of the program is imported.

Keep imports here light (Qt widgets and the palette only); main.py shows this, then imports the
application, which takes a second or two in the packaged program.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import quiz_reporter
from quiz_reporter.palette import TOKENS

TITLE = "퀴즈 리포터"
ICON_PATH = Path(__file__).resolve().parent / "resources" / "app_icon.ico"
# The taskbar groups windows and picks their icon by this ID, not by python/pythonw.
APP_USER_MODEL_ID = "kaicot.QuizReporter"
LOADING = "프로그램을 준비하고 있습니다…"
CREDIT = "프로그램 제작: 조승현 (kaic21@gmail.com)"
WIDTH, HEIGHT = 560, 300


def _pixmap(icon: QIcon) -> QPixmap:
    ratio = QApplication.primaryScreen().devicePixelRatio() if QApplication.primaryScreen() else 1.0
    pixmap = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QColor(TOKENS.primary))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    icon.paint(painter, 44, 64, 96, 96)
    painter.setPen(QColor(TOKENS.on_accent))
    painter.setFont(QFont("Malgun Gothic", 26, QFont.Weight.Bold))
    painter.drawText(QRectF(164, 70, 360, 46), Qt.AlignmentFlag.AlignVCenter, TITLE)
    painter.setPen(QColor(TOKENS.primary_soft))
    painter.setFont(QFont("Malgun Gothic", 12))
    painter.drawText(
        QRectF(164, 116, 360, 30),
        Qt.AlignmentFlag.AlignVCenter,
        "구글 폼 퀴즈 채점 · 학생별 피드백",
    )
    painter.setPen(QColor(TOKENS.on_accent))
    painter.setFont(QFont("Malgun Gothic", 11))
    painter.drawText(QRectF(44, 196, WIDTH - 88, 28), Qt.AlignmentFlag.AlignVCenter, LOADING)
    painter.setPen(QColor(TOKENS.primary_soft))
    painter.setFont(QFont("Malgun Gothic", 9))
    painter.drawText(
        QRectF(44, HEIGHT - 44, WIDTH - 88, 24),
        Qt.AlignmentFlag.AlignVCenter,
        f"{CREDIT}  ·  v{quiz_reporter.__version__}",
    )
    painter.end()
    return pixmap


class StartupSplash(QLabel):
    """A frameless picture window. Not QSplashScreen: its show() waits about a second for
    the window to be exposed, which is the delay this splash is meant to hide."""

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setPixmap(pixmap)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setCursor(Qt.CursorShape.BusyCursor)

    def show(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - WIDTH // 2, area.center().y() - HEIGHT // 2)
        super().show()

    def finish(self, window: QWidget) -> None:
        """Close once the main window is up."""
        self.close()
        window.raise_()
        window.activateWindow()


def create_splash(icon: QIcon) -> StartupSplash:
    splash = StartupSplash(_pixmap(icon))
    splash.setObjectName("startupSplash")
    splash.setWindowTitle(f"{TITLE} 시작 중")
    splash.setAccessibleName(f"{TITLE} 시작 화면")
    splash.setAccessibleDescription(LOADING)
    return splash


def _set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def show_splash(argv: Sequence[str] | None = None) -> tuple[QApplication, StartupSplash]:
    """Create the application, show the splash at once, and hand both to the program."""
    existing = QApplication.instance()
    application = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(list(argv) if argv is not None else sys.argv)
    )
    _set_app_user_model_id()
    application.setApplicationName(TITLE)
    application.setApplicationVersion(quiz_reporter.__version__)
    icon = QIcon(str(ICON_PATH))
    application.setWindowIcon(icon)
    splash = create_splash(icon)
    splash.show()
    splash.repaint()
    application.processEvents()
    return application, splash


__all__ = ["LOADING", "StartupSplash", "create_splash", "show_splash"]
