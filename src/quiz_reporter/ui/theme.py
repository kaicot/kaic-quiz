"""Quiz Reporter's one light theme: a teal accent on quiet grey-green surfaces."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleOption, QWidget

from quiz_reporter.palette import TEXT_PAIRS, TOKENS, ThemeTokens, contrast_ratio


class _CheckboxStyle(QProxyStyle):
    """Paint checkbox indicators in theme colors (the native ones ignore the palette)."""

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if metric in {
            QStyle.PixelMetric.PM_IndicatorWidth,
            QStyle.PixelMetric.PM_IndicatorHeight,
        }:
            return 18
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element not in {
            QStyle.PrimitiveElement.PE_IndicatorCheckBox,
            QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
        }:
            super().drawPrimitive(element, option, painter, widget)
            return
        state = QStyle.StateFlag(getattr(option, "state", 0))
        checked = bool(state & QStyle.StateFlag.State_On)
        partial = bool(state & QStyle.StateFlag.State_NoChange)
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        active = checked or partial
        background = TOKENS.checkbox_checked_bg if active else TOKENS.surface
        border = TOKENS.primary if active else TOKENS.checkbox_border
        if not enabled:
            border = TOKENS.disabled
        rect = option.rect.adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(border), 2))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 3, 3)
        pen = QPen(QColor(TOKENS.check_icon), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if checked:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(rect.left() + rect.width() * 0.22, rect.center().y()),
                        QPointF(
                            rect.left() + rect.width() * 0.43,
                            rect.bottom() - rect.height() * 0.22,
                        ),
                        QPointF(
                            rect.right() - rect.width() * 0.16,
                            rect.top() + rect.height() * 0.22,
                        ),
                    ]
                )
            )
        elif partial:
            painter.setPen(pen)
            painter.drawLine(
                QPointF(rect.left() + rect.width() * 0.22, rect.center().y()),
                QPointF(rect.right() - rect.width() * 0.22, rect.center().y()),
            )
        painter.restore()


def palette() -> QPalette:
    t = TOKENS
    result = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, t.window),
        (QPalette.ColorRole.WindowText, t.text),
        (QPalette.ColorRole.Base, t.surface),
        (QPalette.ColorRole.AlternateBase, t.window),
        (QPalette.ColorRole.Text, t.text),
        (QPalette.ColorRole.Button, t.surface),
        (QPalette.ColorRole.ButtonText, t.text),
        (QPalette.ColorRole.Highlight, t.primary),
        (QPalette.ColorRole.HighlightedText, t.on_accent),
        (QPalette.ColorRole.Link, t.link),
        (QPalette.ColorRole.LinkVisited, t.link),
        (QPalette.ColorRole.PlaceholderText, t.muted),
        (QPalette.ColorRole.ToolTipBase, t.surface),
        (QPalette.ColorRole.ToolTipText, t.text),
    ):
        result.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.disabled))
    return result


def stylesheet() -> str:
    t = TOKENS
    return f"""
        QWidget {{
            background: {t.window}; color: {t.text};
            font-family: "Malgun Gothic", "Segoe UI", sans-serif; font-size: 14px;
        }}
        QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
        QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; }}
        QLineEdit, QComboBox, QSpinBox, QDateTimeEdit, QPlainTextEdit, QTextBrowser,
        QAbstractItemView {{
            background: {t.surface}; color: {t.text};
            border: 1px solid {t.border}; border-radius: 6px; padding: 4px 6px;
            selection-background-color: {t.primary}; selection-color: {t.on_accent};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus,
        QPlainTextEdit:focus {{ border: 2px solid {t.primary}; padding: 3px 5px; }}

        /* ---- top bar, notices, status line ---- */
        QFrame#topBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
        QFrame#topBar QLabel {{ background: transparent; }}
        QLabel#brandMark {{ color: {t.primary}; font-size: 20px; font-weight: 700; }}
        QLabel#brandTitle {{ font-size: 17px; font-weight: 700; }}
        QLabel#brandSubtitle {{ color: {t.muted}; font-size: 12px; }}
        QPushButton#navButton {{
            background: transparent; border: 0; border-bottom: 3px solid transparent;
            border-radius: 0; color: {t.muted}; font-weight: 600;
            min-height: 44px; padding: 0 14px;
        }}
        QPushButton#navButton:hover {{ color: {t.text}; background: {t.primary_soft}; }}
        QPushButton#navButton:checked {{ color: {t.primary}; border-bottom-color: {t.primary}; }}
        QPushButton#navButton:focus {{ outline: none; text-decoration: underline; }}
        QPushButton#helpButton {{
            background: transparent; border: 1px solid {t.border}; border-radius: 15px;
            min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
            font-weight: 700; color: {t.muted}; padding: 0;
        }}
        QPushButton#helpButton:hover, QPushButton#helpButton:focus {{
            border-color: {t.primary}; color: {t.primary}; background: transparent;
        }}
        QFrame#topBar QLabel#topStatus {{
            background: {t.primary_soft}; color: {t.primary}; font-size: 12px; font-weight: 600;
            border-radius: 6px; padding: 3px 10px;
        }}
        QFrame#topBar QLabel#topStatus[role="warning"] {{
            background: {t.warning_soft}; color: {t.warning};
        }}
        QFrame#topBar QLabel#topStatus[role="error"] {{ background: {t.error_soft}; color: {t.error}; }}
        QFrame#noticeBanner {{ background: {t.primary_soft}; border-bottom: 1px solid {t.border}; }}
        QFrame#noticeBanner[kind="warning"] {{ background: {t.warning_soft}; }}
        QFrame#noticeBanner QLabel {{ background: transparent; }}
        QFrame#noticeBanner[kind="warning"] QLabel {{ color: {t.warning}; font-weight: 600; }}
        QStatusBar {{ background: {t.surface}; color: {t.muted}; border-top: 1px solid {t.border}; }}
        QStatusBar QLabel {{ color: {t.muted}; font-size: 12px; padding: 0 6px; }}

        /* ---- buttons ---- */
        QPushButton {{
            background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
            border-radius: 7px; min-height: 32px; padding: 4px 14px;
        }}
        QPushButton:hover {{ border-color: {t.primary}; background: {t.primary_soft}; }}
        QPushButton:focus {{ border: 2px solid {t.primary}; padding: 3px 13px; outline: none; }}
        QPushButton:pressed {{ background: {t.checkbox_checked_bg}; }}
        QPushButton:disabled {{
            color: {t.disabled}; background: {t.window}; border-color: {t.border};
        }}
        QPushButton#primaryActionButton, QPushButton#newQuizButton {{
            background: {t.primary}; color: {t.on_accent}; border-color: {t.primary};
            font-weight: 700;
        }}
        QPushButton#primaryActionButton:hover:enabled, QPushButton#newQuizButton:hover {{
            background: {t.primary_hover}; border-color: {t.primary_hover};
        }}
        QPushButton#primaryActionButton:focus, QPushButton#newQuizButton:focus {{
            border: 2px solid {t.text};
        }}
        QPushButton#primaryActionButton:disabled {{
            background: {t.window}; color: {t.disabled}; border-color: {t.border};
        }}
        QPushButton#newQuizButton {{
            font-size: 17px; min-height: 52px; padding: 6px 28px; border-radius: 10px;
        }}
        QPushButton#dangerButton {{ color: {t.error}; }}
        QPushButton#dangerButton:hover:enabled {{
            border-color: {t.error}; background: {t.error_soft};
        }}
        QPushButton#dangerButton:disabled {{ color: {t.disabled}; }}

        /* ---- page headings and cards ---- */
        QLabel#pageTitle, QLabel#quizPageTitle {{ font-size: 22px; font-weight: 700; }}
        QLabel#sectionTitle {{ font-size: 16px; font-weight: 700; }}
        QLabel[role="hint"] {{ color: {t.muted}; }}
        QLabel[role="success"] {{ color: {t.success}; font-weight: 600; }}
        QLabel[role="error"] {{ color: {t.error}; font-weight: 600; }}
        QLabel[role="warning"] {{ color: {t.warning}; font-weight: 600; }}
        QFrame#card, QFrame#quizCard, QFrame#quizTile, QFrame#emptyState {{
            background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
        }}
        QFrame#quizTile:hover {{ border-color: {t.primary}; }}
        QLabel#tileTitle {{ font-size: 15px; font-weight: 700; }}
        QLabel#tileMeta {{ color: {t.muted}; font-size: 12px; }}
        QLabel#tileScore {{ color: {t.primary}; font-size: 20px; font-weight: 700; }}
        QLabel#tileBadge {{
            border-radius: 9px; padding: 2px 10px; font-size: 12px; font-weight: 600;
            background: {t.primary_soft}; color: {t.primary};
        }}
        QLabel#tileBadge[role="basic"] {{ background: {t.window}; color: {t.muted}; }}

        /* ---- tables ---- */
        QTableWidget, QTableView {{
            gridline-color: {t.border}; alternate-background-color: {t.window}; padding: 0;
        }}
        QTableView::item {{ padding: 0 10px; }}
        QTableView::item:focus {{ outline: none; }}
        QListView::item, QListWidget::item {{ padding: 5px 8px; }}
        /* The header is an item view too: undo the box the item-view rule above gives it. */
        QHeaderView {{ background: {t.window}; border: 0; border-radius: 0; padding: 0; }}
        QHeaderView::section {{
            background: {t.window}; color: {t.text}; border: 0;
            border-bottom: 1px solid {t.border}; padding: 8px 10px; font-weight: 600;
        }}

        /* ---- quiz page (step cards) ---- */
        QLabel#quizStepNumber {{
            background: {t.primary}; color: {t.on_accent}; font-weight: 700;
            border-radius: 13px; min-width: 26px; max-width: 26px;
            min-height: 26px; max-height: 26px;
        }}
        QLabel#quizStepTitle {{ font-size: 16px; font-weight: 700; }}
        QLabel#quizBadge {{
            border-radius: 10px; padding: 3px 12px; font-size: 12px; font-weight: 600;
            background: {t.window}; color: {t.muted}; border: 1px solid {t.border};
        }}
        QLabel#quizBadge[role="ok"] {{
            background: {t.primary_soft}; color: {t.primary}; border-color: {t.primary};
        }}
        QLabel#quizBadge[role="warn"] {{
            background: {t.warning_soft}; color: {t.warning}; border-color: {t.warning};
        }}
        QFrame#quizPanel {{
            background: {t.window}; border: 1px solid {t.border}; border-radius: 8px;
        }}
        QLabel#quizPanelTitle {{ font-weight: 700; }}
        QPlainTextEdit#quizProblems {{ color: {t.warning}; }}
        QProgressBar {{
            background: {t.window}; border: 1px solid {t.border}; border-radius: 4px;
            min-height: 8px; max-height: 8px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {t.primary}; border-radius: 3px; }}
    """


def set_role(widget: QWidget, role: str) -> None:
    """Change a widget's ``role`` property and restyle it right away."""
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def apply_theme(application: QApplication) -> None:
    application.setStyle(_CheckboxStyle())
    application.setPalette(palette())
    application.setStyleSheet(stylesheet())


__all__ = [
    "TEXT_PAIRS",
    "TOKENS",
    "ThemeTokens",
    "apply_theme",
    "contrast_ratio",
    "palette",
    "set_role",
    "stylesheet",
]
