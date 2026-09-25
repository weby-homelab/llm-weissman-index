# Security policy

## Scope

The reference implementation treats benchmark YAML/JSON as hostile input. It
does not fetch source URLs, execute content, evaluate expressions, import
dynamic modules, or deserialize pickle. The CLI has no shell execution path.

## Reporting a vulnerability

Please do not open a public issue for an exploitable vulnerability. Use the
private GitHub security-advisory mechanism for
`weby-homelab/llm-weissman-index` when available, or contact the Weby Homelab
maintainer through the organization profile. Include a minimal reproduction,
affected version/commit, impact, and a suggested mitigation. Do not include
secrets or personal data in the report.

Supported versions are the latest released version and the default branch.
Security fixes should add a regression test and be described in the changelog.

## Repository security controls

The bootstrap workflow uses least-privilege read tokens and immutable Action
commit pins. Dependabot is configured for uv and GitHub Actions. CodeQL
default setup, secret scanning/push protection, dependency review, and an
OpenSSF Scorecard run are considered release/repository settings rather than
hard-coded bootstrap workflow requirements; they require canonical repository
administration and will be verified after authenticated access is available.
