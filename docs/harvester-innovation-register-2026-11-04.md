# SCC Nexus | Environmental Intelligence Harvester Innovation Register
**Edition:** 2026-11-04 | **Status:** research and engineering backlog, not source certification

SCC = Search, Corroborate, Communicate. VVIP = Validation, Verification, Integrity, Provenance.

## Implemented in this review branch

- **OGC API - Records 1.0**: opt-in \`OgcRecordsConnector\` parses structured
  discovery records and their data links, hashes original metadata, emits
  candidate-only source records, records pagination/coverage uncertainty, caps
  requests and blocks non-public initial endpoints and cross-origin next links.
- **CLI**: \`ukei discover --provider ogc-records --ogc-records-endpoint
  https://<public-host>/collections/<collection>/items --query water --limit 25\`.
  No OGC endpoint is queried by default; \`--provider all\` adds it **only when
  an explicit endpoint was provided**. Use only a known, vetted official endpoint.
- **Tests**: fixture-based records, provenance, pagination, incomplete coverage,
  credential-bearing next links, unsafe endpoints and malformed responses.
- **No production promotion, upstream repo modification or automatic scientific
  acceptance**. Discovery is metadata, not harvestability proof.

## Prioritised official UK source leads

These are **source leads** from published provider documentation, not assertions
that specific datasets have been harvested or fully inventoried.

| Region / scope | Official service | Why it matters | Integration path | Current status |
|---|---|---|---|---|
| England | [Defra Data Services Platform](https://environment.data.gov.uk/) | cross-domain environmental data, downloads, linked data APIs | discover APIs/catalogues, validate formats and licences | review-only |
| UK (air monitoring) | [UK-AIR SOS](https://www.api.gov.uk/defra/uk-air-sensor-observation-service/) | cross-nation pollution measurements | SOS 2.0 capabilities, station/series audit | review-only |
| Wales | [NRW data](https://naturalresourceswales.gov.uk/evidence-and-data/accessing-our-data/access-our-data-maps-and-reports/?lang=en) | river levels, warnings, rainfall and flood forecast | API metadata and observed-data quality coding | review-only |
| Scotland | [SEPA Time Series API](https://timeseriesdoc.sepa.org.uk/) | stations, quality-coded observations, revised historical hydrometric series | KiWIS provider adapter with rate limits and history comparison | review-only |
| Northern Ireland | [OpenDataNI](https://www.nidirect.gov.uk/services/opendatani-portal) | NI public datasets and API access | map portal catalogue and resource APIs, verify individual publishers | review-only |
| UK terrestrial and freshwater | [NERC EIDC](https://eidc.ac.uk/) | research-grade historical data and identifiers | access-token aware, rights-respecting catalogue connector | review-only |
| UK marine | [Cefas Data Hub](https://www.cefas.co.uk/data-and-publications/cefas-data-hub-apis/) | marine datasets, recordsets, APIs and mapping services | source-specific metadata/resource adapter | review-only |

**Critical change on 5 October 2026:** EIDC switched programmatic
catalogue/data downloads from basic authentication to personal access tokens.
Do not place tokens in repository configuration, logs, output CSVs or URLs.
Store via secret manager, and distinguish unauthenticated catalogue access,
authenticated access, permissions and licensing. Source:
https://eidc.ac.uk/

## Standards and credible Python tools: evaluate rather than blindly install

1. [OGC API - Records](https://www.ogc.org/standards/ogcapi-records/)
   improves metadata and discovery portability. Current connector is first-stage
   metadata discovery only; providers must be verified individually.
2. [OGC Environmental Data Retrieval 1.2](https://docs.ogc.org/is/19-086r9/19-086r9.html)
   published September 2026: evaluate spatial/temporal queries for meteorology,
   atmosphere, hydrology and scientific environmental observations. A separate
   bounded adapter will need time-zone, CRS, units and pagination tests.
3. [OGC SensorThings API](https://www.ogc.org/standards/sensorthings/)
   models Things, Sensors, Datastreams and Observations. Use its identifiers to
   prevent confusing station metadata, devices and measurements.
4. [STAC](https://stacspec.org/en/about/stac-spec/) and
   [pygeoapi](https://docs.pygeoapi.io/en/stable/introduction.html):
   catalogue imagery, geospatial archives and API-compliant datasets. Validate
   asset media types and bounds; do not confuse tiles or renderings with raw data.
5. [Frictionless Framework](https://framework.frictionlessdata.io/docs/guides/validating-data):
   optional bounded CSV/TSV column, data-type and schema testing.
   Consider [Pandera](https://pandera.readthedocs.io/) for DataFrame-level
   contracts, [DuckDB](https://duckdb.org/) and [PyArrow](https://arrow.apache.org/docs/python/)
   for local columnar analysis. These are proposals, not installed dependencies.
6. [FAIR Principles](https://www.go-fair.org/fair-principles/) and transparent
   reproducibility: persistent identifiers, versioned data dictionaries, frozen
   source checksums, acquisition receipts and independent reruns.

## SCC/VVIP acceptance gates for each new adapter

1. **S — SEARCH:** identify original publisher, stable dataset and station IDs,
   nation, explicit query coverage, total/offset/next link; limit != completeness.
2. **C — CORROBORATE:** independent publisher documentation, temporal and spatial
   extent, licence terms, original metadata snapshot, duplicate grouping.
3. **V — VALIDATE:** bounded sample of actual rows with stable column names,
   units, NA/sentinel handling, timestamps and timezone; test missingness,
   duplicate keys, pagination, data revisions and schema changes.
4. **V — VERIFY:** separate engine or independently reproducible acquisition
   rechecks dates, row counts, hashes and representative aggregate statistics.
5. **I — INTEGRITY:** immutable raw evidence, SHA-256, provenance of transforms,
   exception register, secrets removed from all downloadable artifacts.
6. **P — PROVENANCE:** source URL, dataset ID, recorded access time, licence,
   transformations, author and run version, reviewer's decision.

**Release boundary:** a reachable endpoint, parseable JSON, even a passing
schema test, does not imply scientific admissibility or national completeness.
All new feeds remain \`candidate\` / \`REVIEW_REQUIRED\` until an independent,
original-provider data acquisition and reviewed release gate is complete.

## Additional engineering gates before live expansion

- Redirect and DNS controls require hardening: the existing generic
  \`JsonHttpClient\` uses urllib's default redirect handling; a public HTTPS
  seed URL can still redirect. Before unattended execution against arbitrary
  third-party endpoints, enforce approved host allowlists, disallow or inspect
  redirects before connecting, and protect against DNS rebinding and private
  addresses. **Do not classify this first implementation as SSRF-proof.**
- Per-host rate and concurrency limits; timeout and byte ceilings; conditional
  GET/ETag and Last-Modified; backoff only for safe idempotent failures.
- Query-grid coverage receipts by publisher, UK nation, domain, time window,
  data format and source status. Missing or truncated responses must be
  represented explicitly; no fabricated zero observations.
- Source-specific regression fixtures for historic revisions and timestamp
  effects; no auto-write into SCC Air Quality or other sibling repositories.
- Dry-run and shadow-mode deployment before enabling any scheduled new provider.

## Review sequence

1. Run lint, mypy, isolated fixtures and overall CI on the feature branch.
2. Security review of HTTP redirects, origin, DNS and credentials.
3. Review and verify one official OGC Records endpoint, run bounded opt-in
   discovery and capture provider coverage evidence.
4. Add one national data provider at a time, independently verify historical
   slices, and record date-stamped source-quality exceptions.
5. Merge only after required CI/review; do not deploy to a separate Air Quality
   production system as a side effect.
