# Reproducibility

The repository locks Python dependencies in `uv.lock`. Use the documented
commands in the README and CI. The normal unit suite has no network dependency.
Build with `uv build --no-sources`, inspect both wheel and sdist, and install
the wheel into a clean temporary environment before a release.

The current uv CLI can export a CycloneDX v1.5 JSON SBOM without adding a
runtime dependency:

```bash
uv export --locked --format cyclonedx1.5 --output-file sbom.cdx.json
```

The generated SBOM is a release/build artifact and is intentionally ignored by
Git so regenerated dependency metadata does not create repository noise.

For every result retain the input file, profile file/digest, code commit,
measurement digests, context ID, result digest, raw logs/config/environment
digests, timestamp, seed, and uncertainty fields. A future release workflow
may add artifact attestations, Sigstore provenance, SBOM publication, and PyPI
Trusted Publishing; bootstrap does not publish to PyPI.

The project intentionally does not download models, call provider APIs, or
run benchmark workloads. Reproduction is the responsibility of the measurement
producer and must be labeled independently reproduced, self-measured,
vendor-reported, paper-reported, model-card, derived, unverified, or synthetic.
