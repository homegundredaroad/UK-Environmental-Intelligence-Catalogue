# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

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
