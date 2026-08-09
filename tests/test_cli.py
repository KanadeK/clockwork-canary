from __future__ import annotations

import json
from pathlib import Path

import pytest

from clockwork_canary.cli import build_parser, main


def _repo(tmp_path: Path, cron: str = "17 4 * * 1-5", timezone: str | None = "UTC") -> Path:
    workflow = tmp_path / ".github" / "workflows" / "scheduled.yml"
    workflow.parent.mkdir(parents=True)
    timezone_line = f"      timezone: {timezone}\n" if timezone else ""
    workflow.write_text(
        "name: Scheduled\n"
        "on:\n"
        "  schedule:\n"
        f"    - cron: '{cron}'\n"
        f"{timezone_line}"
        "jobs:\n"
        "  run:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    return tmp_path


def test_scan_healthy_repo_and_write_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    output = tmp_path / "reports" / "audit.json"
    result = main(
        [
            "scan",
            str(root),
            "--start",
            "2026-01-01T00:00:00Z",
            "--horizon-days",
            "10",
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["findings"] == 0
    assert "Wrote json report" in capsys.readouterr().out


def test_scan_risky_repo_honors_fail_on(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, cron="0 4 * * *", timezone=None)
    result = main(
        [
            "scan",
            str(root),
            "--start",
            "2026-01-01T00:00:00+00:00",
            "--horizon-days",
            "5",
            "--fail-on",
            "warning",
        ]
    )
    assert result == 1
    assert "CC003" in capsys.readouterr().out


def test_explain_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "explain",
                "17 4 * * *",
                "--start",
                "2026-01-01T00:00:00Z",
                "--count",
                "2",
            ]
        )
        == 0
    )
    assert "17 4 * * * in UTC" in capsys.readouterr().out
    assert (
        main(
            [
                "explain",
                "17 4 * * *",
                "--start",
                "2026-01-01T00:00:00Z",
                "--count",
                "1",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["occurrences"]


def test_init_and_refuse_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init", str(tmp_path)]) == 0
    target = tmp_path / ".clockwork-canary.json"
    assert json.loads(target.read_text(encoding="utf-8"))["horizon_days"] == 370
    assert main(["init", str(tmp_path)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert main(["init", str(tmp_path), "--force"]) == 0


@pytest.mark.parametrize(
    "argv, message",
    [
        (["scan", "missing"], "does not exist"),
        (["explain", "bad"], "exactly 5"),
        (["explain", "0 0 * * *", "--count", "0"], "between 1 and 1000"),
        (
            ["explain", "0 0 * * *", "--start", "2026-01-01T00:00:00"],
            "explicit UTC offset",
        ),
    ],
)
def test_cli_user_errors_return_two(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    assert message in capsys.readouterr().err


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
