# LWI Specification v0.1

Status: initial reference specification, dated 2026-09-25.

## Scope and non-goals

The LLM Weissman Index (LWI) is a **relative, workload-specific,
protocol-specific, quality-adjusted efficiency index**. It is not an
intelligence score, AGI score, universal model ranking, Elo replacement, or
benchmark-independent number. A result without its context is incomplete.

A valid result identifies the candidate and baseline, workload and revision,
measurement protocol, profile and profile version/digest, candidate and
baseline revisions, measurement environment, comparison context ID, quality
transforms, metric definitions, evidence, and result digest.

## Comparability

Two LWI values are directly comparable only when all of these match:

- `spec_version` and schema version;
- profile ID, profile version, and `profile_digest`;
- workload ID/revision, benchmark/dataset revision, and task;
- measurement protocol, statistic, batch, concurrency, cache, streaming, and
  network boundary;
- baseline identity/revision;
- quality transforms and metric definitions;
- relevant measurement environment keys.

The implementation hashes these semantics into `comparison_context_id`. It
includes the baseline identity but not the candidate identity, so candidates
can be compared only within one baseline-bound context. The candidate and
baseline measurement records separately receive `measurement_digest`; the
complete evaluation receives `result_digest`.

Never put `LWI=180` against baseline A beside `LWI=145` against baseline B in
one ranking. Rebasing is explicitly deferred from v0.1.

## Historical inspiration and why the kernel differs

The historical Weissman Score was created in the context of compression work
for HBO *Silicon Valley*, with Tsachy Weissman and Vinith Misra involved in the
technical material. Contemporary compression implementations use a quality or
compression ratio term multiplied by a logarithmic time term, often of the
form:

```text
historical-style score ∝ quality_ratio · log(1 + baseline_time) / log(1 + candidate_time)
```

The exact historical implementation and later competition variants differ;
LWI treats them as inspiration, not as a normative LLM formula. LWI does not
reuse `log(T_baseline) / log(T_candidate)` because raw dimensional quantities
inside logarithms make the result change when seconds become milliseconds and
create pathological behavior around numeric time `1`. A unit-invariant ratio
must be formed after controlled conversion.

The regression test covers 250 ms / 500 ms and 0.25 s / 0.5 s. Both are the
same dimensionless ratio.

## Quality utility

Raw quality is not assumed to be a ratio scale. A profile must define, for
every quality task:

```yaml
metric_id: task_accuracy
raw_direction: higher_is_better
scale_type: bounded_rate
raw_unit: "1"
valid_range: ["0", "1"]
utility_transform: identity
utility_transform_version: "1"
utility_floor: "0"
utility_ceiling: "1"
source: "profile policy"
```

The scoring kernel consumes a positive dimensionless utility `u`, not an
arbitrary raw score. v0.1 supports explicit `identity`, `one_minus`, and
`reciprocal` transforms. Interval, ordinal, Elo-like, and vendor-defined
reward scales cannot use `identity`; absent a defensible monotonic transform,
the result is not scoreable. Chance correction and automatic `[0,1]`
normalization are not applied.

For quality task `i`:

```text
RQ_i = u_candidate_i / u_baseline_i
ln(RQ) = Σ_i v_i · ln(RQ_i)
```

`v_i >= 0` and `Σv_i = 1`. A baseline utility of zero is rejected. A candidate
utility of exactly zero is represented by an explicit zero aggregate, never an
epsilon; the quality gate normally makes that result `ineligible`.

## Efficiency dimensions and units

For lower-is-better `x`, `R = baseline_x / candidate_x`. For higher-is-better
`x`, `R = candidate_x / baseline_x`. The registry is explicit and distinguishes
decimal `MB/GB` from binary `MiB/GiB`, time, bytes, energy, power, count,
currency, throughput, and dimensionless units. Unit conversion requires both
the same physical dimension and semantic kind; `tokens/s` is not
`requests/s`, and USD is not EUR.

## Kernel

Profile weights satisfy:

```text
wQ >= 0, wj >= 0, wQ + Σ_j wj = 1
```

The reference implementation computes with `Decimal` and a documented
`1e-18` sum tolerance:

```text
LWI = 100 · exp(wQ · ln(RQ) + Σ_j wj · ln(Rj))
```

