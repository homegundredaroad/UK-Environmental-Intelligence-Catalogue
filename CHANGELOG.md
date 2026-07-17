# Changelog

## 0.6.0

- Add strict malformed and HTML-contaminated URL rejection.
- Distinguish policy-blocked HTTP resources from confirmed unreachable resources.
- Treat age as a review warning until publisher cadence is known.
- Add conservative UK licence classification and HTML sanitisation.
- Add semantic ArcGIS Feature/Map Service metadata validation.
- Add richer resource-check counters to validation reports.
- Add the browser-triggered VVIP multi-theme comprehensive scan workflow.

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [0.5.0] - 2026-07-17

### Added

- Schema-2 resource references for downloadable files and machine services.
- CKAN and ArcGIS resource extraction with provenance, licence and modification evidence.
- Bounded resource reachability, licence and recency checks.
- Opt-in resource-validation workflow with a canonical catalogue snapshot artifact.

### Changed

- Natural England ArcGIS account ownership is normalized to the publisher `Natural England`.
- Failed underlying-resource reachability checks may conservatively degrade active records.

## [0.4.0] - 2026-07-17

### Added

- Weighted metadata-completeness scoring with structured missing-field evidence.
- Bounded live URL validation recording HTTP status, elapsed time, redirect target and content type.
- Machine-readable validation reports and opt-in GitHub Actions validation artifacts.

### Changed

- Failed live checks conservatively mark active records as `degraded`.
- Passing checks retain the existing lifecycle state and never auto-promote candidates.

## [0.3.0] - 2026-07-17

### Added

- CKAN and ArcGIS Online discovery adapters with bounded, HTTPS-only JSON retrieval.
- Deterministic discovery de-duplication and raw-metadata provenance hashes.
- `ukei discover` command with provider, query, limit, output and optional import controls.
- Opt-in GitHub Actions live-discovery job with a downloadable JSON report artifact.

### Changed

- Candidate discovery is isolated from deterministic CI and never promotes records automatically.
- GitHub artifact upload uses the current Node.js 24-compatible action release.

## [0.2.0] - 2026-07-17

### Added

- Curated seed manifest for eight official UK environmental data services.
- Guarded seed loader with duplicate, lifecycle, provenance, licence and hash checks.
- Idempotent `ukei seed` command and non-mutating `--dry-run` review mode.

### Changed

- Updated GitHub Actions to Node.js 24-compatible checkout and Python setup actions.
- Resource warnings now fail tests; the direct SQLite mutation test closes explicitly.

## [0.1.0] - 2026-07-17

### Added

- Python package, CLI and configuration system.
- Typed source, validation and connector contracts.
- Versioned SQLite catalogue and validation history.
- Deterministic JSON import/export and integrity verification.
- Test, lint, type-check and GitHub Actions quality gates.
