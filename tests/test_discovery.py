from __future__ import annotations

from pathlib import Path

from clockwork_canary.discovery import discover


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_discovers_schedule_metadata_and_preserves_on_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/workflows/nightly.yml",
        "name: Nightly\n"
        "on:\n"
        "  schedule:\n"
        "    - cron: '17 4 * * 1-5'\n"
        "      timezone: America/New_York\n"
        "jobs:\n"
        "  test:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        python: ['3.11', '3.12']\n"
        "    runs-on: ubuntu-latest\n"
        "  report:\n"
        "    runs-on: [self-hosted, linux]\n",
    )
    result = discover(tmp_path)
    assert result.files_scanned == 1
    assert result.findings == []
    assert len(result.schedules) == 1
    schedule = result.schedules[0]
    assert schedule.workflow_name == "Nightly"
    assert schedule.line == 4
    assert schedule.timezone == "America/New_York"
    assert schedule.timezone_explicit is True
    assert schedule.job_count == 2
    assert schedule.has_matrix is True
    assert schedule.runners == ("linux", "self-hosted", "ubuntu-latest")


def test_missing_workflow_directory_is_actionable(tmp_path: Path) -> None:
    result = discover(tmp_path)
    assert result.files_scanned == 0
    assert result.findings[0].rule_id == "CC001"
    assert "not found" in result.findings[0].title.lower()


def test_invalid_yaml_records_source_line(tmp_path: Path) -> None:
    _write(tmp_path, ".github/workflows/broken.yml", "on:\n  schedule: [\n")
    result = discover(tmp_path)
    assert result.schedules == []
    assert result.findings[0].path.endswith("broken.yml")
    assert result.findings[0].line >= 2


def test_non_mapping_workflow_and_bad_schedule_shapes_are_reported(tmp_path: Path) -> None:
    _write(tmp_path, ".github/workflows/list.yml", "- hello\n")
    _write(tmp_path, ".github/workflows/map.yml", "on:\n  schedule: nope\n")
    _write(
        tmp_path,
        ".github/workflows/items.yml",
        "on:\n"
        "  schedule:\n"
        "    - nope\n"
        "    - cron: 123\n"
        "    - cron: '17 2 * * *'\n"
        "      timezone: 42\n"
        "jobs: {}\n",
    )
    result = discover(tmp_path)
    assert result.schedules == []
    assert result.files_scanned == 3
    assert len(result.findings) == 5
    assert {item.title for item in result.findings} >= {
        "Workflow root must be a mapping",
        "Schedule must be a list",
        "Schedule entry is invalid",
        "Timezone must be a string",
    }


def test_workflows_without_schedules_are_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/workflows/ci.yaml",
        "on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
    )
    result = discover(tmp_path)
    assert result.files_scanned == 1
    assert result.schedules == []
    assert result.findings == []
