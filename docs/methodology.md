# Methodology

LWI separates three layers:

1. **Measurement**: a workload, model revision, protocol, environment, unit,
   statistic, sample count, and provenance record.
2. **Policy**: an immutable profile that chooses required dimensions, quality
   transforms, weights, directions, gates, assumptions, and exclusions.
3. **Kernel**: Decimal conversion, utility aggregation, geometric ratios, and
   context/result digests.

The evidence model keeps four identities separate:

1. **Model artifact** — artifact/checkpoint and weights revision or digest,
   adapters, tokenizer, dtype, and quantization.
2. **Quality context** — dataset/split/task revision, prompt and chat-template
   digests, few-shot selection, scorer/judge configuration, and grading epoch.
3. **Execution system** — runtime, hardware/device count, parallelism, serving
   configuration, and cache policy.
4. **Performance protocol** — scenario, load process, warmup, statistic,
   workload shape, SLO, and failure/retry rules.

If quality and performance declare different artifact revision, dtype, or
quantization, validation returns `ARTIFACT_CONTEXT_MISMATCH`; the result is not
scoreable as one deployment. Candidate and baseline quality contexts must match
when both are declared. The context digest carries only the shared quality
context; candidate-specific measurements stay in measurement/result digests.
Quality and performance do not need identical
physical hosts, but they must identify the relationship honestly.

The separation prevents a profile from being tuned after seeing results and
prevents a benchmark value from being treated as a universal model property.

## Interpretation

`100` means candidate and baseline are identical under the selected context.
`136.604` in the synthetic example means only that the candidate's declared
latency, throughput, and peak-memory observations are twice the baseline's
under `edge-v1`; it is not an intelligence claim.

The most important output is often `status` and `comparison_context_id`, not
the scalar. Ineligible and incomplete results should not enter a leaderboard.

## What v0.1 refuses to do

- rebase across baselines;
- divide arbitrary interval or ordinal scores;
- infer hidden API parameters or hardware;
- mix p50 and p95, warm and cold cache, or incompatible batch/concurrency;
- compare active MoE parameters with dense total parameters;
- convert currencies without preserved FX source/rate/timestamp;
- manufacture uncertainty, latency, or benchmark evidence.

## Analysis output

Every finite score exposes each log-space component as `ratio`, `weight`, and
`weight * ln(ratio)`, plus the sum. This makes a score dominated by one extreme
dimension visible. The `uncertainty_status` is `available` only when all included
observations carry a defensible interval and confidence level; otherwise it is
`unavailable`, not fabricated.

Pareto analysis requires one `comparison_context_id`, identical dimensions and
directions, and unique candidate IDs. Quality utilities remain separate Pareto
dimensions; their geometric aggregate is not used to hide a task-level
trade-off. A scalar LWI never replaces the Pareto view.

External artifacts are imported only through explicit field mappings that carry
source tool/version and raw artifact digest. Similar names such as ITL/TPOT or
mean/p95 are never mapped automatically; unmapped source fields remain unknown.
