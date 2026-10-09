"""The hidden --self-check runs the whole pipeline on synthetic data and reports every check."""

from __future__ import annotations

import json

from quiz_reporter import self_check


def test_self_check_passes_from_source(qapp, tmp_path):
    report = tmp_path / "result.json"

    passed = self_check.run(report)

    result = json.loads(report.read_text(encoding="utf-8"))
    failed = [item for item in result["checks"] if not item["ok"]]
    assert passed and result["passed"], failed
    assert len(result["checks"]) >= 9
    assert result["frozen"] is False


def test_a_failing_writer_is_reported_not_raised(qapp, tmp_path):
    report = tmp_path / "result.json"

    def broken(quiz, folder):
        raise RuntimeError("no fonts")

    assert self_check.run(report, broken) is False
    result = json.loads(report.read_text(encoding="utf-8"))
    assert any("no fonts" in item["detail"] for item in result["checks"])
