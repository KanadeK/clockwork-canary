"""Load and validate repository policy without silently accepting typos."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised for an invalid Clockwork Canary policy."""


@dataclass(frozen=True, slots=True)
class IgnoreRule:
    rule: str
    path: str
    reason: str
    expires: date | None = None


@dataclass(slots=True)
class Policy:
    horizon_days: int = 370
    collision_horizon_days: int = 14
    collision_window_minutes: int = 5
    default_job_minutes: float = 10.0
    monthly_minutes_warning: float = 2000.0
    fail_on: str = "warning"
    durations: dict[str, float] = field(default_factory=dict)
    ignore: list[IgnoreRule] = field(default_factory=list)


_KNOWN_KEYS = {
    "horizon_days",
    "collision_horizon_days",
    "collision_window_minutes",
    "default_job_minutes",
    "monthly_minutes_warning",
    "fail_on",
    "durations",
    "ignore",
}


def load_policy(root: Path, config_path: Path | None = None) -> Policy:
    path = config_path or (root / ".clockwork-canary.json")
    if not path.exists():
        return Policy()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a JSON object")
    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise ConfigError(f"unknown configuration keys: {', '.join(unknown)}")

    policy = Policy()
    for key in (
        "horizon_days",
        "collision_horizon_days",
        "collision_window_minutes",
    ):
        if key in raw:
            value = raw[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ConfigError(f"{key} must be a non-negative integer")
            setattr(policy, key, value)
    if policy.horizon_days < 2:
        raise ConfigError("horizon_days must be at least 2")
    if not 1 <= policy.collision_horizon_days <= policy.horizon_days:
        raise ConfigError("collision_horizon_days must be within horizon_days")

    for key in ("default_job_minutes", "monthly_minutes_warning"):
        if key in raw:
            value = raw[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ConfigError(f"{key} must be a positive number")
            setattr(policy, key, float(value))

    if "fail_on" in raw:
        if raw["fail_on"] not in {"none", "notice", "warning", "error"}:
            raise ConfigError("fail_on must be one of none, notice, warning, or error")
        policy.fail_on = raw["fail_on"]

    if "durations" in raw:
        if not isinstance(raw["durations"], dict):
            raise ConfigError("durations must be an object mapping paths to minutes")
        for path_glob, minutes in raw["durations"].items():
            if not isinstance(path_glob, str) or not isinstance(minutes, (int, float)):
                raise ConfigError("duration entries must map string paths to numeric minutes")
            if isinstance(minutes, bool) or minutes <= 0:
                raise ConfigError("duration minutes must be positive")
            policy.durations[path_glob] = float(minutes)

    if "ignore" in raw:
        if not isinstance(raw["ignore"], list):
            raise ConfigError("ignore must be a list")
        policy.ignore = [_parse_ignore(item) for item in raw["ignore"]]
    return policy


def template() -> dict[str, Any]:
    return {
        "horizon_days": 370,
        "collision_horizon_days": 14,
        "collision_window_minutes": 5,
        "default_job_minutes": 10,
        "monthly_minutes_warning": 2000,
        "fail_on": "warning",
        "durations": {".github/workflows/nightly.yml": 25},
        "ignore": [
            {
                "rule": "CC003",
                "path": ".github/workflows/vendor-sync.yml",
                "reason": "The upstream window is fixed and the job is idempotent.",
                "expires": "2026-12-31",
            }
        ],
    }


def _parse_ignore(raw: Any) -> IgnoreRule:
    if not isinstance(raw, dict):
        raise ConfigError("each ignore entry must be an object")
    allowed = {"rule", "path", "reason", "expires"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"unknown ignore keys: {', '.join(unknown)}")
    for required in ("rule", "path", "reason"):
        if not isinstance(raw.get(required), str) or not raw[required].strip():
            raise ConfigError(f"ignore.{required} must be a non-empty string")
    expires = None
    if raw.get("expires") is not None:
        try:
            expires = date.fromisoformat(raw["expires"])
        except (TypeError, ValueError) as exc:
            raise ConfigError("ignore.expires must use YYYY-MM-DD") from exc
    return IgnoreRule(
        rule=raw["rule"].upper(),
        path=raw["path"],
        reason=raw["reason"],
        expires=expires,
    )
