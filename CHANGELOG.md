# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-08-09

### Fixed

- Remove machine-specific checkout paths from portable JSON evidence.
- Pin the complete packaging toolchain, canonicalize generated metadata newlines, and use host-independent archive streams for byte-identical Windows/Linux assets.
- Upgrade official checkout, setup-python, and upload-artifact workflow dependencies to v7.

## [0.1.0] - 2026-08-08

### Added

- Repository discovery for scheduled GitHub Actions with source locations.
- Five-field cron parser and IANA-timezone simulator.
- GitHub-documented spring-forward advancement and explicit fall-back ambiguity evidence.
- Rules for invalid schedules, sub-five-minute intervals, minute-zero load, DST transitions, cross-workflow collisions, duplicates, runner-minute budgets, and implicit UTC.
- Text, Markdown, JSON, and SARIF 2.1.0 reports.
- Expiring suppressions, per-workflow duration overrides, and fail-on-severity policy.
- Standalone `explain`, repository `scan`, and policy `init` commands.
- Composite GitHub Action, healthy/risky fixtures, full local release gate, CI, CodeQL, and deterministic release packaging.

[0.1.1]: https://github.com/KanadeK/clockwork-canary/releases/tag/v0.1.1
[0.1.0]: https://github.com/KanadeK/clockwork-canary/releases/tag/v0.1.0
