# SCC Nexus Limited — UK Environmental Intelligence
**Weekly review:** 2026-W45 | **Evidence as of:** 2026-11-05T16:40:45+00:00

## Executive summary
- **554** distinct catalogue candidates, of which only **1** currently qualify for independent testing.
- **26** source endpoints were blocked by network policy; they have not been established as missing or permanently inaccessible.
- **15** official direct adapters and **17** monitoring-network enumerations remain missing.
- **Scientific decision: HOLD.** No claim of national completeness, scientific admissibility, exposure effects or historical data accuracy.
- Evidence age: **2.9 days** — within 7-day reporting threshold.

## Harvestability and coverage
| Measure | Latest count | Change from prior distinct week |
|---|---:|---:|
| Discovery records | 587 | Not available |
| Distinct candidate datasets | 554 | Not available |
| Pollutant-relevant datasets | 377 | Not available |
| Explicit air-context datasets | 284 | Not available |
| Machine-readable candidates | 321 | Not available |
| Endpoint probes | 117 | Not available |
| Reachable endpoints | 93 | Not available |
| Safety-policy blocks | 26 | Not available |
| Candidates for independent tests | 1 | Not available |
| Missing direct provider adapters | 15 | Not available |
| Unreconciled monitoring networks | 17 | Not available |
| Registered source systems | 16 | Not available |
| Cross-media source signals | 403 | Not available |

## Priority recommendations
- **P0 — Official data connectors:** 15 required direct adapters absent. Evidence needed: Provider-native endpoint, bounded test and exact schema receipt.
- **P0 — Monitoring network coverage:** 17 inventories lack reconciled stations. Evidence needed: Native active/closed station IDs and registry snapshots.
- **P0 — Transport security:** 26 blocked URLs; not confirmed missing. Evidence needed: Source-verified redirect origins and secure allowlist review.
- **P1 — Historical integrity:** Historical year-by-network completeness not demonstrated. Evidence needed: Original files, versions, checksums, stations and date grids.
- **P1 — Scientific admissibility:** Independent measurement validation and corroboration incomplete. Evidence needed: Raw observations, units, QA flags, second-method reproduction.

## SCC and VVIP claim boundary
SCC = Search, Corroborate, Communicate. VVIP = Validation, Verification, Integrity, Provenance. Discovery and software checks do not grant scientific publication permission. SCC Air Quality reacquires and validates evidence independently in its separate project.

---
## Independent technical and scientific reviewer appendix

### 1. Acquisition provenance and evidence vintage
The underlying focused discovery retained 16 successful searches from 16 queries. These are from the original recorded discovery run, not fresh weekly observations.
A weekly report run reads previously committed files only. It does not prove any original-provider API or environmental station has been updated this week.
Previous comparable week: none available.

### 2. Authoritative source connector gaps
| Direct source adapter ID | Status |
|---|---|
| actris-data-portal | MISSING |
| air-quality-england | MISSING |
| breathe-london-api | MISSING |
| ceda-moles | MISSING |
| defra-get-air-pollution-data | MISSING |
| laqm-central | MISSING |
| londonair-api | MISSING |
| ni-air-sos | MISSING |
| ni-air-spatial-register | MISSING |
| scottish-air-quality-api | MISSING |
| ukair-data-archive | MISSING |
| ukair-locally-managed | MISSING |
| ukair-sos | MISSING |
| wales-air-atom | MISSING |
| wales-air-sos | MISSING |

### 3. Unreconciled monitoring network inventories
| Network ID | Status |
|---|---|
| acid-gas-aerosol | NOT ENUMERATED |
| aurn | NOT ENUMERATED |
| automatic-hydrocarbon | NOT ENUMERATED |
| automatic-mercury | NOT ENUMERATED |
| black-carbon | NOT ENUMERATED |
| heavy-metals | NOT ENUMERATED |
| locally-managed-automatic | NOT ENUMERATED |
| marga | NOT ENUMERATED |
| national-ammonia | NOT ENUMERATED |
| nonautomatic-hydrocarbon | NOT ENUMERATED |
| pah | NOT ENUMERATED |
| particle-concentrations-numbers | NOT ENUMERATED |
| precip-net | NOT ENUMERATED |
| rural-no2 | NOT ENUMERATED |
| stratospheric-ozone-uv | NOT ENUMERATED |
| tomps | NOT ENUMERATED |
| urban-no2 | NOT ENUMERATED |

