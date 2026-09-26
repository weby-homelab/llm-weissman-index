"""Strict, serializable data objects for LWI input records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from .errors import InputError
from .units import decimal_string, get_unit, parse_decimal

_SENSITIVE_QUERY_NAMES = {
    "access_token",
    "access_key",
    "api_key",
    "apikey",
    "auth",
    "client_secret",
    "key",
    "password",
    "private_key",
    "secret",
    "sig",
    "signature",
    "token",
}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _normalise_key(value: str) -> str:
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return snake_case.replace("-", "_").lower()


def _escape_control_characters(value: str) -> str:
    return _CONTROL_CHARACTERS.sub(
        lambda match: f"\\x{ord(match.group(0)):02x}",
        value,
    )


def _redact_text(value: str) -> str:
    redacted = re.sub(
        r"(?i)(\b(?:authorization|proxy-authorization)\s*[=:]\s*)"
        r"(?:[a-z]+\s+)?[^\s,;&]+",
        r"\1[REDACTED]",
        value,
    )
    redacted = re.sub(
        r"(?i)(bearer\s+|(?:[a-z0-9_-]*(?:api[_-]?key|token|secret|password|auth|signature|sig)[a-z0-9_-]*)\s*[=:]\s*)[^\s,;&]+",
        r"\1[REDACTED]",
        redacted,
    )
    return _escape_control_characters(redacted)


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        port = ""
        try:
            if parsed.port is not None:
                port = f":{parsed.port}"
        except ValueError:
            return "[REDACTED_INVALID_URL]"
        netloc = f"{hostname}{port}"
        if parsed.username or parsed.password:
            netloc = f"[REDACTED]@{netloc}"
        query = urlencode(
            [
                (
                    key,
                    "[REDACTED]"
                    if key.lower() in _SENSITIVE_QUERY_NAMES
                    or any(
                        marker in key.lower()
                        for marker in ("token", "secret", "auth", "key", "password", "sig")
                    )
                    else _redact_text(item),
                )
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            ]
        )
        # Tokens embedded as key=value segments in the URL path are not
        # query parameters, but they leak the same way; redact them too.
        safe_path = _redact_text(unquote(parsed.path))
        return urlunsplit(
            (parsed.scheme, netloc, safe_path, query, _redact_text(unquote(parsed.fragment)))
        )
    except ValueError:
        return "[REDACTED_INVALID_URL]"


def _redact_source(value: str) -> str:
    return (
        _redact_url(value)
        if value.strip().lower().startswith(("http://", "https://"))
        else _redact_text(value)
    )


def redact_untrusted(value: Any) -> Any:
    """Redact credential-like mapping keys and text before report/digest output."""

    sensitive_names = _SENSITIVE_QUERY_NAMES | {
        "credential",
        "credentials",
        "refresh_token",
    }
    legitimate_token_fields = {
        "input_token_count",
        "output_token_count",
        "cached_token_count",
        "prompt_token_count",
        "completion_token_count",
    }

    def sensitive_key(key: str) -> bool:
        lowered = _normalise_key(key)
        if lowered in legitimate_token_fields:
            return False
        if lowered in sensitive_names:
            return True
        return (
            lowered in {"authorization", "auth_token", "api_token", "access_token", "refresh_token"}
            or lowered.endswith(("_secret", "_password", "_token", "_api_key"))
            or lowered.startswith(("api_key_", "secret_", "password_"))
        )

    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if sensitive_key(str(key)) else redact_untrusted(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_untrusted(item) for item in value]
    if isinstance(value, str):
        return _redact_source(value)
    return value


def _require_mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("expected an object", code="WRONG_TYPE", path=path)
    return value


def _require_string(value: Any, *, field: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string", code="REQUIRED_FIELD", path=path)
    if _CONTROL_CHARACTERS.search(value):
        raise InputError(
            f"{field} contains control characters",
            code="CONTROL_CHARACTER",
            path=path,
        )
    return value


def _optional_string(value: Any, *, field: str, path: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field=field, path=path)


def _check_keys(data: Mapping[str, Any], allowed: set[str], *, path: str) -> None:
    unexpected = sorted(set(data) - allowed)
    if unexpected:
        raise InputError(
            f"unexpected fields: {', '.join(unexpected)}", code="UNEXPECTED_FIELD", path=path
        )


_MODEL_ARTIFACT_KEYS = {
    "artifact_id",
    "revision",
    "weights_digest",
    "adapter_revision",
    "quantization",
    "dtype",
    "tokenizer",
    "tokenizer_revision",
}
_QUALITY_CONTEXT_KEYS = {
    "dataset",
    "dataset_revision",
    "split",
    "task_revision",
    "prompt_digest",
    "system_prompt_digest",
    "chat_template",
    "chat_template_revision",
    "few_shot_count",
    "few_shot_seed",
    "scorer",
    "scorer_version",
    "judge_provider",
    "judge_model",
    "judge_revision",
    "judge_prompt_digest",
    "judge_temperature",
    "judge_seed",
    "grading_epoch_count",
    "artifact_revision",
    "dtype",
    "quantization",
}
_EXECUTION_SYSTEM_KEYS = {
    "runtime",
    "runtime_version",
    "hardware",
    "device_count",
    "parallelism",
    "serving_config_digest",
    "cache_policy",
    "artifact_revision",
    "dtype",
    "quantization",
}
_IDENTITY_INTEGER_KEYS = {
    "device_count",
    "few_shot_count",
    "few_shot_seed",
    "judge_seed",
    "grading_epoch_count",
}
_IDENTITY_BOOLEAN_KEYS: set[str] = set()


def _optional_identity(
    value: Any,
    *,
    path: str,
    allowed: set[str],
    required: set[str] = frozenset(),
) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _require_mapping(value, path=path)
    _check_keys(data, allowed, path=path)
    missing = sorted(required - set(data))
    if missing:
        raise InputError(
            f"missing identity fields: {', '.join(missing)}",
            code="REQUIRED_FIELD",
            path=path,
        )
    for name, item in data.items():
        if name in _IDENTITY_INTEGER_KEYS:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise InputError(
                    f"{name} must be a non-negative integer",
                    code="WRONG_TYPE",
                    path=f"{path}.{name}",
                )
        elif name in _IDENTITY_BOOLEAN_KEYS:
            if not isinstance(item, bool):
                raise InputError(
                    f"{name} must be a boolean", code="WRONG_TYPE", path=f"{path}.{name}"
                )
        else:
            _require_string(item, field=name, path=f"{path}.{name}")
    return dict(data)


@dataclass(frozen=True)
class Measurement:
    value: Any
    unit: str
    statistic: str
    sample_count: int | None = None
    confidence_level: Any | None = None
    lower_bound: Any | None = None
    upper_bound: Any | None = None
    method: str | None = None
    seed: int | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> Measurement:
        data = _require_mapping(value, path=path)
        _check_keys(
            data,
            {
                "value",
                "unit",
                "statistic",
                "sample_count",
                "confidence_level",
                "lower_bound",
                "upper_bound",
                "method",
                "seed",
            },
            path=path,
        )
        sample_count = data.get("sample_count")
        if sample_count is not None and (
            isinstance(sample_count, bool) or not isinstance(sample_count, int)
        ):
            raise InputError(
                "sample_count must be an integer", code="WRONG_TYPE", path=f"{path}.sample_count"
            )
        if sample_count is not None and sample_count < 1:
            raise InputError(
                "sample_count must be positive", code="INVALID_SAMPLE_COUNT", path=path
            )
        seed = data.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise InputError("seed must be an integer", code="WRONG_TYPE", path=f"{path}.seed")
        if seed is not None and seed < 0:
            raise InputError("seed must be non-negative", code="INVALID_SEED", path=f"{path}.seed")
        unit = _require_string(data.get("unit"), field="unit", path=f"{path}.unit")
        get_unit(unit)
        parsed_value = parse_decimal(data.get("value"), field=f"{path}.value")
        confidence_level = (
            parse_decimal(data["confidence_level"], field=f"{path}.confidence_level")
            if data.get("confidence_level") is not None
            else None
        )
        lower_bound = (
            parse_decimal(data["lower_bound"], field=f"{path}.lower_bound")
            if data.get("lower_bound") is not None
            else None
        )
        upper_bound = (
            parse_decimal(data["upper_bound"], field=f"{path}.upper_bound")
            if data.get("upper_bound") is not None
            else None
        )
        if confidence_level is not None and not (Decimal("0") < confidence_level <= Decimal("1")):
            raise InputError(
                "confidence_level must be between 0 and 1", code="INVALID_UNCERTAINTY", path=path
            )
        if (
            lower_bound is not None
            and upper_bound is not None
            and (lower_bound > upper_bound or not (lower_bound <= parsed_value <= upper_bound))
        ):
            raise InputError(
                "uncertainty bounds must contain value in ascending order",
                code="INVALID_UNCERTAINTY",
                path=path,
            )
        return cls(
            value=parsed_value,
            unit=unit,
            statistic=_require_string(
                data.get("statistic"), field="statistic", path=f"{path}.statistic"
            ),
            sample_count=sample_count,
            confidence_level=confidence_level,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            method=_optional_string(data.get("method"), field="method", path=f"{path}.method"),
            seed=seed,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "value": decimal_string(self.value),
            "unit": self.unit,
            "statistic": self.statistic,
        }
        if self.sample_count is not None:
            result["sample_count"] = self.sample_count
        if self.confidence_level is not None:
            result["confidence_level"] = decimal_string(self.confidence_level)
        if self.lower_bound is not None:
            result["lower_bound"] = decimal_string(self.lower_bound)
        if self.upper_bound is not None:
            result["upper_bound"] = decimal_string(self.upper_bound)
        if self.method is not None:
            result["method"] = _redact_text(self.method)
        if self.seed is not None:
            result["seed"] = self.seed
        return result


@dataclass(frozen=True)
class QualityObservation:
    metric_id: str
    raw: Measurement

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> QualityObservation:
        data = _require_mapping(value, path=path)
        _check_keys(data, {"metric_id", "raw"}, path=path)
        return cls(
            metric_id=_require_string(
                data.get("metric_id"), field="metric_id", path=f"{path}.metric_id"
            ),
            raw=Measurement.from_dict(data.get("raw"), path=f"{path}.raw"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"metric_id": self.metric_id, "raw": self.raw.to_dict()}


@dataclass(frozen=True)
class ParameterObservation:
    measurement: Measurement
    semantics: str
    source: str
    method: str

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> ParameterObservation:
        data = _require_mapping(value, path=path)
        _check_keys(
            data,
            {"value", "unit", "statistic", "sample_count", "method", "seed", "semantics", "source"},
            path=path,
        )
        semantics = _require_string(
            data.get("semantics"), field="semantics", path=f"{path}.semantics"
        )
        source = _require_string(data.get("source"), field="source", path=f"{path}.source")
        method = _require_string(data.get("method"), field="method", path=f"{path}.method")
        measurement = Measurement.from_dict(
            {
                key: data[key]
                for key in ("value", "unit", "statistic", "sample_count", "seed")
                if key in data
            },
            path=path,
        )
        return cls(measurement=measurement, semantics=semantics, source=source, method=method)

    def to_dict(self) -> dict[str, Any]:
        result = self.measurement.to_dict()
        result.update(
            {
                "semantics": self.semantics,
                "source": _redact_source(self.source),
                "method": _redact_text(self.method),
            }
        )
        return result


@dataclass(frozen=True)
class ProvenanceRecord:
    evidence_class: str
    source_type: str
    claim_scope: str
    retrieved_at: str
    source_url: str | None = None
    source_title: str | None = None
    source_date: str | None = None
    model_revision: str | None = None
    benchmark_revision: str | None = None
    notes: str | None = None
    raw_log_digest: str | None = None
    config_digest: str | None = None
    environment_digest: str | None = None
    code_commit_sha: str | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> ProvenanceRecord:
        data = _require_mapping(value, path=path)
        _check_keys(
            data,
            {
                "evidence_class",
                "source_type",
                "claim_scope",
                "retrieved_at",
                "source_url",
                "source_title",
                "source_date",
                "model_revision",
                "benchmark_revision",
                "notes",
                "raw_log_digest",
                "config_digest",
                "environment_digest",
                "code_commit_sha",
            },
            path=path,
        )
        return cls(
            evidence_class=_require_string(
                data.get("evidence_class"), field="evidence_class", path=path
            ),
            source_type=_require_string(data.get("source_type"), field="source_type", path=path),
            claim_scope=_require_string(data.get("claim_scope"), field="claim_scope", path=path),
            retrieved_at=_require_string(data.get("retrieved_at"), field="retrieved_at", path=path),
            source_url=_optional_string(data.get("source_url"), field="source_url", path=path),
            source_title=_optional_string(
                data.get("source_title"), field="source_title", path=path
            ),
            source_date=_optional_string(data.get("source_date"), field="source_date", path=path),
            model_revision=_optional_string(
                data.get("model_revision"), field="model_revision", path=path
            ),
            benchmark_revision=_optional_string(
                data.get("benchmark_revision"), field="benchmark_revision", path=path
            ),
            notes=_optional_string(data.get("notes"), field="notes", path=path),
            raw_log_digest=_optional_string(
                data.get("raw_log_digest"), field="raw_log_digest", path=path
            ),
            config_digest=_optional_string(
                data.get("config_digest"), field="config_digest", path=path
            ),
            environment_digest=_optional_string(
                data.get("environment_digest"), field="environment_digest", path=path
            ),
            code_commit_sha=_optional_string(
                data.get("code_commit_sha"), field="code_commit_sha", path=path
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "evidence_class": _redact_text(self.evidence_class),
            "source_type": _redact_text(self.source_type),
            "claim_scope": _redact_text(self.claim_scope),
            "retrieved_at": _redact_text(self.retrieved_at),
        }
        for name in (
            "source_url",
            "source_title",
            "source_date",
            "model_revision",
            "benchmark_revision",
            "notes",
            "raw_log_digest",
            "config_digest",
            "environment_digest",
            "code_commit_sha",
        ):
            value = getattr(self, name)
            if value is not None:
                if name == "source_url":
                    result[name] = _redact_url(value)
                elif name == "notes" or name in {
                    "source_type",
                    "claim_scope",
                    "source_title",
                    "source_date",
                    "model_revision",
                    "benchmark_revision",
                }:
                    result[name] = _redact_text(value)
                else:
                    result[name] = _redact_text(value)
        return result


@dataclass(frozen=True)
class CostMetadata:
    pricing_timestamp: str
    pricing_source: str
    input_token_count: int
    output_token_count: int
    cached_token_count: int
    request_count: int
    retry_count: int
    failed_request_count: int
    successful_task_count: int
    timed_out_request_count: int = 0
    attempted_request_count: int | None = None
    currency: str | None = None
    total_charge: Decimal | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> CostMetadata:
        data = _require_mapping(value, path=path)
        _check_keys(
            data,
            {
                "pricing_timestamp",
                "pricing_source",
                "input_token_count",
                "output_token_count",
                "cached_token_count",
                "request_count",
                "retry_count",
                "failed_request_count",
                "successful_task_count",
                "timed_out_request_count",
                "attempted_request_count",
                "currency",
                "total_charge",
            },
            path=path,
        )
        fields: dict[str, int] = {}
        for name in (
            "input_token_count",
            "output_token_count",
            "cached_token_count",
            "request_count",
            "retry_count",
            "failed_request_count",
            "successful_task_count",
        ):
            item = data.get(name)
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise InputError(
                    f"{name} must be a non-negative integer", code="WRONG_TYPE", path=path
                )
            fields[name] = item
        for name in ("timed_out_request_count", "attempted_request_count"):
            item = data.get(name, 0 if name == "timed_out_request_count" else None)
            if item is not None and (
                isinstance(item, bool) or not isinstance(item, int) or item < 0
            ):
                raise InputError(
                    f"{name} must be a non-negative integer",
                    code="WRONG_TYPE",
                    path=path,
                )
            if item is not None:
                fields[name] = item
        if fields["successful_task_count"] < 1:
            raise InputError(
                "successful_task_count must be positive",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if fields["failed_request_count"] > fields["request_count"]:
            raise InputError(
                "failed_request_count cannot exceed request_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if (
            fields["failed_request_count"] + fields["successful_task_count"]
            > fields["request_count"]
        ):
            raise InputError(
                "failed and successful counts cannot exceed request_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if fields["successful_task_count"] > fields["request_count"]:
            raise InputError(
                "successful_task_count cannot exceed request_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if fields["cached_token_count"] > fields["input_token_count"]:
            raise InputError(
                "cached_token_count cannot exceed input_token_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if fields["timed_out_request_count"] > fields["failed_request_count"]:
            raise InputError(
                "timed_out_request_count cannot exceed failed_request_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        if (
            fields["failed_request_count"] + fields["successful_task_count"]
            != fields["request_count"]
        ):
            raise InputError(
                "successful and failed requests must account for request_count",
                code="INVALID_COST_METADATA",
                path=path,
            )
        attempted = fields.get("attempted_request_count")
        if attempted is not None and attempted < fields["request_count"] + fields["retry_count"]:
            raise InputError(
                "attempted_request_count cannot omit retries",
                code="INVALID_COST_METADATA",
                path=path,
            )
        currency = _optional_string(data.get("currency"), field="currency", path=path)
        total_charge = (
            parse_decimal(data["total_charge"], field=f"{path}.total_charge")
            if data.get("total_charge") is not None
            else None
        )
        if total_charge is not None and currency is None:
            raise InputError(
                "total_charge requires currency", code="INVALID_COST_METADATA", path=path
            )
        return cls(
            pricing_timestamp=_require_string(
                data.get("pricing_timestamp"), field="pricing_timestamp", path=path
            ),
            pricing_source=_require_string(
                data.get("pricing_source"), field="pricing_source", path=path
            ),
            **fields,
            currency=currency,
            total_charge=total_charge,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "pricing_timestamp": self.pricing_timestamp,
            "pricing_source": _redact_url(self.pricing_source)
            if self.pricing_source.startswith(("http://", "https://"))
            else _redact_text(self.pricing_source),
            "input_token_count": self.input_token_count,
            "output_token_count": self.output_token_count,
            "cached_token_count": self.cached_token_count,
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "failed_request_count": self.failed_request_count,
            "successful_task_count": self.successful_task_count,
            "timed_out_request_count": self.timed_out_request_count,
        }
        if self.attempted_request_count is not None:
            result["attempted_request_count"] = self.attempted_request_count
        if self.currency is not None:
            result["currency"] = _redact_text(self.currency)
        if self.total_charge is not None:
            result["total_charge"] = decimal_string(self.total_charge)
        return result


@dataclass(frozen=True)
class SystemRecord:
    id: str
    revision: str
    quality: tuple[QualityObservation, ...]
    metrics: Mapping[str, Measurement]
    parameters: Mapping[str, ParameterObservation]
    parameter_status: str
    parameter_claims: tuple[dict[str, Any], ...]
    provenance: tuple[ProvenanceRecord, ...]
    environment: Mapping[str, Any]
    cost_metadata: CostMetadata | None
    model_artifact: Mapping[str, Any] | None = None
    quality_context: Mapping[str, Any] | None = None
    execution_system: Mapping[str, Any] | None = None
    operating_envelope: Mapping[str, Any] | None = None
    provider: str | None = None
    model_id: str | None = None
    snapshot: str | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> SystemRecord:
        data = _require_mapping(value, path=path)
        _check_keys(
            data,
            {
                "id",
                "revision",
                "provider",
                "model_id",
                "snapshot",
                "quality",
                "metrics",
                "parameters",
                "provenance",
                "environment",
                "cost_metadata",
                "metadata",
                "model_artifact",
                "quality_context",
                "execution_system",
                "operating_envelope",
            },
            path=path,
        )
        quality_data = data.get("quality")
        if not isinstance(quality_data, list):
            raise InputError("quality must be a list", code="WRONG_TYPE", path=f"{path}.quality")
        quality = tuple(
            QualityObservation.from_dict(item, path=f"{path}.quality[{index}]")
            for index, item in enumerate(quality_data)
        )
        metric_data = _require_mapping(data.get("metrics"), path=f"{path}.metrics")
        metrics = {
            _require_string(
                metric_id, field="metric_id", path=f"{path}.metrics"
            ): Measurement.from_dict(observation, path=f"{path}.metrics.{metric_id}")
            for metric_id, observation in metric_data.items()
        }
        parameter_data = _require_mapping(data.get("parameters"), path=f"{path}.parameters")
        _check_keys(parameter_data, {"total", "active", "trainable", "status", "claims"}, path=path)
        parameters = {
            name: ParameterObservation.from_dict(
                parameter_data[name], path=f"{path}.parameters.{name}"
            )
            for name in ("total", "active", "trainable")
            if parameter_data.get(name) is not None
        }
        claims = parameter_data.get("claims", [])
        if not isinstance(claims, list):
            raise InputError("parameter claims must be a list", code="WRONG_TYPE", path=path)
        parameter_claims = tuple(
            _require_mapping(claim, path=f"{path}.parameters.claims") for claim in claims
        )
        provenance_data = data.get("provenance")
        if not isinstance(provenance_data, list) or not provenance_data:
            raise InputError(
                "provenance must be a non-empty list", code="MISSING_PROVENANCE", path=path
            )
        environment = _require_mapping(data.get("environment"), path=f"{path}.environment")
        metadata = data.get("metadata")
        if metadata is not None:
            metadata = _require_mapping(metadata, path=f"{path}.metadata")
        parameter_status = parameter_data.get("status", "unknown")
        if parameter_status not in {"verified", "reported", "disputed", "unknown"}:
            raise InputError("invalid parameter status", code="INVALID_PARAMETER_STATUS", path=path)
        return cls(
            id=_require_string(data.get("id"), field="id", path=path),
            revision=_require_string(data.get("revision"), field="revision", path=path),
            provider=_optional_string(data.get("provider"), field="provider", path=path),
            model_id=_optional_string(data.get("model_id"), field="model_id", path=path),
            snapshot=_optional_string(data.get("snapshot"), field="snapshot", path=path),
            quality=quality,
            metrics=metrics,
            parameters=parameters,
            parameter_status=parameter_status,
            parameter_claims=parameter_claims,
            provenance=tuple(
                ProvenanceRecord.from_dict(item, path=f"{path}.provenance[{index}]")
                for index, item in enumerate(provenance_data)
            ),
            environment=environment,
            cost_metadata=(
                CostMetadata.from_dict(data["cost_metadata"], path=f"{path}.cost_metadata")
                if data.get("cost_metadata") is not None
                else None
            ),
            model_artifact=_optional_identity(
                data.get("model_artifact"),
                path=f"{path}.model_artifact",
                allowed=_MODEL_ARTIFACT_KEYS,
                required={"artifact_id", "revision"},
            ),
            quality_context=_optional_identity(
                data.get("quality_context"),
                path=f"{path}.quality_context",
                allowed=_QUALITY_CONTEXT_KEYS,
            ),
            execution_system=_optional_identity(
                data.get("execution_system"),
                path=f"{path}.execution_system",
                allowed=_EXECUTION_SYSTEM_KEYS,
            ),
            operating_envelope=(
                _require_mapping(data["operating_envelope"], path=f"{path}.operating_envelope")
                if data.get("operating_envelope") is not None
                else None
            ),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "revision": self.revision,
            "quality": [item.to_dict() for item in self.quality],
            "metrics": {name: self.metrics[name].to_dict() for name in sorted(self.metrics)},
            "parameters": {
                "status": self.parameter_status,
                **{name: self.parameters[name].to_dict() for name in sorted(self.parameters)},
                "claims": redact_untrusted(list(self.parameter_claims)),
            },
            "provenance": [item.to_dict() for item in self.provenance],
            "environment": redact_untrusted(dict(self.environment)),
        }
        for name in ("provider", "model_id", "snapshot"):
            value = getattr(self, name)
            if value is not None:
                result[name] = redact_untrusted(value)
        if self.cost_metadata is not None:
            result["cost_metadata"] = self.cost_metadata.to_dict()
        for name in ("model_artifact", "quality_context", "execution_system", "operating_envelope"):
            value = getattr(self, name)
            if value is not None:
                result[name] = redact_untrusted(dict(value))
        if self.metadata is not None:
            result["metadata"] = redact_untrusted(dict(self.metadata))
        return result


@dataclass(frozen=True)
class ComparisonInput:
    spec_version: str
    schema_version: str
    candidate: SystemRecord
    baseline: SystemRecord
    workload: Mapping[str, Any]
    protocol: Mapping[str, Any]
    measurement_environment: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Any) -> ComparisonInput:
        data = _require_mapping(value, path="$")
        _check_keys(
            data,
            {
                "spec_version",
                "schema_version",
                "candidate",
                "baseline",
                "workload",
                "protocol",
                "measurement_environment",
            },
            path="$",
        )
        environment = _require_mapping(
            data.get("measurement_environment"), path="$.measurement_environment"
        )
        _check_keys(environment, {"candidate", "baseline"}, path="$.measurement_environment")
        for name in ("candidate", "baseline", "workload", "protocol"):
            if name not in data:
                raise InputError(f"{name} is required", code="REQUIRED_FIELD", path=f"$.{name}")
        return cls(
            spec_version=_require_string(
                data.get("spec_version"), field="spec_version", path="$.spec_version"
            ),
            schema_version=_require_string(
                data.get("schema_version"), field="schema_version", path="$.schema_version"
            ),
            candidate=SystemRecord.from_dict(data.get("candidate"), path="$.candidate"),
            baseline=SystemRecord.from_dict(data.get("baseline"), path="$.baseline"),
            workload=_require_mapping(data.get("workload"), path="$.workload"),
            protocol=_require_mapping(data.get("protocol"), path="$.protocol"),
            measurement_environment={
                "candidate": _require_mapping(
                    environment.get("candidate"), path="$.measurement_environment.candidate"
                ),
                "baseline": _require_mapping(
                    environment.get("baseline"), path="$.measurement_environment.baseline"
                ),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "schema_version": self.schema_version,
            "candidate": self.candidate.to_dict(),
            "baseline": self.baseline.to_dict(),
            "workload": redact_untrusted(dict(self.workload)),
            "protocol": redact_untrusted(dict(self.protocol)),
            "measurement_environment": {
                "candidate": redact_untrusted(dict(self.measurement_environment["candidate"])),
                "baseline": redact_untrusted(dict(self.measurement_environment["baseline"])),
            },
        }
