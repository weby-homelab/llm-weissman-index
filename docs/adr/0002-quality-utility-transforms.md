# ADR 0002: Explicit quality utility transforms

## Decision

Profiles must declare scale type, direction, range, transform, transform
version, utility bounds, and source. The kernel operates only on positive
dimensionless utility.

## Rationale

Accuracy rates, losses, ordinal judgments, Elo-like values, and vendor rewards
do not share a ratio-scale interpretation. Refusing an unsupported transform
is more defensible than manufacturing a ratio.

## Consequence

Profile authors carry normative responsibility. A changed transform changes the
profile digest and must not mutate released results.
