# UK Environmental Intelligence Catalogue

[![CI](https://github.com/homegundredaroad/UK-Environmental-Intelligence-Catalogue/actions/workflows/ci.yml/badge.svg)](https://github.com/homegundredaroad/UK-Environmental-Intelligence-Catalogue/actions/workflows/ci.yml)

An evidence-led, auditable framework for cataloguing and validating UK environmental data
sources. Release `0.1.0` establishes the engineering foundation: it does not claim comprehensive
source coverage and does not treat discovered data as verified evidence.

## Sprint 0 capabilities

- installable Python package and `ukei` command-line interface;
- environment-aware, dependency-free configuration;
- structured or human-readable logging;
- typed connector and validator interfaces;
- deterministic source records and SHA-256 provenance hashes;
- versioned SQLite catalogue with validation history;
- JSON import/export and catalogue integrity checks;
- strict tests, linting, typing and GitHub Actions CI.

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
ukei demo
ukei list
ukei validate
```

By default the database is created at `.ukei/catalogue.sqlite3`. Override it with
`UKEI_DATABASE_PATH` or `--database`.

## CLI

```text
ukei init                         initialise or migrate the catalogue
ukei status                       show catalogue and configuration status
ukei add --title ... --url ...    add or update a source record
ukei demo                         add a clearly labelled demonstration record
ukei list [--format table|json]   list current source records
ukei show SOURCE_ID               show one complete record
ukei validate [SOURCE_ID]         run deterministic metadata validation
ukei export OUTPUT.json           create a canonical JSON export
ukei import-json INPUT.json       import records from a canonical export
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

## Evidence and safety position

Catalogue entries are metadata assertions, not proof that a dataset is accurate, current, complete,
licensed for every use, or suitable for regulatory, health or source-attribution conclusions. Every
connector added after Sprint 0 must preserve original metadata, record retrieval time and validation
history, and distinguish `candidate`, `verified`, `degraded` and `retired` states.
