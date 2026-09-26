from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from llm_weissman.digests import sha256_digest
from llm_weissman.errors import InputError
from llm_weissman.models import ComparisonInput
from llm_weissman.profiles import load_profile
from llm_weissman.report import evaluation_document
from llm_weissman.scoring import evaluate


def test_machine_readable_schemas_are_valid_json_with_version_contracts() -> None:
    schema_dir = Path(__file__).parents[1] / "schemas"
    paths = sorted(schema_dir.glob("*.schema.json"))
    assert {path.name for path in paths} == {
        "comparison.schema.json",
        "live-benchmark.schema.json",
        "measurement.schema.json",
        "profile.schema.json",
        "result.schema.json",
    }
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["required"]
        jsonschema.Draft202012Validator.check_schema(schema)


def test_committed_profiles_validate_against_profile_schema() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "schemas" / "profile.schema.json").read_text(encoding="utf-8")
    )
    for path in sorted((Path(__file__).parents[1] / "profiles").glob("*.yaml")):
        jsonschema.validate(yaml.safe_load(path.read_text(encoding="utf-8")), schema)


def test_synthetic_comparison_validates_offline_against_comparison_schema() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads((root / "schemas" / "comparison.schema.json").read_text(encoding="utf-8"))
    comparison = yaml.safe_load(
        (root / "examples" / "synthetic" / "comparison.yaml").read_text(encoding="utf-8")
    )
    jsonschema.validate(comparison, schema)


def test_runtime_result_validates_against_result_schema() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads((root / "schemas" / "result.schema.json").read_text(encoding="utf-8"))
    comparison = ComparisonInput.from_dict(
        yaml.safe_load(
            (root / "examples" / "synthetic" / "comparison.yaml").read_text(encoding="utf-8")
        )
    )
    evaluation = evaluate(comparison, load_profile("edge-v1"))
    jsonschema.validate(
        evaluation_document(evaluation, comparison, load_profile("edge-v1")), schema
    )


def test_measurement_digest_declares_public_scope_not_raw_integrity() -> None:
    root = Path(__file__).parents[1]
    comparison = ComparisonInput.from_dict(
        yaml.safe_load(
            (root / "examples" / "synthetic" / "comparison.yaml").read_text(encoding="utf-8")
        )
    )
    profile = load_profile("edge-v1")
    evaluation = evaluate(comparison, profile)
    document = evaluation_document(evaluation, comparison, profile)

    assert document["measurement_digest_semantics"] == "normalized_public_record_v1"
    assert document["raw_artifact_integrity"] == {
        "candidate": "unavailable",
        "baseline": "unavailable",
    }
    assert document["measurement_digests"]["candidate"] != sha256_digest(
        comparison.candidate.to_dict()
    )


def test_report_rejects_evaluation_and_comparison_binding_mismatch() -> None:
    root = Path(__file__).parents[1]
    data = yaml.safe_load(
        (root / "examples" / "synthetic" / "comparison.yaml").read_text(encoding="utf-8")
    )
    comparison = ComparisonInput.from_dict(data)
    profile = load_profile("edge-v1")
    evaluation = evaluate(comparison, profile)

    data["baseline"]["revision"] = "different-baseline-revision"
    mismatched = ComparisonInput.from_dict(data)
    with pytest.raises(InputError, match="evaluation does not match"):
        evaluation_document(evaluation, mismatched, profile)


def test_measurement_schema_rejects_nonfinite_decimal_strings() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "schemas" / "measurement.schema.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"value": "NaN", "unit": "count", "statistic": "point"}, schema)
    jsonschema.validate({"value": "1e-3", "unit": "count", "statistic": "point"}, schema)
