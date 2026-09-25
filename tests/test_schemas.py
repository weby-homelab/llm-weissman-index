from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from llm_weissman.models import ComparisonInput
from llm_weissman.profiles import load_profile
from llm_weissman.report import evaluation_document
from llm_weissman.scoring import evaluate


def test_machine_readable_schemas_are_valid_json_with_version_contracts() -> None:
    schema_dir = Path(__file__).parents[1] / "schemas"
    paths = sorted(schema_dir.glob("*.schema.json"))
    assert {path.name for path in paths} == {
        "comparison.schema.json",
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
