"""Repository-level schedule simulation and actionable risk rules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Policy
from .cron import CronExpression, CronSyntaxError, iter_occurrences
from .discovery import DiscoveryResult
from .models import AuditReport, Finding, Occurrence, ScheduleMetrics, ScheduleSpec

_SEVERITY_ORDER = {"notice": 1, "warning": 2, "error": 3}


@dataclass(slots=True)
class _Timeline:
    expression: CronExpression
    total: int
    window: list[Occurrence]
    next_runs: list[Occurrence]
    gap_examples: list[Occurrence]
    fold_examples: list[Occurrence]
    minimum_interval: int | None


@dataclass(slots=True)
class _CollisionStats:
    count: int = 0
    exact: int = 0
    examples: list[dict[str, object]] = field(default_factory=list)


def analyze(
    root: Path,
    discovery: DiscoveryResult,
    policy: Policy,
    simulation_start: datetime,
    generated_at: datetime | None = None,
) -> AuditReport:
    if simulation_start.tzinfo is None:
        raise ValueError("simulation_start must be timezone-aware")
    start = simulation_start.astimezone(UTC)
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    findings = list(discovery.findings)
    metrics: list[ScheduleMetrics] = []
    timelines: dict[str, _Timeline] = {}
    cache: dict[tuple[str, str], _Timeline] = {}

    for schedule in discovery.schedules:
        try:
            expression = CronExpression.parse(schedule.expression)
            timezone = ZoneInfo(schedule.timezone)
        except (CronSyntaxError, ZoneInfoNotFoundError) as exc:
            findings.append(
                _finding(
                    "CC001",
                    "error",
                    "Schedule cannot be simulated",
                    str(exc),
                    schedule,
                )
            )
            continue

        cache_key = (schedule.expression, schedule.timezone)
        timeline = cache.get(cache_key)
        if timeline is None:
            timeline = _build_timeline(expression, timezone, start, policy)
            cache[cache_key] = timeline
        timelines[schedule.schedule_id] = timeline

        monthly_runs = timeline.total * 30 / policy.horizon_days
        duration = _duration_for(schedule, policy)
        monthly_minutes = monthly_runs * schedule.job_count * duration
        metrics.append(
            ScheduleMetrics(
                schedule_id=schedule.schedule_id,
                runs_in_horizon=timeline.total,
                runs_per_30_days=monthly_runs,
                estimated_runner_minutes_per_30_days=monthly_minutes,
                minimum_interval_minutes=timeline.minimum_interval,
                next_runs=tuple(timeline.next_runs),
            )
        )

        if timeline.minimum_interval is not None and timeline.minimum_interval < 5:
            findings.append(
                _finding(
                    "CC002",
                    "error",
                    "Schedule is more frequent than GitHub allows",
                    (
                        "The shortest simulated interval is "
                        f"{timeline.minimum_interval} minute(s); "
                        "GitHub Actions requires at least 5 minutes."
                    ),
                    schedule,
                    {"minimum_interval_minutes": timeline.minimum_interval},
                )
            )
        if 0 in expression.minutes:
            findings.append(
                _finding(
                    "CC003",
                    "warning",
                    "Schedule hits the start of an hour",
                    (
                        "GitHub documents higher scheduled-workflow load at the start of an hour. "
                        "Choose a non-zero minute when exact alignment is unnecessary."
                    ),
                    schedule,
                    {"selected_minutes": sorted(expression.minutes)},
                )
            )
        if timeline.gap_examples:
            findings.append(
                _finding(
                    "CC004",
                    "warning",
                    "Schedule crosses a daylight-saving gap",
                    (
                        "At least one intended wall-clock run does not exist and advances to the "
                        "next valid local time."
                    ),
                    schedule,
                    {"examples": [item.as_dict() for item in timeline.gap_examples]},
                )
            )
        if timeline.fold_examples:
            findings.append(
                _finding(
                    "CC005",
                    "warning",
                    "Schedule enters a repeated daylight-saving hour",
                    (
                        "The selected local time occurs twice during fall-back. GitHub does not "
                        "document a portable once-versus-twice guarantee; keep the job idempotent "
                        "or move it outside the repeated hour."
                    ),
                    schedule,
                    {"examples": [item.as_dict() for item in timeline.fold_examples]},
                )
            )
        if monthly_minutes > policy.monthly_minutes_warning:
            findings.append(
                _finding(
                    "CC008",
                    "warning",
                    "Estimated monthly runner-minute budget is high",
                    (
                        f"Approximately {monthly_minutes:.0f} raw runner-minutes per 30 days, "
                        f"above the configured {policy.monthly_minutes_warning:.0f} threshold."
                    ),
                    schedule,
                    {
                        "runs_per_30_days": round(monthly_runs, 2),
                        "job_count": schedule.job_count,
                        "minutes_per_job": duration,
                        "estimated_runner_minutes": round(monthly_minutes, 2),
                    },
                )
            )
        if not schedule.timezone_explicit:
            findings.append(
                _finding(
                    "CC009",
                    "notice",
                    "Schedule relies on implicit UTC",
                    "Add timezone: UTC to make intent explicit, or use an IANA local timezone.",
                    schedule,
                )
            )

    findings.extend(_duplicate_findings(discovery.schedules, timelines))
    findings.extend(_collision_findings(discovery.schedules, timelines, policy))
    active, suppressed = _apply_ignores(findings, policy, generated.date())
    active.sort(key=_finding_sort_key)
    suppressed.sort(key=_finding_sort_key)
    metrics.sort(key=lambda item: item.schedule_id)
    schedules = sorted(discovery.schedules, key=lambda item: item.schedule_id)
    assumptions = [
        (
            "Runner-minute estimates use each workflow's job count times the configured duration; "
            "matrix expansion, retries, and billing multipliers are not inferred."
        ),
        (
            "Collisions are simulated over the first "
            f"{policy.collision_horizon_days} days with a "
            f"{policy.collision_window_minutes}-minute window."
        ),
        (
            "Spring-forward runs follow GitHub's documented advance-to-next-valid-time behavior; "
            "fall-back behavior is reported as ambiguous rather than guessed."
        ),
    ]
    return AuditReport(
        root=root.resolve(),
        generated_at=generated,
        simulation_start=start,
        horizon_days=policy.horizon_days,
        schedules=schedules,
        metrics=metrics,
        findings=active,
        suppressed_findings=suppressed,
        assumptions=assumptions,
    )


def should_fail(findings: Iterable[Finding], threshold: str) -> bool:
    if threshold == "none":
        return False
    wanted = _SEVERITY_ORDER[threshold]
    return any(_SEVERITY_ORDER[item.severity] >= wanted for item in findings)


def _build_timeline(
    expression: CronExpression,
    timezone: ZoneInfo,
    start: datetime,
    policy: Policy,
) -> _Timeline:
    end = start + timedelta(days=policy.horizon_days)
    collision_end = start + timedelta(days=policy.collision_horizon_days)
    total = 0
    window: list[Occurrence] = []
    next_runs: list[Occurrence] = []
    gaps: list[Occurrence] = []
    folds: list[Occurrence] = []
    minimum_interval: int | None = None
    previous_actual: datetime | None = None

    for occurrence in iter_occurrences(expression, timezone, start, end):
        total += 1
        if len(next_runs) < 8:
            next_runs.append(occurrence)
        if occurrence.actual_utc <= collision_end:
            window.append(occurrence)
        if occurrence.adjusted_for_gap and len(gaps) < 3:
            gaps.append(occurrence)
        if occurrence.local_time.fold == 1 and len(folds) < 3:
            folds.append(occurrence)
        if previous_actual is not None:
            delta = int((occurrence.actual_utc - previous_actual).total_seconds() // 60)
            if delta >= 0 and (minimum_interval is None or delta < minimum_interval):
                minimum_interval = delta
        previous_actual = occurrence.actual_utc
    return _Timeline(
        expression=expression,
        total=total,
        window=window,
        next_runs=next_runs,
        gap_examples=gaps,
        fold_examples=folds,
        minimum_interval=minimum_interval,
    )


def _duplicate_findings(
    schedules: list[ScheduleSpec], timelines: dict[str, _Timeline]
) -> list[Finding]:
    grouped: dict[tuple[str, str], list[ScheduleSpec]] = defaultdict(list)
    for schedule in schedules:
        if schedule.schedule_id in timelines:
            grouped[(schedule.expression, schedule.timezone)].append(schedule)
    findings: list[Finding] = []
    for (expression, timezone), members in grouped.items():
        if len(members) < 2:
            continue
        first = sorted(members, key=lambda item: item.schedule_id)[0]
        findings.append(
            _finding(
                "CC007",
                "warning",
                "Duplicate schedules trigger together",
                (
                    f"{len(members)} entries use {expression!r} in {timezone}; consolidate them "
                    "or document why simultaneous runs are required."
                ),
                first,
                {"schedule_ids": [item.schedule_id for item in members]},
                tuple(item.schedule_id for item in members),
            )
        )
    return findings


def _collision_findings(
    schedules: list[ScheduleSpec], timelines: dict[str, _Timeline], policy: Policy
) -> list[Finding]:
    schedule_by_id = {item.schedule_id: item for item in schedules}
    duplicate_keys = {
        frozenset((left.schedule_id, right.schedule_id))
        for index, left in enumerate(schedules)
        for right in schedules[index + 1 :]
        if left.expression == right.expression and left.timezone == right.timezone
    }
    events: list[tuple[datetime, str]] = []
    for schedule_id, timeline in timelines.items():
        events.extend((item.actual_utc, schedule_id) for item in timeline.window)
    events.sort(key=lambda item: (item[0], item[1]))

    stats: dict[frozenset[str], _CollisionStats] = {}
    window = timedelta(minutes=policy.collision_window_minutes)
    for index, (when, schedule_id) in enumerate(events):
        cursor = index + 1
        while cursor < len(events) and events[cursor][0] - when <= window:
            other_when, other_id = events[cursor]
            cursor += 1
            if other_id == schedule_id:
                continue
            pair = frozenset((schedule_id, other_id))
            if pair in duplicate_keys:
                continue
            entry = stats.setdefault(pair, _CollisionStats())
            entry.count += 1
            delta = int((other_when - when).total_seconds() // 60)
            if delta == 0:
                entry.exact += 1
            if len(entry.examples) < 3:
                entry.examples.append(
                    {
                        "first_utc": when.isoformat().replace("+00:00", "Z"),
                        "second_utc": other_when.isoformat().replace("+00:00", "Z"),
                        "delta_minutes": delta,
                    }
                )

    findings: list[Finding] = []
    for pair, entry in sorted(stats.items(), key=lambda item: sorted(item[0])):
        identifiers = tuple(sorted(pair))
        first = schedule_by_id[identifiers[0]]
        exact = entry.exact
        severity = "warning" if exact else "notice"
        findings.append(
            _finding(
                "CC006",
                severity,
                "Scheduled workflows collide" if exact else "Scheduled workflows nearly collide",
                (
                    f"The pair lands within {policy.collision_window_minutes} minute(s) "
                    f"{entry.count} time(s) in the collision horizon; {exact} are exact."
                ),
                first,
                {
                    "schedule_ids": list(identifiers),
                    "collision_count": entry.count,
                    "exact_count": exact,
                    "examples": entry.examples,
                },
                identifiers,
            )
        )
    return findings


def _duration_for(schedule: ScheduleSpec, policy: Policy) -> float:
    matches = [
        (pattern, minutes)
        for pattern, minutes in policy.durations.items()
        if fnmatch(schedule.path, pattern)
    ]
    if not matches:
        return policy.default_job_minutes
    matches.sort(key=lambda item: (-len(item[0]), item[0]))
    return matches[0][1]


def _apply_ignores(
    findings: list[Finding], policy: Policy, today: date
) -> tuple[list[Finding], list[Finding]]:
    active: list[Finding] = []
    suppressed: list[Finding] = []
    for finding in findings:
        ignored = any(
            item.rule == finding.rule_id
            and fnmatch(finding.path, item.path)
            and (item.expires is None or item.expires >= today)
            for item in policy.ignore
        )
        (suppressed if ignored else active).append(finding)
    return active, suppressed


def _finding(
    rule_id: str,
    severity: str,
    title: str,
    message: str,
    schedule: ScheduleSpec,
    evidence: dict[str, object] | None = None,
    schedule_ids: tuple[str, ...] | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        message=message,
        path=schedule.path,
        line=schedule.line,
        schedule_ids=schedule_ids or (schedule.schedule_id,),
        evidence=evidence or {},
    )


def _finding_sort_key(item: Finding) -> tuple[int, str, int, str]:
    return (-_SEVERITY_ORDER[item.severity], item.path, item.line, item.rule_id)
