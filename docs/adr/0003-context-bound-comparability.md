# ADR 0003: Context-bound comparability

## Decision

Generate a SHA-256 `comparison_context_id` from spec/profile/workload/protocol,
baseline identity, quality transforms, metric definitions, and relevant
environment keys. Refuse cross-context Pareto output.

## Rationale

A relative score is not portable across arbitrary baselines or measurement
protocols. A visible, deterministic identity prevents accidental mixed tables
and makes reports auditable.

## Deferred

Rebasing, uncertainty propagation through the aggregate, hosted leaderboards,
and automatic benchmark orchestration are outside v0.1.
