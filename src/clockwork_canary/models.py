"""Typed domain models shared by discovery, analysis, and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

Severity = Literal["notice", "warning", "error"]


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    """One ``on.schedule`` entry discovered in a workflow."""

    schedule_id: str
    workflow_name: str
    path: str
    line: int
    expression: str
    timezone: str
    timezone_explicit: bool
    job_count: int
    runners: tuple[str, ...]
    has_matrix: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.schedule_id,
            "workflow": self.workflow_name,
            "path": self.path,
            "line": self.line,
            "expression": self.expression,
            "timezone": self.timezone,
            "timezone_explicit": self.timezone_explicit,
            "job_count": self.job_count,
            "runners": list(self.runners),
            "has_matrix": self.has_matrix,
        }


@dataclass(frozen=True, slots=True)
class Occurrence:
    """A simulated scheduled run."""

    actual_utc: datetime
    local_time: datetime
    intended_local: datetime | None = None
    adjusted_for_gap: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual_utc": self.actual_utc.isoformat().replace("+00:00", "Z"),
            "local_time": self.local_time.isoformat(),
            "intended_local": self.intended_local.isoformat() if self.intended_local else None,
            "adjusted_for_dst_gap": self.adjusted_for_gap,
            "fold": self.local_time.fold,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """One actionable audit result."""

    rule_id: str
    severity: Severity
    title: str
    message: str
    path: str
    line: int
    schedule_ids: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "schedule_ids": list(self.schedule_ids),
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ScheduleMetrics:
    """Simulation metrics for one schedule."""

    schedule_id: str
    runs_in_horizon: int
    runs_per_30_days: float
    estimated_runner_minutes_per_30_days: float
    minimum_interval_minutes: int | None
    next_runs: tuple[Occurrence, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "runs_in_horizon": self.runs_in_horizon,
            "runs_per_30_days": round(self.runs_per_30_days, 2),
            "estimated_runner_minutes_per_30_days": round(
                self.estimated_runner_minutes_per_30_days, 2
            ),
            "minimum_interval_minutes": self.minimum_interval_minutes,
            "next_runs": [item.as_dict() for item in self.next_runs],
        }


@dataclass(slots=True)
class AuditReport:
    """Complete, reporter-neutral audit result."""

    root: Path
    generated_at: datetime
    simulation_start: datetime
    horizon_days: int
    schedules: list[ScheduleSpec]
    metrics: list[ScheduleMetrics]
    findings: list[Finding]
    suppressed_findings: list[Finding]
    assumptions: list[str]

    def as_dict(self) -> dict[str, Any]:
        counts = {severity: 0 for severity in ("error", "warning", "notice")}
        for finding in self.findings:
            counts[finding.severity] += 1
        return {
            "schema_version": "1.0",
            "tool": {"name": "clockwork-canary", "version": _package_version()},
            "root": str(self.root),
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "simulation_start": self.simulation_start.isoformat().replace("+00:00", "Z"),
            "horizon_days": self.horizon_days,
            "summary": {
                "schedules": len(self.schedules),
                "findings": len(self.findings),
                "suppressed": len(self.suppressed_findings),
                **counts,
            },
            "assumptions": self.assumptions,
            "schedules": [item.as_dict() for item in self.schedules],
            "metrics": [item.as_dict() for item in self.metrics],
            "findings": [item.as_dict() for item in self.findings],
            "suppressed_findings": [item.as_dict() for item in self.suppressed_findings],
        }


def _package_version() -> str:
    from . import __version__

    return __version__
