from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clockwork_canary.analyzer import analyze
from clockwork_canary.config import Policy
from clockwork_canary.discovery import DiscoveryResult
from clockwork_canary.models import AuditReport, ScheduleSpec
from clockwork_canary.reporters import render


def _report() -> AuditReport:
    schedule = ScheduleSpec(
        schedule_id="demo",
        workflow_name="Demo",
        path=".github/workflows/demo.yml",
        line=4,
        expression="0 4 * * *",
        timezone="UTC",
        timezone_explicit=False,
        job_count=1,
        runners=("ubuntu-latest",),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return analyze(
        Path("."),
        DiscoveryResult([schedule], [], 1),
        Policy(horizon_days=5, collision_horizon_days=2),
        start,
        generated_at=start,
    )


def test_text_and_markdown_reports_are_readable() -> None:
    report = _report()
    text = render(report, "text")
    markdown = render(report, "markdown")
    assert "Clockwork Canary" in text
    assert "CC003" in text
    assert "| Workflow | Cron |" in markdown
    assert "## Assumptions" in markdown


def test_json_report_has_stable_schema() -> None:
    payload = json.loads(render(_report(), "json"))
    assert payload["schema_version"] == "1.0"
    assert payload["tool"]["version"] == "0.1.1"
    assert payload["summary"]["schedules"] == 1
    assert payload["metrics"][0]["next_runs"]


def test_sarif_contains_rules_locations_and_evidence() -> None:
    payload = json.loads(render(_report(), "sarif"))
    run = payload["runs"][0]
    assert payload["version"] == "2.1.0"
    assert any(rule["id"] == "CC003" for rule in run["tool"]["driver"]["rules"])
    assert run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 4


def test_unknown_report_format_fails() -> None:
    with pytest.raises(ValueError, match="unknown output format"):
        render(_report(), "xml")
