"""Typed, offline performance evidence primitives.

This module deliberately does not execute a benchmark client.  It validates and
derives facts from an already-preserved trace or operating-point artifact.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .errors import InputError
from .models import Measurement, redact_untrusted
from .units import DECIMAL_WORKING_PRECISION, convert, decimal_string, get_unit, parse_decimal

SCENARIOS = frozenset({"offline", "open_loop", "closed_loop"})
CACHE_STATES = frozenset({"cold", "warm", "controlled", "unknown"})
LATENCY_SEMANTICS = frozenset({"ttft", "tpot", "itl", "e2e", "queue"})
POINT_KINDS = frozenset({"observed", "derived", "interpolated"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("expected an object", code="WRONG_TYPE", path=path)
    if any(not isinstance(key, str) for key in value):
        raise InputError("object keys must be strings", code="WRONG_TYPE", path=path)
    return value


def _string(value: Any, *, field: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string", code="REQUIRED_FIELD", path=path)
    if _CONTROL_CHARACTERS.search(value):
        raise InputError(
            f"{field} contains control characters", code="CONTROL_CHARACTER", path=path
        )
    return value


def _keys(data: Mapping[str, Any], allowed: set[str], *, path: str) -> None:
    unexpected = sorted(set(data) - allowed)
    if unexpected:
        raise InputError(
            f"unexpected fields: {', '.join(unexpected)}", code="UNEXPECTED_FIELD", path=path
        )


def _count(value: Any, *, field: str, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{field} must be a non-negative integer", code="WRONG_TYPE", path=path)
    return value


def _dimensioned_measurement(
    value: Any,
    *,
    path: str,
    dimension: str,
    semantic: str | None = None,
) -> Measurement:
    measurement = Measurement.from_dict(value, path=path)
    unit = get_unit(measurement.unit)
    if unit.dimension != dimension or (semantic is not None and unit.semantic != semantic):
        raise InputError(
            f"measurement must use {dimension}/{semantic or 'any'} units",
            code="WRONG_METRIC_DIMENSION",
            path=path,
        )
    return measurement


@dataclass(frozen=True)
class SLO:
    """Per-request latency SLO thresholds, all represented in seconds."""

    thresholds: Mapping[str, Measurement]

    @classmethod
    def from_dict(cls, value: Any, *, path: str = "$.slo") -> SLO:
        data = _mapping(value, path=path)
        _keys(data, set(LATENCY_SEMANTICS), path=path)
        if not data:
            raise InputError(
                "SLO must define at least one threshold", code="INVALID_SLO", path=path
            )
        thresholds: dict[str, Measurement] = {}
        for name, raw in data.items():
            thresholds[name] = _dimensioned_measurement(
                raw,
                path=f"{path}.{name}",
                dimension="time",
                semantic="time",
            )
        return cls(thresholds=thresholds)

    def to_dict(self) -> dict[str, Any]:
        return {name: item.to_dict() for name, item in sorted(self.thresholds.items())}


@dataclass(frozen=True)
class RequestTrace:
    """One preserved request outcome used only for offline goodput derivation."""

    request_id: str
    success: bool
    timed_out: bool
    retry_count: int
    latency: Mapping[str, Measurement]

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> RequestTrace:
        data = _mapping(value, path=path)
        _keys(data, {"request_id", "success", "timed_out", "retry_count", "latency"}, path=path)
        success = data.get("success")
        timed_out = data.get("timed_out", False)
        if not isinstance(success, bool) or not isinstance(timed_out, bool):
            raise InputError("success and timed_out must be booleans", code="WRONG_TYPE", path=path)
        if success and timed_out:
            raise InputError(
                "a successful request cannot be timed out", code="INVALID_TRACE", path=path
            )
        latency_data = _mapping(data.get("latency"), path=f"{path}.latency")
        _keys(latency_data, set(LATENCY_SEMANTICS), path=f"{path}.latency")
        latency = {
            name: _dimensioned_measurement(
                item,
                path=f"{path}.latency.{name}",
                dimension="time",
                semantic="time",
            )
            for name, item in latency_data.items()
        }
        return cls(
            request_id=_string(data.get("request_id"), field="request_id", path=path),
            success=success,
            timed_out=timed_out,
            retry_count=_count(data.get("retry_count", 0), field="retry_count", path=path),
            latency=latency,
        )

    def meets_slo(self, slo: SLO) -> bool:
        if not self.success:
            return False
        for name, threshold in slo.thresholds.items():
            observed = self.latency.get(name)
            if observed is None:
                return False
            observed_seconds = convert(observed.value, observed.unit, "s")
            threshold_seconds = convert(threshold.value, threshold.unit, "s")
            if observed_seconds > threshold_seconds:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "timed_out": self.timed_out,
            "retry_count": self.retry_count,
            "latency": {
                name: measurement.to_dict() for name, measurement in sorted(self.latency.items())
            },
        }


@dataclass(frozen=True)
class GoodputResult:
    """Observed SLO-satisfying request rate derived from preserved traces."""

    measurement_duration_seconds: Decimal
    attempted_count: int
    successful_count: int
    slo_satisfied_count: int
    failed_count: int
    timed_out_count: int
    retry_count: int
    goodput: Decimal
    slo: SLO

    def to_dict(self) -> dict[str, Any]:
        return {
            "measurement_duration_seconds": decimal_string(self.measurement_duration_seconds),
            "attempted_count": self.attempted_count,
            "successful_count": self.successful_count,
            "slo_satisfied_count": self.slo_satisfied_count,
            "failed_count": self.failed_count,
            "timed_out_count": self.timed_out_count,
            "retry_count": self.retry_count,
            "goodput": decimal_string(self.goodput),
            "slo": self.slo.to_dict(),
        }


def compute_goodput(
    traces: Sequence[RequestTrace],
    measurement_duration: Measurement | Decimal | str,
    slo: SLO,
) -> GoodputResult:
    """Compute goodput without inferring missing requests or interpolating points."""

    if isinstance(measurement_duration, Measurement):
        duration = convert(measurement_duration.value, measurement_duration.unit, "s")
    else:
        duration = parse_decimal(measurement_duration, field="measurement_duration")
    if duration <= 0:
        raise InputError(
            "measurement duration must be positive",
            code="INVALID_DURATION",
            path="measurement_duration",
        )
    identifiers = [trace.request_id for trace in traces]
    if len(set(identifiers)) != len(identifiers):
        raise InputError("request IDs must be unique", code="DUPLICATE_REQUEST_ID", path="traces")
    successful = sum(trace.success for trace in traces)
    timed_out = sum(trace.timed_out for trace in traces)
    failed = len(traces) - successful
    satisfied = sum(trace.meets_slo(slo) for trace in traces)
    retries = sum(trace.retry_count for trace in traces)
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        goodput = Decimal(satisfied) / duration
    return GoodputResult(
        measurement_duration_seconds=duration,
        attempted_count=len(traces),
        successful_count=successful,
        slo_satisfied_count=satisfied,
        failed_count=failed,
        timed_out_count=timed_out,
        retry_count=retries,
        goodput=goodput,
        slo=slo,
    )


@dataclass(frozen=True)
class OperatingPoint:
    """One observed or explicitly derived point in a serving envelope."""

    point_id: str
    scenario: str
    measurement_duration: Measurement
    attempted_count: int
    successful_count: int
    failed_count: int
    timed_out_count: int
    retry_count: int
    cache_state: str
    workload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    point_kind: str = "observed"
    load_target: Measurement | None = None
    achieved_load: Measurement | None = None
    throughput: Measurement | None = None
    latency: Mapping[str, Measurement] | None = None
    goodput: Measurement | None = None
    goodput_slo: SLO | None = None
    client: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> OperatingPoint:
        data = _mapping(value, path=path)
        _keys(
            data,
            {
                "point_id",
                "scenario",
                "measurement_duration",
                "attempted_count",
                "successful_count",
                "failed_count",
                "timed_out_count",
                "retry_count",
                "cache_state",
                "workload",
                "provenance",
                "point_kind",
                "load_target",
                "achieved_load",
                "throughput",
                "latency",
                "goodput",
                "goodput_slo",
                "client",
            },
            path=path,
        )
        scenario = _string(data.get("scenario"), field="scenario", path=path)
        if scenario not in SCENARIOS:
            raise InputError("unsupported performance scenario", code="INVALID_SCENARIO", path=path)
        cache_state = _string(data.get("cache_state"), field="cache_state", path=path)
        if cache_state not in CACHE_STATES:
            raise InputError("unsupported cache state", code="INVALID_CACHE_STATE", path=path)
        point_kind = data.get("point_kind", "observed")
        if not isinstance(point_kind, str) or point_kind not in POINT_KINDS:
            raise InputError(
                "unsupported operating point kind", code="INVALID_POINT_KIND", path=path
            )
        attempted = _count(data.get("attempted_count"), field="attempted_count", path=path)
        successful = _count(data.get("successful_count"), field="successful_count", path=path)
        failed = _count(data.get("failed_count"), field="failed_count", path=path)
        timed_out = _count(data.get("timed_out_count"), field="timed_out_count", path=path)
        retries = _count(data.get("retry_count"), field="retry_count", path=path)
        if successful + failed != attempted:
            raise InputError(
                "successful and failed counts must account for attempted_count",
                code="INVALID_FAILURE_ACCOUNTING",
                path=path,
            )
        if timed_out > failed:
            raise InputError(
                "timed_out_count cannot exceed failed_count",
                code="INVALID_FAILURE_ACCOUNTING",
                path=path,
            )
        workload = _mapping(data.get("workload"), path=f"{path}.workload")
        _string(workload.get("id"), field="workload.id", path=f"{path}.workload")
        _string(workload.get("revision"), field="workload.revision", path=f"{path}.workload")
        provenance = _mapping(data.get("provenance"), path=f"{path}.provenance")
        for name in ("source_tool", "source_tool_version", "raw_artifact_digest", "evidence_class"):
            _string(provenance.get(name), field=name, path=f"{path}.provenance")
        latency_data = _mapping(data.get("latency", {}), path=f"{path}.latency")
        _keys(latency_data, set(LATENCY_SEMANTICS), path=f"{path}.latency")
        latency = {
            name: _dimensioned_measurement(
                item,
                path=f"{path}.latency.{name}",
                dimension="time",
                semantic="time",
            )
            for name, item in latency_data.items()
        }
        goodput = (
            _dimensioned_measurement(
                data["goodput"],
                path=f"{path}.goodput",
                dimension="throughput",
                semantic="requests",
            )
            if data.get("goodput") is not None
            else None
        )
        goodput_slo = (
            SLO.from_dict(data["goodput_slo"], path=f"{path}.goodput_slo")
            if data.get("goodput_slo") is not None
            else None
        )
        if goodput is not None and goodput_slo is None:
            raise InputError(
                "goodput requires its SLO configuration",
                code="GOODPUT_SLO_MISSING",
                path=path,
            )
        return cls(
            point_id=_string(data.get("point_id"), field="point_id", path=path),
            scenario=scenario,
            measurement_duration=_dimensioned_measurement(
                data.get("measurement_duration"),
                path=f"{path}.measurement_duration",
                dimension="time",
                semantic="time",
            ),
            attempted_count=attempted,
            successful_count=successful,
            failed_count=failed,
            timed_out_count=timed_out,
            retry_count=retries,
            cache_state=cache_state,
            workload=dict(workload),
            provenance=dict(provenance),
            point_kind=point_kind,
            load_target=(
                _dimensioned_measurement(
                    data["load_target"],
                    path=f"{path}.load_target",
                    dimension="throughput",
                    semantic="requests",
                )
                if data.get("load_target") is not None
                else None
            ),
            achieved_load=(
                _dimensioned_measurement(
                    data["achieved_load"],
                    path=f"{path}.achieved_load",
                    dimension="throughput",
                    semantic="requests",
                )
                if data.get("achieved_load") is not None
                else None
            ),
            throughput=(
                Measurement.from_dict(data["throughput"], path=f"{path}.throughput")
                if data.get("throughput") is not None
                else None
            ),
            latency=latency,
            goodput=goodput,
            goodput_slo=goodput_slo,
            client=(
                _mapping(data["client"], path=f"{path}.client")
                if data.get("client") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "point_id": self.point_id,
            "scenario": self.scenario,
            "measurement_duration": self.measurement_duration.to_dict(),
            "attempted_count": self.attempted_count,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "timed_out_count": self.timed_out_count,
            "retry_count": self.retry_count,
            "cache_state": self.cache_state,
            "workload": redact_untrusted(dict(self.workload)),
            "provenance": redact_untrusted(dict(self.provenance)),
            "point_kind": self.point_kind,
        }
        for name in ("load_target", "achieved_load", "throughput", "goodput"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value.to_dict()
        if self.latency is not None:
            result["latency"] = {
                name: value.to_dict() for name, value in sorted(self.latency.items())
            }
        if self.goodput_slo is not None:
            result["goodput_slo"] = self.goodput_slo.to_dict()
        if self.client is not None:
            result["client"] = redact_untrusted(dict(self.client))
        return result


@dataclass(frozen=True)
class OperatingEnvelope:
    """A protocol-bound set of preserved operating points."""

    protocol_id: str
    protocol_version: str
    scenario: str
    points: tuple[OperatingPoint, ...]
    adequacy_method: str | None = None
    minimum_observed_points: int | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str = "$.operating_envelope") -> OperatingEnvelope:
        data = _mapping(value, path=path)
        _keys(
            data,
            {
                "protocol_id",
                "protocol_version",
                "scenario",
                "points",
                "adequacy_method",
                "minimum_observed_points",
            },
            path=path,
        )
        points_data = data.get("points")
        if not isinstance(points_data, list) or not points_data:
            raise InputError(
                "operating envelope needs at least one point",
                code="OPERATING_POINTS_MISSING",
                path=path,
            )
        points = tuple(
            OperatingPoint.from_dict(item, path=f"{path}.points[{index}]")
            for index, item in enumerate(points_data)
        )
        scenario = _string(data.get("scenario"), field="scenario", path=path)
        if scenario not in SCENARIOS:
            raise InputError("unsupported performance scenario", code="INVALID_SCENARIO", path=path)
        if any(point.scenario != scenario for point in points):
            raise InputError(
                "all operating points must use the envelope scenario",
                code="SCENARIO_MISMATCH",
                path=path,
            )
        identifiers = [point.point_id for point in points]
        if len(set(identifiers)) != len(identifiers):
            raise InputError(
                "operating point IDs must be unique", code="DUPLICATE_POINT_ID", path=path
            )
        minimum = data.get("minimum_observed_points")
        if minimum is not None:
            minimum = _count(minimum, field="minimum_observed_points", path=path)
            if minimum < 1:
                raise InputError(
                    "minimum_observed_points must be positive",
                    code="INVALID_ENVELOPE_ADEQUACY",
                    path=path,
                )
        return cls(
            protocol_id=_string(data.get("protocol_id"), field="protocol_id", path=path),
            protocol_version=_string(
                data.get("protocol_version"), field="protocol_version", path=path
            ),
            scenario=scenario,
            points=points,
            adequacy_method=(
                _string(data["adequacy_method"], field="adequacy_method", path=path)
                if data.get("adequacy_method") is not None
                else None
            ),
            minimum_observed_points=minimum,
        )

    @property
    def observed_points(self) -> tuple[OperatingPoint, ...]:
        return tuple(point for point in self.points if point.point_kind == "observed")

    def max_observed_goodput(self) -> Decimal | None:
        values: list[Decimal] = []
        for point in self.observed_points:
            if point.goodput is not None:
                values.append(convert(point.goodput.value, point.goodput.unit, "requests/s"))
        return max(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "scenario": self.scenario,
            "points": [point.to_dict() for point in self.points],
        }
        if self.adequacy_method is not None:
            result["adequacy_method"] = self.adequacy_method
        if self.minimum_observed_points is not None:
            result["minimum_observed_points"] = self.minimum_observed_points
        return result


def validate_envelope_adequacy(envelope: OperatingEnvelope) -> tuple[str, ...]:
    """Return warnings; no universal point-count rule is imposed."""

    warnings: list[str] = []
    if envelope.minimum_observed_points is None or envelope.adequacy_method is None:
        warnings.append("OPERATING_ENVELOPE_ADEQUACY_UNSPECIFIED")
    elif len(envelope.observed_points) < envelope.minimum_observed_points:
        warnings.append("OPERATING_ENVELOPE_POINTS_INSUFFICIENT")
    if not envelope.observed_points:
        warnings.append("OPERATING_ENVELOPE_NO_OBSERVED_POINTS")
    if any(point.point_kind == "interpolated" for point in envelope.points):
        warnings.append("INTERPOLATED_POINT_NOT_FOR_DEFAULT_SCORING")
    return tuple(warnings)
