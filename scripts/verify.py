"""Single local/CI release gate with functional and packaging evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_ROOT = ROOT / ".verify-tmp"
START = "2026-01-01T00:00:00Z"


def run(
    label: str,
    command: list[str],
    *,
    expected: set[int] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"[{label}] {' '.join(command)}")
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )
    allowed = expected or {0}
    if process.returncode not in allowed:
        if capture:
            print(process.stdout)
            print(process.stderr, file=sys.stderr)
        raise RuntimeError(
            f"{label} failed with exit {process.returncode}; expected {sorted(allowed)}"
        )
    return process


def functional_acceptance() -> None:
    VERIFY_ROOT.mkdir(parents=True, exist_ok=True)
    healthy = VERIFY_ROOT / "healthy.json"
    risky = VERIFY_ROOT / "risky.json"
    run(
        "healthy fixture",
        [
            sys.executable,
            "-m",
            "clockwork_canary",
            "scan",
            "examples/healthy-repo",
            "--start",
            START,
            "--format",
            "json",
            "--output",
            str(healthy),
        ],
    )
    healthy_payload = json.loads(healthy.read_text(encoding="utf-8"))
    if healthy_payload["summary"]["findings"] != 0:
        raise RuntimeError("healthy fixture produced findings")

    run(
        "risky fixture evidence",
        [
            sys.executable,
            "-m",
            "clockwork_canary",
            "scan",
            "examples/risky-repo",
            "--start",
            START,
            "--fail-on",
            "none",
            "--format",
            "json",
            "--output",
            str(risky),
        ],
    )
    risky_payload = json.loads(risky.read_text(encoding="utf-8"))
    actual_rules = {item["rule_id"] for item in risky_payload["findings"]}
    expected_rules = {f"CC{number:03d}" for number in range(2, 10)}
    if not expected_rules <= actual_rules:
        raise RuntimeError(f"risky fixture missing rules: {sorted(expected_rules - actual_rules)}")
    run(
        "risky fixture policy exit",
        [
            sys.executable,
            "-m",
            "clockwork_canary",
            "scan",
            "examples/risky-repo",
            "--start",
            START,
        ],
        expected={1},
        capture=True,
    )
    explained = run(
        "DST explanation",
        [
            sys.executable,
            "-m",
            "clockwork_canary",
            "explain",
            "30 2 * * *",
            "--timezone",
            "America/New_York",
            "--start",
            "2026-03-07T00:00:00Z",
            "--count",
            "4",
            "--format",
            "json",
        ],
        capture=True,
    )
    occurrences = json.loads(explained.stdout)["occurrences"]
    if not any(item["adjusted_for_dst_gap"] for item in occurrences):
        raise RuntimeError("DST explanation did not preserve a spring-forward adjustment")


def clean_wheel_smoke() -> None:
    wheels = sorted((ROOT / "release").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel, found {len(wheels)}")
    environment = VERIFY_ROOT / "wheel-venv"
    if environment.exists():
        shutil.rmtree(environment)
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    if sys.platform == "win32":
        python = environment / "Scripts" / "python.exe"
    else:
        python = environment / "bin" / "python"
    install_command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
    ]
    wheelhouse = ROOT / ".wheelhouse"
    if wheelhouse.is_dir() and any(wheelhouse.glob("*.whl")):
        install_command.extend(["--no-index", "--find-links", str(wheelhouse)])
    install_command.append(str(wheels[0]))
    run(
        "clean wheel install",
        install_command,
    )
    run("clean wheel version", [str(python), "-m", "clockwork_canary", "--version"])
    run(
        "clean wheel scan",
        [
            str(python),
            "-m",
            "clockwork_canary",
            "scan",
            "examples/healthy-repo",
            "--start",
            START,
        ],
    )


def sdist_rebuild_smoke() -> None:
    sdists = sorted((ROOT / "release").glob("*.tar.gz"))
    if len(sdists) != 1:
        raise RuntimeError(f"expected one sdist, found {len(sdists)}")
    output = VERIFY_ROOT / "sdist-wheel"
    output.mkdir()
    run(
        "sdist rebuild",
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(output),
            str(sdists[0]),
        ],
    )
    rebuilt = list(output.glob("*.whl"))
    if len(rebuilt) != 1:
        raise RuntimeError(f"sdist rebuild produced {len(rebuilt)} wheels")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-package", action="store_true")
    args = parser.parse_args(argv)
    if VERIFY_ROOT.exists():
        resolved = VERIFY_ROOT.resolve()
        if resolved.parent != ROOT:
            raise RuntimeError(f"refusing to replace unexpected path: {resolved}")
        shutil.rmtree(resolved)
    VERIFY_ROOT.mkdir()
    try:
        run("format", [sys.executable, "-m", "ruff", "format", "--check", "."])
        run("lint", [sys.executable, "-m", "ruff", "check", "."])
        run("types", [sys.executable, "-m", "mypy", "src", "tests", "scripts"])
        run(
            "tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "--cov=clockwork_canary",
                "--cov-branch",
                "--cov-report=term-missing",
            ],
        )
        functional_acceptance()
        run("example reports", [sys.executable, "scripts/generate_examples.py"])
        run("local links", [sys.executable, "scripts/check_links.py"])
        run("secret scan", [sys.executable, "scripts/secret_scan.py"])
        if not args.skip_package:
            run("package", [sys.executable, "scripts/package_release.py", "--clean"])
            sdist_rebuild_smoke()
            clean_wheel_smoke()
            run("manifest", [sys.executable, "scripts/package_release.py", "--verify"])
    finally:
        if VERIFY_ROOT.exists():
            shutil.rmtree(VERIFY_ROOT)
    print("release gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
