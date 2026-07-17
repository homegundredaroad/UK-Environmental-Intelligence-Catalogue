# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

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
