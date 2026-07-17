# UK Environmental Intelligence Catalogue

[![CI](https://github.com/homegundredaroad/UK-Environmental-Intelligence-Catalogue/actions/workflows/ci.yml/badge.svg)](https://github.com/homegundredaroad/UK-Environmental-Intelligence-Catalogue/actions/workflows/ci.yml)

An evidence-led, auditable framework for cataloguing and validating UK environmental data
sources. Release `0.3.0` adds bounded discovery from data.gov.uk and ArcGIS Online. It does not claim
comprehensive source coverage and does not treat catalogue inclusion as verified evidence.

## Sprint 0 capabilities

- installable Python package and `ukei` command-line interface;
- environment-aware, dependency-free configuration;
- structured or human-readable logging;
- typed connector and validator interfaces;
- deterministic source records and SHA-256 provenance hashes;
- versioned SQLite catalogue with validation history;
- JSON import/export and catalogue integrity checks;
- strict tests, linting, typing and GitHub Actions CI.

## Sprint 1 capabilities

- eight manually reviewed, high-value official UK environmental data services;
- explicit licence positions, provenance URLs, formats, themes and coverage notes;
- deterministic packaged seed manifest with duplicate and policy guards;
- idempotent `ukei seed` import and non-mutating `ukei seed --dry-run` review;
- every seed remains `candidate` until repeatable live validation supports promotion.

## Sprint 2 capabilities

- bounded discovery adapters for the data.gov.uk CKAN API and ArcGIS Online search;
- HTTPS-only JSON retrieval with response-size limits and independent provider error reporting;
- deterministic URL normalisation, de-duplication and raw-metadata provenance hashes;
- candidate-only discovery reports, with optional import into the local catalogue;
- an opt-in browser-triggered live discovery job that publishes a downloadable JSON artifact.

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ukei init
ukei status
ukei seed --dry-run
ukei seed
ukei list
ukei validate
ukei discover --provider all --query "air quality" --output discovery.json
```

By default the database is created at `.ukei/catalogue.sqlite3`. Override it with
`UKEI_DATABASE_PATH` or `--database`.

## CLI

```text
ukei init                         initialise or migrate the catalogue
ukei status                       show catalogue and configuration status
ukei add --title ... --url ...    add or update a source record
ukei demo                         add a clearly labelled demonstration record
ukei seed [--dry-run]             load or inspect curated candidate sources
ukei list [--format table|json]   list current source records
ukei show SOURCE_ID               show one complete record
ukei validate [SOURCE_ID]         run deterministic metadata validation
ukei export OUTPUT.json           create a canonical JSON export
ukei import-json INPUT.json       import records from a canonical export
ukei discover [OPTIONS]           discover candidate sources from official catalogue APIs
```

Run `ukei COMMAND --help` for complete arguments. Commands return non-zero exit codes for invalid
input or failed validation, making them suitable for automation.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `UKEI_DATABASE_PATH` | `.ukei/catalogue.sqlite3` | SQLite catalogue location |
| `UKEI_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `UKEI_LOG_FORMAT` | `text` | `text` or `json` |
| `UKEI_HTTP_TIMEOUT_SECONDS` | `20` | Future network connector timeout |

See [`docs/architecture.md`](docs/architecture.md) for boundaries and design decisions and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the quality gate. Windows upload and first-run instructions
are in [`docs/windows-quickstart.md`](docs/windows-quickstart.md).

Live discovery is deliberately opt-in in GitHub Actions: open **Actions → CI → Run workflow**, tick
**Run bounded live discovery**, then download the `ukei-discovery-report` artifact after the run.

## Evidence and safety position

Catalogue entries are metadata assertions, not proof that a dataset is accurate, current, complete,
licensed for every use, or suitable for regulatory, health or source-attribution conclusions. Every
connector added after Sprint 0 must preserve original metadata, record retrieval time and validation
history, and distinguish `candidate`, `verified`, `degraded` and `retired` states.
