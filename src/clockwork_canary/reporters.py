"""Deterministic text, Markdown, JSON, and SARIF renderers."""

from __future__ import annotations

import json
from typing import Any

from .models import AuditReport, Finding

_RULES = {
    "CC001": ("Invalid schedule", "A workflow or schedule cannot be parsed or simulated."),
    "CC002": ("Unsupported frequency", "The interval is shorter than five minutes."),
    "CC003": ("Start-of-hour load", "The schedule uses minute zero."),
    "CC004": ("DST gap", "A wall-clock run falls in a skipped spring-forward hour."),
    "CC005": ("DST fold", "A wall-clock run falls in a repeated fall-back hour."),
    "CC006": ("Schedule collision", "Two schedules run within the configured window."),
    "CC007": ("Duplicate schedule", "Two or more entries have the same cron and timezone."),
    "CC008": ("Runner-minute budget", "Estimated monthly runner-minutes exceed policy."),
    "CC009": ("Implicit UTC", "The schedule relies on GitHub's default timezone."),
}


def render(report: AuditReport, output_format: str) -> str:
    if output_format == "text":
        return render_text(report)
    if output_format == "markdown":
        return render_markdown(report)
    if output_format == "json":
        return json.dumps(report.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output_format == "sarif":
        return json.dumps(_sarif(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    raise ValueError(f"unknown output format: {output_format}")


def render_text(report: AuditReport) -> str:
    data = report.as_dict()
    summary = data["summary"]
    lines = [
        "Clockwork Canary",
        (
            f"{summary['schedules']} schedule(s) | {summary['error']} error(s) | "
            f"{summary['warning']} warning(s) | {summary['notice']} notice(s) | "
            f"{summary['suppressed']} suppressed"
        ),
        "",
    ]
    metric_by_id = {item.schedule_id: item for item in report.metrics}
    if report.schedules:
        lines.append("Schedules")
        for schedule in report.schedules:
            metric = metric_by_id.get(schedule.schedule_id)
            estimate = (
                f"~{metric.runs_per_30_days:.1f} runs/30d, "
                f"~{metric.estimated_runner_minutes_per_30_days:.0f} runner-min/30d"
                if metric
                else "not simulated"
            )
            lines.append(
                f"  {schedule.path}:{schedule.line}  {schedule.expression}  "
                f"[{schedule.timezone}]  {estimate}"
            )
        lines.append("")
    if report.findings:
        lines.append("Findings")
        for finding in report.findings:
            lines.extend(_text_finding(finding))
    else:
        lines.append("No active findings.")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: AuditReport) -> str:
    data = report.as_dict()
    summary = data["summary"]
    lines = [
        "# Clockwork Canary audit",
        "",
        (
            f"**{summary['schedules']} schedules · {summary['error']} errors · "
            f"{summary['warning']} warnings · {summary['notice']} notices · "
            f"{summary['suppressed']} suppressed**"
        ),
        "",
        f"Simulation starts `{data['simulation_start']}` and covers {report.horizon_days} days.",
        "",
        "## Schedules",
        "",
        "| Workflow | Cron | Timezone | Runs / 30d | Est. runner-min / 30d |",
        "|---|---|---:|---:|---:|",
    ]
    metric_by_id = {item.schedule_id: item for item in report.metrics}
    for schedule in report.schedules:
        metric = metric_by_id.get(schedule.schedule_id)
        monthly_runs = f"{metric.runs_per_30_days:.2f}" if metric else "—"
        runner_minutes = f"{metric.estimated_runner_minutes_per_30_days:.2f}" if metric else "—"
        lines.append(
            "| "
            f"`{schedule.path}:{schedule.line}` | `{schedule.expression}` | "
            f"`{schedule.timezone}` | "
            f"{monthly_runs} | {runner_minutes} |"
        )
    if not report.schedules:
        lines.append("| _None_ | — | — | — | — |")

    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No active findings.")
    for finding in report.findings:
        lines.extend(
            [
                f"### {finding.rule_id} · {finding.severity.upper()} · {finding.title}",
                "",
                f"`{finding.path}:{finding.line}` — {finding.message}",
                "",
            ]
        )
    lines.extend(["## Assumptions", ""])
    lines.extend(f"- {item}" for item in report.assumptions)
    lines.append("")
    return "\n".join(lines)


def _text_finding(finding: Finding) -> list[str]:
    return [
        f"  [{finding.severity.upper()}] {finding.rule_id} {finding.path}:{finding.line}",
        f"    {finding.title}: {finding.message}",
    ]


def _sarif(report: AuditReport) -> dict[str, Any]:
    rules = []
    for rule_id, (name, description) in sorted(_RULES.items()):
        rules.append(
            {
                "id": rule_id,
                "name": name.replace(" ", ""),
                "shortDescription": {"text": name},
                "fullDescription": {"text": description},
                "helpUri": (
                    "https://github.com/KanadeK/clockwork-canary/blob/main/docs/RULES.md#"
                    f"{rule_id.lower()}"
                ),
            }
        )
    results = []
    for finding in report.findings:
        results.append(
            {
                "ruleId": finding.rule_id,
                "level": {"error": "error", "warning": "warning", "notice": "note"}[
                    finding.severity
                ],
                "message": {"text": f"{finding.title}: {finding.message}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.path.replace("\\", "/")},
                            "region": {"startLine": max(1, finding.line)},
                        }
                    }
                ],
                "properties": {
                    "scheduleIds": list(finding.schedule_ids),
                    "evidence": finding.evidence,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Clockwork Canary",
                        "informationUri": "https://github.com/KanadeK/clockwork-canary",
                        "version": report.as_dict()["tool"]["version"],
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
