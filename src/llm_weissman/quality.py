"""Explicit quality utility transforms and weighted aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .errors import InputError
from .models import QualityObservation
from .profiles import QualityDefinition
from .units import DECIMAL_WORKING_PRECISION, convert, decimal_string


@dataclass(frozen=True)
class QualityResult:
    candidate_utilities: dict[str, Decimal]
    baseline_utilities: dict[str, Decimal]
    quality_ratio: Decimal
    candidate_aggregate: Decimal
    baseline_aggregate: Decimal
    retention: Decimal
    log_ratio: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_utilities": {
                key: decimal_string(value) for key, value in self.candidate_utilities.items()
            },
            "baseline_utilities": {
                key: decimal_string(value) for key, value in self.baseline_utilities.items()
            },
            "quality_ratio": decimal_string(self.quality_ratio),
            "candidate_aggregate": decimal_string(self.candidate_aggregate),
            "baseline_aggregate": decimal_string(self.baseline_aggregate),
            "retention": decimal_string(self.retention),
            "log_ratio": decimal_string(self.log_ratio) if self.log_ratio is not None else None,
        }


def transform_quality(observation: QualityObservation, definition: QualityDefinition) -> Decimal:
    """Apply only the transform named by the immutable profile definition."""

    if observation.metric_id != definition.metric_id:
        raise InputError("quality metric ID mismatch", code="METRIC_ID_MISMATCH")
    non_ratio_scales = {
        "interval",
        "interval_scale",
        "ordinal",
        "vendor_defined_reward",
        "elo_like",
        "custom_reward",
    }
    if definition.scale_type in non_ratio_scales and definition.utility_transform == "identity":
        raise InputError(
            f"raw {definition.scale_type} quality cannot use identity utility",
            code="QUALITY_SCALE_NOT_COMPARABLE",
        )
    raw = convert(observation.raw.value, observation.raw.unit, definition.raw_unit)
    lower, upper = definition.valid_range
    if raw < lower or raw > upper:
        raise InputError(
            f"raw quality value for {definition.metric_id!r} is outside the profile range",
            code="QUALITY_OUT_OF_RANGE",
        )
    if definition.utility_transform == "identity":
        if definition.raw_direction != "higher_is_better":
            raise InputError(
                "identity quality utility requires higher_is_better",
                code="QUALITY_TRANSFORM_INVALID",
            )
        utility = raw
    elif definition.utility_transform == "one_minus":
        if definition.raw_direction != "lower_is_better":
            raise InputError(
                "one_minus quality utility requires lower_is_better",
                code="QUALITY_TRANSFORM_INVALID",
            )
        with localcontext() as context:
            context.prec = DECIMAL_WORKING_PRECISION
            utility = Decimal("1") - raw
    elif definition.utility_transform == "reciprocal":
        if definition.raw_direction != "lower_is_better":
            raise InputError(
                "reciprocal quality utility requires lower_is_better",
                code="QUALITY_TRANSFORM_INVALID",
            )
        if raw <= 0:
            raise InputError(
                "reciprocal quality transform needs a positive raw value",
                code="QUALITY_TRANSFORM_INVALID",
            )
        with localcontext() as context:
            context.prec = DECIMAL_WORKING_PRECISION
            utility = Decimal("1") / raw
    else:
        raise InputError(
            f"unsupported utility transform: {definition.utility_transform}",
            code="QUALITY_TRANSFORM_UNSUPPORTED",
        )
    if utility < definition.utility_floor or utility > definition.utility_ceiling:
        raise InputError(
            f"utility for {definition.metric_id!r} is outside declared utility bounds",
            code="UTILITY_OUT_OF_RANGE",
        )
    return utility


def aggregate_quality(
    candidate: tuple[QualityObservation, ...],
    baseline: tuple[QualityObservation, ...],
    definitions: tuple[QualityDefinition, ...],
) -> QualityResult:
    candidate_by_id = _unique_observations(candidate, "candidate")
    baseline_by_id = _unique_observations(baseline, "baseline")
    candidate_utilities: dict[str, Decimal] = {}
    baseline_utilities: dict[str, Decimal] = {}
    for definition in definitions:
        if (
            definition.metric_id not in candidate_by_id
            or definition.metric_id not in baseline_by_id
        ):
            raise InputError(
                f"required quality metric {definition.metric_id!r} is missing",
                code="REQUIRED_METRIC_MISSING",
            )
        candidate_utilities[definition.metric_id] = transform_quality(
            candidate_by_id[definition.metric_id], definition
        )
        baseline_utilities[definition.metric_id] = transform_quality(
            baseline_by_id[definition.metric_id], definition
        )
    if any(
        definition.weight > 0 and baseline_utilities[definition.metric_id] <= 0
        for definition in definitions
    ):
        raise InputError("baseline quality utility must be positive", code="ZERO_BASELINE_UTILITY")
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        candidate_log = Decimal("0")
        baseline_log = Decimal("0")
        for definition in definitions:
            candidate_utility = candidate_utilities[definition.metric_id]
            baseline_utility = baseline_utilities[definition.metric_id]
            if definition.weight == 0:
                continue
            baseline_log += definition.weight * baseline_utility.ln()
            if candidate_utility > 0:
                candidate_log += definition.weight * candidate_utility.ln()
        baseline_aggregate = baseline_log.exp()
        if any(
            definition.weight > 0 and candidate_utilities[definition.metric_id] == 0
            for definition in definitions
        ):
            candidate_aggregate = Decimal("0")
            quality_ratio = Decimal("0")
            log_ratio = None
        else:
            candidate_aggregate = candidate_log.exp()
            quality_ratio = candidate_aggregate / baseline_aggregate
            log_ratio = quality_ratio.ln()
        retention = quality_ratio
    return QualityResult(
        candidate_utilities=candidate_utilities,
        baseline_utilities=baseline_utilities,
        quality_ratio=quality_ratio,
        candidate_aggregate=candidate_aggregate,
        baseline_aggregate=baseline_aggregate,
        retention=retention,
        log_ratio=log_ratio,
    )


def _unique_observations(
    observations: tuple[QualityObservation, ...], label: str
) -> dict[str, QualityObservation]:
    result: dict[str, QualityObservation] = {}
    for observation in observations:
        if observation.metric_id in result:
            raise InputError(
                f"duplicate quality metric {observation.metric_id!r} in {label}",
                code="DUPLICATE_METRIC_ID",
            )
        result[observation.metric_id] = observation
    return result
