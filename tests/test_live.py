from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.live import LiveBenchmarkPolicy


def _policy(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "policy_version": "1",
        "enabled": True,
        "activation_mode": "explicit",
        "target_allowlist": ["https://authorized.example.test/v1/generate"],
        "authorization_statement": "written test authorization",
        "max_concurrency": 2,
        "max_request_rate": "1.5",
        "max_total_requests": 100,
        "max_duration_seconds": "60",
        "timeout_seconds": "5",
        "abort_error_rate": "0.25",
        "max_estimated_cost": "2.00",
        "currency": "USD",
    }
    value.update(changes)
    return value


def test_live_policy_is_default_deny_and_dry_run_never_executes() -> None:
    policy = LiveBenchmarkPolicy.from_dict(_policy())
    with pytest.raises(InputError, match="explicit activation"):
        policy.dry_run(target="https://authorized.example.test/v1/generate")
    result = policy.dry_run(target="https://authorized.example.test/v1/generate", activate=True)
    assert result["execution"] == "not performed"
    assert result["max_total_requests"] == 100


def test_live_policy_rejects_non_https_or_credentialed_targets() -> None:
    for target in (
        "http://authorized.example.test/generate",
        "https://user:password@authorized.example.test/generate",
        "https://localhost/generate",
        "https://localhost./generate",
        "https://127.0.0.1/generate",
        "https://127.0.0.1./generate",
        "https://10.0.0.1./generate",
        "https://169.254.169.254./generate",
        "https://[::1]/generate",
        "https://[malformed/generate",
    ):
        with pytest.raises(InputError, match="credential-free HTTPS"):
            LiveBenchmarkPolicy.from_dict(_policy(target_allowlist=[target]))


def test_live_policy_rejects_unallowlisted_target_and_disabled_policy() -> None:
    policy = LiveBenchmarkPolicy.from_dict(_policy())
    with pytest.raises(InputError, match="allowlist"):
        policy.dry_run(target="https://other.example.test/generate", activate=True)
    disabled = LiveBenchmarkPolicy.from_dict(_policy(enabled=False))
    with pytest.raises(InputError, match="disabled"):
        disabled.dry_run(target="https://authorized.example.test/v1/generate", activate=True)


def test_enabled_policy_needs_authorization_statement() -> None:
    with pytest.raises(InputError, match="authorization statement"):
        LiveBenchmarkPolicy.from_dict(_policy(authorization_statement="unknown"))


def test_direct_policy_construction_cannot_bypass_abort_rate_bounds() -> None:
    policy = LiveBenchmarkPolicy.from_dict(_policy())

    with pytest.raises(InputError, match="abort_error_rate"):
        replace(policy, abort_error_rate=Decimal("0"))


def test_live_policy_rejects_non_explicit_activation_mode() -> None:
    with pytest.raises(InputError, match="activation_mode"):
        LiveBenchmarkPolicy.from_dict(_policy(activation_mode="automatic"))


@pytest.mark.parametrize(
    ("value", "valid"),
    [("0", False), ("-0.1", False), ("1.01", False), ("0.0001", True), ("1", True), (1, True)],
)
def test_abort_error_rate_schema_and_runtime_share_exact_bounds(value: object, valid: bool) -> None:
    import json
    from pathlib import Path

    import jsonschema

    schema = json.loads(
        (Path(__file__).parents[1] / "schemas" / "live-benchmark.schema.json").read_text(
            encoding="utf-8"
        )
    )
    policy = _policy(abort_error_rate=value)
    if valid:
        LiveBenchmarkPolicy.from_dict(policy)
        jsonschema.validate(policy, schema)
    else:
        with pytest.raises(InputError):
            LiveBenchmarkPolicy.from_dict(policy)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(policy, schema)


def test_live_schema_rejects_zero_caps_credentialed_targets_and_orphan_cost() -> None:
    import json
    from pathlib import Path

    import jsonschema

    schema = json.loads(
        (Path(__file__).parents[1] / "schemas" / "live-benchmark.schema.json").read_text(
            encoding="utf-8"
        )
    )
    base = _policy()
    jsonschema.validate(base, schema)
    for field in ("max_request_rate", "max_duration_seconds", "timeout_seconds"):
        bad = dict(base)
        bad[field] = "0"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)
    bad = dict(base)
    bad["target_allowlist"] = ["https://user:pw@example.test/generate"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
    bad = dict(base)
    del bad["currency"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
