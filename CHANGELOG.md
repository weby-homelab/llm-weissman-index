# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Explicit performance evidence primitives for scenarios, observed operating
  envelopes, latency semantics, SLO-bound goodput, cache state, workload shape,
  and failure/retry accounting.
- Separate model-artifact, quality-context, and execution-system identities with
  mismatch validation and shared-context digest binding.
- Pairwise envelope compatibility (scenario, protocol, workload, single SLO,
  uniform cache) and publication evidence gates (model artifact, measured
  provenance, operating envelopes).
- Log-space LWI contribution reporting, finite-value Pareto validation, a
  non-guessing explicit importer contract, and default-deny live policy schema.

### Hardened

- Report-boundary redaction now covers parameter metadata, camelCase credential
  keys, URL userinfo/query tokens, and terminal control characters.
- Comparison/measurement/profile schemas now share finite-decimal contracts;
  CI validates a clean wheel install and installed CLI smoke test.
- URL-path token redaction, unhashable-enum structured errors, CLI InputError
  boundaries, and live-policy schema parity (positive caps, credential-free
  targets, cost/currency binding).

## [0.1.0] - 2026-09-25

### Added

- Versioned LWI specification, profiles, units, quality utilities, gates,
  provenance, digests, validation, Pareto dominance, CLI, examples, tests,
  and machine-readable schemas.
- Synthetic deterministic example and caveated GLiNER2.5-Decide evidence case
  study.

### Security

- Safe YAML loading, bounded input files, strict fields, no code execution,
  read-only CI token permissions, and immutable SHA-pinned CI actions.
