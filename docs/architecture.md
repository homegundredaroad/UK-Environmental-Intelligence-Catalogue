# Architecture

## Scope of release 0.1

Sprint 0 is a local catalogue kernel. It supplies stable contracts and an auditable persistence layer
before network discovery or source-specific harvesters are introduced.

```text
CLI -> application models -> catalogue repository -> SQLite
                       |-> connector contract
                       |-> validator contract and validation history
```

## Boundaries

- `models.py` contains immutable domain records and canonical serialization.
- `connectors/base.py` defines discovery and harvesting contracts without network policy.
- `validation/base.py` defines composable checks and a deterministic metadata validator.
- `catalogue.py` owns migrations, transactions and persistence mappings.
- `cli.py` translates user input into domain operations and stable exit codes.

SQLite is deliberately the first persistence target: it makes development and evidence inspection
portable. The domain and connector interfaces do not expose SQLite objects, leaving a route to a
PostgreSQL/PostGIS implementation without changing connectors.

## Trust model

Discovery produces candidates. Validation produces dated observations, not permanent truth. Status
transitions are explicit. SHA-256 hashes cover canonical record content so later mutation is
detectable. Validation events are append-only.

## Planned sequence

1. Sprint 1: seed catalogue with a small, manually reviewed official-source set.
2. Sprint 2: discovery adapters for CKAN, ArcGIS, STAC and OGC catalogues.
3. Sprint 3: network, licence, schema and duplicate validators.
4. Sprint 4: immutable raw metadata snapshots and change detection.
5. Sprint 5: source-specific connectors, each with fixtures and contract tests.

