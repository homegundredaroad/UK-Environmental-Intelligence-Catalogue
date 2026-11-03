# SCC Air Quality — source discovery for regulatory scrutiny

This opt-in and monthly workflow builds a **candidate-only** register of environmental source libraries relevant to industrial emissions, monitoring, permitting, meteorology, quality assurance and regulatory accountability. It reuses the existing UKEI CKAN/data.gov.uk and ArcGIS discovery adapters. This is **metadata discovery, not the harvesting or verification of measured emissions**.

## Operation

Once the review PR is merged: **Actions → SCC Air Quality governance source discovery → Run workflow**. The bounded scheduled run occurs on the **5th of each month at 04:23 UTC**. Ten tightly focused queries, at most 40 source candidates per provider and query, a local ephemeral SQLite database and a 35-minute job timeout. No production website, VPS, protected reports or scientific release are modified.

The downloadable `scc-airquality-governance-source-discovery` artifact contains:

- `discovery/00.json` … `09.json`: untouched per-query source candidates, provider receipts and errors.
- `query_coverage_receipts.json`: query-level counts, provider coverage and exceptions.
- `scc_airquality_candidate_sources.json`: cross-query deduplicated catalogue leads, original metadata hashes and explicit candidate-only flags.
- `official_reference_leads.json`: six official source entry points with licence-review requirements.
- `scc_airquality_governance_manifest.json`: output counts, failures and a fail-closed status.

A report with a provider error or missing query is **incomplete** and fails the job; diagnostic artifacts remain available when possible. A green job indicates **successful discovery of metadata**, not verified measurements, permits or regulatory compliance.

## SCC and VVIP obligations

**Search** for new sources and versions; **Corroborate** original documents, legal context and independent records; **Communicate** only bounded, supported findings with explicit uncertainty.

**Validation:** distinguish ambient air from stack emissions, continuous from periodic samples, and means from maxima. **Verification:** authenticate permit-effective periods, pollutant and chemical basis, dry/wet and oxygen corrections, reference volume, averaging window, instrument QA and uncertainty before any comparison. **Integrity:** preserve original source and response SHA-256 hashes and revision histories. **Provenance:** maintain exact source URLs, provider IDs, query terms and timestamps.

All discoveries remain **CANDIDATE_METADATA_ONLY**, with `compliance_conclusion_allowed=false`, `licence_reuse_cleared=false`, `measurements_comparable=false`. Nothing automatically promotes a candidate or establishes a breach.

The Environment Agency's [incinerator annual monitoring library](https://environment.data.gov.uk/dataset/3500ab14-6546-45cf-acb2-c2a40e350737) uses a **conditional licence**, so the reports must not be blindly republished as public research downloads.

This workflow is a complement to SCC Air Quality's independently versioned governance workbench and to the general UKEI comprehensive discovery scan, not a replacement for either.
