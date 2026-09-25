# Prior-art review (2026-09-25)

This review searched the exact phrases `LLM Weissman Index`, `LLM Weissman
Score`, `AI Weissman Score`, and `language model Weissman score`, plus adjacent
work on quality/latency/efficiency benchmarking. The unauthenticated GitHub
repository API returned zero repositories for the exact-name queries and
`weissman llm`. Search-engine access was inconsistent and is not treated as
proof of absence. We therefore state only: **during this dated review we did
not find an established public metric under the exact name “LLM Weissman
Index”.** This is not a “first ever” claim.

| Retrieved source | Source date | Type | Claim supported and design implication |
|---|---:|---|---|
| https://spectrum.ieee.org/a-made-for-tv-compression-algorithm | 2014-07-25 | IEEE Spectrum primary journalism | Describes the HBO *Silicon Valley* compression consultation, Tsachy Weissman and Vinith Misra attribution, and historical context. LWI is independent and does not claim affiliation. |
| https://web.stanford.edu/~tsachy/ | page updated 2025-07-21 | author/institution page | Confirms Tsachy Weissman’s Stanford compression/information-theory role and links current latency-quality LLM work. |
| https://www.competitive-agent.com/ | retrieved 2026-09-25 | author project page | `Win Fast or Lose Slow` introduces HFTBench/StreetFighter and studies latency-quality tradeoffs; LWI must remain workload-specific. |
| https://arxiv.org/abs/2505.19481 | 2025-05-26 | paper | Latency-sensitive LLM decisions show that speed and quality interact by task; it is adjacent research, not the LWI kernel. |
| https://mlcommons.org/benchmarks/inference-datacenter/ | current V6.1 page retrieved 2026-09-25 | official benchmark | MLPerf uses scenario/metric rules, quality targets, reproducible submissions, divisions, and change logs; LWI adopts the reproducibility discipline. |
| https://mlcommons.org/benchmarks/endpoints/ | current page retrieved 2026-09-25 | official benchmark | MLPerf Endpoints characterizes throughput, interactivity, TTFT P95, concurrency, curves, peer review, and reproducibility; LWI does not replace this benchmark. |
| https://arxiv.org/abs/1911.02549 | 2020-05-09 revision | peer-reviewed benchmark paper | Architecture-neutral, representative, reproducible measurement rules motivate LWI’s protocol/context boundary. |
| https://arxiv.org/abs/2606.17712 and https://aitdcc.github.io/ | 2026-06-16 | compression benchmark/paper | A current non-LLM Weissman-style competition uses a gzip baseline, compression ratio, time, and Pareto analysis. Its implementation exposes the unit/pathology reason LWI uses dimensionless ratios and `log(1+t)` only as historical context, not as its kernel. |
| https://fastino.ai/blog/gliner-2-5-decide-open-weight-decision-model | 2026-09-24 | vendor primary source | GLiNER2.5-Decide blog reports 60.1%, 340M, and vendor latency; values remain vendor-reported. |
| https://huggingface.co/fastino/GLiNER2.5-Decide | retrieved 2026-09-25 | model card | Model card reports 60.2%, 340M, license Apache-2.0, and Fast Decisions details. The disagreement is preserved, not averaged. |

## What LWI adds

Relative baseline normalization is combined with versioned quality utility
transforms, explicit mixed efficiency dimensions, immutable policy profiles,
context-bound comparability, provenance-aware records, uncertainty fields, and
reusable Pareto checks. These are design goals and implementation choices, not
a claim that the composition is scientifically final or universally novel.
