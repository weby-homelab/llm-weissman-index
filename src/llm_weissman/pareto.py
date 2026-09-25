"""Context-bound Pareto dominance helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .errors import InputError


@dataclass(frozen=True)
class ParetoPoint:
    candidate_id: str
    context_id: str
    values: Mapping[str, Decimal]
    directions: Mapping[str, str]
    candidate_revision: str = ""

    def dominates(self, other: ParetoPoint) -> bool:
        if self.context_id != other.context_id:
            raise InputError("Pareto points have incompatible contexts", code="CONTEXT_MISMATCH")
        if set(self.values) != set(other.values) or set(self.values) != set(self.directions):
            raise InputError(
                "Pareto points have incompatible dimensions", code="METRIC_SET_MISMATCH"
            )
        if dict(self.directions) != dict(other.directions):
            raise InputError(
                "Pareto points have incompatible directions", code="DIRECTION_MISMATCH"
            )
        no_worse = True
        strictly_better = False
        for metric_id, direction in self.directions.items():
            left = self.values[metric_id]
            right = other.values[metric_id]
            if direction == "higher_is_better":
                no_worse &= left >= right
                strictly_better |= left > right
            elif direction == "lower_is_better":
                no_worse &= left <= right
                strictly_better |= left < right
            else:
                raise InputError(
                    f"invalid Pareto direction {direction!r}", code="INVALID_DIRECTION"
                )
        return no_worse and strictly_better


def pareto_dominated(points: list[ParetoPoint]) -> dict[str, bool]:
    """Return dominance flags; all points must share one comparison context."""

    if not points:
        return {}
    context_ids = {point.context_id for point in points}
    if len(context_ids) != 1:
        raise InputError("Pareto output cannot mix comparison contexts", code="CONTEXT_MISMATCH")
    identifiers = [point.candidate_id for point in points]
    if len(set(identifiers)) != len(identifiers):
        raise InputError(
            "Pareto points must have unique candidate IDs", code="DUPLICATE_CANDIDATE_ID"
        )
    result: dict[str, bool] = {}
    for point in points:
        result[point.candidate_id] = any(
            other.candidate_id != point.candidate_id and other.dominates(point) for other in points
        )
    return result
