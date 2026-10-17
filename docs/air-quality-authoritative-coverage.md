# SCC Air Quality authoritative coverage audit

The harvestability gate proves that a discovered endpoint can be considered for independent testing.
It does not prove that SCC Air Quality has found the complete UK monitoring universe. This coverage audit
adds that separate completeness control.

## What complete means

For SCC/VVIP purposes, coverage is not measured by the number of catalogue records. It is complete only
when all of the following are true:

1. every governed source system marked `required_for_exhaustive` has a direct inventory connector or an
   explicitly reviewed exception;
2. every governed national monitoring network has been enumerated, including current and closed sites;
3. station identifiers, coordinates, network memberships, pollutants, methods, time spans and data
   endpoints are reconciled against the original provider;
4. there are no unexplained station or dataset gaps; and
5. historical revisions and method changes are versioned rather than silently overwriting evidence.

Until those conditions pass, the coverage claim remains:

`INCOMPLETE_UNTIL_REQUIRED_CONNECTORS_AND_STATION_RECONCILIATION_PASS`

## Quality tiers

The registry keeps different evidence classes separate:

- **STATUTORY_REFERENCE** — national/devolved reference and compliance monitoring with formal QA/QC;
- **OFFICIAL_LOCAL** — local-authority and official regional monitoring, assessed per station/period;
- **LOW_COST_SENSOR** — calibrated sensor networks, useful for spatial intelligence but not assumed
  reference-equivalent;
- **RESEARCH_SPECIALIST** — specialist atmospheric/research observations assessed per dataset;
- **DERIVED_TOOL** — importers and analysis tools used only for discovery or independent cross-checking.

A lower tier is not automatically lower value. The tiers prevent unlike measurements from being
silently pooled.

## Source systems in the registry

The v1 registry explicitly covers the UK-AIR SOS and archive, the newer Defra download service,
locally-managed monitoring, LAQM structured submissions, Scotland's public API, Wales SOS and Atom
services, Northern Ireland SOS and Spatial Object Register, LondonAir, Air Quality England,
Breathe London, ACTRIS, CEDA and the openair/ukaq ecosystem as an independent cross-check.

The national-network registry separately names AURN, locally-managed automatic monitoring, automatic
and non-automatic hydrocarbons, PAH, TOMPs, Black Carbon, Heavy Metals, Particle Concentrations and
Numbers, Stratospheric Ozone/UV, Precip-Net, Acid Gas and Aerosol, Rural NO2, National Ammonia,
MARGA, Automatic Mercury and the UK Urban NO2 Network.

Observed site counts are audit hints only. They must not be summed into a UK site total because one
physical monitoring site can belong to several networks.

## Historical evidence is mutable

Ratified or previously published data are not treated as immutable. SCC/VVIP requires retrieval time,
content hash, provider edition/supersession lineage and method/instrument metadata. The initial registry
contains explicit controls for:

- later revisions to ratified data;
- the formal reissue of 2022-2023 ammonia results;
- the ozone scale/method change from 1 January 2025; and
- 2023 particle-number instrument replacements and changed particle-size ranges.

A reproducible analysis should therefore reacquire or pin the provider edition used for each release.

## Current architectural gap

The catalogue's general discovery adapters currently cover data.gov.uk CKAN and Natural England
ArcGIS search. They are useful discovery layers but cannot demonstrate UK air-quality completeness.
The authoritative coverage matrix deliberately reports source-native connectors and network
enumeration as missing until they are implemented and reconciled.

This is a fail-closed control: a large catalogue can never make the completeness flag turn green by
itself.

## Outputs

`python -m ukei.air_quality_coverage MANIFEST OUTPUT_DIR` creates:

- `authoritative-coverage-matrix.csv`
- `authoritative-coverage-receipt.json`

The matrix records source-system representation and connector status. The receipt records the
outstanding direct-connector and network-enumeration gaps and always preserves the SCC/VVIP scientific
claim boundary.

## SCC Air Quality governed handoff

The SCC Air Quality handoff now carries a compressed, checksum-protected copy of this authoritative source/network registry alongside the focused discovery catalogue. The handoff remains discovery/governance intelligence only: it does not confer scientific admissibility or authorise production changes. SCC Air Quality must independently reacquire original-provider evidence and prove each connector/network inventory in its test and research repositories.
