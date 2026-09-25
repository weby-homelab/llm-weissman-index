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
