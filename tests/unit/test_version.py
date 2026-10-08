"""The version lives in two places; they must agree."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import quiz_reporter

ROOT = Path(__file__).resolve().parents[2]


def test_package_and_pyproject_versions_match():
    with open(ROOT / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]

    assert quiz_reporter.__version__ == project["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", project["version"])
