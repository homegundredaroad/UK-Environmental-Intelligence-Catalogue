# v0.9 code and evidence audit

## Evidence reviewed

The 19 July 2026 comprehensive run contained 15,437 unique sources, 34,478 resources,
214,949 validation events and 31 merged validation shards. SQLite integrity, source-ID uniqueness
and canonical-URL uniqueness passed. Validation completed in approximately 100 minutes.

The audit found that 17 of 24 data.gov.uk searches remained truncated at 1,000 results, 62.9% of
source licences required review, 49.1% of resource licences required review, 25% of resource URLs
used legacy HTTP, and 34.9% of resources lacked a normalized format. The old headline
`failed_count` mixed these warnings with genuine unavailability; only 144 sources were degraded.

## Engineering changes

- Validation observations now carry `pass`, `warning`, `error` or `critical` severity.
- Confirmed missing resources and licence gaps receive compact CSV review queues.
- CKAN and ArcGIS text is cleansed of HTML/CSS before use; format aliases are normalized.
- WMS and WFS services are checked through bounded `GetCapabilities` requests.
- ML uses cleansed text, fits KMeans once, weights titles and exposes record titles with outliers.
- OpenAI and Gemini are independent failure domains; partial results and errors are checkpointed.
- The final catalogue artifact no longer repeats all discovery reports or the 151 MB detailed report.
- Merging fails closed if shard-report coverage does not match the canonical catalogue count.

## Standards direction

The next data-model revision should map original evidence to DCAT 3 dataset, distribution and data
service concepts while preserving the existing lossless provider payload hashes. Quality evidence
should follow the W3C Data Quality Vocabulary principle that consumers receive enough information
to make their own fitness-for-purpose judgment. Coverage work should follow FAIR principles:
machine-findable identifiers and metadata, resolvable access protocols, interoperable vocabularies
and explicit reuse evidence.

## Remaining priorities

1. Replace 1,000-result thematic sampling with complete, incremental provider harvesting.
2. Add direct official connectors for devolved administrations and specialist scientific portals.
3. Add DCAT, OGC API Records, CSW and Atom harvesting.
4. Normalize themes against a controlled environmental vocabulary while retaining original tags.
5. Require two temporally separated 404 observations before degradation; retain HTTP 410 as
   immediately material.
6. Implement retry budgets and provider-aware rate limiting for 429, 5xx and network failures.
7. Add licence evidence URLs and canonical identifiers without using AI to infer legal rights.
