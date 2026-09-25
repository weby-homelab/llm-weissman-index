# Threats to validity

LWI is a measurement aid, not a guarantee against gaming. Reviewers should
consider each item before accepting a result:

- Goodhart's law, benchmark contamination, memorization, and training on
  evaluation data;
- workload, baseline, hardware, profile-weight, and quality-transform
  cherry-picking;
- quantization, dtype, batch size, concurrency, warm/cold cache, prompt/KV
  cache, speculative decoding, retries, failure omission, and provider
  batching;
- network location, API drift, pricing drift, currency changes, output length,
  tokenizer revision, metric-definition drift, benchmark revision drift, and
  missing model revisions;
- vendor-reported versus reproduced evidence, missing uncertainty, false
  precision, specialist versus generalist tasks, and hidden API internals;
- total versus active MoE parameters, marketing labels, disputed counts, and
  correlation/double-counting between latency/throughput, parameters/bytes,
  runtime/energy/cost, and TTFT/end-to-end latency.

The validator detects many unit, statistic, missing-field, protocol,
environment, currency, evidence, parameter, and context errors. It cannot
detect benchmark contamination, dishonest logs, all provider-side batching,
or a strategically selected workload. Profiles therefore document known
correlations and exclusions and never claim natural-law weights.

Quality gates also introduce a discontinuity near the threshold. Uncertainty
is represented at input level in v0.1, but aggregate interval propagation is
not implemented and must not be inferred from the point estimate.
