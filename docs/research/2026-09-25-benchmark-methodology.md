# Benchmark methodology research note — 2026-09-25 baseline

**Repository:** `weby-homelab/llm-weissman-index`  
**Mission baseline:** 2026-09-25  
**Retrieval date:** 2026-09-26 UTC  
**Purpose:** choose evidence and safety practices for an LWI normalization and
comparability layer, not to inflate LWI values.

This note records source snapshots reviewed for this change. It is research
input, not a claim that LWI implements or complies with any upstream benchmark.

## Sources and decisions

| Source and observed version/date | Practice adopted in LWI | Deliberately not adopted |
|---|---|---|
| [MLPerf Inference: Datacenter](https://mlcommons.org/benchmarks/inference-datacenter/), current results page v6.1; rules at [inference_policies](https://github.com/mlcommons/inference_policies/blob/master/inference_rules.adoc); retrieved 2026-09-26 | Explicit scenario/metric rules, benchmark and system provenance, raw-result links, and no cross-context ranking. | MLPerf submission/compliance claim, LoadGen runs, fixed upstream thresholds, or long hardware runs in normal PR CI. LWI calls this MLPerf-inspired only. |
| [MLPerf Endpoints](https://mlcommons.org/benchmarks/endpoints/) and [endpoints repository](https://github.com/mlcommons/endpoints); observed results v0.7; retrieved 2026-09-26 | Capacity as declared operating points/envelopes rather than one lucky throughput number; per-point provenance and review status. | A universal seven-point rule, 600-second runs, or production endpoint traffic. Adequacy is protocol-specific in LWI. |
| [vLLM Benchmark Suites](https://docs.vllm.ai/en/stable/benchmarking/), documentation dated 2026-08-11; retrieved 2026-09-26 | Preserve load scenario, TTFT/TPOT/ITL/E2E semantics, detailed artifacts, seed, token workload, and cache policy. | Reimplementing `vllm bench`, unpinned model downloads, prefix-cache advantages, or live endpoint tests in PR CI. |
| [OLMES](https://github.com/allenai/olmes) and [lm-evaluation-harness interface](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md); OLMES observed alpha 0.1.0; `lm-eval` observed 0.4.13; retrieved 2026-09-26 | Dataset/task/model hashes, revisions, split, few-shot seed, generation config, sample logs, and explicit validation/dry-run concepts. | Treating an academic headline score as contamination-safe, enabling untrusted remote code, or requiring a live judge/API in CI. |
| [Inspect log files](https://inspect.aisi.org.uk/eval-logs.html) and [scoring policy](https://inspect.aisi.org.uk/scoring-policy.html); observed Inspect 0.3.269; retrieved 2026-09-26 | Durable structured logs, explicit correct/incorrect/error/unscored accounting, bounded concurrency, and preservation of scorer metadata. | Treating model-graded output as ground truth without judge provenance/calibration or importing agent execution as LWI performance automatically. |
| [LiveBench](https://github.com/LiveBench/LiveBench) and [paper](https://arxiv.org/abs/2406.19314); observed package 0.0.4 and monthly-release design; retrieved 2026-09-26 | Record benchmark release, release age, source/revision, contamination status, and objective scorer identity. | Calling a rolling “latest” release contamination-free or running paid model APIs in ordinary CI. |
| [pyperf run benchmark](https://pyperf.readthedocs.io/en/latest/run_benchmark.html); observed 2.10.0 release; retrieved 2026-09-26 | Use calibration, warmups, multiple processes, metadata, instability warnings, and saved artifacts for controlled local microbenchmarks. | Gating normal PRs on noisy shared-runner wall-clock timings or using pyperf as a remote LLM quality protocol. |
| [OpenCode V2 permissions](https://opencode.ai/docs/permissions/), last updated 2026-09-25; retrieved 2026-09-26 | `permission` allow/ask/deny semantics, last-match-wins review, edit-deny read-only agents, no secret-path permission, and narrow external-directory scope. | Legacy `tools` configuration, broad `--auto` for live/secret work, or credential access through committed project config. |
| [GitHub Actions security hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions), rolling guidance retrieved 2026-09-26 | Read-only token permissions, full SHA action pins, no `pull_request_target` checkout of untrusted code, fork-safe jobs, Dependabot coverage, and isolated future live workflows. | Secrets in fork PR jobs, persistent self-hosted runners, shell interpolation of untrusted contexts, and live production benchmarks in normal CI. |

## Resulting LWI policy

- LWI is a validation, normalization, provenance, and analysis layer over
  preserved observations; it is not an inference load generator.
- Quality context, model artifact, execution system, and performance protocol
  are distinct identities. A mismatch is invalid rather than averaged away.
- Serving evidence uses `offline`, `open_loop`, or `closed_loop` scenarios and
  explicit observed operating points. Interpolation is display-only by default.
- Goodput is derived only from preserved request traces and an explicit SLO;
  failures, retries, cache state, token shape, and client headroom remain visible.
- Uncertainty is reported as unavailable when no defensible method is present.
- External normalization requires an explicit field map and raw artifact digest;
  similar names do not establish semantic equivalence.
- Normal PR CI remains deterministic/offline with no GPU, provider secret, paid
  judge, live endpoint, or network load benchmark. `pyperf` is informational and
  controlled-run only.

## Residual limitations

This repository still cannot prove that a producer honestly generated a raw log,
detect all training contamination, or independently reproduce a vendor claim.
The GLiNER2.5-Decide example remains a caveated case study, not publication
evidence. Those limitations are part of the result interpretation boundary.
