# ADR 0001: Relative geometric index

## Decision

Use a weighted geometric mean of dimensionless candidate/baseline ratios and
anchor the baseline at 100.

## Rationale

Geometric aggregation preserves multiplicative reciprocity, prevents one
dimension's unit scale from dominating, and makes the contribution of each
policy weight explicit. Decimal arithmetic plus log-space evaluation gives a
stable reference implementation.

## Rejected

The historical logarithm-of-time expression was not copied because it is
unit-sensitive and pathological around numeric time 1. A universal arithmetic
mean was rejected because it has poor multiplicative semantics.
