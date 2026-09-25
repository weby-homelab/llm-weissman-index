from __future__ import annotations

from pathlib import Path

import pytest

from llm_weissman.errors import InputError
from llm_weissman.models import ComparisonInput
from llm_weissman.profiles import load_profile
from llm_weissman.scoring import evaluate
from llm_weissman.validation import load_data_file, parse_comparison, validate_comparison


def _provenance() -> list[dict[str, str]]:
    return [
        {
            "evidence_class": "synthetic",
            "source_type": "synthetic_fixture",
            "claim_scope": "test-only",
            "retrieved_at": "2026-09-25T00:00:00Z",
        }
    ]


def _system(*, latency: str = "0.25", throughput: str = "80", quality: str = "0.96") -> dict:
    return {
        "id": "synthetic-system",
        "revision": "synthetic-1",
        "quality": [
            {
                "metric_id": "task_accuracy",
                "raw": {"value": quality, "unit": "1", "statistic": "mean", "sample_count": 100},
            }
        ],
        "metrics": {
            "latency": {"value": latency, "unit": "s", "statistic": "p50", "sample_count": 100},
            "throughput": {
                "value": throughput,
                "unit": "tokens/s",
                "statistic": "mean",
                "sample_count": 100,
            },
            "peak_memory": {"value": "2", "unit": "GiB", "statistic": "max", "sample_count": 100},
        },
        "parameters": {"status": "unknown", "claims": []},
        "provenance": _provenance(),
        "environment": {"device_class": "synthetic", "runtime": "reference"},
    }


def _comparison(candidate: dict | None = None, baseline: dict | None = None) -> dict:
    return {
        "spec_version": "0.1",
        "schema_version": "1",
        "candidate": candidate or _system(),
        "baseline": baseline or _system(),
        "workload": {
            "id": "synthetic-classification",
            "revision": "1",
            "benchmark": "synthetic",
            "benchmark_revision": "synthetic-v1",
            "task": "classification",
            "dataset_checksum": "sha256:synthetic",
            "input_token_count": 64,
            "output_token_count": 8,
        },
        "protocol": {
            "id": "synthetic-protocol",
            "version": "1",
            "measurement_statistic": "p50",
            "warmup_policy": "10 requests",
            "repeat_count": 100,
            "random_seed": 7,
            "batch_size": 1,
            "concurrency": 1,
        },
        "measurement_environment": {
            "candidate": {
                "device_class": "synthetic",
                "runtime": "reference",
                "runtime_version": "1",
                "dtype": "fp32",
                "quantization": "none",
                "batch_size": 1,
                "concurrency": 1,
                "cache_state": "cold",
                "network_inclusion": "excluded",
                "streaming": False,
            },
            "baseline": {
                "device_class": "synthetic",
                "runtime": "reference",
                "runtime_version": "1",
                "dtype": "fp32",
                "quantization": "none",
                "batch_size": 1,
                "concurrency": 1,
                "cache_state": "cold",
                "network_inclusion": "excluded",
                "streaming": False,
            },
        },
    }


def test_identical_candidate_and_baseline_score_100() -> None:
    comparison = parse_comparison(_comparison())
    evaluation = evaluate(comparison, load_profile("edge-v1"))
    assert evaluation.status == "eligible"
    assert evaluation.lwi == 100
    assert evaluation.context_id.startswith("sha256:")
    assert evaluation.result_digest.startswith("sha256:")


def test_better_lower_latency_and_higher_throughput_cannot_decrease_score() -> None:
    profile = load_profile("edge-v1")
    baseline = _system(latency="0.25", throughput="80")
    worse = evaluate(
        parse_comparison(_comparison(_system(latency="0.5", throughput="40"), baseline)), profile
    )
    better = evaluate(
        parse_comparison(_comparison(_system(latency="0.125", throughput="160"), baseline)), profile
    )
    assert worse.lwi is not None and better.lwi is not None
    assert better.lwi > worse.lwi


def test_missing_required_metric_is_incomplete_and_not_reweighted() -> None:
    candidate = _system()
    del candidate["metrics"]["peak_memory"]
    evaluation = evaluate(parse_comparison(_comparison(candidate)), load_profile("edge-v1"))
    assert evaluation.status == "incomplete"
    assert evaluation.reason == "required_metric_missing"
    assert evaluation.lwi is None


def test_environment_and_statistic_mismatches_are_structured_errors() -> None:
    data = _comparison()
    data["measurement_environment"]["baseline"]["device_class"] = "different"
    data["baseline"]["metrics"]["latency"]["statistic"] = "p95"
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    codes = {issue.code for issue in report.errors}
    assert "HARDWARE_CONTEXT_MISMATCH" in codes
    assert "STATISTIC_MISMATCH" in codes


def test_safe_loader_rejects_python_yaml_tags(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text("!!python/object/apply:os.system ['id']\n", encoding="utf-8")
    with pytest.raises(InputError, match="valid JSON/YAML"):
        load_data_file(path)


def test_unknown_unit_fails_at_model_boundary() -> None:
    data = _comparison()
    data["candidate"]["metrics"]["latency"]["unit"] = "fortnights"
    with pytest.raises(InputError, match="unknown unit"):
        ComparisonInput.from_dict(data)


def test_parameter_semantics_and_status_are_required_for_param_profile() -> None:
    data = _comparison()
    for system in (data["candidate"], data["baseline"]):
        system["metrics"] = {}
        system["parameters"] = {
            "status": "unknown",
            "total": {
                "value": "100",
                "unit": "count",
                "statistic": "point",
                "semantics": "active",
                "source": "test",
                "method": "reported",
            },
            "claims": [],
        }
    evaluation = evaluate(
        parse_comparison(_comparison(data["candidate"], data["baseline"])), load_profile("param-v1")
    )
    assert evaluation.status == "incomplete"
    codes = {issue.code for issue in evaluation.issues}
    assert "PARAMETER_SEMANTICS_MISMATCH" in codes
    assert "PARAMETER_STATUS_NOT_SCOREABLE" in codes


def test_context_id_binds_baseline_identity_and_measurements() -> None:
    profile = load_profile("edge-v1")
    first = evaluate(parse_comparison(_comparison()), profile)
    changed_baseline = _system(latency="0.75")
    second = evaluate(parse_comparison(_comparison(baseline=changed_baseline)), profile)
    assert first.context_id != second.context_id
