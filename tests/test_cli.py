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


def test_context_without_json_flag_is_human_readable() -> None:
    completed = _run("context", str(SYNTHETIC), "--profile", str(EDGE_PROFILE))
    assert completed.returncode == 0, completed.stderr
    assert "comparison context ID:" in completed.stdout
    assert completed.stdout.lstrip().startswith("comparison context ID:")
    assert not completed.stdout.lstrip().startswith("{")


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
