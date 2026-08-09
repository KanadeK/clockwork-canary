# Clockwork Canary audit

**5 schedules · 1 errors · 13 warnings · 3 notices · 0 suppressed**

Simulation starts `2026-01-01T00:00:00Z` and covers 370 days.

## Schedules

| Workflow | Cron | Timezone | Runs / 30d | Est. runner-min / 30d |
|---|---|---:|---:|---:|
| `.github/workflows/nightly.yml:5` | `0 2 * * *` | `America/New_York` | 30.00 | 300.00 |
| `.github/workflows/sync.yml:11` | `*/2 * * * *` | `UTC` | 21600.00 | 216000.00 |
| `.github/workflows/sync.yml:5` | `0 2 * * *` | `America/New_York` | 30.00 | 300.00 |
| `.github/workflows/sync.yml:7` | `2 2 * * *` | `America/New_York` | 30.00 | 300.00 |
| `.github/workflows/sync.yml:9` | `30 1 * * *` | `America/New_York` | 30.08 | 300.81 |

## Findings

### CC002 · ERROR · Schedule is more frequent than GitHub allows

`.github/workflows/sync.yml:11` — The shortest simulated interval is 2 minute(s); GitHub Actions requires at least 5 minutes.

### CC003 · WARNING · Schedule hits the start of an hour

`.github/workflows/nightly.yml:5` — GitHub documents higher scheduled-workflow load at the start of an hour. Choose a non-zero minute when exact alignment is unnecessary.

### CC004 · WARNING · Schedule crosses a daylight-saving gap

`.github/workflows/nightly.yml:5` — At least one intended wall-clock run does not exist and advances to the next valid local time.

### CC006 · WARNING · Scheduled workflows collide

`.github/workflows/nightly.yml:5` — The pair lands within 3 minute(s) 21 time(s) in the collision horizon; 7 are exact.

### CC007 · WARNING · Duplicate schedules trigger together

`.github/workflows/nightly.yml:5` — 2 entries use '0 2 * * *' in America/New_York; consolidate them or document why simultaneous runs are required.

### CC003 · WARNING · Schedule hits the start of an hour

`.github/workflows/sync.yml:5` — GitHub documents higher scheduled-workflow load at the start of an hour. Choose a non-zero minute when exact alignment is unnecessary.

### CC004 · WARNING · Schedule crosses a daylight-saving gap

`.github/workflows/sync.yml:5` — At least one intended wall-clock run does not exist and advances to the next valid local time.

### CC004 · WARNING · Schedule crosses a daylight-saving gap

`.github/workflows/sync.yml:7` — At least one intended wall-clock run does not exist and advances to the next valid local time.

### CC005 · WARNING · Schedule enters a repeated daylight-saving hour

`.github/workflows/sync.yml:9` — The selected local time occurs twice during fall-back. GitHub does not document a portable once-versus-twice guarantee; keep the job idempotent or move it outside the repeated hour.

### CC003 · WARNING · Schedule hits the start of an hour

`.github/workflows/sync.yml:11` — GitHub documents higher scheduled-workflow load at the start of an hour. Choose a non-zero minute when exact alignment is unnecessary.

### CC006 · WARNING · Scheduled workflows collide

`.github/workflows/sync.yml:11` — The pair lands within 3 minute(s) 21 time(s) in the collision horizon; 7 are exact.

### CC006 · WARNING · Scheduled workflows collide

`.github/workflows/sync.yml:11` — The pair lands within 3 minute(s) 21 time(s) in the collision horizon; 7 are exact.

### CC006 · WARNING · Scheduled workflows collide

`.github/workflows/sync.yml:11` — The pair lands within 3 minute(s) 21 time(s) in the collision horizon; 7 are exact.

### CC008 · WARNING · Estimated monthly runner-minute budget is high

`.github/workflows/sync.yml:11` — Approximately 216000 raw runner-minutes per 30 days, above the configured 2000 threshold.

### CC006 · NOTICE · Scheduled workflows nearly collide

`.github/workflows/nightly.yml:5` — The pair lands within 3 minute(s) 7 time(s) in the collision horizon; 0 are exact.

### CC006 · NOTICE · Scheduled workflows nearly collide

`.github/workflows/sync.yml:5` — The pair lands within 3 minute(s) 7 time(s) in the collision horizon; 0 are exact.

### CC009 · NOTICE · Schedule relies on implicit UTC

`.github/workflows/sync.yml:11` — Add timezone: UTC to make intent explicit, or use an IANA local timezone.

## Assumptions

- Runner-minute estimates use each workflow's job count times the configured duration; matrix expansion, retries, and billing multipliers are not inferred.
- Collisions are simulated over the first 7 days with a 3-minute window.
- Spring-forward runs follow GitHub's documented advance-to-next-valid-time behavior; fall-back behavior is reported as ambiguous rather than guessed.
