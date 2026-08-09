"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__
from .analyzer import analyze, should_fail
from .config import ConfigError, load_policy, template
from .cron import CronExpression, CronSyntaxError, iter_occurrences
from .discovery import discover
from .reporters import render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clockwork-canary",
        description=(
            "Audit scheduled GitHub Actions for DST surprises, load spikes, collisions, "
            "and runner-minute risk."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan a repository's scheduled workflows")
    scan.add_argument("path", nargs="?", default=".", help="repository root (default: current dir)")
    scan.add_argument("--config", type=Path, help="policy JSON path")
    scan.add_argument("--horizon-days", type=int, help="override simulation horizon")
    scan.add_argument("--collision-window", type=int, help="override collision window in minutes")
    scan.add_argument("--start", help="fixed ISO-8601 simulation start; useful for CI evidence")
    scan.add_argument(
        "--format",
        choices=("text", "json", "markdown", "sarif"),
        default="text",
        help="report format",
    )
    scan.add_argument("--output", type=Path, help="write the report to a file")
    scan.add_argument(
        "--fail-on",
        choices=("none", "notice", "warning", "error"),
        help="exit 1 at or above this severity (default: policy value)",
    )

    explain = subparsers.add_parser("explain", help="simulate one cron expression")
    explain.add_argument("expression")
    explain.add_argument("--timezone", default="UTC")
    explain.add_argument("--start", help="ISO-8601 start (default: now)")
    explain.add_argument("--count", type=int, default=10)
    explain.add_argument("--format", choices=("text", "json"), default="text")

    init = subparsers.add_parser("init", help="write a documented policy template")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            return _scan(args)
        if args.command == "explain":
            return _explain(args)
        if args.command == "init":
            return _init(args)
    except (ConfigError, CronSyntaxError, ZoneInfoNotFoundError, ValueError, OSError) as exc:
        print(f"clockwork-canary: {exc}", file=sys.stderr)
        return 2
    return 2


def _scan(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        raise ValueError(f"repository path does not exist: {root}")
    config_path = args.config.resolve() if args.config else None
    policy = load_policy(root, config_path)
    if args.horizon_days is not None:
        if args.horizon_days < 2:
            raise ValueError("--horizon-days must be at least 2")
        policy.horizon_days = args.horizon_days
        policy.collision_horizon_days = min(policy.collision_horizon_days, args.horizon_days)
    if args.collision_window is not None:
        if args.collision_window < 0:
            raise ValueError("--collision-window cannot be negative")
        policy.collision_window_minutes = args.collision_window
    start = _parse_datetime(args.start) if args.start else datetime.now(UTC)
    # A fixed start opts into reproducible evidence mode, including report metadata.
    generated_at = start if args.start else None
    report = analyze(root, discover(root), policy, start, generated_at=generated_at)
    rendered = render(report, args.format)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"Wrote {args.format} report to {output}")
    else:
        print(rendered, end="")
    threshold = args.fail_on or policy.fail_on
    return 1 if should_fail(report.findings, threshold) else 0


def _explain(args: argparse.Namespace) -> int:
    if args.count < 1 or args.count > 1000:
        raise ValueError("--count must be between 1 and 1000")
    expression = CronExpression.parse(args.expression)
    timezone = ZoneInfo(args.timezone)
    start = _parse_datetime(args.start) if args.start else datetime.now(UTC)
    end = start + timedelta(days=400)
    occurrences = []
    for occurrence in iter_occurrences(expression, timezone, start, end):
        occurrences.append(occurrence)
        if len(occurrences) >= args.count:
            break
    payload = {
        "expression": expression.source,
        "timezone": args.timezone,
        "parsed": expression.describe(),
        "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "occurrences": [item.as_dict() for item in occurrences],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"{expression.source} in {args.timezone}")
        print(expression.describe())
        for item in occurrences:
            suffix = (
                f" (advanced from {item.intended_local.isoformat()})"
                if item.adjusted_for_gap and item.intended_local
                else ""
            )
            print(
                f"  {item.actual_utc.isoformat().replace('+00:00', 'Z')}  "
                f"{item.local_time.isoformat()}{suffix}"
            )
    return 0


def _init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / ".clockwork-canary.json"
    if target.exists() and not args.force:
        raise ValueError(f"refusing to overwrite {target}; pass --force to replace it")
    target.write_text(
        json.dumps(template(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {target}")
    return 0


def _parse_datetime(source: str) -> datetime:
    normalized = source[:-1] + "+00:00" if source.endswith("Z") else source
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 datetime: {source}") from exc
    if value.tzinfo is None:
        raise ValueError("datetime must include Z or an explicit UTC offset")
    return value.astimezone(UTC)
