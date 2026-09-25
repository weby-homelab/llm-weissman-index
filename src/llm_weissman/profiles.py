"""Versioned LWI profile policy and built-in profile registry."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .digests import sha256_digest
from .errors import InputError
from .formula import validate_weights
from .safeio import load_yaml
from .units import decimal_string, get_unit, parse_decimal


@dataclass(frozen=True)
class QualityDefinition:
    metric_id: str
    weight: Decimal
    raw_direction: str
    scale_type: str
    raw_unit: str
    valid_range: tuple[Decimal, Decimal]
    utility_transform: str
    utility_transform_version: str
    utility_floor: Decimal
    utility_ceiling: Decimal
    source: str

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> QualityDefinition:
        if not isinstance(value, dict):
            raise InputError("quality definition must be an object", code="WRONG_TYPE", path=path)
        allowed = {
            "metric_id",
            "weight",
            "raw_direction",
            "scale_type",
            "raw_unit",
            "valid_range",
            "utility_transform",
            "utility_transform_version",
            "utility_floor",
            "utility_ceiling",
            "source",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            raise InputError(
                f"unexpected fields: {', '.join(unexpected)}", code="UNEXPECTED_FIELD", path=path
            )
        valid_range = value.get("valid_range")
        if not isinstance(valid_range, list) or len(valid_range) != 2:
            raise InputError("valid_range must contain two values", code="INVALID_RANGE", path=path)
        lower = parse_decimal(valid_range[0], field=f"{path}.valid_range[0]")
        upper = parse_decimal(valid_range[1], field=f"{path}.valid_range[1]")
        if lower > upper:
            raise InputError(
                "valid_range lower bound exceeds upper bound", code="INVALID_RANGE", path=path
            )
        raw_unit = _required_string(value.get("raw_unit"), "raw_unit", path)
        if get_unit(raw_unit).dimension != "dimensionless":
            raise InputError(
                "quality raw_unit must be dimensionless", code="WRONG_METRIC_DIMENSION", path=path
            )
        raw_direction = _required_string(value.get("raw_direction"), "raw_direction", path)
        if raw_direction not in {"higher_is_better", "lower_is_better"}:
            raise InputError("invalid raw_direction", code="INVALID_DIRECTION", path=path)
        scale_type = _required_string(value.get("scale_type"), "scale_type", path)
        known_scales = {
            "ratio_scale",
            "bounded_rate",
            "error_rate",
            "perplexity",
            "interval",
            "interval_scale",
            "ordinal",
            "vendor_defined_reward",
            "elo_like",
            "custom_reward",
        }
        if scale_type not in known_scales:
            raise InputError(
                "unsupported quality scale_type", code="QUALITY_SCALE_UNSUPPORTED", path=path
            )
        utility_floor = parse_decimal(value.get("utility_floor"), field=f"{path}.utility_floor")
        utility_ceiling = parse_decimal(
            value.get("utility_ceiling"), field=f"{path}.utility_ceiling"
        )
        if utility_floor < 0 or utility_ceiling <= utility_floor:
            raise InputError(
                "utility bounds must be positive and ordered",
                code="INVALID_UTILITY_BOUNDS",
                path=path,
            )
        utility_transform = _required_string(
            value.get("utility_transform"), "utility_transform", path
        )
        if utility_transform not in {"identity", "one_minus", "reciprocal"}:
            raise InputError(
                "unsupported utility transform", code="QUALITY_TRANSFORM_UNSUPPORTED", path=path
            )
        transform_version = _required_string(
            value.get("utility_transform_version"), "utility_transform_version", path
        )
        if transform_version != "1":
            raise InputError(
                "unsupported utility transform version",
                code="QUALITY_TRANSFORM_VERSION_UNSUPPORTED",
                path=path,
            )
        if (
            scale_type
            in {
                "interval",
                "interval_scale",
                "ordinal",
                "vendor_defined_reward",
                "elo_like",
                "custom_reward",
            }
            and utility_transform == "identity"
        ):
            raise InputError(
                "non-ratio quality cannot use identity utility",
                code="QUALITY_SCALE_NOT_COMPARABLE",
                path=path,
            )
        if utility_transform == "identity" and raw_direction != "higher_is_better":
            raise InputError(
                "identity quality utility requires higher_is_better",
                code="QUALITY_TRANSFORM_INVALID",
                path=path,
            )
        if utility_transform in {"one_minus", "reciprocal"} and raw_direction != "lower_is_better":
            raise InputError(
                "inverse quality utility requires lower_is_better",
                code="QUALITY_TRANSFORM_INVALID",
                path=path,
            )
        return cls(
            metric_id=_required_string(value.get("metric_id"), "metric_id", path),
            weight=parse_decimal(value.get("weight"), field=f"{path}.weight"),
            raw_direction=raw_direction,
            scale_type=scale_type,
            raw_unit=raw_unit,
            valid_range=(lower, upper),
            utility_transform=utility_transform,
            utility_transform_version=transform_version,
            utility_floor=utility_floor,
            utility_ceiling=utility_ceiling,
            source=_required_string(value.get("source"), "source", path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "weight": decimal_string(self.weight),
            "raw_direction": self.raw_direction,
            "scale_type": self.scale_type,
            "raw_unit": self.raw_unit,
            "valid_range": [decimal_string(item) for item in self.valid_range],
            "utility_transform": self.utility_transform,
            "utility_transform_version": self.utility_transform_version,
            "utility_floor": decimal_string(self.utility_floor),
            "utility_ceiling": decimal_string(self.utility_ceiling),
            "source": self.source,
        }


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    weight: Decimal
    direction: str
    dimension: str
    canonical_unit: str
    statistic: str
    source: str
    parameter_semantics: str | None = None

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> MetricDefinition:
        if not isinstance(value, dict):
            raise InputError("metric definition must be an object", code="WRONG_TYPE", path=path)
        allowed = {
            "metric_id",
            "weight",
            "direction",
            "dimension",
            "canonical_unit",
            "statistic",
            "source",
            "parameter_semantics",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            raise InputError(
                f"unexpected fields: {', '.join(unexpected)}", code="UNEXPECTED_FIELD", path=path
            )
        direction = _required_string(value.get("direction"), "direction", path)
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise InputError("invalid metric direction", code="INVALID_DIRECTION", path=path)
        canonical_unit = _required_string(value.get("canonical_unit"), "canonical_unit", path)
        unit = get_unit(canonical_unit)
        dimension = _required_string(value.get("dimension"), "dimension", path)
        if unit.dimension != dimension:
            raise InputError(
                "canonical unit dimension does not match profile",
                code="WRONG_METRIC_DIMENSION",
                path=path,
            )
        return cls(
            metric_id=_required_string(value.get("metric_id"), "metric_id", path),
            weight=parse_decimal(value.get("weight"), field=f"{path}.weight"),
            direction=direction,
            dimension=dimension,
            canonical_unit=canonical_unit,
            statistic=_required_string(value.get("statistic"), "statistic", path),
            source=_required_string(value.get("source"), "source", path),
            parameter_semantics=(
                _required_string(value.get("parameter_semantics"), "parameter_semantics", path)
                if value.get("parameter_semantics") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "metric_id": self.metric_id,
            "weight": decimal_string(self.weight),
            "direction": self.direction,
            "dimension": self.dimension,
            "canonical_unit": self.canonical_unit,
            "statistic": self.statistic,
            "source": self.source,
        }
        if self.parameter_semantics is not None:
            result["parameter_semantics"] = self.parameter_semantics
        return result


@dataclass(frozen=True)
class QualityGate:
    minimum_retention: Decimal

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> QualityGate:
        if not isinstance(value, dict) or set(value) != {"minimum_retention"}:
            raise InputError(
                "quality_gate must define minimum_retention only",
                code="INVALID_QUALITY_GATE",
                path=path,
            )
        threshold = parse_decimal(value["minimum_retention"], field=f"{path}.minimum_retention")
        if threshold < 0:
            raise InputError(
                "minimum_retention cannot be negative", code="INVALID_QUALITY_GATE", path=path
            )
        return cls(threshold)

    def to_dict(self) -> dict[str, Any]:
        return {"minimum_retention": decimal_string(self.minimum_retention)}


@dataclass(frozen=True)
class Profile:
    spec_version: str
    profile_id: str
    version: str
    intended_use: str
    policy_statement: str
    quality_weight: Decimal
    quality: tuple[QualityDefinition, ...]
    metrics: tuple[MetricDefinition, ...]
    quality_gate: QualityGate
    environment_comparison_keys: tuple[str, ...]
    valid_workload_assumptions: tuple[str, ...]
    known_correlations: tuple[str, ...]
    known_exclusions: tuple[str, ...]
    mode: str

    @classmethod
    def from_dict(cls, value: Any, *, path: str = "$") -> Profile:
        if not isinstance(value, dict):
            raise InputError("profile must be an object", code="WRONG_TYPE", path=path)
        if value.get("spec_version") != "0.1":
            raise InputError(
                "unsupported profile spec_version", code="SPEC_VERSION_UNSUPPORTED", path=path
            )
        if value.get("mode") not in {"parameter", "edge", "api"}:
            raise InputError("unsupported profile mode", code="PROFILE_MODE_UNSUPPORTED", path=path)
        allowed = {
            "spec_version",
            "profile_id",
            "version",
            "intended_use",
            "policy_statement",
            "weights",
            "quality",
            "metrics",
            "quality_gate",
            "environment_comparison_keys",
            "valid_workload_assumptions",
            "known_correlations",
            "known_exclusions",
            "mode",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            raise InputError(
                f"unexpected fields: {', '.join(unexpected)}", code="UNEXPECTED_FIELD", path=path
            )
        weights = value.get("weights")
        if not isinstance(weights, dict) or set(weights) != {"quality", "metrics"}:
            raise InputError(
                "weights must define quality and metrics", code="INVALID_WEIGHTS", path=path
            )
        metric_weight_data = weights.get("metrics")
        if not isinstance(metric_weight_data, dict):
            raise InputError("weights.metrics must be an object", code="INVALID_WEIGHTS", path=path)
        quality = tuple(
            QualityDefinition.from_dict(item, path=f"{path}.quality[{index}]")
            for index, item in enumerate(_required_list(value.get("quality"), "quality", path))
        )
        metrics = tuple(
            MetricDefinition.from_dict(item, path=f"{path}.metrics[{index}]")
            for index, item in enumerate(_required_list(value.get("metrics"), "metrics", path))
        )
        quality_ids = [item.metric_id for item in quality]
        metric_ids = [item.metric_id for item in metrics]
        if len(set(quality_ids)) != len(quality_ids) or len(set(metric_ids)) != len(metric_ids):
            raise InputError(
                "profile metric IDs must be unique", code="DUPLICATE_METRIC_ID", path=path
            )
        if set(metric_weight_data) != set(metric_ids):
            raise InputError(
                "weights.metrics must match metric definitions", code="INVALID_WEIGHTS", path=path
            )
        quality_weight = parse_decimal(weights["quality"], field=f"{path}.weights.quality")
        if quality_weight <= 0:
            raise InputError(
                "quality weight must be positive in v0.1",
                code="ZERO_QUALITY_WEIGHT",
                path=path,
            )
        resource_weights = {
            metric_id: parse_decimal(weight, field=f"{path}.weights.metrics.{metric_id}")
            for metric_id, weight in metric_weight_data.items()
        }
        for metric in metrics:
            if metric.weight != resource_weights[metric.metric_id]:
                raise InputError(
                    f"metric weight for {metric.metric_id!r} disagrees with weights.metrics",
                    code="INVALID_WEIGHTS",
                    path=path,
                )
        validate_weights({"quality": quality_weight, **resource_weights})
        quality_task_weights = {item.metric_id: item.weight for item in quality}
        validate_weights(quality_task_weights)
        return cls(
            spec_version=_required_string(value.get("spec_version"), "spec_version", path),
            profile_id=_required_string(value.get("profile_id"), "profile_id", path),
            version=_required_string(value.get("version"), "version", path),
            intended_use=_required_string(value.get("intended_use"), "intended_use", path),
            policy_statement=_required_string(
                value.get("policy_statement"), "policy_statement", path
            ),
            quality_weight=quality_weight,
            quality=quality,
            metrics=metrics,
            quality_gate=QualityGate.from_dict(
                value.get("quality_gate"), path=f"{path}.quality_gate"
            ),
            environment_comparison_keys=tuple(
                _required_string(item, "environment key", path)
                for item in _required_list(
                    value.get("environment_comparison_keys"), "environment_comparison_keys", path
                )
            ),
            valid_workload_assumptions=tuple(
                _required_string(item, "assumption", path)
                for item in _required_list(
                    value.get("valid_workload_assumptions"), "valid_workload_assumptions", path
                )
            ),
            known_correlations=tuple(
                _required_string(item, "correlation", path)
                for item in _required_list(
                    value.get("known_correlations"), "known_correlations", path
                )
            ),
            known_exclusions=tuple(
                _required_string(item, "exclusion", path)
                for item in _required_list(value.get("known_exclusions"), "known_exclusions", path)
            ),
            mode=_required_string(value.get("mode"), "mode", path),
        )

    @property
    def metric_by_id(self) -> dict[str, MetricDefinition]:
        return {item.metric_id: item for item in self.metrics}

    @property
    def quality_by_id(self) -> dict[str, QualityDefinition]:
        return {item.metric_id: item for item in self.quality}

    @property
    def resource_weights(self) -> dict[str, Decimal]:
        return {item.metric_id: item.weight for item in self.metrics}

    @property
    def canonical_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "profile_id": self.profile_id,
            "version": self.version,
            "intended_use": self.intended_use,
            "policy_statement": self.policy_statement,
            "weights": {
                "quality": decimal_string(self.quality_weight),
                "metrics": {item.metric_id: decimal_string(item.weight) for item in self.metrics},
            },
            "quality": [item.to_dict() for item in self.quality],
            "metrics": [item.to_dict() for item in self.metrics],
            "quality_gate": self.quality_gate.to_dict(),
            "environment_comparison_keys": list(self.environment_comparison_keys),
            "valid_workload_assumptions": list(self.valid_workload_assumptions),
            "known_correlations": list(self.known_correlations),
            "known_exclusions": list(self.known_exclusions),
            "mode": self.mode,
        }

    @property
    def digest(self) -> str:
        return sha256_digest(self.canonical_dict)


def _required_string(value: Any, name: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{name} must be a non-empty string", code="REQUIRED_FIELD", path=path)
    return value


def _required_list(value: Any, name: str, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputError(f"{name} must be a list", code="REQUIRED_FIELD", path=path)
    return value


def _profile(
    profile_id: str,
    intended_use: str,
    policy_statement: str,
    quality_weight: str,
    quality: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    metric_weights: dict[str, str],
    environment_keys: list[str],
    assumptions: list[str],
    correlations: list[str],
    exclusions: list[str],
    mode: str,
) -> dict[str, Any]:
    return {
        "spec_version": "0.1",
        "profile_id": profile_id,
        "version": "1",
        "intended_use": intended_use,
        "policy_statement": policy_statement,
        "weights": {"quality": quality_weight, "metrics": metric_weights},
        "quality": quality,
        "metrics": metrics,
        "quality_gate": {"minimum_retention": "0.95"},
        "environment_comparison_keys": environment_keys,
        "valid_workload_assumptions": assumptions,
        "known_correlations": correlations,
        "known_exclusions": exclusions,
        "mode": mode,
    }


_TASK_ACCURACY = {
    "metric_id": "task_accuracy",
    "weight": "1",
    "raw_direction": "higher_is_better",
    "scale_type": "bounded_rate",
    "raw_unit": "1",
    "valid_range": ["0", "1"],
    "utility_transform": "identity",
    "utility_transform_version": "1",
    "utility_floor": "0",
    "utility_ceiling": "1",
    "source": "LWI v0.1 policy: benchmark-defined bounded exact-match or accuracy rate.",
}


BUILTIN_PROFILE_DATA: dict[str, dict[str, Any]] = {
    "param-v1": _profile(
        "param-v1",
        "Parameter-normalized comparisons with quality and total parameter semantics.",
        "Normative project policy; not a scientific constant and not a universal model ranking.",
        "0.70",
        [_TASK_ACCURACY],
        [
            {
                "metric_id": "parameters_total",
                "weight": "0.30",
                "direction": "lower_is_better",
                "dimension": "count",
                "canonical_unit": "count",
                "statistic": "point",
                "source": "Reported or measured total parameter count with explicit semantics.",
                "parameter_semantics": "total",
            }
        ],
        {"parameters_total": "0.30"},
        [],
        [
            "The candidate and baseline total parameter claims are semantically comparable.",
            "Quality is measured on the same workload.",
        ],
        ["Parameter count is not an inference-cost proxy for every architecture."],
        [
            "Disputed parameter claims are not scoreable in param-v1.",
            "Active and trainable parameters cannot substitute for total parameters.",
        ],
        "parameter",
    ),
    "edge-v1": _profile(
        "edge-v1",
        "Local or edge inference with quality, latency, throughput, and peak memory "
        "under a matched protocol.",
        "Normative project policy; weights intentionally encode one edge deployment use case only.",
        "0.55",
        [_TASK_ACCURACY],
        [
            {
                "metric_id": "latency",
                "weight": "0.25",
                "direction": "lower_is_better",
                "dimension": "time",
                "canonical_unit": "s",
                "statistic": "p50",
                "source": "Measured request latency under the declared protocol.",
            },
            {
                "metric_id": "throughput",
                "weight": "0.10",
                "direction": "higher_is_better",
                "dimension": "throughput",
                "canonical_unit": "tokens/s",
                "statistic": "mean",
                "source": "Measured generated-token throughput with token semantics.",
            },
            {
                "metric_id": "peak_memory",
                "weight": "0.10",
                "direction": "lower_is_better",
                "dimension": "bytes",
                "canonical_unit": "B",
                "statistic": "max",
                "source": "Measured peak memory for the declared process boundary.",
            },
        ],
        {"latency": "0.25", "throughput": "0.10", "peak_memory": "0.10"},
        [
            "device_class",
            "runtime",
            "runtime_version",
            "dtype",
            "quantization",
            "batch_size",
            "concurrency",
            "cache_state",
            "network_inclusion",
            "streaming",
        ],
        [
            "The workload has stable input/output token semantics.",
            "Candidate and baseline run under the same hardware/protocol comparison keys.",
        ],
        ["Latency and throughput can correlate; both represent responsiveness and capacity."],
        [
            "Energy and cost are excluded because their boundary and pricing metadata "
            "are not assumed."
        ],
        "edge",
    ),
    "api-v1": _profile(
        "api-v1",
        "Observable hosted/API workloads that do not guess hidden internals or hardware.",
        "Normative policy; provider price and endpoint behavior are time-dependent observations.",
        "0.45",
        [_TASK_ACCURACY],
        [
            {
                "metric_id": "ttft",
                "weight": "0.20",
                "direction": "lower_is_better",
                "dimension": "time",
                "canonical_unit": "s",
                "statistic": "p95",
                "source": "Observed first-token time under the declared client/network boundary.",
            },
            {
                "metric_id": "e2e_latency",
                "weight": "0.15",
                "direction": "lower_is_better",
                "dimension": "time",
                "canonical_unit": "s",
                "statistic": "p50",
                "source": "Observed end-to-end request latency with token counts recorded.",
            },
            {
                "metric_id": "cost_per_successful_task",
                "weight": "0.15",
                "direction": "lower_is_better",
                "dimension": "currency",
                "canonical_unit": "USD",
                "statistic": "mean",
                "source": "Observed successful-task cost with pricing provenance and "
                "no silent FX conversion.",
            },
            {
                "metric_id": "throughput",
                "weight": "0.05",
                "direction": "higher_is_better",
                "dimension": "throughput",
                "canonical_unit": "tokens/s",
                "statistic": "mean",
                "source": "Observed aggregate token throughput under declared client concurrency.",
            },
        ],
        {
            "ttft": "0.20",
            "e2e_latency": "0.15",
            "cost_per_successful_task": "0.15",
            "throughput": "0.05",
        },
        [
            "client_region",
            "api_version",
            "batch_size",
            "concurrency",
            "cache_state",
            "network_inclusion",
            "streaming",
        ],
        [
            "The provider/API revision and client protocol are recorded for every result.",
            "Cost is measured per successful task, not copied from a headline token price.",
        ],
        [
            "TTFT and end-to-end latency can correlate but represent first-response "
            "and completion experience."
        ],
        [
            "Unknown parameters, provider hardware, and hidden batching are excluded "
            "rather than guessed."
        ],
        "api",
    ),
}

RELEASED_PROFILE_DIGESTS = {
    "param-v1": "sha256:7af990df9460174d02acfda0b712267447a9d5b605a4df56aeb2ceceec694a40",
    "edge-v1": "sha256:0d208ff01f225e2f86cefc6188d9ea94c589193a0075473b816c819103182f8d",
    "api-v1": "sha256:8b40ba3597b4b027ec25f724563cb0757f59ca3d56129e133f159577816f91a6",
}


def load_profile(source: str | Path) -> Profile:
    """Load a profile by path or immutable built-in identifier."""

    path = Path(source)
    if path.is_file():
        if path.stat().st_size > 256 * 1024:
            raise InputError("profile file is too large", code="INPUT_TOO_LARGE", path=str(path))
        try:
            data = load_yaml(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, UnicodeError, yaml.YAMLError) as exc:
            raise InputError(
                "profile YAML is invalid", code="INVALID_YAML", path=str(path)
            ) from exc
        profile = Profile.from_dict(data, path=str(path))
        _ensure_released_profile_integrity(profile)
        return profile
    if str(source) not in BUILTIN_PROFILE_DATA:
        raise InputError(f"unknown profile: {source}", code="UNKNOWN_PROFILE", path="profile")
    profile = Profile.from_dict(BUILTIN_PROFILE_DATA[str(source)], path=f"builtin:{source}")
    _ensure_released_profile_integrity(profile)
    return profile


def _ensure_released_profile_integrity(profile: Profile) -> None:
    pinned_digest = RELEASED_PROFILE_DIGESTS.get(profile.profile_id)
    if profile.version == "1" and pinned_digest is not None and profile.digest != pinned_digest:
        raise InputError(
            f"released profile {profile.profile_id} v{profile.version} has an unexpected digest",
            code="RELEASED_PROFILE_MUTATED",
            path="profile",
        )
    expected_data = BUILTIN_PROFILE_DATA.get(profile.profile_id)
    if expected_data is None or profile.version != "1":
        return
    expected = Profile.from_dict(expected_data, path=f"builtin:{profile.profile_id}")
    if profile.digest != expected.digest:
        raise InputError(
            f"released profile {profile.profile_id} v{profile.version} does not match "
            "its immutable digest",
            code="RELEASED_PROFILE_MUTATED",
            path="profile",
        )
