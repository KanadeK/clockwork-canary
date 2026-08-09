"""Fail when a committed Markdown file points at a missing local target."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
TEXT_FILES = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "CONTRIBUTING.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in LINK.finditer(line):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            candidate = (path.parent / unquote(target)).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}:{line_number}: path escapes repository")
                continue
            if not candidate.exists():
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_number}: missing local target {target!r}"
                )
    return errors


def main() -> int:
    errors = [error for path in TEXT_FILES for error in check_file(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"local links: PASS ({len(TEXT_FILES)} Markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
