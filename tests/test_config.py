from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from clockwork_canary.config import ConfigError, load_policy, template


def _config(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / ".clockwork-canary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_defaults_and_complete_config(tmp_path: Path) -> None:
    assert load_policy(tmp_path).horizon_days == 370
    path = _config(
        tmp_path,
        {
            "horizon_days": 40,
            "collision_horizon_days": 10,
            "collision_window_minutes": 2,
            "default_job_minutes": 5.5,
            "monthly_minutes_warning": 500,
            "fail_on": "error",
            "durations": {".github/workflows/*.yml": 12},
            "ignore": [
                {
                    "rule": "cc003",
                    "path": "*.yml",
                    "reason": "fixed upstream window",
                    "expires": "2026-12-31",
                }
            ],
        },
    )
    policy = load_policy(tmp_path, path)
    assert policy.horizon_days == 40
    assert policy.default_job_minutes == 5.5
    assert policy.durations[".github/workflows/*.yml"] == 12
    assert policy.ignore[0].rule == "CC003"
    assert policy.ignore[0].expires == date(2026, 12, 31)


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "root"),
        ({"mystery": 1}, "unknown"),
        ({"horizon_days": 1}, "at least 2"),
        ({"horizon_days": True}, "non-negative integer"),
        ({"horizon_days": 10, "collision_horizon_days": 11}, "within"),
        ({"collision_window_minutes": -1}, "non-negative"),
        ({"default_job_minutes": 0}, "positive"),
        ({"monthly_minutes_warning": False}, "positive"),
        ({"fail_on": "loud"}, "fail_on"),
        ({"durations": []}, "durations"),
        ({"durations": {"x": "fast"}}, "numeric"),
        ({"durations": {"x": 0}}, "positive"),
        ({"ignore": {}}, "ignore must be a list"),
        ({"ignore": ["nope"]}, "object"),
        ({"ignore": [{"rule": "CC1", "path": "*", "reason": ""}]}, "reason"),
        (
            {"ignore": [{"rule": "CC1", "path": "*", "reason": "why", "extra": True}]},
            "unknown ignore",
        ),
        (
            {"ignore": [{"rule": "CC1", "path": "*", "reason": "why", "expires": "soon"}]},
            "YYYY-MM-DD",
        ),
    ],
)
def test_invalid_configuration_is_rejected(tmp_path: Path, payload: object, message: str) -> None:
    path = _config(tmp_path, payload)
    with pytest.raises(ConfigError, match=message):
        load_policy(tmp_path, path)


def test_malformed_json_and_template(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot read"):
        load_policy(tmp_path, path)
    assert template()["fail_on"] == "warning"
