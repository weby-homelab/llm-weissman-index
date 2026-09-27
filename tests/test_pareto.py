from decimal import Decimal
from types import SimpleNamespace

import pytest

from llm_weissman.cli import _pareto_values
from llm_weissman.errors import InputError
from llm_weissman.pareto import ParetoPoint, pareto_dominated


def _point(name: str, latency: str, quality: str) -> ParetoPoint:
    return ParetoPoint(
        candidate_id=name,
        context_id="sha256:context",
        values={"latency": Decimal(latency), "quality": Decimal(quality)},
        directions={"latency": "lower_is_better", "quality": "higher_is_better"},
    )


def test_dominated_point_is_flagged_without_scalar_ranking() -> None:
    flags = pareto_dominated([_point("a", "1", "0.9"), _point("b", "2", "0.8")])
    assert flags == {"a": False, "b": True}


def test_tradeoff_points_are_not_dominated() -> None:
    flags = pareto_dominated([_point("a", "1", "0.8"), _point("b", "2", "0.9")])
    assert flags == {"a": False, "b": False}


def test_normalized_resource_ratio_treats_larger_as_better() -> None:
    fast = ParetoPoint(
        "fast",
        "sha256:context",
        {"latency": Decimal("2"), "quality": Decimal("1")},
        {"latency": "higher_is_better", "quality": "higher_is_better"},
    )
    slow = ParetoPoint(
        "slow",
        "sha256:context",
        {"latency": Decimal("1"), "quality": Decimal("1")},
        {"latency": "higher_is_better", "quality": "higher_is_better"},
    )
    assert pareto_dominated([fast, slow]) == {"fast": False, "slow": True}


def test_pareto_quality_and_resource_dimensions_are_namespaced() -> None:
    evaluation = SimpleNamespace(
        quality=SimpleNamespace(candidate_utilities={"task_accuracy": Decimal("1")}),
        resource_ratios={"quality:task_accuracy": Decimal("2")},
    )

    assert _pareto_values(evaluation) == {
        "quality:task_accuracy": Decimal("1"),
        "resource:quality:task_accuracy": Decimal("2"),
    }


def test_incompatible_contexts_are_rejected() -> None:
    other = ParetoPoint(
        "b",
        "sha256:other",
        {"latency": Decimal("2"), "quality": Decimal("0.8")},
        {"latency": "lower_is_better", "quality": "higher_is_better"},
    )
    with pytest.raises(InputError, match="contexts"):
        pareto_dominated([_point("a", "1", "0.9"), other])


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_nonfinite_pareto_values_are_rejected(value: Decimal) -> None:
    point = ParetoPoint(
        "bad",
        "sha256:context",
        {"latency": value},
        {"latency": "lower_is_better"},
    )
    with pytest.raises(InputError, match="finite|decimal"):
        pareto_dominated([point])


def test_invalid_direction_is_rejected_even_for_singleton() -> None:
    point = ParetoPoint(
        "bad",
        "sha256:context",
        {"latency": Decimal("1")},
        {"latency": "unknown"},
    )
    with pytest.raises(InputError, match="direction"):
        pareto_dominated([point])


def test_empty_pareto_dimensions_are_rejected() -> None:
    point = ParetoPoint("empty", "sha256:context", {}, {})
    with pytest.raises(InputError, match="dimension"):
        pareto_dominated([point])
