"""Numerically stable Decimal implementation of the LWI kernel."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext

from .errors import InputError
from .units import DECIMAL_WORKING_PRECISION, parse_decimal

WEIGHT_TOLERANCE = Decimal("1e-18")


def validate_weights(
    weights: Mapping[str, Decimal], *, tolerance: Decimal = WEIGHT_TOLERANCE
) -> None:
    if not weights:
        raise InputError("at least one weight is required", code="WEIGHT_SUM_INVALID")
    total = Decimal("0")
    for name, weight in weights.items():
        parsed = parse_decimal(weight, field=f"weight[{name}]")
        if parsed < 0:
            raise InputError(f"weight {name!r} cannot be negative", code="WEIGHT_NEGATIVE")
        total += parsed
    if abs(total - Decimal("1")) > tolerance:
        raise InputError(
            f"weights must sum to 1 within {tolerance}; got {total}",
            code="WEIGHT_SUM_INVALID",
        )


def weighted_geometric_ratio(
    ratios: Mapping[str, Decimal], weights: Mapping[str, Decimal]
) -> Decimal:
    if set(ratios) != set(weights):
        raise InputError("ratio and weight dimensions differ", code="METRIC_SET_MISMATCH")
    parsed_weights = {
        name: parse_decimal(weight, field=f"weight[{name}]") for name, weight in weights.items()
    }
    validate_weights(parsed_weights)
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        logarithm = Decimal("0")
        for name, ratio in ratios.items():
            value = parse_decimal(ratio, field=f"ratio[{name}]")
            if value <= 0:
                raise InputError(f"ratio {name!r} must be positive", code="NONPOSITIVE_RATIO")
            logarithm += parsed_weights[name] * value.ln()
        return logarithm.exp()


def compute_lwi(
    quality_ratio: Decimal,
    resource_ratios: Mapping[str, Decimal],
    quality_weight: Decimal,
    resource_weights: Mapping[str, Decimal],
) -> Decimal:
    """Compute ``100 * exp(wQ*ln(RQ) + sum(wj*ln(Rj)))``."""

    quality_ratio = parse_decimal(quality_ratio, field="quality_ratio")
    quality_weight = parse_decimal(quality_weight, field="quality_weight")
    resource_weights = {
        name: parse_decimal(value, field=f"weight[{name}]")
        for name, value in resource_weights.items()
    }
    all_weights = {"quality": quality_weight, **resource_weights}
    validate_weights(all_weights)
    if quality_ratio < 0:
        raise InputError("quality ratio cannot be negative", code="NEGATIVE_QUALITY_RATIO")
    if quality_ratio == 0:
        raise InputError(
            "zero quality ratio has no finite logarithm; caller must use the "
            "explicit zero-quality path",
            code="ZERO_QUALITY_RATIO",
        )
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        logarithm = quality_weight * quality_ratio.ln()
        for name, ratio in resource_ratios.items():
            if name not in resource_weights:
                raise InputError(
                    f"missing weight for resource {name!r}", code="METRIC_SET_MISMATCH"
                )
            ratio = parse_decimal(ratio, field=f"ratio[{name}]")
            if ratio <= 0:
                raise InputError(f"ratio {name!r} must be positive", code="NONPOSITIVE_RATIO")
            logarithm += resource_weights[name] * ratio.ln()
        if set(resource_ratios) != set(resource_weights):
            raise InputError("resource ratios and weights differ", code="METRIC_SET_MISMATCH")
        return Decimal("100") * logarithm.exp()
