"""Small, high-signal secret preflight for release contents."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    "",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest-tmp",
    ".ruff_cache",
    ".verify-tmp",
    "build",
    "dist",
    "release",
}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def candidate_files() -> list[Path]:
    process = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode == 0 and process.stdout.strip():
        paths = [ROOT / line for line in process.stdout.splitlines()]
    else:
        paths = list(ROOT.rglob("*"))
    return sorted(
        path
        for path in paths
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not (set(path.relative_to(ROOT).parts) & EXCLUDED_PARTS)
    )


def main() -> int:
    findings: list[str] = []
    paths = candidate_files()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: possible {label}")
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"secret scan: PASS ({len(paths)} text files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
