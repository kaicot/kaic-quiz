"""The one theme keeps readable contrast (WCAG AA: 4.5 for normal text)."""

from __future__ import annotations

import pytest

from quiz_reporter.ui.theme import TEXT_PAIRS, contrast_ratio


def test_contrast_ratio_matches_known_values():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)


@pytest.mark.parametrize(("label", "foreground", "background"), TEXT_PAIRS)
def test_every_text_pair_meets_wcag_aa(label, foreground, background):
    assert contrast_ratio(foreground, background) >= 4.5, label
