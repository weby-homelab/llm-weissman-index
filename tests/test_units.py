from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.units import convert, parse_decimal


def test_equivalent_milliseconds_and_seconds_have_identical_ratio() -> None:
    candidate_ms = convert(Decimal("250"), "ms", "s")
    baseline_ms = convert(Decimal("500"), "ms", "s")
    candidate_s = convert(Decimal("0.25"), "s", "s")
    baseline_s = convert(Decimal("0.5"), "s", "s")
    assert candidate_ms / baseline_ms == candidate_s / baseline_s


def test_decimal_parser_rejects_nonfinite_values() -> None:
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(InputError):
            parse_decimal(value)


def test_decimal_parser_bounds_huge_exponents() -> None:
    with pytest.raises(InputError, match="outside the supported bound"):
        parse_decimal("1e1001")


def test_unknown_and_wrong_dimension_units_are_rejected() -> None:
    with pytest.raises(InputError, match="unknown unit"):
        convert(Decimal("1"), "fortnights", "s")
    with pytest.raises(InputError, match="dimensions differ"):
        convert(Decimal("1"), "ms", "MB")


def test_decimal_and_binary_byte_units_are_distinct_but_controlled() -> None:
    assert convert(Decimal("1"), "MB", "B") == Decimal("1000000")
    assert convert(Decimal("1"), "MiB", "B") == Decimal("1048576")
