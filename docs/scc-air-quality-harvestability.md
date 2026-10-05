# SCC Air Quality harvestability gate

This gate converts the sanitised discovery handoff into a bounded, reviewable qualification manifest.
It does **not** turn catalogue discoveries into scientific evidence and it does not authorise production
use in SCC Air Quality.

## Lifecycle

\`DISCOVERED -> RELEVANCE_MATCHED -> MACHINE_READABLE -> REACHABLE -> CANDIDATE_FOR_TEST\`

\`CANDIDATE_FOR_TEST\` means only that SCC Air Quality may independently reacquire the original-provider
endpoint in its test environment. Promotion to scientific or production use remains outside this
repository.

## Qualification rules

The builder groups records using a deterministic provider/title/geography dataset key, selects the
strongest machine endpoint available, rebuilds pollutant/stressor relevance using the governed registry,
and attaches existing or bounded live reachability evidence. URLs that are non-HTTPS or contain
credential-like query parameters, embedded credentials, or the \`REDACTED\` marker are never live-probed.

A row can become \`CANDIDATE_FOR_TEST\` only when all of the following are true:

- the dataset has a governed pollutant/stressor relevance match;
- a machine-readable endpoint is identified;
- the selected endpoint has a successful reachability observation;
- licence metadata is explicit enough for review; and
- no credential-bearing access pattern is present.

Even then, \`vvip_status\` remains \`REVIEW_REQUIRED\`, \`schema_verified\` remains \`no\`, and
\`provider_verified\` remains \`no\` until downstream review supplies stronger evidence.

## Outputs

The repository keeps only the lean review snapshot:

- \`handoff/sccairquality/harvestability/harvestability-manifest.csv\`
- \`handoff/sccairquality/harvestability/harvestability-receipt.json\`

The workflow artifact retains the fuller evidence bundle, including the selected endpoint and grouped
source records, for 30 days. The receipt always records that scientific admissibility is not conferred
and production change is not authorised.

## SCC/VVIP boundary

The catalogue discovers and qualifies. SCC Air Quality independently reacquires and validates from the
original provider. A catalogue success, a reachability success, or a \`CANDIDATE_FOR_TEST\` row must never
be represented as proof of accuracy, completeness, comparability, regulatory suitability, exposure, or
health effect.
