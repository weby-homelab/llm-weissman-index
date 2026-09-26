"""Default-deny validation for any future live benchmark policy.

LWI intentionally has no live load generator.  These objects make an eventual
integration declarative and bounded instead of accepting commands or arbitrary
Python from an input file.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from .errors import InputError
from .models import redact_untrusted
from .units import parse_decimal

_ABORT_ERROR_RATE_PATTERN = re.compile(r"^(?:0\.(?:[0-9]*[1-9][0-9]*)|1(?:\.0+)?)$")


def _mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("expected an object", code="WRONG_TYPE", path=path)
    return value


def _string(value: Any, *, field: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string", code="REQUIRED_FIELD", path=path)
    return value


def _integer(value: Any, *, field: str, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InputError(
            f"{field} must be an integer >= {minimum}", code="INVALID_LIVE_CAP", path=path
        )
    return value


def _positive_decimal(value: Any, *, field: str, path: str) -> Decimal:
    try:
        parsed = parse_decimal(value, field=path)
    except InputError as exc:
        raise InputError(str(exc), code="INVALID_LIVE_CAP", path=path) from exc
    if parsed <= 0:
        raise InputError(f"{field} must be positive", code="INVALID_LIVE_CAP", path=path)
    return parsed


def _keys(data: Mapping[str, Any], allowed: set[str], *, path: str) -> None:
    unexpected = sorted(set(data) - allowed)
    if unexpected:
        raise InputError(
            f"unexpected live policy fields: {', '.join(unexpected)}",
            code="UNEXPECTED_FIELD",
            path=path,
        )


def _validate_target(value: Any, *, path: str) -> str:
    target = _string(value, field="target", path=path)
    try:
        parsed = urlsplit(target)
        hostname = parsed.hostname
    except ValueError as exc:
        raise InputError(
            "live targets must be public, credential-free HTTPS URLs",
            code="UNSAFE_TARGET",
            path=path,
        ) from exc
    normalized_hostname = (hostname or "").rstrip(".").lower()
    private_literal = normalized_hostname == "localhost" or normalized_hostname.endswith(
        ".localhost"
    )
    if not private_literal and hostname:
        try:
            private_literal = not ip_address(hostname).is_global
        except ValueError:
            pass
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or private_literal
    ):
        raise InputError(
            "live targets must be public, credential-free HTTPS URLs",
            code="UNSAFE_TARGET",
            path=path,
        )
    return target


@dataclass(frozen=True)
class LiveBenchmarkPolicy:
    policy_version: str
    enabled: bool
    activation_mode: str
    target_allowlist: tuple[str, ...]
    authorization_statement: str
    max_concurrency: int
    max_request_rate: Decimal
    max_total_requests: int
    max_duration_seconds: Decimal
    timeout_seconds: Decimal
    abort_error_rate: Decimal
    max_estimated_cost: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        _string(self.policy_version, field="policy_version", path="$")
        if not isinstance(self.enabled, bool):
            raise InputError("enabled must be boolean", code="WRONG_TYPE", path="$.enabled")
        if self.activation_mode != "explicit":
            raise InputError(
                "live activation_mode must be explicit",
                code="LIVE_MODE_NOT_EXPLICIT",
                path="$.activation_mode",
            )
        if not self.target_allowlist:
            raise InputError(
                "target_allowlist must be a non-empty list",
                code="TARGET_ALLOWLIST_MISSING",
                path="$.target_allowlist",
            )
        for index, target in enumerate(self.target_allowlist):
            _validate_target(target, path=f"$.target_allowlist[{index}]")
        authorization = _string(
            self.authorization_statement,
            field="authorization_statement",
            path="$",
        )
        if self.enabled and authorization.lower() in {"", "none", "unknown", "unauthorized"}:
            raise InputError(
                "enabled live policy needs an authorization statement",
                code="AUTHORIZATION_MISSING",
                path="$.authorization_statement",
            )
        _integer(self.max_concurrency, field="max_concurrency", path="$")
        _positive_decimal(self.max_request_rate, field="max_request_rate", path="$")
        _integer(self.max_total_requests, field="max_total_requests", path="$")
        _positive_decimal(self.max_duration_seconds, field="max_duration_seconds", path="$")
        _positive_decimal(self.timeout_seconds, field="timeout_seconds", path="$")
        if isinstance(self.abort_error_rate, str) and not _ABORT_ERROR_RATE_PATTERN.fullmatch(
            self.abort_error_rate
        ):
            raise InputError(
                "abort_error_rate must use a decimal representation in (0, 1]",
                code="INVALID_LIVE_CAP",
                path="$.abort_error_rate",
            )
        error_rate = parse_decimal(self.abort_error_rate, field="$.abort_error_rate")
        if not (Decimal("0") < error_rate <= Decimal("1")):
            raise InputError(
                "abort_error_rate must be between 0 and 1",
                code="INVALID_LIVE_CAP",
                path="$.abort_error_rate",
            )
        if self.max_estimated_cost is not None:
            _positive_decimal(self.max_estimated_cost, field="max_estimated_cost", path="$")
            _string(self.currency, field="currency", path="$")
        elif self.currency is not None:
            _string(self.currency, field="currency", path="$")

    @classmethod
    def from_dict(cls, value: Any, *, path: str = "$") -> LiveBenchmarkPolicy:
        data = _mapping(value, path=path)
        _keys(
            data,
            {
                "policy_version",
                "enabled",
                "activation_mode",
                "target_allowlist",
                "authorization_statement",
                "max_concurrency",
                "max_request_rate",
                "max_total_requests",
                "max_duration_seconds",
                "timeout_seconds",
                "abort_error_rate",
                "max_estimated_cost",
                "currency",
            },
            path=path,
        )
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise InputError("enabled must be boolean", code="WRONG_TYPE", path=f"{path}.enabled")
        activation_mode = _string(data.get("activation_mode"), field="activation_mode", path=path)
        if activation_mode != "explicit":
            raise InputError(
                "live activation_mode must be explicit",
                code="LIVE_MODE_NOT_EXPLICIT",
                path=f"{path}.activation_mode",
            )
        targets = data.get("target_allowlist")
        if not isinstance(targets, list) or not targets:
            raise InputError(
                "target_allowlist must be a non-empty list",
                code="TARGET_ALLOWLIST_MISSING",
                path=f"{path}.target_allowlist",
            )
        normalized_targets: list[str] = []
        for index, target in enumerate(targets):
            normalized_targets.append(
                _validate_target(target, path=f"{path}.target_allowlist[{index}]")
            )
        raw_error_rate = data.get("abort_error_rate")
        if isinstance(raw_error_rate, str) and not _ABORT_ERROR_RATE_PATTERN.fullmatch(
            raw_error_rate
        ):
            raise InputError(
                "abort_error_rate must use a decimal representation in (0, 1]",
                code="INVALID_LIVE_CAP",
                path=f"{path}.abort_error_rate",
            )
        error_rate = parse_decimal(raw_error_rate, field=f"{path}.abort_error_rate")
        if not (Decimal("0") < error_rate <= Decimal("1")):
            raise InputError(
                "abort_error_rate must be between 0 and 1",
                code="INVALID_LIVE_CAP",
                path=f"{path}.abort_error_rate",
            )
        max_cost = data.get("max_estimated_cost")
        currency = data.get("currency")
        if max_cost is not None:
            max_cost = _positive_decimal(
                max_cost, field="max_estimated_cost", path=f"{path}.max_estimated_cost"
            )
            currency = _string(currency, field="currency", path=path)
        elif currency is not None:
            currency = _string(currency, field="currency", path=path)
        authorization = _string(
            data.get("authorization_statement"), field="authorization_statement", path=path
        )
        if enabled and authorization.lower() in {"", "none", "unknown", "unauthorized"}:
            raise InputError(
                "enabled live policy needs an authorization statement",
                code="AUTHORIZATION_MISSING",
                path=f"{path}.authorization_statement",
            )
        return cls(
            policy_version=_string(data.get("policy_version"), field="policy_version", path=path),
            enabled=enabled,
            activation_mode=activation_mode,
            target_allowlist=tuple(normalized_targets),
            authorization_statement=authorization,
            max_concurrency=_integer(
                data.get("max_concurrency"), field="max_concurrency", path=path
            ),
            max_request_rate=_positive_decimal(
                data.get("max_request_rate"), field="max_request_rate", path=path
            ),
            max_total_requests=_integer(
                data.get("max_total_requests"), field="max_total_requests", path=path
            ),
            max_duration_seconds=_positive_decimal(
                data.get("max_duration_seconds"), field="max_duration_seconds", path=path
            ),
            timeout_seconds=_positive_decimal(
                data.get("timeout_seconds"), field="timeout_seconds", path=path
            ),
            abort_error_rate=error_rate,
            max_estimated_cost=max_cost,
            currency=currency,
        )

    def dry_run(self, *, target: str, activate: bool = False) -> dict[str, Any]:
        """Validate requested activation and return safe caps without executing traffic."""

        if not activate:
            raise InputError(
                "live mode is default-deny; explicit activation is required",
                code="LIVE_MODE_NOT_EXPLICIT",
                path="activate",
            )
        if not self.enabled:
            raise InputError("live policy is disabled", code="LIVE_MODE_DISABLED", path="enabled")
        if target not in self.target_allowlist:
            raise InputError(
                "target is not in the live allowlist", code="TARGET_NOT_ALLOWLISTED", path="target"
            )
        return redact_untrusted(
            {
                "policy_version": self.policy_version,
                "target": target,
                "max_concurrency": self.max_concurrency,
                "max_request_rate": str(self.max_request_rate),
                "max_total_requests": self.max_total_requests,
                "max_duration_seconds": str(self.max_duration_seconds),
                "timeout_seconds": str(self.timeout_seconds),
                "abort_error_rate": str(self.abort_error_rate),
                "max_estimated_cost": (
                    str(self.max_estimated_cost) if self.max_estimated_cost is not None else None
                ),
                "currency": self.currency,
                "execution": "not performed",
            }
        )
