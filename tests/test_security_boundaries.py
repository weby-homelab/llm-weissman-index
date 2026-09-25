from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from llm_weissman.errors import InputError
from llm_weissman.models import CostMetadata, Measurement, ProvenanceRecord
from llm_weissman.profiles import Profile, load_profile
from llm_weissman.provenance import provenance_issues
from llm_weissman.validation import load_data_file


def test_duplicate_json_and_yaml_keys_are_rejected(tmp_path: Path) -> None:
    json_path = tmp_path / "duplicate.json"
    json_path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    yaml_path = tmp_path / "duplicate.yaml"
    yaml_path.write_text("a: 1\na: 2\n", encoding="utf-8")
    with pytest.raises(InputError, match="valid JSON/YAML"):
        load_data_file(json_path)
    with pytest.raises(InputError, match="valid JSON/YAML"):
        load_data_file(yaml_path)


def test_nonstandard_json_and_pathological_shape_are_rejected(tmp_path: Path) -> None:
    nan_path = tmp_path / "nan.json"
    nan_path.write_text('{"value": NaN}', encoding="utf-8")
    deep_path = tmp_path / "deep.json"
    deep_path.write_text('{"x":' * 60 + "1" + "}" * 60, encoding="utf-8")
    with pytest.raises(InputError, match="valid JSON/YAML"):
        load_data_file(nan_path)
    with pytest.raises(InputError, match="valid JSON/YAML"):
        load_data_file(deep_path)


def test_malformed_provenance_url_is_structured_not_a_traceback(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    path.write_text(
        """
spec_version: '0.1'
schema_version: '1'
candidate:
  id: c
  revision: r
  quality: []
  metrics: {}
  parameters: {status: unknown, claims: []}
  provenance:
    - evidence_class: synthetic
      source_type: test
      claim_scope: test
      retrieved_at: '2026-09-25'
      source_url: 'https://[bad'
  environment: {}
baseline:
  id: b
  revision: r
  quality: []
  metrics: {}
  parameters: {status: unknown, claims: []}
  provenance:
    - evidence_class: synthetic
      source_type: test
      claim_scope: test
      retrieved_at: '2026-09-25'
  environment: {}
workload: {id: w, revision: r, benchmark: b, task: t, dataset_checksum: sha256:x}
protocol:
  id: p
  version: '1'
  measurement_statistic: mean
  warmup_policy: none
  repeat_count: 1
  batch_size: 1
  concurrency: 1
measurement_environment: {candidate: {}, baseline: {}}
""",
        encoding="utf-8",
    )
    # The loader is syntax-safe; malformed provenance is handled by the semantic layer.
    data = load_data_file(path)
    assert data["candidate"]["id"] == "c"
    record = ProvenanceRecord(
        evidence_class="synthetic",
        source_type="test",
        claim_scope="test",
        retrieved_at="2026-09-25",
        source_url="https://[bad",
    )
    assert any(
        code == "INVALID_PROVENANCE_URL" for code, _, _ in provenance_issues(record, path="test")
    )


def test_provenance_serialization_redacts_credentials_and_query_tokens() -> None:
    record = ProvenanceRecord(
        evidence_class="model_card",
        source_type="test",
        claim_scope="test",
        retrieved_at="2026-09-25T00:00:00Z",
        source_url="https://user:password@example.org/card?auth_token=secret&x=ok#access_token=fragmentsecret",
        source_title="test",
        model_revision="r",
        benchmark_revision="b",
        notes="api_key=supersecret Bearer abcdef",
    )
    rendered = json.dumps(record.to_dict())
    assert "user:password@" not in rendered
    assert "auth_token=secret" not in rendered
    assert "fragmentsecret" not in rendered
    assert "supersecret" not in rendered
    assert "abcdef" not in rendered
    assert "[REDACTED]" in rendered


def test_uncertainty_requires_ordered_bounds_and_valid_confidence() -> None:
    with pytest.raises(InputError, match="confidence_level"):
        Measurement.from_dict(
            {"value": "1", "unit": "count", "statistic": "point", "confidence_level": "1.1"},
            path="measurement",
        )
    with pytest.raises(InputError, match="uncertainty bounds"):
        Measurement.from_dict(
            {
                "value": "1",
                "unit": "count",
                "statistic": "point",
                "lower_bound": "2",
                "upper_bound": "1",
            },
            path="measurement",
        )


def test_cost_metadata_requires_successful_task_denominator() -> None:
    with pytest.raises(InputError, match="successful_task_count"):
        CostMetadata.from_dict(
            {
                "pricing_timestamp": "2026-09-25T00:00:00Z",
                "pricing_source": "test",
                "input_token_count": 1,
                "output_token_count": 1,
                "cached_token_count": 0,
                "request_count": 0,
                "retry_count": 0,
                "failed_request_count": 0,
                "successful_task_count": 0,
            },
            path="cost_metadata",
        )


def test_profile_rejects_non_dimensionless_quality_units_and_unknown_versions() -> None:
    profile = load_profile("edge-v1")
    changed = dict(profile.canonical_dict)
    quality = dict(changed["quality"][0])
    quality["raw_unit"] = "USD"
    changed["quality"] = [quality]
    with pytest.raises(InputError, match="dimensionless"):
        Profile.from_dict(changed)
    quality["raw_unit"] = "1"
    quality["utility_transform_version"] = "99"
    changed["quality"] = [quality]
    with pytest.raises(InputError, match="transform version"):
        Profile.from_dict(changed)
    quality["utility_transform_version"] = "1"
    quality["scale_type"] = "ordinal_custom"
    changed["quality"] = [quality]
    with pytest.raises(InputError, match="scale_type"):
        Profile.from_dict(changed)


def test_decimal_digest_preserves_accepted_precision() -> None:
    left = Measurement(Decimal("0.12345678901234567890123456781"), "1", "mean")
    right = Measurement(Decimal("0.12345678901234567890123456784"), "1", "mean")
    from llm_weissman.digests import sha256_digest

    assert sha256_digest(left.to_dict()) != sha256_digest(right.to_dict())


def test_released_profile_file_cannot_change_without_a_new_version(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "profiles" / "edge-v1.yaml"
    changed = tmp_path / "edge-v1.yaml"
    content = source.read_text(encoding="utf-8").replace(
        "Normative project policy; weights intentionally encode one edge deployment use case only.",
        "Changed policy semantics must use a new profile version.",
    )
    changed.write_text(content, encoding="utf-8")
    with pytest.raises(InputError, match="unexpected digest"):
        from llm_weissman.profiles import load_profile

        load_profile(changed)
