# Security model

## Trust boundaries

- CLI input files and profile files are untrusted local data.
- External benchmark/model-card text is untrusted evidence.
- Provenance URLs are stored but never requested by the package.
- GitHub Actions, lockfiles, build artifacts, and generated reports are supply
  chain boundaries.

## Controls

- `yaml.safe_load`, JSON parsing, a 5 MiB input cap, strict object fields,
  bounded Decimal parsing, explicit unit registry, and no `eval`, `exec`,
  pickle, dynamic imports, shell execution, or template execution.
- URL metadata is validated for scheme/credentials and never dereferenced.
- Unknown units, dimensions, statistics, parameter semantics, currencies,
  protocols, and missing provenance fail closed or produce structured warnings.
- CI has workflow-level `contents: read`, full commit-SHA action pins, no
  `pull_request_target`, and no release/publish job.
- OpenCode project permissions deny secret file reads, ask for shell by default,
  and use edit-deny read-only review agents.

## Residual risks

The package cannot prove that a producer's raw log was honestly generated,
that a benchmark was uncontaminated, or that a provider model did not drift
between requests. It also cannot prevent a maintainer from selecting a
flattering workload/profile. Those are documented validity threats and require
review, preregistration, raw evidence, and context-bound reporting.
