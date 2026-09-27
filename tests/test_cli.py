from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SYNTHETIC = ROOT / "examples" / "synthetic" / "comparison.yaml"
EDGE_PROFILE = ROOT / "profiles" / "edge-v1.yaml"
GLINER = ROOT / "examples" / "gliner25-decide" / "comparison.yaml"
PARAM_PROFILE = ROOT / "profiles" / "param-v1.yaml"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "llm_weissman.cli", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_compute_json_exposes_context_and_result_digests() -> None:
    completed = _run("compute", str(SYNTHETIC), "--profile", str(EDGE_PROFILE), "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "eligible"
    assert payload["lwi"].startswith("136.6040256754395518851229935")
    assert payload["comparison_context_id"].startswith("sha256:")
    assert payload["result_digest"].startswith("sha256:")


def test_report_human_output_is_not_a_bare_score() -> None:
    completed = _run("report", str(SYNTHETIC), "--profile", str(EDGE_PROFILE))
    assert completed.returncode == 0, completed.stderr
    assert "comparison context ID:" in completed.stdout
    assert "Quality gate:" in completed.stdout
    assert "Raw metrics" in completed.stdout


def test_context_preserves_legitimate_token_counts_and_baseline_binding() -> None:
    completed = _run("context", str(SYNTHETIC), "--profile", str(EDGE_PROFILE), "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["workload"]["input_token_count"] == 128
    assert payload["workload"]["output_token_count"] == 16
    assert payload["baseline"]["measurement_digest"].startswith("sha256:")
    assert payload["baseline"]["measurement_digest_semantics"] == "normalized_public_record_v1"
    assert payload["baseline"]["raw_artifact_integrity"] == "unavailable"

    computed = _run("compute", str(SYNTHETIC), "--profile", str(EDGE_PROFILE), "--json")
    assert computed.returncode == 0, computed.stderr
    computed_payload = json.loads(computed.stdout)
    assert (
        computed_payload["measurement_digests"]["baseline"]
        == payload["baseline"]["measurement_digest"]
    )


def test_validate_wrong_typed_scenario_is_structured_error(tmp_path) -> None:
    import yaml

    data = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    data["protocol"]["scenario"] = ["open_loop"]
    path = tmp_path / "bad-scenario.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    completed = _run("validate", str(path), "--profile", str(EDGE_PROFILE), "--json")
    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["valid"] is False
    assert any(error["code"] == "INVALID_SCENARIO" for error in payload["errors"])


def test_cli_error_outputs_redact_untrusted_values(tmp_path) -> None:
    import yaml

    data = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    data["protocol"]["evidence_tier"] = "credential=validation-secret"
    data["candidate"]["provenance"][0]["evidence_class"] = "credential=class-secret"
    data["candidate"]["quality"][0]["metric_id"] = "credential=metric-secret"
    validation_path = tmp_path / "validation-secret.yaml"
    validation_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    human = _run("validate", str(validation_path), "--profile", str(EDGE_PROFILE))

    assert human.returncode == 1
    assert "validation-secret" not in human.stdout
    assert "class-secret" not in human.stdout
    assert "metric-secret" not in human.stdout
    assert "[REDACTED]" in human.stdout

    report = _run("report", str(validation_path), "--profile", str(EDGE_PROFILE))

    assert report.returncode == 3
    assert "validation-secret" not in report.stdout
    assert "class-secret" not in report.stdout
    assert "metric-secret" not in report.stdout
    assert "[REDACTED]" in report.stdout

    data["candidate"]["metrics"]["latency"]["unit"] = "private_key=unit-secret"
    parse_path = tmp_path / "parse-secret.yaml"
    parse_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    structured = _run("validate", str(parse_path), "--profile", str(EDGE_PROFILE), "--json")

    assert structured.returncode == 2
    assert "unit-secret" not in structured.stdout
    assert "[REDACTED]" in structured.stdout


def test_validate_json_redacts_scalar_versions(tmp_path) -> None:
    import yaml

    data = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    data["spec_version"] = "credential=cli-spec-secret"
    data["schema_version"] = "Authorization: Basic cli-schema-secret"
    path = tmp_path / "scalar-secrets.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    completed = _run("validate", str(path), "--profile", str(EDGE_PROFILE), "--json")

    assert completed.returncode == 1, completed.stderr
    assert "cli-spec-secret" not in completed.stdout
    assert "cli-schema-secret" not in completed.stdout
    assert "[REDACTED]" in completed.stdout


def test_pareto_output_redacts_candidate_ids(tmp_path) -> None:
    import yaml

    base = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    paths = []
    for index in range(2):
        data = yaml.safe_load(yaml.safe_dump(base))
        data["candidate"]["id"] = f"credential=pareto-secret-{index}"
        path = tmp_path / f"pareto-{index}.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        paths.append(path)

    completed = _run(
        "pareto",
        *(str(path) for path in paths),
        "--profile",
        str(EDGE_PROFILE),
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    assert "pareto-secret-0" not in completed.stdout
    assert "pareto-secret-1" not in completed.stdout
    assert "[REDACTED]" in completed.stdout
    payload = json.loads(completed.stdout)
    assert len(payload["pareto_dominated"]) == 2


def test_context_without_json_flag_is_human_readable() -> None:
    completed = _run("context", str(SYNTHETIC), "--profile", str(EDGE_PROFILE))
    assert completed.returncode == 0, completed.stderr
    assert "comparison context ID:" in completed.stdout
    assert completed.stdout.lstrip().startswith("comparison context ID:")
    assert not completed.stdout.lstrip().startswith("{")


def test_context_json_redacts_untrusted_baseline_identity(tmp_path: Path) -> None:
    import yaml

    data = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    data["baseline"]["provider"] = "https://provider.example/model?access_token=context-secret"
    data["baseline"]["model_id"] = "Authorization: Basic context-model-secret"
    path = tmp_path / "context-secrets.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    completed = _run("context", str(path), "--profile", str(EDGE_PROFILE), "--json")

    assert completed.returncode == 0, completed.stderr
    assert "context-secret" not in completed.stdout
    assert "context-model-secret" not in completed.stdout
    assert "[REDACTED]" in completed.stdout


def test_context_human_redacts_untrusted_baseline_identity(tmp_path: Path) -> None:
    import yaml

    data = yaml.safe_load(SYNTHETIC.read_text(encoding="utf-8"))
    data["baseline"]["id"] = "Authorization: Basic human-context-secret"
    data["baseline"]["revision"] = "token=human-revision-secret"
    path = tmp_path / "human-context-secrets.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    completed = _run("context", str(path), "--profile", str(EDGE_PROFILE))

    assert completed.returncode == 0, completed.stderr
    assert "human-context-secret" not in completed.stdout
    assert "human-revision-secret" not in completed.stdout
    assert "[REDACTED]" in completed.stdout


def test_gliner_case_study_is_not_leaderboard_eligible() -> None:
    completed = _run("compute", str(GLINER), "--profile", str(PARAM_PROFILE), "--json")
    assert completed.returncode == 3
    payload = json.loads(completed.stdout)
    assert payload["status"] == "incomplete"
    assert payload["lwi"] is None
    assert any(error["code"] == "PARAMETER_CLAIM_DISPUTED" for error in payload["errors"])
    assert any(error["code"] == "PARAMETER_CLAIMS_CONFLICT" for error in payload["errors"])
    assert payload["parameter_metadata"]["baseline"]["status"] == "disputed"
    assert any(
        error["code"] == "PARAMETER_CLAIM_DISPUTED" and error["path"].startswith("$.baseline")
        for error in payload["errors"]
    )
