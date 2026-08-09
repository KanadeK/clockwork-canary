# Acceptance commands

Run from the repository root on Python 3.11 or later.

## 1. Install

```bash
python -m pip install -e ".[dev]"
clockwork-canary --version
```

Expected: version `0.1.1` and exit code `0`.

## 2. Healthy fixture

```bash
clockwork-canary scan examples/healthy-repo \
  --start 2026-01-01T00:00:00Z
```

Expected: one schedule, zero active findings, exit code `0`.

## 3. Risky fixture

```bash
clockwork-canary scan examples/risky-repo \
  --start 2026-01-01T00:00:00Z
```

Expected: non-zero exit because policy fails on warnings. Output must include at least `CC002`, `CC003`, `CC004`, `CC005`, `CC006`, `CC007`, `CC008`, and `CC009` across the fixture schedules.

## 4. DST evidence

```bash
clockwork-canary explain "30 2 * * *" \
  --timezone America/New_York \
  --start 2026-03-07T00:00:00Z \
  --count 4 \
  --format json
```

Expected: one occurrence with `adjusted_for_dst_gap: true`, intended local time `2026-03-08T02:30:00`, and actual UTC time `2026-03-08T07:00:00Z`.

## 5. Report formats

```bash
clockwork-canary scan examples/risky-repo --fail-on none \
  --start 2026-01-01T00:00:00Z \
  --format markdown --output reports/audit.md

clockwork-canary scan examples/risky-repo --fail-on none \
  --start 2026-01-01T00:00:00Z \
  --format sarif --output reports/audit.sarif
```

Expected: both files exist; SARIF parses as JSON, declares version `2.1.0`, and every result has a rule ID and source location.

## 6. Full release gate

```bash
python scripts/verify.py
```

Expected stages:

1. Ruff lint and format check;
2. strict mypy;
3. pytest with at least 92% branch coverage;
4. healthy/risky/DST acceptance;
5. README local-link validation;
6. secret scan;
7. wheel and sdist build;
8. wheel install in a clean virtual environment;
9. release manifest and checksum verification.

The final line must say `release gate: PASS`. A partial run is not a release pass.
