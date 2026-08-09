from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from clockwork_canary.analyzer import analyze, should_fail
from clockwork_canary.config import IgnoreRule, Policy
from clockwork_canary.discovery import DiscoveryResult
from clockwork_canary.models import AuditReport, Finding, ScheduleSpec

START = datetime(2026, 1, 1, tzinfo=UTC)


def _schedule(
    schedule_id: str,
    expression: str,
    *,
    timezone: str = "UTC",
    explicit: bool = True,
    path: str | None = None,
    line: int = 4,
    jobs: int = 1,
) -> ScheduleSpec:
    return ScheduleSpec(
        schedule_id=schedule_id,
        workflow_name=schedule_id,
        path=path or f".github/workflows/{schedule_id}.yml",
        line=line,
        expression=expression,
        timezone=timezone,
        timezone_explicit=explicit,
        job_count=jobs,
        runners=("ubuntu-latest",),
    )


def _report(schedules: list[ScheduleSpec], policy: Policy | None = None) -> AuditReport:
    return analyze(
        Path("."),
        DiscoveryResult(schedules=schedules, findings=[], files_scanned=len(schedules)),
        policy or Policy(horizon_days=35, collision_horizon_days=7),
        START,
        generated_at=START,
    )


def test_frequency_load_budget_and_implicit_timezone_rules() -> None:
    policy = Policy(
        horizon_days=7,
        collision_horizon_days=2,
        default_job_minutes=10,
        monthly_minutes_warning=100,
    )
    report = _report([_schedule("fast", "*/2 * * * *", explicit=False)], policy)
    rule_ids = {item.rule_id for item in report.findings}
    assert {"CC002", "CC003", "CC008", "CC009"} <= rule_ids
    metric = report.metrics[0]
    assert metric.minimum_interval_minutes == 2
    assert metric.estimated_runner_minutes_per_30_days > 100


def test_duplicate_and_near_collision_are_summarized_once_per_pair() -> None:
    schedules = [
        _schedule("one", "17 4 * * *"),
        _schedule("two", "17 4 * * *"),
        _schedule("near", "19 4 * * *"),
    ]
    report = _report(schedules)
    duplicates = [item for item in report.findings if item.rule_id == "CC007"]
    collisions = [item for item in report.findings if item.rule_id == "CC006"]
    assert len(duplicates) == 1
    assert len(collisions) == 2
    assert all(item.evidence["collision_count"] > 0 for item in collisions)


def test_exact_nonduplicate_collision_is_warning() -> None:
    schedules = [
        _schedule("utc", "17 4 * * *", timezone="UTC"),
        _schedule("tokyo", "17 13 * * *", timezone="Asia/Tokyo"),
    ]
    report = _report(schedules)
    collision = next(item for item in report.findings if item.rule_id == "CC006")
    assert collision.severity == "warning"
    assert collision.evidence["exact_count"] > 0


def test_dst_gap_and_fold_are_reported() -> None:
    policy = Policy(horizon_days=370, collision_horizon_days=2)
    schedules = [
        _schedule("gap", "30 2 * * *", timezone="America/New_York"),
        _schedule("fold", "30 1 * * *", timezone="America/New_York"),
    ]
    report = _report(schedules, policy)
    assert {item.rule_id for item in report.findings} >= {"CC004", "CC005"}


def test_invalid_cron_timezone_and_discovery_findings_survive() -> None:
    existing = Finding(
        rule_id="CC001",
        severity="error",
        title="broken yaml",
        message="bad",
        path=".github/workflows/bad.yml",
        line=2,
    )
    discovery = DiscoveryResult(
        schedules=[
            _schedule("bad-cron", "nope"),
            _schedule("bad-zone", "17 4 * * *", timezone="Mars/Olympus"),
        ],
        findings=[existing],
        files_scanned=3,
    )
    report = analyze(
        Path("."),
        discovery,
        Policy(horizon_days=5, collision_horizon_days=2),
        START,
        generated_at=START,
    )
    assert len([item for item in report.findings if item.rule_id == "CC001"]) == 3
    assert report.metrics == []


def test_duration_override_and_matrix_assumption() -> None:
    policy = Policy(horizon_days=30, collision_horizon_days=2, default_job_minutes=10)
    policy.durations = {
        ".github/workflows/*.yml": 4,
        ".github/workflows/nightly.yml": 2,
    }
    schedule = _schedule("nightly", "17 4 * * *", path=".github/workflows/nightly.yml", jobs=2)
    report = _report([schedule], policy)
    assert 119 < report.metrics[0].estimated_runner_minutes_per_30_days < 125
    assert "matrix expansion" in report.assumptions[0]


def test_active_ignore_suppresses_but_expired_ignore_does_not() -> None:
    policy = Policy(horizon_days=10, collision_horizon_days=2)
    policy.ignore = [
        IgnoreRule(
            rule="CC003",
            path=".github/workflows/*.yml",
            reason="accepted",
            expires=date(2026, 1, 2),
        ),
        IgnoreRule(
            rule="CC009",
            path="*",
            reason="expired",
            expires=date(2025, 12, 31),
        ),
    ]
    report = _report([_schedule("hour", "0 4 * * *", explicit=False)], policy)
    assert any(item.rule_id == "CC003" for item in report.suppressed_findings)
    assert any(item.rule_id == "CC009" for item in report.findings)


def test_should_fail_thresholds() -> None:
    findings = [
        Finding("CC009", "notice", "n", "n", "x", 1),
        Finding("CC003", "warning", "w", "w", "x", 1),
    ]
    assert not should_fail(findings, "none")
    assert should_fail(findings, "notice")
    assert should_fail(findings, "warning")
    assert not should_fail(findings, "error")


def test_analyze_requires_aware_start() -> None:
    try:
        analyze(
            Path("."),
            DiscoveryResult([], [], 0),
            Policy(),
            datetime(2026, 1, 1),
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")
