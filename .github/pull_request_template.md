## Summary

<!-- What changed and why? Include the workload/profile/context implications. -->

## Evidence and provenance

- [ ] No benchmark value, parameter count, latency, or model revision was fabricated.
- [ ] External values retain source URL, source date, retrieval date, evidence class, and claim scope.
- [ ] Released profiles were not edited in place.

## Verification

```text
uv lock --check
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build --no-sources
```

<!-- Paste actual results. Do not write “tests pass” without commands. -->
