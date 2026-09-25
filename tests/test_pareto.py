from decimal import Decimal

import pytest

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


def test_incompatible_contexts_are_rejected() -> None:
    other = ParetoPoint(
        "b",
        "sha256:other",
        {"latency": Decimal("2"), "quality": Decimal("0.8")},
        {"latency": "lower_is_better", "quality": "higher_is_better"},
    )
    with pytest.raises(InputError, match="contexts"):
        pareto_dominated([_point("a", "1", "0.9"), other])
