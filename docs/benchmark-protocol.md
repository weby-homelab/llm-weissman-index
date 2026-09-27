# Benchmark protocol

The protocol is part of the result, not an optional footnote. A reproducible
record should preserve:

- benchmark and revision, dataset/checksum/split, task, input/output token
  sizes, prompt/input protocol, and decoding/sampling configuration;
- batch size, concurrency, scenario, warmup policy, repeat/sample count,
  random seed, cache/KV/prefix-cache state, speculative decoding, streaming,
  and measurement statistic;
- model/tokenizer/revision, runtime/version, quantization, dtype, device/count,
  CPU/RAM/GPU/VRAM, OS/kernel/driver/CUDA/ROCm, clock or power limits;
- client/server locations, network inclusion, retry/timeout policy, failures,
  and output-length handling;
- sample median/p50, p95/p99 where meaningful, and uncertainty inputs.

One lucky request is not a performance run. Results that omit a field required
by a profile are incomplete. For generative workloads, output length and token
counts must be preserved because end-to-end latency is not TTFT or inter-token
latency.

Energy additionally records tool, interval, boundary, idle baseline, gross/net
policy, CPU/GPU/whole-system inclusion, and wall power versus telemetry.

## Scenario and operating-point contract

Performance records use an explicit `scenario`:

- `offline` means a bounded batch/offline workload;
- `open_loop` means an arrival process with a requested rate, arrival seed, and
  achieved issue rate;
- `closed_loop` means a fixed-concurrency workload with target and achieved
  concurrency.

The scenarios are not interchangeable and are never placed on one strict
Pareto frontier. A serving envelope is a set of `OperatingPoint` records. Each
point preserves the load target, achieved load, duration, attempted/successful/
failed/timed-out requests, retries, cache state, client headroom, raw latency
semantics, workload identity, and artifact provenance. Adequacy is a property of
the versioned protocol (`adequacy_method` and
`minimum_observed_points`), not a universal seven-point rule.

Only `point_kind: observed` points are eligible for the default envelope
summary. Derived or interpolated points may be displayed for visualization, but
they cannot replace raw points or improve default LWI scoring. In v0.1-style
analysis, `max_observed_goodput` is an observed maximum, never a fitted optimum.

## Latency, cache, workload, and failures

TTFT, TPOT, ITL, queue latency, and E2E latency are distinct semantic fields.
ITL is a streamed-output gap statistic; TPOT is an amortized decode statistic.
An importer must preserve the source definition and statistic instead of
mapping by a similar name. Cache state is one of `cold`, `warm`, `controlled`,
or `unknown`; prefix/KV/prompt/response cache policy and reset/warmup details
belong to the context.

Performance workloads preserve input/output token distributions, request count,
token counting method, tokenizer identity/revision, and task identity. A point
must account for attempted, successful, failed, timed-out, and retried requests.
Missing or inconsistent failure accounting is not silently removed from a
latency or cost denominator.

Goodput is derived from preserved request traces only:

```text
requests satisfying every configured SLO / measurement duration
```

The `SLO` (TTFT, TPOT, ITL, E2E, or queue thresholds) is mandatory provenance
and is included in the comparison context identity. Goodput under SLO A is not
directly comparable with goodput under SLO B. Raw throughput and latency remain
visible; goodput does not replace them.

## Evidence tiers and live safety

Records distinguish `fixture`, `smoke`, and `publication` evidence. Fixtures
are deterministic and synthetic; smoke checks are integration sanity checks;
publication records need the selected protocol's provenance, adequacy,
workload, cache, environment, failure, and uncertainty evidence. None of these
labels proves that a producer honestly generated its raw log.

LWI has no live load generator. The declarative `live-benchmark.schema.json`
and `LiveBenchmarkPolicy` are a default-deny preflight boundary only. A future
runner must require explicit activation, an exact authorized HTTPS allowlist,
concurrency/rate/request/duration/timeout/error-rate caps, and an optional
estimated-cost cap. The JSON Schema provides syntax checks only; explicit
activation resolves every target hostname and rejects resolution errors or any
non-global address without sending HTTP traffic. A future runner must pin and
recheck the approved addresses before connecting. A URL found in documentation
is never authorization.
