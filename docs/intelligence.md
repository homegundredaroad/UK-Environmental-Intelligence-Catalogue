# Advisory intelligence add-ons

Version 0.8 separates intelligence from evidence collection. Discovery and validation remain
deterministic. Machine-learning and language-model outputs are review aids only.

## Local machine learning

`ukei ml INPUT.json OUTPUT.json` uses TF-IDF features, MiniBatchKMeans and IsolationForest. It
creates thematic clusters and anomaly scores that can help find unusual, duplicated or poorly
described records. Results are deterministic for a fixed input and do not modify the catalogue.

## OpenAI and Gemini

`ukei enrich INPUT.json OUTPUT.json --provider both --max-records 50` classifies the records most
likely to need review. The command requires `OPENAI_API_KEY`, `OPENAI_MODEL`, `GEMINI_API_KEY` and
`GEMINI_MODEL`. Responses must match a narrow JSON schema. Prompts prohibit inferred licences,
availability, scientific validity and legal permissions. Every row records the provider, returned
model, prompt version and a reproducible cache key.

The GitHub workflow defaults AI enrichment off and caps it at 50 records per provider. Increase the
limit only after reviewing cost, rate limits and the first advisory report. Use a current,
cost-efficient model for high-volume classification; reserve frontier reasoning models for a small
manual-review queue.

## Security and governance

- Store API keys only as repository or environment secrets.
- Never commit keys, model responses containing sensitive data, or raw prompts containing secrets.
- Catalogue metadata is sent to the selected provider when enrichment is enabled.
- Model output must receive human review before it informs policy, regulation or operational work.
- Canonical status changes continue to require deterministic validation evidence.
