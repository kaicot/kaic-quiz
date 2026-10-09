"""Test-wide setup: real Windows fonts for offscreen Qt, so PDFs embed Korean glyphs as they do
in the program (offscreen Qt otherwise finds no fonts at all)."""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    os.environ.setdefault(
        "QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    )
