# SCC Nexus — UK-AIR Atom historical feed index pilot

**Date:** 2026-11-06. **Governance:** SCC (Search, Corroborate, Communicate) /
VVIP (Validation, Verification, Integrity, Provenance).

This is a **first-party historical *catalogue discovery*** implementation, not a
data harvester for air concentration measurements. It has no permission to
publish scientific findings or write to SCC Air Quality's separate repository.

## Authoritative source

Defra [UK-AIR Atom Download Services](https://uk-air.defra.gov.uk/data/atom-dls/)
documents automatic, non-automatic and aggregated annual feeds, starting in
1973, plus a methods-metadata feed. The pages state OGL reuse with attribution.
Presence of a URL does **not** establish that a year's observations are complete,
ratified, consistently comparable or available for every site/pollutant.

The inventory accepts only official exact-path Atom URLs on
\`https://uk-air.defra.gov.uk\` and refuses query strings, cross-site URLs and
non-HTTPS paths. It preserves the *original* provider index HTML and SHA-256;
returns a year-by-category matrix and explicit missing-index-year lists.

## Run

Offline using a preserved original HTML file:

\`\`\`bash
python -m ukei.uk_air_atom \
  --input-html ukair-atom-index-original.html \
  --year 2026 --output output/atom-historical-index
\`\`\`

One bounded live request to Defra's published HTML index:

\`\`\`bash
python -m ukei.uk_air_atom --live --year 2026 \
  --timeout 10 --output output/atom-historical-index
\`\`\`

The live request uses strict public HTTPS DNS preflight, blocks proxies and
redirects, and limits the response to 2,000,000 bytes. DNS preflight is
**not** connection pinning; an independent networking security review is still
needed before arbitrary third-party URLs are ever used. If Defra requires a
redirect, this first implementation **fails closed** and the route is reviewed
separately; never switch off transport guards to make a run appear green.

Outputs:
- \`atom-index-original.html\` — exact original byte snapshot, private evidence.
- \`atom-index-manifest.csv\` — one machine-parsable row for each advertised feed.
- \`atom-index-receipt.json\` — raw and manifest hashes, observed counts,
  missing-year ledger, duplicate and rejection counts, mode and timestamp.

The monthly/push/manual GitHub workflow is
\`.github/workflows/ukair-atom-index.yml\`. It retains a private GitHub
Actions artifact; **it does not commit source HTML or new datasets**.

## Scientific next stage

1. Independent original-provider metadata check and HTTP status verification
   for a *small preselected* sample of annual feeds (e.g., 2019, 2023, 2025).
2. Parse Atom entries securely with bounded XML and explicitly record revisions,
   modified dates, actual file formats and station identifiers.
3. Apply measured-data schema, units, UTC/BST, missingness, site opening/closure,
   ratification, reissued years and checksum comparisons.
4. Cross-check with Defra's new
   [Get Air Pollution Data service](https://get-air-pollution-data.defra.gov.uk/)
   and official [UK-AIR archive](https://uk-air.defra.gov.uk/data/).
5. Keep all annual-network completeness and country-specific coverage claims
   on **HOLD** until independently reproduced.

Use these existing SCC/VVIP repository tools and audit reports instead of
adding a new array of interdependent Colab notebooks.
