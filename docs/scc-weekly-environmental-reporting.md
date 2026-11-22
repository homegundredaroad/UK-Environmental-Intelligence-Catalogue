# SCC Nexus Limited — Weekly UK Environmental Intelligence Reporting

**SCC:** Search, Corroborate, Communicate. **VVIP:** Validation, Verification, Integrity, Provenance.

This is a complete automated **status and independent-review reporting suite**.
It does not collect fresh observations, certify historic accuracy, approve
scientific findings or write to the separate SCC Air Quality repository.

## One simple current/archive structure

- reports/weekly/current/ — the latest SCC Nexus executive and scientific status.
- reports/weekly/archive/YYYY-Www/ — latest published edition for that ISO week.
- reports/weekly/revisions/YYYY-Www/<snapshot-hash>/ — immutable-by-workflow
  evidence revision for each different source snapshot in the same ISO week.
- GitHub Actions artifact — full matching pack, retained for 90 days.

The bounded source-qualification workflow is scheduled for Saturdays 04:23 UTC.
The weekly reporter has Sunday 06:17 UTC and Sunday 18:47 UTC fallback
schedules, plus manual runs and a successful-qualification follow-up.
GitHub-hosted schedules can be significantly delayed or skipped: check actual
run and commit timestamps, not the cron time. A duplicate edition with identical
weekly input hashes is not republished just because the renderer ran again.

| Output | Contents |
|---|---|
| public-summary.md | Current evidence, executive context, SCC/VVIP boundaries and actions |
| dashboard.html | Mobile- and print-friendly SCC Nexus navy-and-gold dashboard |
| reviewer-report.md | Full technical and scientific appendix, evidence provenance, gaps and audit methods |
| metrics.csv | Exact counts and comparable dated changes |
| gap-register.csv | Missing authoritative adapters and station network inventories |
| action-register.csv | Priority actions and precise evidence required |
| snapshot.json | Week-specific comparison baseline |
| receipt.json | Input SHA-256, freshness, technical gates and explicit scientific HOLD |
| bundle-manifest.json | SHA-256 for every generated file |

The report reads committed catalogue, handoff, harvestability and national
coverage receipts. It cross-checks actual CSV rows against reported counts,
sha256 provenance, policy review queue, source identity and the required
national adapter/station gap ledgers. Mismatches fail closed, not silently.

There is no weekly trend without an earlier distinct ISO-week snapshot.
Re-running the same week does not count as an improvement. The reporting date
is never substituted for the source-qualification timestamp. A receipt older
than seven days is labelled STALE and demands a separate human review.

A second, explicit **source-continuity** calculation compares the SHA-256
digests of every committed input against the previous distinct week's
snapshot. It distinguishes no baseline, unchanged input, and source changes
which still require original-provider investigation. A fresh weekly dashboard
is **not** a fresh environmental harvest. Repeating a bounded qualification
does not update the original discovery time or validate a single observation.

The archive/YYYY-Www edition is the last issued report for that week. If new
qualified source receipts arrive during the same week, a new revision is saved
under revisions/YYYY-Www/<snapshot-hash> before the week's latest edition
changes. The workflow refuses to overwrite an existing source-hash revision.
The Git history and original-provider archives remain the controlling record
for independent reproducibility.

## Run in the existing repository or approved Colab environment

    python -m ukei.weekly_reporting \
      --root . \
      --archive reports/weekly/archive \
      --output reports/weekly/preview

No new notebook or framework dependency is required; this runs with Python's
standard library and requires no outbound network access.

## Public versus scientific status

The public report may show metadata and project readiness, but it is **not**
a release of environmental findings. Even when the generator passes automated
tests, scientific status remains HOLD until a separately signed and independently
reproduced scientific review accepts original data, licence, version, units,
timestamps, quality flags, spatial/temporal coverage and methods.

No private data, authentication credentials, raw provider response bodies or
sibling-repository files are copied into the public weekly folders.

## Next steps

1. Reconcile policy-blocked redirects to approved publisher endpoints without
   bypassing security and without classifying refused connections as dead.
2. Audit Defra UK-AIR Atom historical feeds and independently reacquire a
   bounded sample of original measurement files before completeness claims.
3. Build direct official adapters for England, Scotland, Wales and Northern
   Ireland; reconcile native station IDs for current and closed sites.
4. Capture historical revisions, missing intervals, raw hashes and second-method
   scientific comparisons and attach their receipts in future weekly reports.
5. Commission independent specialist scrutiny and keep approval records separate
   from technical CI.
