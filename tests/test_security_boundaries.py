from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from llm_weissman.errors import InputError
from llm_weissman.importers import ImportedMetrics
from llm_weissman.models import (
    ComparisonInput,
    CostMetadata,
    Measurement,
    ProvenanceRecord,
    redact_untrusted,
)
from llm_weissman.profiles import Profile, load_profile
from llm_weissman.provenance import provenance_issues
from llm_weissman.validation import ValidationIssue, load_data_file


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
        source_url="https://user:password@example.org/card/token%3Dpathsecret?auth_token=secret&x=ok#access_token=fragmentsecret",
        source_title="test",
        model_revision="r",
        benchmark_revision="b",
        notes="api_key=supersecret Bearer abcdef Authorization: Basic basicsecret",
        raw_log_digest="Authorization: Basic logsecret",
        config_digest="api_key=configsecret",
        environment_digest="token=environmentsecret",
    )
    rendered = json.dumps(record.to_dict())
    assert "user:password@" not in rendered
    assert "auth_token=secret" not in rendered
    assert "pathsecret" not in rendered
    assert "fragmentsecret" not in rendered
    assert "supersecret" not in rendered
    assert "abcdef" not in rendered
    assert "basicsecret" not in rendered
    assert "logsecret" not in rendered
    assert "configsecret" not in rendered
    assert "environmentsecret" not in rendered
    assert "[REDACTED]" in rendered


def test_untrusted_serialization_redacts_cookie_session_and_csrf_values() -> None:
    payload = {
        "Cookie": "cookie-secret",
        "session_id": "session-secret",
        "csrfmiddlewaretoken": "csrf-secret",
        "headers": "X-CSRFToken: header-secret",
        "source_url": (
            "https://example.org/card?cookie=query-secret&session_id=query-session"
            "&csrf=query-csrf&ok=visible"
        ),
        "input_token_count": 7,
        "output_token_count": "opaque-token-count-secret",
    }

    rendered = json.dumps(redact_untrusted(payload), sort_keys=True)

    for secret in (
        "cookie-secret",
        "session-secret",
        "csrf-secret",
        "header-secret",
        "query-secret",
        "query-session",
        "query-csrf",
        "opaque-token-count-secret",
    ):
        assert secret not in rendered
    assert '"input_token_count": 7' in rendered
    assert "[REDACTED]" in rendered


def test_direct_serializers_redact_url_userinfo_and_padded_sensitive_keys() -> None:
    record = ProvenanceRecord(
        evidence_class="model_card",
        source_type="test",
        claim_scope="test",
        retrieved_at="2026-09-25T00:00:00Z",
        source_title="SSH://user:title-secret@example.org/card",
        notes="see ssh://user:notes-secret@example.org/card credential=notes-credential-secret",
    )
    cost = CostMetadata.from_dict(
        {
            "pricing_timestamp": "2026-09-25T00:00:00Z",
            "pricing_source": (
                "HTTPS://billing:pricing-secret@example.org?credential=pricing-credential-secret"
            ),
            "input_token_count": 1,
            "output_token_count": 1,
            "cached_token_count": 0,
            "request_count": 1,
            "retry_count": 0,
            "failed_request_count": 0,
            "successful_task_count": 1,
        },
        path="cost_metadata",
    )
    rendered = json.dumps(
        {
            "record": record.to_dict(),
            "cost": cost.to_dict(),
            "headers": redact_untrusted({" Authorization ": "header-secret"}),
        }
    )

    for secret in (
        "title-secret",
        "notes-secret",
        "notes-credential-secret",
        "pricing-secret",
        "pricing-credential-secret",
        "header-secret",
    ):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_text_and_validation_issue_redaction_cover_quoted_secret_keys() -> None:
    payload = redact_untrusted(
        {
            "notes": (
                "private_key=private-secret access_key=access-secret "
                '"token": "quoted-token-secret" key="key-secret" '
                "credential=credential-secret with spaces"
            ),
            "credential=key-secret": "visible",
            "ssh://user:key-url-secret@example.org": "visible",
            "proxy-authorization": "proxy-header-secret",
            "x-auth": "x-auth-secret",
            "tokenValue": "camel-token-secret",
            "privatekey": "concatenated-private-secret",
            "accesskey": "concatenated-access-secret",
        }
    )
    issue = ValidationIssue(
        code="INVALID_INPUT",
        severity="error",
        message='invalid value "token": "issue-secret"',
        path="$.metadata.credential=path-secret",
    )
    rendered = json.dumps({"payload": payload, "issue": issue.to_dict()})

    for secret in (
        "private-secret",
        "access-secret",
        "quoted-token-secret",
        "key-secret",
        "credential-secret",
        "key-url-secret",
        "proxy-header-secret",
        "x-auth-secret",
        "camel-token-secret",
        "concatenated-private-secret",
        "concatenated-access-secret",
        "issue-secret",
        "path-secret",
    ):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_system_identity_serialization_redacts_ids_and_revisions() -> None:
    root = Path(__file__).parents[1]
    data = load_data_file(root / "examples" / "synthetic" / "comparison.yaml")
    data["candidate"]["id"] = "https://user:id-secret@example.org/model"
    data["candidate"]["revision"] = "HTTPS://user:revision-secret@example.org/revision"
    comparison = ComparisonInput.from_dict(data)

    rendered = json.dumps(comparison.candidate.to_dict())

    assert "id-secret" not in rendered
    assert "revision-secret" not in rendered
    assert "[REDACTED]" in rendered


