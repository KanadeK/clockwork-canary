# Contributing

Thank you for improving Clockwork Canary.

## Before opening a change

1. Search existing issues and the [rule catalog](docs/RULES.md).
2. Reduce schedule bugs to a synthetic workflow. Never commit a real secret or private production schedule.
3. Explain which GitHub-documented behavior, POSIX cron rule, or deliberately conservative policy supports the change.

## Local setup

```bash
python -m pip install -e ".[dev]"
python scripts/verify.py
```

Target Python 3.11 or later. New rules must include:

- a stable `CCxxx` identifier;
- source location and repair-oriented wording;
- positive, negative, and boundary tests;
- JSON and SARIF-safe evidence;
- documentation in `docs/RULES.md`.

Avoid adding runtime dependencies unless the feature cannot be implemented safely with the standard library or existing PyYAML boundary. Reports must remain deterministic when `--start` is fixed.

## Pull requests

Keep commits focused. In the description, include the problem, behavioral change, compatibility impact, and output from `python scripts/verify.py`. By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
