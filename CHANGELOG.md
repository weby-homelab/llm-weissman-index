# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.2.0] - 2026-09-27

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
  keys, cookie/session/CSRF values, URL userinfo/query tokens, and terminal
  control characters.
- Comparison/measurement/profile schemas now share finite-decimal contracts;
  CI validates a clean wheel install and installed CLI smoke test.
- URL-path token redaction, unhashable-enum structured errors, CLI InputError
  boundaries, and live-policy schema parity (positive caps, credential-free
  targets, cost/currency binding).
- Live target validation normalizes trailing-dot hostnames before rejecting
  private or loopback IP literals.
- GLiNER2.5-Decide evidence labels and conflicting published parameter claims
  remain explicit rather than being promoted to an unsupported score.

### Documentation

- The README architecture diagram now presents the four-stage evidence,
  comparison-context, analysis/eligibility, and auditable-output flow with a
  textual equivalent for readers who do not use Mermaid.

### Security / robustness

- YAML and JSON inputs remain bounded, strict, non-executable, and offline;
  provenance URLs are recorded but never fetched by the package.
- Live benchmark policy remains declarative and default-deny; no live traffic
  or paid external judge was run for this release.

### Compatibility

- The software package and CLI release version is `0.2.0`; existing `validate`,
  `compute`, and `report` commands remain available, with context-bound
  `context` and `pareto` analysis available for the expanded evidence model.
- `spec_version: "0.1"`, `schema_version: "1"`, `param-v1`, `edge-v1`, and
  `api-v1` remain unchanged, including their released profile digests.
- Validation is intentionally stricter for malformed or incomparable
  performance/provenance records. Inputs that relied on silently accepted
  invalid semantics must be corrected rather than silently reweighted.

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