### 4. Network metadata signals
| Source | Jurisdiction | Adapter | Discovery signals | Reachable |
|---|---|---|---:|---:|
| ukair-sos | United Kingdom | MISSING | 19 | 0 |
| ukair-data-archive | United Kingdom | MISSING | 5 | 0 |
| defra-get-air-pollution-data | United Kingdom | MISSING | 0 | 0 |
| ukair-locally-managed | United Kingdom | MISSING | 2 | 0 |
| laqm-central | England, Scotland and Wales with scheme-specific rules | MISSING | 6 | 0 |
| scottish-air-quality-api | Scotland | MISSING | 29 | 1 |
| wales-air-sos | Wales | MISSING | 0 | 0 |
| wales-air-atom | Wales | MISSING | 0 | 0 |
| ni-air-sos | Northern Ireland | MISSING | 4 | 0 |
| ni-air-spatial-register | Northern Ireland | MISSING | 1 | 0 |
| londonair-api | Greater London | MISSING | 38 | 1 |
| air-quality-england | England | MISSING | 0 | 0 |
| breathe-london-api | Greater London | MISSING | 2 | 0 |
| actris-data-portal | European with UK facilities | MISSING | 0 | 0 |
| ceda-moles | United Kingdom and international research holdings | MISSING | 7 | 0 |
| openair-ukaq | United Kingdom | NOT_CANONICAL | 0 | 0 |

### 5. Policy-blocked sources by publisher and category
Safety denials remain UNKNOWN reachability. They must never be automatically unblocked, counted as dataset losses or promoted to research-ready.
| Publisher | Blocked |
|---|---:|
| City of Bradford Metropolitan District Council | 1 |
| City of York Council | 22 |
| Leeds City Council | 3 |

| Safety category | Count |
|---|---:|
| redirect_disallowed | 26 |

### 6. Historical and scientific interpretation safeguards
- Reconcile official UK station and network IDs with source-native records.
- Audit yearly completeness, start/end dates, missing intervals, revisions, retrospective corrections, UTC/BST transitions, units and measurement methods.
- Check ratified versus provisional data, source licences and reuse restrictions.
- Validate row-level observation files using independent tools and researchers.
- Do not treat a year-index URL, successful HTTP request, metadata title or automated QA gate as a complete historical time series.
- Registry references 4 historical revision rules; these are not evidence of fully exercised checks.

### 7. Verified-input SHA-256 fingerprints
| Source type | SHA-256 |
|---|---|
| catalogue | 30612071f11531a5ae7cf5fd37e33c8eb31a3269f26adb7c5f3c93cb88b69fd4 |
| coverage | 1c8eaffbe313b2d16bb879252237e20be5b2ab6bbc318834f8426766b492fa0e |
| handoff | 104450db9c2f4d7f008bd6cc99940ec487144221faa00a26fce6f8e6cf76f472 |
| harvest | 3e2f273a787c3454842c427f516ca377b40d4549bc7c631adad6d927113a8bb5 |
| manifest | 7cc672a1f3ab4ad3f1c09bb3394ee04a147d57f4d14a32172ea14b3027ff08a6 |
| matrix | 53a4a652ec52962d159021c7d6f93f2068d5c350149ea37eb49083b978ac6c8a |
| policy | 3c64ba112a8dad147305fa4f8cfc4a39e3954e920b56ba7e3614438f4b78510d |

### 8. Reviewer evidence requests
| Priority | Review gate | Current limitation | Required new evidence |
|---|---|---|---|
| P0 | Official data connectors | 15 required direct adapters absent | Provider-native endpoint, bounded test and exact schema receipt |
| P0 | Monitoring network coverage | 17 inventories lack reconciled stations | Native active/closed station IDs and registry snapshots |
| P0 | Transport security | 26 blocked URLs; not confirmed missing | Source-verified redirect origins and secure allowlist review |
| P1 | Historical integrity | Historical year-by-network completeness not demonstrated | Original files, versions, checksums, stations and date grids |
| P1 | Scientific admissibility | Independent measurement validation and corroboration incomplete | Raw observations, units, QA flags, second-method reproduction |
| P1 | External peer scrutiny | Scientific publication approval not present | Named reviewer assessment, limitations and recorded sign-off |

### 9. Publication and independent scrutiny
A named scientific reviewer must examine original observations, reproduce findings, approve licensing and limitations, and record an explicit decision. This report does not constitute that approval.
The accompanying machine-readable receipt, snapshot, summary metrics, gap register and bundle manifest support independent inspection.
