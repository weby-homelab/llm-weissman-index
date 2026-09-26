from __future__ import annotations

from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.performance import (
    SLO,
    OperatingEnvelope,
    OperatingPoint,
    RequestTrace,
    compute_goodput,
    validate_envelope_adequacy,
)


def _measurement(value: str, unit: str = "s") -> dict[str, str]:
    return {"value": value, "unit": unit, "statistic": "point"}


def _slo() -> SLO:
    return SLO.from_dict(
        {
            "ttft": _measurement("0.100"),
            "tpot": _measurement("0.020"),
            "e2e": _measurement("0.500"),
        }
    )


def _trace(
    request_id: str,
    *,
    ttft: str = "0.050",
    tpot: str = "0.010",
    e2e: str = "0.250",
    success: bool = True,
    timed_out: bool = False,
    retry_count: int = 0,
) -> RequestTrace:
    return RequestTrace.from_dict(
        {
            "request_id": request_id,
            "success": success,
            "timed_out": timed_out,
            "retry_count": retry_count,
            "latency": {
                "ttft": _measurement(ttft),
                "tpot": _measurement(tpot),
                "e2e": _measurement(e2e),
            },
        },
        path=f"trace.{request_id}",
    )


def _point(point_id: str, *, point_kind: str = "observed", goodput: str = "10") -> dict:
    return {
        "point_id": point_id,
        "scenario": "open_loop",
        "measurement_duration": _measurement("10"),
        "attempted_count": 100,
        "successful_count": 100,
        "failed_count": 0,
        "timed_out_count": 0,
        "retry_count": 0,
        "cache_state": "controlled",
        "workload": {"id": "w", "revision": "1"},
        "provenance": {
            "source_tool": "synthetic",
            "source_tool_version": "1",
            "raw_artifact_digest": "sha256:fixture",
            "evidence_class": "synthetic",
        },
        "point_kind": point_kind,
        "goodput": {
            "value": goodput,
            "unit": "requests/s",
            "statistic": "mean",
        },
        "goodput_slo": {"e2e": _measurement("0.500")},
    }


def test_all_requests_satisfying_slo_produce_goodput() -> None:
    result = compute_goodput([_trace("a"), _trace("b")], Decimal("1"), _slo())
    assert result.slo_satisfied_count == 2
    assert result.failed_count == 0
    assert result.retry_count == 0
    assert result.goodput == Decimal("2")


@pytest.mark.parametrize(
    ("trace_kwargs", "expected_satisfied"),
    [
        ({"ttft": "0.101"}, 0),
        ({"tpot": "0.021"}, 0),
        ({"e2e": "0.501"}, 0),
        ({"success": False}, 0),
        ({"success": False, "timed_out": True}, 0),
    ],
)
def test_each_slo_or_transport_failure_is_not_goodput(
    trace_kwargs: dict[str, object], expected_satisfied: int
) -> None:
    result = compute_goodput([_trace("failed", **trace_kwargs)], Decimal("1"), _slo())
    assert result.slo_satisfied_count == expected_satisfied
    assert result.goodput == Decimal("0")


@pytest.mark.parametrize("latency", ["0", "-0.001"])
def test_request_trace_rejects_nonpositive_latency(latency: str) -> None:
    with pytest.raises(InputError, match="positive"):
        _trace("invalid", e2e=latency)


def test_operating_point_rejects_nonpositive_duration_and_wrong_throughput_unit() -> None:
    invalid_duration = _point("duration")
    invalid_duration["measurement_duration"] = _measurement("0")
    with pytest.raises(InputError, match="positive"):
        OperatingPoint.from_dict(invalid_duration, path="point")

    invalid_throughput = _point("throughput")
    invalid_throughput["throughput"] = _measurement("1", unit="tokens/s")
    with pytest.raises(InputError, match="throughput/requests"):
        OperatingPoint.from_dict(invalid_throughput, path="point")


def test_retry_then_success_is_accounted_without_hiding_retry() -> None:
    result = compute_goodput(
        [_trace("retried", retry_count=2), _trace("plain")], Decimal("2"), _slo()
    )
    assert result.successful_count == 2
    assert result.slo_satisfied_count == 2
    assert result.retry_count == 2
    assert result.goodput == Decimal("1")


def test_raw_throughput_can_increase_while_goodput_decreases() -> None:
    good = compute_goodput([_trace(str(index)) for index in range(10)], Decimal("1"), _slo())
    overloaded = compute_goodput(
        [_trace(str(index), e2e="0.600") for index in range(20)], Decimal("1"), _slo()
    )
    assert overloaded.attempted_count > good.attempted_count
    assert overloaded.goodput < good.goodput


def test_operating_envelope_uses_only_observed_goodput() -> None:
    envelope = OperatingEnvelope.from_dict(
        {
            "protocol_id": "p",
            "protocol_version": "1",
            "scenario": "open_loop",
            "adequacy_method": "fixture protocol v1",
            "minimum_observed_points": 1,
            "points": [
                _point("observed", goodput="8"),
                _point("curve", point_kind="interpolated", goodput="99"),
            ],
        }
    )
    assert envelope.max_observed_goodput() == Decimal("8")
    assert "INTERPOLATED_POINT_NOT_FOR_DEFAULT_SCORING" in validate_envelope_adequacy(envelope)


def test_envelope_rejects_mixed_scenarios_and_bad_accounting() -> None:
    invalid = _point("bad")
    invalid["successful_count"] = 90
    with pytest.raises(InputError, match="account for attempted_count"):
        OperatingPoint.from_dict(invalid, path="point")

    mixed = _point("mixed")
    mixed["scenario"] = "closed_loop"
    with pytest.raises(InputError, match="envelope scenario"):
        OperatingEnvelope.from_dict(
            {
                "protocol_id": "p",
                "protocol_version": "1",
                "scenario": "open_loop",
                "points": [_point("base"), mixed],
            }
        )


def test_duplicate_trace_ids_and_invalid_cache_state_fail_closed() -> None:
    with pytest.raises(InputError, match="unique"):
        compute_goodput([_trace("same"), _trace("same")], Decimal("1"), _slo())
    invalid = _point("cache")
    invalid["cache_state"] = "secret-warm"
    with pytest.raises(InputError, match="cache state"):
        OperatingPoint.from_dict(invalid, path="point")
