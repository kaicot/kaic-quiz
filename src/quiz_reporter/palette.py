"""Quiz Reporter's colors, shared by the window theme and the printed reports (no Qt here)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Semantic colors shared by the palette, the stylesheet and painted indicators."""

    window: str
    surface: str
    text: str
    muted: str
    disabled: str
    on_accent: str
    border: str
    primary: str
    primary_hover: str
    primary_soft: str
    link: str
    success: str
    error: str
    error_soft: str
    warning: str
    warning_soft: str
    checkbox_border: str
    checkbox_checked_bg: str
    check_icon: str


TOKENS = ThemeTokens(
    window="#F4F7F6",
    surface="#FFFFFF",
    text="#1F2933",
    muted="#52606D",
    disabled="#7B8794",
    on_accent="#FFFFFF",
    border="#D3DDDA",
    primary="#0F766E",
    primary_hover="#115E59",
    primary_soft="#E3F2EF",
    link="#0F766E",
    success="#15803D",
    error="#B42318",
    error_soft="#FDECEA",
    warning="#9A4A00",
    warning_soft="#FFF4E5",
    checkbox_border="#3E4C59",
    checkbox_checked_bg="#CDEBE5",
    check_icon="#134E4A",
)

# (label, foreground, background) pairs the screens draw text with; tests hold them to WCAG AA.
TEXT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("text on window", TOKENS.text, TOKENS.window),
    ("text on surface", TOKENS.text, TOKENS.surface),
    ("muted on surface", TOKENS.muted, TOKENS.surface),
    ("muted on window", TOKENS.muted, TOKENS.window),
    ("button text on primary", TOKENS.on_accent, TOKENS.primary),
    ("button text on primary hover", TOKENS.on_accent, TOKENS.primary_hover),
    ("primary on soft", TOKENS.primary, TOKENS.primary_soft),
    ("link on surface", TOKENS.link, TOKENS.surface),
    ("success on surface", TOKENS.success, TOKENS.surface),
    ("error on surface", TOKENS.error, TOKENS.surface),
    ("error on soft", TOKENS.error, TOKENS.error_soft),
    ("warning on surface", TOKENS.warning, TOKENS.surface),
    ("warning on soft", TOKENS.warning, TOKENS.warning_soft),
)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two ``#RRGGBB`` colors."""

    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


__all__ = ["TEXT_PAIRS", "TOKENS", "ThemeTokens", "contrast_ratio"]
