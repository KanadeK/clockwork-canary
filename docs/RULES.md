# Rule catalog

Rules describe review evidence, not moral judgments. Stable IDs make suppressions and CI policies durable.

## CC001

### Invalid schedule

Raised when the workflow directory is missing, YAML cannot be parsed, the workflow/schedule shape is invalid, the cron expression is unsupported, or the IANA timezone cannot be loaded.

**Repair:** run a general workflow linter such as `actionlint`, correct the reported file and line, then rerun Clockwork Canary. Use exactly five cron fields and a canonical IANA name such as `America/New_York` or explicit `UTC`.

## CC002

### Unsupported frequency

Raised when consecutive simulated runs are less than five minutes apart. GitHub Actions documents five minutes as the shortest supported schedule interval.

**Repair:** change the expression to `*/5` or slower. If the workload truly requires sub-five-minute execution, use a scheduler designed for that requirement.

## CC003

### Start-of-hour load

Raised whenever minute zero is selected. GitHub documents the start of each hour as a high-load period where scheduled events can be delayed and, under sufficient load, dropped.

**Repair:** choose a stable non-zero minute such as `17` or `43` unless the external contract genuinely requires the hour boundary. An accepted fixed window can be suppressed with a reason and expiry.

## CC004

### DST gap

Raised when a timezone-aware schedule selects a wall-clock minute that does not exist during spring-forward. GitHub documents that such runs advance to the next valid time.

**Repair:** move the schedule outside the transition window, use UTC when local alignment is unnecessary, or make downstream logic safe for the compressed interval. Evidence records intended and actual times.

## CC005

### DST fold

Raised when a selected wall-clock time occurs twice during fall-back. GitHub's public schedule documentation does not state a portable once-versus-twice guarantee for the repeated hour.

**Repair:** move outside the repeated hour, use UTC, or make the job idempotent with an external operation key. Do not depend on an undocumented run count.

## CC006

### Schedule collision

Raised once per pair when schedules land within `collision_window_minutes` during the collision horizon. Exact collisions are warnings; near collisions are notices.

**Repair:** stagger schedules, add downstream concurrency/idempotency controls, or reduce the collision window if the resources are genuinely independent.

## CC007

### Duplicate schedule

Raised when two or more entries have identical cron and timezone values.

**Repair:** consolidate jobs into one workflow or document why simultaneous independent runs are required. Duplicate pairs are excluded from CC006 to avoid double-reporting.

## CC008

### Runner-minute budget

Raised when the estimated raw 30-day runner minutes exceed `monthly_minutes_warning`.

The estimate is:

```text
runs per 30 days × top-level job count × configured minutes per job
```

**Repair:** set realistic per-workflow durations, reduce frequency, combine jobs, or raise the reviewed threshold. Matrix expansion, retries, conditions, actual duration, and billing multipliers are deliberately not guessed.

## CC009

### Implicit UTC

Raised as a notice when a schedule omits `timezone`. GitHub defaults to UTC, but reviewers cannot distinguish intentional UTC from a forgotten local-time conversion.

**Repair:** add `timezone: UTC` to state intent, or use the desired IANA timezone.

## Suppression policy

Suppressions match an exact rule ID and a glob against the finding path. They require a non-empty reason. An expired suppression stops applying automatically. Unknown keys or invalid expiry dates make configuration fail rather than silently broadening an exception.
