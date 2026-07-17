# Data model

## Source record

Every record has a stable identifier, title, canonical URL, publisher, description, licence,
geographic scope, update frequency, formats, themes, lifecycle status, discovery and verification
timestamps, provenance URL, connector name, canonical SHA-256 content hash and creation/update times.

Lifecycle values are:

- `candidate`: discovered or entered but not sufficiently corroborated;
- `verified`: checks defined by project policy passed at a recorded time;
- `degraded`: previously useful but now failing material checks;
- `retired`: intentionally removed from active use while history remains.

## Validation event

An append-only event records the source, check name, pass/fail outcome, timestamp, explanatory
message and structured details. Revalidation adds an event; it does not rewrite history.

Sprint 3 metadata observations include a weighted completeness score and missing-field list. Live URL
observations can include HTTP status, elapsed milliseconds, final redirect URL, content type, or a
transport failure reason. These checks establish reachability and metadata completeness only; they
do not prove data accuracy, currency, licensing suitability or fitness for a particular purpose.

A failed live URL check may move an active record to `degraded`. Passing checks preserve the current
state: candidate records require a separate human-governed promotion policy before becoming
`verified`, and retired records are never reactivated automatically.
