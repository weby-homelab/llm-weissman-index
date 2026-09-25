# Methodology

LWI separates three layers:

1. **Measurement**: a workload, model revision, protocol, environment, unit,
   statistic, sample count, and provenance record.
2. **Policy**: an immutable profile that chooses required dimensions, quality
   transforms, weights, directions, gates, assumptions, and exclusions.
3. **Kernel**: Decimal conversion, utility aggregation, geometric ratios, and
   context/result digests.

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
