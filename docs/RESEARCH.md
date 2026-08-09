# Research and non-duplication record

Research date: 2026-08-08 (America/Los_Angeles)

## Decision

Build **Clockwork Canary**, an offline repository-level simulator and risk auditor for scheduled GitHub Actions.

The selected wedge is not “another cron parser” and not “another GitHub Actions syntax linter.” It is the missing temporal review layer after syntax is already valid: future UTC/local instants, DST gaps and folds, repository-wide collisions, minute-zero load concentration, and a transparent runner-minute planning envelope.

## Why now

GitHub shipped per-schedule IANA timezone support on 2026-03-19. The current event documentation says spring-forward schedules inside missing hours advance to the next valid time. GitHub separately warns that the start of every hour is a high-load period where scheduled events can be delayed and, under enough load, queued jobs may be dropped. Public-repository schedules can also be disabled after 60 days without activity.

This creates a new class of valid-but-operationally-risky schedules. A syntax-only result is no longer enough.

Primary evidence:

- GitHub changelog, timezone launch: https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/
- GitHub event semantics, minimum interval, timezone, DST, and inactivity: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- GitHub troubleshooting, hour-start delay/drop warning: https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflows-running-at-unexpected-times
- GitHub community timezone request and post-launch discussion: https://github.com/orgs/community/discussions/13454

## Existing projects checked

### Directly adjacent

| Project | What it already does | Deliberate Clockwork Canary boundary |
|---|---|---|
| [actionlint](https://github.com/rhysd/actionlint) | Broad GitHub Actions static analysis; cron syntax, five-minute interval, and IANA timezone validation | Does not expand a repository's valid schedules into a shared future timeline, correlate collisions, surface DST evidence, or estimate runner minutes |
| [CronosJS](https://github.com/jaclarke/cronosjs) | Runtime cron scheduling library with timezone/DST controls | Library for running tasks, not an offline GitHub workflow audit or SARIF gate |
| [diffoscope](https://diffoscope.org/) and reproducible-build tooling | Forensic comparison of build artifacts | Different problem space; evaluated but rejected for this project |

### Local and previously discussed work excluded

The workspace catalog was inspected before creation. It already includes agent security, AGENTS.md tooling, README command rehearsal, dependency health, environment drift, Git diff risk, flaky-test replay, release ledgers, logs-to-reproduction, API contract drift, data workbenches, document preflight, game-development utilities, and many domain-specific local-first tools.

Clockwork Canary does not reuse those products' primary input, analysis, or output contract. In particular:

- it is not `envseismograph` (environment snapshot drift);
- it is not `pipesonata` (historical CI timing/failure visualization);
- it is not `actionguard`/`agentguard` (security policy scanning);
- it is not `readme-flightcheck` (documentation rehearsal);
- it is not `release-ledger` (release evidence aggregation).

## Candidate matrix

| Candidate | Demand | Direct competition | Complete v0.1 feasibility | Decision |
|---|---:|---:|---:|---|
| GitHub schedule temporal audit | High: new timezone feature plus long-running reliability pain | Low for the repository-wide temporal layer | High | Selected |
| CLI help/API breaking-change detector | Real maintainership need | Medium: language-specific snapshot and compatibility tools | Medium | Rejected for weaker novelty |
| Environment-variable documentation drift | Broad need | Medium/high: dotenv linters and env documentation generators | High | Rejected for crowded positioning |
| Reproducible artifact double-build Action | Strong supply-chain value | High: reprotest, diffoscope, Reproducible Builds ecosystem | Medium | Rejected as not sufficiently unoccupied |

## Search method and limitation

Searches covered the local repository catalog and memory registry, GitHub repository queries, web-indexed GitHub repositories/issues, official GitHub documentation, GitHub Community, and developer discussions. Exact repository queries for “cron DST linter” and “GitHub Actions cron timezone” returned no results before the authenticated GitHub Search API hit its rate limit; web search was then used for synonym and competitor coverage.

No directly equivalent open-source project was found in the searched evidence. This is a defensible novelty result, **not a claim that global nonexistence can be mathematically proven**. If a direct equivalent appears, the comparison table should be updated rather than hidden.

## Star and discovery hypothesis

No implementation can guarantee stars. The project is designed for organic GitHub discovery through:

- a newly changed platform behavior with existing community demand;
- a narrow one-command value proposition;
- visible file/line findings and SARIF integration;
- no service, token, or AI dependency;
- reproducible healthy/risky fixtures;
- a complementary relationship with the established `actionlint` ecosystem;
- searchable topics: `github-actions`, `cron`, `timezone`, `scheduler`, `static-analysis`, `devtools`.
