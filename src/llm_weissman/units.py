"""Small, explicit unit registry for comparable LWI observations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from .errors import InputError

DECIMAL_MAX_DIGITS = 100
DECIMAL_MAX_ADJUSTED_EXPONENT = 1000
DECIMAL_WORKING_PRECISION = 120


@dataclass(frozen=True)
class Unit:
    name: str
    dimension: str
    semantic: str
    factor_to_canonical: Decimal
    canonical_name: str


def _d(value: str) -> Decimal:
    return Decimal(value)


with localcontext() as _unit_context:
    _unit_context.prec = DECIMAL_WORKING_PRECISION
    _TOKENS_PER_MINUTE = Decimal("1") / Decimal("60")


_UNITS: dict[str, Unit] = {
    "1": Unit("1", "dimensionless", "ratio", _d("1"), "1"),
    "dimensionless": Unit("dimensionless", "dimensionless", "ratio", _d("1"), "1"),
    "%": Unit("%", "dimensionless", "ratio", _d("0.01"), "1"),
    "ns": Unit("ns", "time", "time", _d("1e-9"), "s"),
    "us": Unit("us", "time", "time", _d("1e-6"), "s"),
    "µs": Unit("µs", "time", "time", _d("1e-6"), "s"),
    "ms": Unit("ms", "time", "time", _d("1e-3"), "s"),
    "s": Unit("s", "time", "time", _d("1"), "s"),
    "min": Unit("min", "time", "time", _d("60"), "s"),
    "h": Unit("h", "time", "time", _d("3600"), "s"),
    "B": Unit("B", "bytes", "bytes", _d("1"), "B"),
    "KB": Unit("KB", "bytes", "bytes", _d("1000"), "B"),
    "MB": Unit("MB", "bytes", "bytes", _d("1000000"), "B"),
    "GB": Unit("GB", "bytes", "bytes", _d("1000000000"), "B"),
    "KiB": Unit("KiB", "bytes", "bytes", _d("1024"), "B"),
    "MiB": Unit("MiB", "bytes", "bytes", _d("1048576"), "B"),
    "GiB": Unit("GiB", "bytes", "bytes", _d("1073741824"), "B"),
    "J": Unit("J", "energy", "energy", _d("1"), "J"),
    "kJ": Unit("kJ", "energy", "energy", _d("1000"), "J"),
    "Wh": Unit("Wh", "energy", "energy", _d("3600"), "J"),
    "kWh": Unit("kWh", "energy", "energy", _d("3600000"), "J"),
    "W": Unit("W", "power", "power", _d("1"), "W"),
    "kW": Unit("kW", "power", "power", _d("1000"), "W"),
    "count": Unit("count", "count", "count", _d("1"), "count"),
    "tokens/s": Unit("tokens/s", "throughput", "tokens", _d("1"), "tokens/s"),
    "tokens/min": Unit("tokens/min", "throughput", "tokens", _TOKENS_PER_MINUTE, "tokens/s"),
    "requests/s": Unit("requests/s", "throughput", "requests", _d("1"), "requests/s"),
    "items/s": Unit("items/s", "throughput", "items", _d("1"), "items/s"),
    "USD": Unit("USD", "currency", "USD", _d("1"), "USD"),
    "EUR": Unit("EUR", "currency", "EUR", _d("1"), "EUR"),
    "UAH": Unit("UAH", "currency", "UAH", _d("1"), "UAH"),
}


def parse_decimal(value: Any, *, field: str = "value") -> Decimal:
    """Parse a bounded finite Decimal without accepting NaN or infinity."""

    if isinstance(value, bool) or value is None or isinstance(value, float):
        raise InputError(f"{field} must be a finite decimal", code="INVALID_NUMBER", path=field)
    if isinstance(value, str) and len(value) > DECIMAL_MAX_DIGITS:
        raise InputError(f"{field} has too many characters", code="NUMBER_TOO_LARGE", path=field)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError(
            f"{field} must be a finite decimal", code="INVALID_NUMBER", path=field
        ) from exc
    if not result.is_finite():
        raise InputError(f"{field} must be finite", code="NONFINITE_NUMBER", path=field)
    if len(result.as_tuple().digits) > DECIMAL_MAX_DIGITS:
        raise InputError(
            f"{field} has too many significant digits", code="NUMBER_TOO_LARGE", path=field
        )
    if result != 0 and abs(result.adjusted()) > DECIMAL_MAX_ADJUSTED_EXPONENT:
        raise InputError(
            f"{field} exponent is outside the supported bound", code="NUMBER_TOO_LARGE", path=field
        )
    return result


def decimal_string(value: Decimal) -> str:
    """Return a stable, non-exponential decimal representation."""

    if not value.is_finite():
        raise InputError("non-finite Decimal cannot be serialized", code="NONFINITE_NUMBER")
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def get_unit(name: str) -> Unit:
    if not isinstance(name, str) or name not in _UNITS:
        raise InputError(f"unknown unit: {name!r}", code="UNKNOWN_UNIT", path="unit")
    return _UNITS[name]


def convert(value: Decimal, unit_name: str, target_name: str) -> Decimal:
    """Convert only between units with identical dimensions and semantics."""

    source = get_unit(unit_name)
    target = get_unit(target_name)
    if (source.dimension, source.semantic) != (target.dimension, target.semantic):
        raise InputError(
            f"cannot compare {unit_name!r} with {target_name!r}: dimensions differ",
            code="WRONG_METRIC_DIMENSION",
            path="unit",
        )
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        return value * source.factor_to_canonical / target.factor_to_canonical


def canonical_value(value: Decimal, unit_name: str) -> tuple[Decimal, Unit]:
    unit = get_unit(unit_name)
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        return value * unit.factor_to_canonical, unit
