# Quality transforms

Quality transforms are benchmark policy, not universal statistics.

| Scale | Safe default in v0.1 |
|---|---|
| Ratio scale with meaningful zero | Explicit `identity` may be defensible |
| Bounded rate | Explicit `identity` with declared range, such as `[0,1]` |
| Error rate | Explicit `one_minus` only when lower error truly means higher utility |
| Perplexity-like positive loss | Explicit `reciprocal` may be appropriate after review |
| Interval, ordinal, Elo-like, vendor reward | No identity ratio; define and version a monotonic transform first |

Transforms must be deterministic, monotonic in the intended direction, versioned
before comparison, and identical for candidate and baseline. Do not infer
chance correction, normalize against observed min/max, or pick a transform
because it improves a preferred model.

The implementation reports the raw observation, transform metadata, utility,
aggregate utility, quality ratio, and retention. A zero baseline utility is an
undefined ratio and is rejected.
