from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from llm_weissman.errors import InputError
from llm_weissman.models import ComparisonInput, Measurement
from llm_weissman.profiles import load_profile
from llm_weissman.report import evaluation_document, render_report
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


def test_log_space_contributions_reconcile_to_final_score() -> None:
    evaluation = evaluate(parse_comparison(_comparison()), load_profile("edge-v1"))
    assert evaluation.lwi is not None
    assert evaluation.log_contribution_sum is not None
    assert set(evaluation.contributions) == {"quality", "latency", "throughput", "peak_memory"}
    expected = (evaluation.lwi / Decimal("100")).ln()
    assert abs(evaluation.log_contribution_sum - expected) < Decimal("1e-20")


def test_quality_context_changes_comparison_context_identity() -> None:
    profile = load_profile("edge-v1")
    first = evaluate(parse_comparison(_comparison()), profile)
    changed = _comparison()
    for system in (changed["candidate"], changed["baseline"]):
        system["quality_context"] = {
            "dataset": "synthetic-dataset",
            "dataset_revision": "1",
            "split": "test",
            "prompt_digest": "sha256:" + "a" * 64,
            "scorer": "exact-match",
            "scorer_version": "1",
            "artifact_revision": system["revision"],
        }
    second = evaluate(parse_comparison(changed), profile)
    assert first.context_id != second.context_id


def test_quality_and_execution_artifact_mismatch_is_not_scoreable() -> None:
    data = _comparison()
    for system in (data["candidate"], data["baseline"]):
        system["model_artifact"] = {
            "artifact_id": system["id"],
            "revision": system["revision"],
            "quantization": "fp16",
            "dtype": "fp16",
        }
        system["quality_context"] = {
            "artifact_revision": system["revision"],
            "quantization": "fp16",
            "dtype": "fp16",
        }
        system["execution_system"] = {
            "artifact_revision": system["revision"],
            "quantization": "int4",
            "dtype": "int4",
        }
    evaluation = evaluate(parse_comparison(data), load_profile("edge-v1"))
    assert evaluation.status == "invalid"
    assert any(issue.code == "ARTIFACT_CONTEXT_MISMATCH" for issue in evaluation.issues)


def test_parameter_sources_and_identity_urls_are_redacted_at_result_boundary() -> None:
    data = _comparison()
    for system in (data["candidate"], data["baseline"]):
        system["metrics"] = {}
        system["model_id"] = "https://model.example.test/card?access_token=id1"
        system["parameters"] = {
            "status": "reported",
            "total": {
                "value": "100",
                "unit": "count",
                "statistic": "point",
                "semantics": "total",
                "source": "https://source.example.test?api_key=src1",
                "method": "clientSecret=met1",
            },
            "claims": [],
        }
    evaluation = evaluate(parse_comparison(data), load_profile("param-v1"))
    rendered = json.dumps(
        evaluation_document(evaluation, parse_comparison(data), load_profile("param-v1"))
    )
    assert "id1" not in rendered
    assert "src1" not in rendered
    assert "met1" not in rendered
    assert "[REDACTED]" in rendered
    human = render_report(evaluation, parse_comparison(data), load_profile("param-v1"))
    assert "id1" not in human


def test_measurement_rejects_negative_seed_and_control_characters() -> None:
    with pytest.raises(InputError, match="non-negative"):
        Measurement.from_dict(
            {"value": "1", "unit": "count", "statistic": "point", "seed": -1},
            path="measurement",
        )
    with pytest.raises(InputError, match="control characters"):
        Measurement.from_dict(
            {"value": "1", "unit": "count", "statistic": "point", "method": "bad\x1b"},
            path="measurement",
        )


def test_goodput_slo_is_part_of_comparison_context_identity() -> None:
    def envelope(slo: str) -> dict:
        return {
            "protocol_id": "open-loop-fixture",
            "protocol_version": "1",
            "scenario": "open_loop",
            "points": [
                {
                    "point_id": "p1",
                    "scenario": "open_loop",
                    "measurement_duration": {
                        "value": "10",
                        "unit": "s",
                        "statistic": "point",
                    },
                    "attempted_count": 10,
                    "successful_count": 10,
                    "failed_count": 0,
                    "timed_out_count": 0,
                    "retry_count": 0,
                    "cache_state": "controlled",
                    "workload": {"id": "synthetic", "revision": "1"},
                    "provenance": {
                        "source_tool": "synthetic",
                        "source_tool_version": "1",
                        "raw_artifact_digest": "sha256:" + "a" * 64,
                        "evidence_class": "synthetic",
                    },
                    "goodput": {
                        "value": "1",
                        "unit": "requests/s",
                        "statistic": "mean",
                    },
                    "goodput_slo": {"e2e": {"value": slo, "unit": "s", "statistic": "point"}},
                }
            ],
        }

    first_data = _comparison()
    second_data = _comparison()
    for system in (first_data["candidate"], first_data["baseline"]):
        system["operating_envelope"] = envelope("0.5")
    for system in (second_data["candidate"], second_data["baseline"]):
        system["operating_envelope"] = envelope("0.6")
    profile = load_profile("edge-v1")
    first = evaluate(parse_comparison(first_data), profile)
    second = evaluate(parse_comparison(second_data), profile)
    assert first.context_id != second.context_id


