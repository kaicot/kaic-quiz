"""Data/FORMAT.json: written for unmarked folders, newer formats open read-only."""

from __future__ import annotations

import json

from quiz_reporter.errors import Err, Ok
from quiz_reporter.infrastructure.data_format import (
    DATA_FORMAT,
    DataFormat,
    ensure_data_format,
    read_data_format,
)


def test_an_unmarked_folder_gets_the_current_format(tmp_path):
    assert read_data_format(tmp_path) == Ok(None)

    marked = ensure_data_format(tmp_path, "4.2.0")

    assert marked == Ok(DataFormat(DATA_FORMAT, "4.2.0"))
    assert json.loads((tmp_path / "FORMAT.json").read_text(encoding="utf-8")) == {
        "data_format": DATA_FORMAT,
        "written_by": "4.2.0",
    }
    # Later starts leave the marker as it is.
    assert ensure_data_format(tmp_path, "4.3.0") == Ok(DataFormat(DATA_FORMAT, "4.2.0"))


def test_newer_and_damaged_markers_refuse_writing(tmp_path):
    (tmp_path / "FORMAT.json").write_text('{"data_format": 2, "written_by": "5.0.0"}')
    newer = ensure_data_format(tmp_path, "4.2.0")
    assert isinstance(newer, Err) and newer.errors[0].code == "DATA_FORMAT_NEWER"
    assert "5.0.0" in str(newer.errors[0].context["reason"])

    (tmp_path / "FORMAT.json").write_text("{broken")
    damaged = ensure_data_format(tmp_path, "4.2.0")
    assert isinstance(damaged, Err) and damaged.errors[0].code == "DATA_FORMAT_UNREADABLE"