Baseline against itself is exactly 100 for identical validated inputs. For the
same context and without a gate intervention, reciprocal comparisons satisfy
`LWI(A,B) * LWI(B,A) ≈ 10000` within Decimal precision.

## Gates and statuses

Profiles may define `quality_gate.minimum_retention`, conceptually `RQ >=
threshold`. A failed gate returns `status: ineligible`, no leaderboard-friendly
numeric LWI, and still reports candidate utility, baseline utility, retention,
threshold, and margin. The discontinuity near the threshold is intentional and
must be discussed when interpreting results.

Other statuses are:

- `eligible`: all required semantics passed and a numeric LWI was computed;
- `incomplete`: required measurements/provenance/context are missing or
  disputed;
- `invalid`: malformed or contradictory input;
- `ineligible`: valid observations but a policy gate or zero-quality path
  prevents ranking.

## Profiles

`param-v1`, `edge-v1`, and `api-v1` are explicit normative policies, not
scientific constants. They declare intended use, required metrics, weights,
directions, gates, assumptions, correlations, and exclusions. A missing
metric never causes silent redistribution of its weight. A changed policy
requires a new profile version/digest.

## Provenance and uncertainty

Evidence classes are labels, not quality rankings: independent reproduction,
self-measured, vendor-reported, paper-reported, model-card, derived,
unverified, and synthetic. External records preserve URL, title, source date,
retrieval time, source type, claim scope, model/benchmark revisions, and notes.
Measured records can preserve raw-log/config/environment digests, code commit,
sample count, confidence level, interval bounds, method, and seed. v0.1 does
not propagate aggregate confidence intervals; it must not invent them.

## Identity and performance evidence

An evidence record may declare separate model-artifact, quality-context, and
execution-system identities. Quality context includes dataset/task/prompt/
scorer/judge semantics; execution system includes runtime/hardware/parallelism/
serving/cache semantics. If a declared quality artifact and performance artifact
disagree on revision, dtype, or quantization, validation returns
`ARTIFACT_CONTEXT_MISMATCH` rather than presenting one deployment score.
Candidate and baseline quality contexts must also be identical when both are
declared (`QUALITY_CONTEXT_MISMATCH`); the comparison context carries only the
shared quality context, while candidate-specific artifact and measurement data
stay in measurement/result digests so Pareto can compare candidates within one
baseline-bound context.

Performance protocols declare `offline`, `open_loop`, or `closed_loop` when they
claim publication evidence. Operating envelopes contain observed points with
load target/achieved load, duration, outcome counts, cache state, latency
semantics, workload identity, client headroom, and provenance. Adequacy is
versioned by the protocol; there is no universal point-count invariant.
Interpolated/derived points are retained as such and do not enter default
observed-point scoring.

Goodput is a derived request rate from preserved traces and an explicit SLO. The
SLO is part of the comparison context, so goodput under different thresholds is
not directly comparable. Failed, timed-out, and retried requests remain in the
accounting denominator. TTFT, TPOT, ITL, queue latency, and E2E latency are
different metric semantics and must not be silently mapped to one another.

Evidence is labeled `fixture`, `smoke`, or `publication`; the label does not
prove honesty or contamination status. `publication` additionally requires an
explicit model artifact, measured (`self_measured`/`independent_reproduced`)
provenance, and — for performance profiles — an operating envelope for both
systems that agrees with the top-level protocol/workload on scenario, protocol,
and workload identity, with a single goodput SLO and uniform cache state.
Live benchmark execution is outside the
reference package and is default-deny even when a URL is present.

## Parameters and hosted APIs

Total, active, and trainable parameters are separate observations with source,
method, and status. Dense models may have active=total; MoE models often do
not. Disputed claims remain disputed and are not selected for an impressive
score. Hosted/API models may have unknown parameters/hardware and are eligible
only for observable profiles that record provider, model ID, revision/snapshot
when available, client region, API version, streaming, timeout/retry policy,
concurrency, and network assumptions.

## Precision and output

Intermediate ratios are never rounded. JSON preserves Decimal strings. Human
reports use six significant digits by default and expose raw observations,
warnings, digests, and gates. A rounded human display is not a new measurement.
