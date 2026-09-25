# Contributing

Contributions should improve the defensibility, reproducibility, or usability
of LWI without turning it into a universal intelligence ranking.

## Before opening a pull request

```bash
uv lock --check
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build --no-sources
git diff --check
```

No network is required by the normal test suite. Do not add a dependency for a
small arithmetic task. If a dependency is necessary, explain its runtime
purpose, license, maintenance, and lockfile impact.

## Methodology changes

Do not edit a released profile in place. Add a new version, update the formal
specification/ADR when semantics change, and add regression tests for every
invariant. Raw benchmark values need source, retrieval date, evidence class,
model revision, and benchmark revision. Vendor-reported values must remain
vendor-reported.

## Pull requests

Use a focused branch and a conventional commit-style title (`feat:`, `fix:`,
`docs:`, `test:`, `ci:`, or `chore:`). Explain the context boundary and
validation commands. Never include secrets, credentials, private keys, model
weights, or local benchmark logs containing sensitive data.
