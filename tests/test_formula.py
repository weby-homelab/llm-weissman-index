from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.formula import compute_lwi


def test_baseline_against_itself_is_100() -> None:
    score = compute_lwi(
        Decimal("1"),
        {"latency": Decimal("1")},
        Decimal("0.5"),
        {"latency": Decimal("0.5")},
    )
    assert score == Decimal("100")


def test_reciprocal_property_holds_for_same_context() -> None:
    forward = compute_lwi(
        Decimal("1.2"),
        {"latency": Decimal("2"), "throughput": Decimal("1.5")},
        Decimal("0.4"),
        {"latency": Decimal("0.35"), "throughput": Decimal("0.25")},
    )
    reverse = compute_lwi(
        Decimal("1") / Decimal("1.2"),
        {"latency": Decimal("0.5"), "throughput": Decimal("1") / Decimal("1.5")},
        Decimal("0.4"),
        {"latency": Decimal("0.35"), "throughput": Decimal("0.25")},
    )
    assert abs(forward * reverse - Decimal("10000")) < Decimal("1e-35")


def test_zero_quality_ratio_is_not_hidden_by_epsilon() -> None:
    with pytest.raises(InputError, match="zero quality ratio"):
        compute_lwi(
            Decimal("0"),
            {"latency": Decimal("1")},
            Decimal("0.5"),
            {"latency": Decimal("0.5")},
        )


def test_invalid_weight_sum_is_rejected() -> None:
    with pytest.raises(InputError, match="sum to 1"):
        compute_lwi(
            Decimal("1"),
            {"latency": Decimal("1")},
            Decimal("0.6"),
            {"latency": Decimal("0.6")},
        )
