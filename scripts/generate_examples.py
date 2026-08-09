"""Regenerate committed, fixed-time example reports from the real CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from clockwork_canary.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "generated"
START = "2026-01-01T00:00:00Z"


def main() -> int:
    if OUTPUT.exists():
        resolved = OUTPUT.resolve()
        if resolved.parent != (ROOT / "docs").resolve():
            raise RuntimeError(f"refusing to replace unexpected path: {resolved}")
        shutil.rmtree(resolved)
    OUTPUT.mkdir(parents=True)
    jobs = [
        (
            [
                "scan",
                str(ROOT / "examples" / "healthy-repo"),
                "--start",
                START,
                "--format",
                "text",
                "--output",
                str(OUTPUT / "healthy.txt"),
            ],
            0,
        ),
        (
            [
                "scan",
                str(ROOT / "examples" / "risky-repo"),
                "--start",
                START,
                "--fail-on",
                "none",
                "--format",
                "markdown",
                "--output",
                str(OUTPUT / "risky.md"),
            ],
            0,
        ),
        (
            [
                "scan",
                str(ROOT / "examples" / "risky-repo"),
                "--start",
                START,
                "--fail-on",
                "none",
                "--format",
                "json",
                "--output",
                str(OUTPUT / "risky.json"),
            ],
            0,
        ),
        (
            [
                "scan",
                str(ROOT / "examples" / "risky-repo"),
                "--start",
                START,
                "--fail-on",
                "none",
                "--format",
                "sarif",
                "--output",
                str(OUTPUT / "risky.sarif"),
            ],
            0,
        ),
    ]
    for arguments, expected in jobs:
        result = cli_main(arguments)
        if result != expected:
            raise RuntimeError(f"example generation returned {result}: {arguments}")
    print(f"example reports: PASS ({len(jobs)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
