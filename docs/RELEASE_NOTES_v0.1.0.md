# Clockwork Canary v0.1.0

The first public release turns scheduled GitHub Actions into a reviewable future timeline.

Highlights:

- scans all workflow schedule entries with file/line evidence;
- simulates IANA timezone behavior across spring gaps and autumn folds;
- detects duplicate, exact, and near-colliding workflows;
- flags minute-zero load concentration and sub-five-minute intervals;
- estimates raw runner-minute envelopes with explicit assumptions;
- emits terminal, Markdown, JSON, and SARIF 2.1.0 reports;
- ships a composite GitHub Action, expiring suppressions, healthy/risky fixtures, and a reproducible release gate.

See `SHA256SUMS` and `release-manifest.json` before installing an asset. The wheel and source distribution are built twice under a fixed source epoch and must match byte-for-byte before publication.
