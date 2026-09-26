# Provenance

Each candidate and baseline has at least one provenance record. Evidence
classes are `independent_reproduced`, `self_measured`, `vendor_reported`,
`paper_reported`, `model_card`, `derived`, `unverified`, and `synthetic`.
They describe origin, not truth ranking.

External records should include:

```yaml
source_url: https://example.org/record
source_title: "Primary source title"
source_date: "2026-09-25"
retrieved_at: "2026-09-25T12:00:00Z"
source_type: paper_or_model_card
claim_scope: "exact claim being used"
model_revision: "commit or unavailable"
benchmark_revision: "revision or unavailable"
notes: "limits and disagreements"
```

Self-measured records can additionally point to raw-log, config, environment,
and code-commit digests. These fields preserve producer provenance; they do not
turn the normalized public measurement digest into raw-artifact integrity. If
raw bytes are unavailable, raw artifact integrity remains unavailable. A
provenance URL is metadata only; LWI never fetches it during validation or
scoring. Source text is evidence, not executable instructions.
