# Failure repair guide

Do not bypass a failing gate with `--no-deps`, disabled tests, reduced coverage, `|| true`, or a weaker `--fail-on` unless the repository policy change is the reviewed goal.

## Editable install or build fails

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m build
```

- If setuptools reports a license metadata conflict, keep the SPDX `license = "MIT"` expression and do not add the superseded `License ::` classifier.
- If README or license files are missing, restore them before rebuilding; do not remove package metadata to silence the error.
- On Windows timezone lookup failures, confirm the conditional `tzdata` dependency installed.

If PyPI is temporarily unreachable during the clean-wheel smoke test, populate an ignored local wheelhouse and rerun the unchanged gate:

```bash
python -m pip download --only-binary=:all: --dest .wheelhouse \
  "PyYAML>=6.0.2,<7" "tzdata>=2026.1"
python scripts/verify.py
```

The isolated venv then installs the release wheel and its declared dependencies with `--no-index --find-links .wheelhouse`. Never commit platform-specific wheels.

## CC001 parsing errors

Run `actionlint` first if available, then inspect the exact Clockwork Canary line. Confirm `on.schedule` is a list and every item contains a quoted five-field `cron` string. Use an IANA timezone, not an abbreviation such as `EST`.

## A healthy workflow unexpectedly fails

Use a fixed start and isolate the rule:

```bash
clockwork-canary scan path/to/repo --start 2026-01-01T00:00:00Z \
  --format json --fail-on none --output reports/debug.json
```

Check `evidence`, `schedule_ids`, assumptions, and policy duration globs. If the finding is accepted, add the narrowest rule/path suppression with a reason and expiry. Do not suppress by broad `*` unless every matching workflow was reviewed.

## DST output differs across machines

Compare Python and `tzdata` versions. Governments can change timezone rules, so tzdata is a real input. Reinstall from the lock-free declared bounds, then rerun with the same `--start`. If the upstream timezone database changed, update committed reports and explain the difference.

## Coverage or test failure

```bash
python -m pytest -x -vv
python -m pytest --cov=clockwork_canary --cov-branch --cov-report=term-missing
```

Repair the first functional failure before chasing coverage. Add a behavioral test for every bug. Never exclude a module merely to raise the percentage.

The project fixes pytest's base temp directory at `.pytest-tmp` because stale ACLs under the shared Windows `%TEMP%/pytest-of-*` root can otherwise block fixture setup. If that repository-local directory itself is locked, close only processes using it and remove that exact directory before retrying; do not clear the system temp tree.

## Ruff or mypy failure

```bash
python -m ruff check . --fix
python -m ruff format .
python -m mypy src tests scripts
```

Review automated edits, rerun tests, and keep public models typed. Avoid blanket `ignore_errors` or `Any` escapes.

## Release manifest mismatch

```bash
python scripts/package_release.py --clean
python scripts/package_release.py --verify
```

If two builds differ, inspect wheel and sdist archive timestamps/content before publishing. Do not replace a public tag to hide a mismatch; fix the source and publish a new patch version.

## GitHub Actions failure after local PASS

1. Open the exact failing job and preserve its log.
2. Confirm the remote commit equals local `git rev-parse HEAD`.
3. Reproduce with the same Python/OS matrix entry.
4. Fix and rerun the full local gate.
5. Push a new commit; never move an already published release tag without explicit recovery approval.

## Release or authentication failure

```bash
gh auth status
git remote -v
gh run list --limit 10
gh release view v0.1.0
```

Authentication, a green local build, a pushed commit, a green CI run, a tag, and a GitHub Release are separate facts. Do not send a completion notification until all required remote facts are verified.