def test_custom_metric_keys_are_redacted_in_system_and_importer_outputs() -> None:
    root = Path(__file__).parents[1]
    data = load_data_file(root / "examples" / "synthetic" / "comparison.yaml")
    data["candidate"]["metrics"]["credential=system-metric-secret"] = data["candidate"]["metrics"][
        "latency"
    ]
    comparison = ComparisonInput.from_dict(data)
    measurement = Measurement(Decimal("1"), "ms", "p50")
    imported = ImportedMetrics(
        source_tool="fixture",
        source_tool_version="1",
        raw_artifact_digest="sha256:" + "a" * 64,
        raw_artifact_digest_status="verified",
        field_mapping={},
        metrics={"credential=import-metric-secret": measurement},
        unknown_fields=("credential=unknown-field-secret",),
    )

    rendered = json.dumps(
        {"system": comparison.candidate.to_dict(), "imported": imported.to_dict()}
    )

    for secret in (
        "system-metric-secret",
        "import-metric-secret",
        "unknown-field-secret",
    ):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_system_identity_serialization_redacts_untrusted_fields() -> None:
    root = Path(__file__).parents[1]
    data = load_data_file(root / "examples" / "synthetic" / "comparison.yaml")
    data["baseline"]["provider"] = "https://provider.example/model?access_token=provider-secret"
    data["baseline"]["model_id"] = "Authorization: Basic model-secret"
    comparison = ComparisonInput.from_dict(data)

    rendered = json.dumps(comparison.baseline.to_dict())
    assert "provider-secret" not in rendered
    assert "model-secret" not in rendered
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


def test_cost_metadata_cannot_hide_cache_failures_or_retries() -> None:
    base = {
        "pricing_timestamp": "2026-09-25T00:00:00Z",
        "pricing_source": "test",
        "input_token_count": 10,
        "output_token_count": 5,
        "cached_token_count": 2,
        "request_count": 2,
        "retry_count": 1,
        "failed_request_count": 1,
        "successful_task_count": 1,
        "timed_out_request_count": 1,
        "attempted_request_count": 3,
        "currency": "USD",
        "total_charge": "0.50",
    }
    CostMetadata.from_dict(base, path="cost_metadata")
    invalid_cases = (
        {"cached_token_count": 11},
        {"timed_out_request_count": 2},
        {"successful_task_count": 2},
        {"attempted_request_count": 2},
    )
    for change in invalid_cases:
        candidate = dict(base)
        candidate.update(change)
        with pytest.raises(InputError, match="cost metadata|cannot|account"):
            CostMetadata.from_dict(candidate, path="cost_metadata")
    without_currency = dict(base)
    without_currency.pop("currency")
    with pytest.raises(InputError, match="currency"):
        CostMetadata.from_dict(without_currency, path="cost_metadata")


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


def test_profile_rejects_reserved_quality_dimension_id() -> None:
    profile = load_profile("edge-v1")
    changed = dict(profile.canonical_dict)
    metrics = [dict(item) for item in changed["metrics"]]
    metrics[0]["metric_id"] = "quality"
    changed["metrics"] = metrics
    changed["weights"] = {
        "quality": "0.55",
        "metrics": {"quality": "0.45", "throughput": "0.10", "peak_memory": "0.10"},
    }
    with pytest.raises(InputError, match="reserved"):
        Profile.from_dict(changed)


def test_url_path_tokens_are_redacted() -> None:
    from llm_weissman.models import redact_untrusted

    rendered = redact_untrusted({"source": "https://example.test/card/api_key=k1/next"})
    assert "api_key=k1" not in str(rendered)
    assert "[REDACTED]" in str(rendered)


def test_decoded_url_control_characters_are_escaped() -> None:
    rendered = str(
        redact_untrusted({"source": "https://example.test/card/%0AInjected%09tab%0Dreturn"})
    )
    assert "\n" not in rendered
    assert "\r" not in rendered
    assert "\t" not in rendered
    assert r"\x0a" in rendered
    assert r"\x09" in rendered
    assert r"\x0d" in rendered


def test_embedded_url_userinfo_with_control_characters_is_redacted() -> None:
    rendered = str(
        redact_untrusted({"note": "see https://user:literal-secret\n@example.test/card"})
    )
    assert "literal-secret" not in rendered
    assert "\n" not in rendered
    assert "[REDACTED]" in rendered


def test_comparison_scalar_metadata_is_redacted_in_public_dict() -> None:
    root = Path(__file__).parents[1]
    data = load_data_file(root / "examples" / "synthetic" / "comparison.yaml")
    data["spec_version"] = "credential=spec-secret"
    data["schema_version"] = "Authorization: Basic schema-secret"
    rendered = json.dumps(ComparisonInput.from_dict(data).to_dict())

    assert "spec-secret" not in rendered
    assert "schema-secret" not in rendered
    assert "[REDACTED]" in rendered


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
