# Units and metric semantics

The registry is deliberately small. Supported dimensions include time, bytes,
energy, power, count, currency, throughput, and dimensionless values. `MB` and
`GB` are decimal; `MiB` and `GiB` are binary. Currency codes are not exchange
rates: USD/EUR/UAH comparisons fail unless the same currency is observed.

The statistic is separate from the unit. p50, p95, mean, max, and minimum are
not interchangeable. A metric also has a semantic kind: tokens/s cannot be
converted into requests/s merely because both are rates.

Physical resource values must be finite and positive. NaN, infinity, negative
latency, zero denominators, unknown units, wrong dimensions, and excessive
decimal exponents are rejected before scoring.