def test_publication_tier_requires_scenario_and_token_provenance() -> None:
    data = _comparison()
    data["protocol"]["evidence_tier"] = "publication"
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    codes = {issue.code for issue in report.errors}
    assert "SCENARIO_MISSING" in codes
    assert "WORKLOAD_TOKEN_METADATA_MISSING" in codes


def test_tail_percentile_without_protocol_adequacy_emits_warning() -> None:
    data = _comparison()
    data["candidate"]["metrics"]["latency"]["statistic"] = "p95"
    data["baseline"]["metrics"]["latency"]["statistic"] = "p95"
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    assert any(issue.code == "PERCENTILE_ADEQUACY_UNSPECIFIED" for issue in report.warnings)


def _bound_envelope(*, slo: str = "0.5", cache_state: str = "controlled") -> dict:
    return {
        "protocol_id": "synthetic-protocol",
        "protocol_version": "1",
        "scenario": "open_loop",
        "points": [
            {
                "point_id": "p1",
                "scenario": "open_loop",
                "measurement_duration": {"value": "10", "unit": "s", "statistic": "point"},
                "attempted_count": 10,
                "successful_count": 10,
                "failed_count": 0,
                "timed_out_count": 0,
                "retry_count": 0,
                "cache_state": cache_state,
                "workload": {"id": "synthetic-classification", "revision": "1"},
                "provenance": {
                    "source_tool": "synthetic",
                    "source_tool_version": "1",
                    "raw_artifact_digest": "sha256:" + "a" * 64,
                    "evidence_class": "synthetic",
                },
                "goodput": {"value": "1", "unit": "requests/s", "statistic": "mean"},
                "goodput_slo": {"e2e": {"value": slo, "unit": "s", "statistic": "point"}},
            }
        ],
    }


def test_publication_without_envelope_is_not_scoreable() -> None:
    data = _comparison()
    data["protocol"]["evidence_tier"] = "publication"
    data["protocol"]["scenario"] = "open_loop"
    data["protocol"]["target_request_rate"] = "10"
    data["protocol"]["arrival_process"] = "poisson"
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    assert any(issue.code == "OPERATING_ENVELOPE_MISSING" for issue in report.errors)


def test_mixed_goodput_slo_across_systems_is_rejected() -> None:
    data = _comparison()
    data["candidate"]["operating_envelope"] = _bound_envelope(slo="0.5")
    data["baseline"]["operating_envelope"] = _bound_envelope(slo="0.6")
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    assert any(issue.code == "GOODPUT_SLO_MISMATCH" for issue in report.errors)


def test_mismatched_quality_contexts_are_not_comparable() -> None:
    data = _comparison()
    data["candidate"]["quality_context"] = {"dataset": "a", "split": "test"}
    data["baseline"]["quality_context"] = {"dataset": "b", "split": "test"}
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    assert any(issue.code == "QUALITY_CONTEXT_MISMATCH" for issue in report.errors)


def test_publication_requires_measured_evidence_and_artifact() -> None:
    data = _comparison()
    data["protocol"]["evidence_tier"] = "publication"
    data["protocol"]["scenario"] = "offline"
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    codes = {issue.code for issue in report.errors}
    assert "MODEL_ARTIFACT_MISSING" in codes
    assert "PUBLICATION_EVIDENCE_CLASS" in codes


def test_envelope_protocol_mismatch_is_rejected() -> None:
    data = _comparison()
    envelope = _bound_envelope()
    envelope["protocol_id"] = "other-protocol"
    data["candidate"]["operating_envelope"] = envelope
    data["baseline"]["operating_envelope"] = _bound_envelope()
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    assert any(issue.code == "ENVELOPE_PROTOCOL_MISMATCH" for issue in report.errors)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scenario", ["open_loop"]),
        ("scenario", {"open_loop": True}),
        ("cache_state", ["cold"]),
        ("cache_state", {"cold": True}),
        ("evidence_tier", ["publication"]),
        ("evidence_tier", {"publication": True}),
    ],
)
def test_wrong_typed_protocol_enums_are_structured_errors(field: str, value: object) -> None:
    data = _comparison()
    data["protocol"][field] = value
    report = validate_comparison(parse_comparison(data), load_profile("edge-v1"))
    codes = {issue.code for issue in report.errors}
    assert codes & {"INVALID_SCENARIO", "INVALID_CACHE_STATE", "INVALID_EVIDENCE_TIER"}
