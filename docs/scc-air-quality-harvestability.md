# SCC Air Quality harvestability gate

This gate converts the sanitised discovery handoff into a bounded, reviewable qualification manifest.
It does **not** turn catalogue discoveries into scientific evidence and it does not authorise production
use in SCC Air Quality.

## Lifecycle

`DISCOVERED -> RELEVANCE_MATCHED -> MACHINE_READABLE -> REACHABLE -> CANDIDATE_FOR_TEST`

`CANDIDATE_FOR_TEST` means only that SCC Air Quality may independently reacquire the original-provider
endpoint in its test environment. Promotion to scientific or production use remains outside this
repository.

## Qualification rules

The builder groups records using a deterministic provider/title/geography dataset key, selects the
strongest machine endpoint available, rebuilds pollutant/stressor relevance using the governed registry,
and attaches existing or bounded live reachability evidence. URLs that are non-HTTPS or contain
credential-like query parameters, embedded credentials, or the `REDACTED` marker are never live-probed.

A row can become `CANDIDATE_FOR_TEST` only when all of the following are true:

- the dataset has a governed pollutant/stressor relevance match;
- its title, description or themes contain explicit air-context evidence (for example air quality,
  atmospheric monitoring, diffusion tubes or a named air-pollutant concentration);
- a machine-readable endpoint is identified;
- the selected endpoint has a successful reachability observation;
- licence metadata is explicit enough for review; and
- no credential-bearing access pattern is present.

A cross-media pollutant match on its own is not enough. Water, soil, sediment and other environmental
datasets stay review-only unless the record also carries explicit air-context evidence.

Even then, `vvip_status` remains `REVIEW_REQUIRED`, `schema_verified` remains `no`, and
`provider_verified` remains `no` until downstream review supplies stronger evidence.

## Outputs

The repository keeps only the lean review snapshot:

- `handoff/sccairquality/harvestability/harvestability-manifest.csv`
- `handoff/sccairquality/harvestability/harvestability-receipt.json`
- `handoff/sccairquality/harvestability/policy-block-review.csv`

The workflow artifact retains the fuller evidence bundle, including the selected endpoint and grouped
source records, for 30 days. The receipt always records that scientific admissibility is not conferred
and production change is not authorised.

## SCC/VVIP boundary

The catalogue discovers and qualifies. SCC Air Quality independently reacquires and validates from the
original provider. A catalogue success, a reachability success, or a `CANDIDATE_FOR_TEST` row must never
be represented as proof of accuracy, completeness, comparability, regulatory suitability, exposure, or
health effect.

## Policy-block review (5 November 2026)

A network safety block is **not evidence that a dataset is missing or unreachable**.
When the bounded transport refuses a redirect, a non-public DNS answer, a DNS
resolution, or an invalid endpoint, the manifest keeps the record, sets
`probe_outcome=blocked_by_policy` and `reachable=unknown`, and emits a separate
`policy-block-review.csv` queue. All these records remain `DISCOVERED_ONLY` and
`REVIEW_REQUIRED`, never `CANDIDATE_FOR_TEST`.

The queue deliberately excludes raw failure messages and endpoint URLs; reviewers
can cross-reference the manifest by `dataset_key` and `source_id`. Release receipts
record `policy_blocked_count` and the queue filename, and CI verifies consistency.
A denial must not trigger an automatic exception, redirect approval or security
bypass. Review original-provider metadata and approved host/redirect policies,
then test a separately approved provider adapter with pinned domain policies.

The 5 November qualification receipt had 26 policy blocks and only 2 datasets
eligible for independent testing, compared with 24 in the preceding receipt.
Most of the changed entries came from York/Leeds open-data feeds. This records a
**classification and network-policy change**, not proof of permanent source loss.
