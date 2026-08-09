"""Discover scheduled GitHub Actions while preserving source locations."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .models import Finding, ScheduleSpec


class GitHubActionsLoader(yaml.SafeLoader):
    """YAML loader that keeps the GitHub key ``on`` as a string."""


GitHubActionsLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for resolver_key, resolvers in GitHubActionsLoader.yaml_implicit_resolvers.items():
    GitHubActionsLoader.yaml_implicit_resolvers[resolver_key] = [
        item for item in resolvers if item[0] != "tag:yaml.org,2002:bool"
    ]


@dataclass(slots=True)
class DiscoveryResult:
    schedules: list[ScheduleSpec]
    findings: list[Finding]
    files_scanned: int


def discover(root: Path) -> DiscoveryResult:
    root = root.resolve()
    workflow_root = root / ".github" / "workflows"
    if not workflow_root.is_dir():
        return DiscoveryResult(
            schedules=[],
            findings=[
                Finding(
                    rule_id="CC001",
                    severity="error",
                    title="Workflow directory not found",
                    message=f"Expected scheduled workflows under {workflow_root}.",
                    path=".github/workflows",
                    line=1,
                )
            ],
            files_scanned=0,
        )

    paths = sorted([*workflow_root.rglob("*.yml"), *workflow_root.rglob("*.yaml")])
    schedules: list[ScheduleSpec] = []
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.load(text, Loader=GitHubActionsLoader)
            node = yaml.compose(text, Loader=GitHubActionsLoader)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            line = _yaml_error_line(exc)
            findings.append(
                Finding(
                    rule_id="CC001",
                    severity="error",
                    title="Workflow cannot be parsed",
                    message=str(exc).splitlines()[0],
                    path=relative,
                    line=line,
                )
            )
            continue

        if not isinstance(data, dict):
            findings.append(
                Finding(
                    rule_id="CC001",
                    severity="error",
                    title="Workflow root must be a mapping",
                    message="The workflow did not parse to a YAML object.",
                    path=relative,
                    line=1,
                )
            )
            continue

        event = data.get("on")
        if not isinstance(event, dict) or "schedule" not in event:
            continue
        raw_schedules = event.get("schedule")
        if not isinstance(raw_schedules, list):
            findings.append(
                Finding(
                    rule_id="CC001",
                    severity="error",
                    title="Schedule must be a list",
                    message="GitHub Actions expects on.schedule to contain a list of cron objects.",
                    path=relative,
                    line=_mapping_value_line(node, ("on", "schedule")),
                )
            )
            continue

        locations = _schedule_locations(node)
        raw_jobs = data.get("jobs")
        jobs = cast(dict[str, Any], raw_jobs) if isinstance(raw_jobs, dict) else {}
        runners, has_matrix = _job_metadata(jobs)
        workflow_name = str(data.get("name") or path.stem)
        for index, raw in enumerate(raw_schedules):
            line = locations[index] if index < len(locations) else 1
            if not isinstance(raw, dict) or not isinstance(raw.get("cron"), str):
                findings.append(
                    Finding(
                        rule_id="CC001",
                        severity="error",
                        title="Schedule entry is invalid",
                        message="Each on.schedule item must contain a string cron value.",
                        path=relative,
                        line=line,
                    )
                )
                continue
            raw_timezone = raw.get("timezone")
            if raw_timezone is not None and not isinstance(raw_timezone, str):
                findings.append(
                    Finding(
                        rule_id="CC001",
                        severity="error",
                        title="Timezone must be a string",
                        message="Use an IANA name such as America/New_York.",
                        path=relative,
                        line=line,
                    )
                )
                continue
            schedule_id = f"{relative}:{line}:{index + 1}"
            schedules.append(
                ScheduleSpec(
                    schedule_id=schedule_id,
                    workflow_name=workflow_name,
                    path=relative,
                    line=line,
                    expression=raw["cron"].strip(),
                    timezone=(raw_timezone or "UTC").strip(),
                    timezone_explicit=raw_timezone is not None,
                    job_count=max(1, len(jobs)),
                    runners=runners,
                    has_matrix=has_matrix,
                )
            )

    return DiscoveryResult(schedules=schedules, findings=findings, files_scanned=len(paths))


def _job_metadata(jobs: dict[str, Any]) -> tuple[tuple[str, ...], bool]:
    runners: set[str] = set()
    has_matrix = False
    for raw_job in jobs.values():
        if not isinstance(raw_job, dict):
            continue
        raw_runner = raw_job.get("runs-on")
        if isinstance(raw_runner, str):
            runners.add(raw_runner)
        elif isinstance(raw_runner, list):
            runners.update(str(item) for item in raw_runner)
        strategy = raw_job.get("strategy")
        has_matrix = has_matrix or (isinstance(strategy, dict) and "matrix" in strategy)
    return tuple(sorted(runners)), has_matrix


def _schedule_locations(node: Node | None) -> list[int]:
    schedule = _mapping_value_node(node, ("on", "schedule"))
    if not isinstance(schedule, SequenceNode):
        return []
    lines: list[int] = []
    for item in schedule.value:
        cron_node = _mapping_value_node(item, ("cron",))
        lines.append((cron_node or item).start_mark.line + 1)
    return lines


def _mapping_value_line(node: Node | None, path: tuple[str, ...]) -> int:
    value = _mapping_value_node(node, path)
    return value.start_mark.line + 1 if value else 1


def _mapping_value_node(node: Node | None, path: tuple[str, ...]) -> Node | None:
    current = node
    for wanted in path:
        if not isinstance(current, MappingNode):
            return None
        match: Node | None = None
        for key, value in current.value:
            if isinstance(key, ScalarNode) and key.value == wanted:
                match = value
                break
        current = match
    return current


def _yaml_error_line(exc: BaseException) -> int:
    mark = getattr(exc, "problem_mark", None)
    return int(mark.line) + 1 if mark is not None else 1
