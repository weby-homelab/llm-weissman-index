"""Safe parsing and semantic validation for untrusted comparison records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import InputError
from .models import ComparisonInput, Measurement, SystemRecord
from .performance import CACHE_STATES, SCENARIOS, OperatingEnvelope, validate_envelope_adequacy
from .profiles import MetricDefinition, Profile
from .provenance import provenance_issues
from .safeio import DuplicateKeyError, load_json, load_yaml
from .units import canonical_value, convert, decimal_string, get_unit, parse_decimal

MAX_INPUT_BYTES = 5 * 1024 * 1024
SUPPORTED_SPEC_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSION = "1"
EVIDENCE_TIERS = {"fixture", "smoke", "publication"}
TAIL_STATISTICS = {"p90", "p95", "p99"}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    path: str = "$"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.ok,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


def load_data_file(path: str | Path) -> dict[str, Any]:
    """Load bounded JSON/YAML with a safe YAML constructor and no execution."""

    file_path = Path(path)
    if not file_path.is_file():
        raise InputError(
            f"input file does not exist: {file_path}", code="FILE_NOT_FOUND", path=str(file_path)
        )
    if file_path.stat().st_size > MAX_INPUT_BYTES:
        raise InputError("input file is too large", code="INPUT_TOO_LARGE", path=str(file_path))
    try:
        raw = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputError(
            "input file cannot be read", code="FILE_READ_ERROR", path=str(file_path)
        ) from exc
    try:
        data = load_json(raw) if file_path.suffix.lower() == ".json" else load_yaml(raw)
    except (
        DuplicateKeyError,
        ValueError,
        UnicodeError,
        RecursionError,
        TypeError,
        yaml.YAMLError,
    ) as exc:
        raise InputError(
            "input is not valid JSON/YAML", code="INVALID_SYNTAX", path=str(file_path)
        ) from exc
    if not isinstance(data, dict):
        raise InputError("input root must be an object", code="WRONG_TYPE", path=str(file_path))
    return data


def parse_comparison(data: dict[str, Any]) -> ComparisonInput:
    return ComparisonInput.from_dict(data)


def validate_comparison(comparison: ComparisonInput, profile: Profile) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if comparison.spec_version != SUPPORTED_SPEC_VERSION:
        issues.append(
            ValidationIssue(
                "SPEC_VERSION_UNSUPPORTED", "error", "unsupported spec_version", "$.spec_version"
            )
        )
    if comparison.schema_version != SUPPORTED_SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "SCHEMA_VERSION_UNSUPPORTED",
                "error",
                "unsupported schema_version",
                "$.schema_version",
            )
        )
    _validate_workload(comparison.workload, comparison.protocol, profile, issues)
    _validate_protocol(comparison.protocol, profile, issues)
    _validate_system(comparison.candidate, "candidate", profile, issues)
    _validate_system(comparison.baseline, "baseline", profile, issues)
    _validate_environment(comparison, profile, issues)
    _validate_metric_sets(comparison, profile, issues)
    _validate_provenance(comparison.candidate, "candidate", issues)
    _validate_provenance(comparison.baseline, "baseline", issues)
    _validate_evidence_class_consistency(comparison, issues)
    _validate_revision_bindings(comparison, issues)
    _validate_quality_context_compatibility(comparison, issues)
    _validate_envelope_compatibility(comparison, profile, issues)
    _validate_publication_evidence(comparison, profile, issues)
    return ValidationReport(tuple(issues))


def _validate_workload(
    workload: dict[str, Any],
    protocol: dict[str, Any],
    profile: Profile,
    issues: list[ValidationIssue],
) -> None:
    required = {"id", "revision", "benchmark", "task"}
    _require_string_keys(workload, required, "$.workload", issues)
    checksum = workload.get("dataset_checksum")
    if not isinstance(checksum, str) or not checksum.strip():
        issues.append(
            ValidationIssue(
                "DATASET_CHECKSUM_MISSING",
                "error",
                "dataset checksum is required for a scoreable workload",
                "$.workload",
            )
        )
    if profile.mode != "parameter":
        for key in ("input_token_count", "output_token_count"):
            value = workload.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                issues.append(
                    ValidationIssue(
                        "TOKEN_COUNT_MISSING",
                        "error",
                        f"{key} is required for performance profiles",
                        "$.workload",
                    )
                )
        for key in ("token_count_method", "tokenizer", "tokenizer_revision"):
            if key not in workload:
                issues.append(
                    ValidationIssue(
                        "WORKLOAD_TOKEN_METADATA_MISSING",
                        "error" if protocol.get("evidence_tier") == "publication" else "warning",
                        f"{key} is not recorded for a performance workload",
                        "$.workload",
                    )
                )


def _validate_protocol(
    protocol: dict[str, Any], profile: Profile, issues: list[ValidationIssue]
) -> None:
    required = {
        "id",
        "version",
        "measurement_statistic",
        "warmup_policy",
        "repeat_count",
        "batch_size",
        "concurrency",
    }
    _require_string_keys(
        protocol, {"id", "version", "measurement_statistic", "warmup_policy"}, "$.protocol", issues
    )
    for name in ("repeat_count", "batch_size", "concurrency"):
        value = protocol.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            issues.append(
                ValidationIssue(
                    "PROTOCOL_FIELD_INVALID",
                    "error",
                    f"{name} must be a positive integer",
                    "$.protocol",
                )
            )
    if (
        profile.mode != "parameter"
        and isinstance(protocol.get("repeat_count"), int)
        and protocol["repeat_count"] < 2
    ):
        issues.append(
            ValidationIssue(
                "REPEAT_COUNT_TOO_SMALL",
                "error",
                "performance profiles require at least two repeated observations",
                "$.protocol.repeat_count",
            )
        )
    if "random_seed" not in protocol:
        issues.append(
            ValidationIssue(
                "RANDOM_SEED_MISSING",
                "error",
                "all profiles require an explicit random_seed",
                "$.protocol",
            )
        )
    else:
        seed = protocol.get("random_seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            issues.append(
                ValidationIssue(
                    "RANDOM_SEED_INVALID",
                    "error",
                    "random_seed must be a non-negative integer",
                    "$.protocol.random_seed",
                )
            )
    missing = sorted(required - set(protocol))
    if missing:
        issues.append(
            ValidationIssue(
                "PROTOCOL_FIELD_MISSING",
                "error",
                f"missing protocol fields: {', '.join(missing)}",
                "$.protocol",
            )
        )
    evidence_tier = protocol.get("evidence_tier")
    if evidence_tier is not None and (
        not isinstance(evidence_tier, str) or evidence_tier not in EVIDENCE_TIERS
    ):
        issues.append(
            ValidationIssue(
                "INVALID_EVIDENCE_TIER",
                "error",
                f"unsupported evidence_tier {evidence_tier!r}",
                "$.protocol.evidence_tier",
            )
        )
    if profile.mode != "parameter":
        scenario = protocol.get("scenario")
        if scenario is None:
            issues.append(
                ValidationIssue(
                    "SCENARIO_MISSING",
                    "error" if evidence_tier == "publication" else "warning",
                    "performance protocol must declare offline, open_loop, or closed_loop",
                    "$.protocol.scenario",
                )
            )
        elif not isinstance(scenario, str) or scenario not in SCENARIOS:
            issues.append(
                ValidationIssue(
                    "INVALID_SCENARIO",
                    "error",
                    "scenario must be offline, open_loop, or closed_loop",
                    "$.protocol.scenario",
                )
            )
        if "cache_state" in protocol and (
            not isinstance(protocol["cache_state"], str)
            or protocol["cache_state"] not in CACHE_STATES
        ):
            issues.append(
                ValidationIssue(
                    "INVALID_CACHE_STATE",
                    "error",
                    "cache_state must be cold, warm, controlled, or unknown",
                    "$.protocol.cache_state",
                )
            )
        if evidence_tier == "publication" and scenario == "open_loop":
            _require_positive_protocol_field("target_request_rate", protocol, issues)
            _require_protocol_field("arrival_process", protocol, issues)
        if evidence_tier == "publication" and scenario == "closed_loop":
            _require_positive_protocol_field("target_concurrency", protocol, issues)
        percentile_policy = protocol.get("percentile_min_samples")
        if percentile_policy is not None:
            if not isinstance(percentile_policy, dict):
                issues.append(
                    ValidationIssue(
                        "INVALID_PERCENTILE_POLICY",
                        "error",
                        "percentile_min_samples must be an object",
                        "$.protocol.percentile_min_samples",
                    )
                )
            else:
                for statistic, minimum in percentile_policy.items():
                    if statistic not in TAIL_STATISTICS or (
                        isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1
                    ):
                        issues.append(
                            ValidationIssue(
                                "INVALID_PERCENTILE_POLICY",
                                "error",
                                "percentile policy keys/values are invalid",
                                "$.protocol.percentile_min_samples",
                            )
                        )


def _validate_system(
    system: SystemRecord, label: str, profile: Profile, issues: list[ValidationIssue]
) -> None:
    if profile.mode == "api" and (not system.provider or not system.model_id):
        issues.append(
            ValidationIssue(
                "API_IDENTITY_MISSING",
                "error",
                "API profile requires provider and model_id",
                f"$.{label}",
            )
        )
    if profile.mode == "api" and not system.snapshot:
        issues.append(
            ValidationIssue(
                "MODEL_SNAPSHOT_MISSING",
                "warning",
                "API snapshot/version is unavailable",
                f"$.{label}",
            )
        )
    revision_text = system.revision.strip().lower()
    if any(
        marker in revision_text
        for marker in ("unknown", "unavailable", "not-provided", "not provided", "missing")
    ):
        issues.append(
            ValidationIssue(
                "MODEL_REVISION_MISSING",
                "error",
                "candidate/baseline model revision is unavailable",
                f"$.{label}.revision",
            )
        )
    for record_index, record in enumerate(system.provenance):
        for code, severity, message in provenance_issues(
            record, path=f"$.{label}.provenance[{record_index}]"
        ):
            issues.append(
                ValidationIssue(code, severity, message, f"$.{label}.provenance[{record_index}]")
            )
    _validate_parameter_claims(system, label, issues, strict=profile.mode == "parameter")
    _validate_identity_bindings(system, label, issues)
    _validate_operating_envelope(system, label, profile, issues)


def _validate_environment(
    comparison: ComparisonInput, profile: Profile, issues: list[ValidationIssue]
) -> None:
    candidate = comparison.measurement_environment["candidate"]
    baseline = comparison.measurement_environment["baseline"]
    for key in profile.environment_comparison_keys:
        if key not in candidate or key not in baseline:
            issues.append(
                ValidationIssue(
                    "ENVIRONMENT_CONTEXT_MISSING",
                    "error",
                    f"missing environment key {key!r}",
                    "$.measurement_environment",
                )
            )
        elif candidate[key] != baseline[key]:
            code = (
                "HARDWARE_CONTEXT_MISMATCH"
                if key in {"device_class", "device"}
                else "PROTOCOL_CONTEXT_MISMATCH"
            )
            issues.append(
                ValidationIssue(
                    code,
                    "error",
                    f"candidate and baseline differ for {key!r}",
                    "$.measurement_environment",
                )
            )
    for label, system in (("candidate", comparison.candidate), ("baseline", comparison.baseline)):
        declared = system.environment
        observed = comparison.measurement_environment[label]
        for key in profile.environment_comparison_keys:
            if key in declared and key in observed and declared[key] != observed[key]:
                issues.append(
                    ValidationIssue(
                        "ENVIRONMENT_DUPLICATE_MISMATCH",
                        "error",
                        f"{label} system.environment disagrees with "
                        f"measurement_environment for {key!r}",
                        f"$.{label}.environment",
                    )
                )
    protocol_cache_state = comparison.protocol.get("cache_state")
    if isinstance(protocol_cache_state, str) and protocol_cache_state in CACHE_STATES:
        for label in ("candidate", "baseline"):
            environment_cache_state = comparison.measurement_environment[label].get("cache_state")
            if (
                environment_cache_state is not None
                and environment_cache_state != protocol_cache_state
            ):
                issues.append(
                    ValidationIssue(
                        "PROTOCOL_ENVIRONMENT_MISMATCH",
                        "error",
                        f"{label} cache_state disagrees with protocol",
                        f"$.measurement_environment.{label}",
                    )
                )


def _validate_metric_sets(
    comparison: ComparisonInput, profile: Profile, issues: list[ValidationIssue]
) -> None:
    quality_ids = set(profile.quality_by_id)
    for label, system in (("candidate", comparison.candidate), ("baseline", comparison.baseline)):
        observed_quality = [item.metric_id for item in system.quality]
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in observed_quality:
            if item in seen:
                duplicates.add(item)
            seen.add(item)
        duplicates = sorted(duplicates)
        if duplicates:
            issues.append(
                ValidationIssue(
                    "DUPLICATE_METRIC_ID",
                    "error",
                    f"duplicate quality IDs: {', '.join(duplicates)}",
                    f"$.{label}.quality",
                )
            )
        unexpected_quality = sorted(set(observed_quality) - quality_ids)
        if unexpected_quality:
            issues.append(
                ValidationIssue(
                    "UNEXPECTED_QUALITY_METRIC",
                    "error",
                    f"quality IDs are not in profile: {', '.join(unexpected_quality)}",
                    f"$.{label}.quality",
                )
            )
    for definition in profile.quality:
        for label, system in (
            ("candidate", comparison.candidate),
            ("baseline", comparison.baseline),
        ):
            observation = next(
                (item for item in system.quality if item.metric_id == definition.metric_id), None
            )
            if observation is None:
                issues.append(
                    ValidationIssue(
                        "REQUIRED_METRIC_MISSING",
                        "error",
                        f"missing quality metric {definition.metric_id!r}",
                        f"$.{label}.quality",
                    )
                )
            elif observation.raw.statistic != "mean":
                issues.append(
                    ValidationIssue(
                        "STATISTIC_MISMATCH",
                        "error",
                        f"quality metric {definition.metric_id!r} must use mean statistic",
                        f"$.{label}.quality",
                    )
                )
            if observation is not None:
                _validate_sampling(
                    observation.raw, comparison.protocol, f"$.{label}.quality", issues
                )
                if (
                    observation.raw.seed is not None
                    and observation.raw.seed != comparison.protocol.get("random_seed")
                ):
                    issues.append(
                        ValidationIssue(
                            "MEASUREMENT_SEED_MISMATCH",
                            "error",
                            "quality measurement seed must match protocol random_seed",
                            f"$.{label}.quality",
                        )
                    )
    for definition in profile.metrics:
        for label, system in (
            ("candidate", comparison.candidate),
            ("baseline", comparison.baseline),
        ):
            measurement = _metric_measurement(system, definition)
            if measurement is None:
                issues.append(
                    ValidationIssue(
                        "REQUIRED_METRIC_MISSING",
                        "error",
                        f"missing required metric {definition.metric_id!r}",
                        f"$.{label}",
                    )
                )
                continue
            if definition.parameter_semantics is not None:
                parameter = system.parameters.get(definition.parameter_semantics)
                if parameter is not None and parameter.semantics != definition.parameter_semantics:
                    issues.append(
                        ValidationIssue(
                            "PARAMETER_SEMANTICS_MISMATCH",
                            "error",
                            f"parameter semantics must be {definition.parameter_semantics!r}",
                            f"$.{label}.parameters.{definition.parameter_semantics}",
                        )
                    )
                if system.parameter_status not in {"verified", "reported"}:
                    issues.append(
                        ValidationIssue(
                            "PARAMETER_CLAIM_DISPUTED"
                            if system.parameter_status == "disputed"
                            else "PARAMETER_STATUS_NOT_SCOREABLE",
                            "error",
                            "parameter status must be verified or reported for parameter scoring",
                            f"$.{label}.parameters",
                        )
                    )
            if definition.parameter_semantics is None:
                _validate_sampling(measurement, comparison.protocol, f"$.{label}.metrics", issues)
            if measurement.seed is not None and measurement.seed != comparison.protocol.get(
                "random_seed"
            ):
                issues.append(
                    ValidationIssue(
                        "MEASUREMENT_SEED_MISMATCH",
                        "error",
                        "measurement seed must match protocol random_seed",
                        f"$.{label}.metrics",
                    )
                )
            _validate_measurement(measurement, definition, label, issues)
            if definition.metric_id == "cost_per_successful_task" and system.cost_metadata is None:
                issues.append(
                    ValidationIssue(
                        "COST_METADATA_MISSING", "error", "cost metadata is required", f"$.{label}"
                    )
                )
        candidate_measurement = _metric_measurement(comparison.candidate, definition)
        baseline_measurement = _metric_measurement(comparison.baseline, definition)
        if (
            candidate_measurement is not None
            and baseline_measurement is not None
            and get_unit(candidate_measurement.unit).semantic
            != get_unit(baseline_measurement.unit).semantic
        ):
            issues.append(
                ValidationIssue(
                    "UNIT_SEMANTIC_MISMATCH",
                    "error",
                    f"metric {definition.metric_id!r} uses unlike units",
                    "$.candidate",
                )
            )


def _metric_measurement(system: SystemRecord, definition: MetricDefinition) -> Measurement | None:
    if definition.parameter_semantics is not None:
        observation = system.parameters.get(definition.parameter_semantics)
        return observation.measurement if observation else None
    return system.metrics.get(definition.metric_id)


def _validate_measurement(
    measurement: Measurement,
    definition: MetricDefinition,
    label: str,
    issues: list[ValidationIssue],
) -> None:
    try:
        canonical, unit = canonical_value(measurement.value, measurement.unit)
        expected = get_unit(definition.canonical_unit)
        if (unit.dimension, unit.semantic) != (expected.dimension, expected.semantic):
            raise InputError("wrong metric dimension", code="WRONG_METRIC_DIMENSION")
        if measurement.statistic != definition.statistic:
            issues.append(
                ValidationIssue(
                    "STATISTIC_MISMATCH",
                    "error",
                    f"{definition.metric_id!r} must use {definition.statistic}",
                    f"$.{label}.metrics",
                )
            )
        if canonical <= 0:
            issues.append(
                ValidationIssue(
                    "NONPOSITIVE_PHYSICAL_METRIC",
                    "error",
                    f"{definition.metric_id!r} must be positive",
                    f"$.{label}",
                )
            )
    except InputError as exc:
        issues.append(ValidationIssue(exc.code, "error", str(exc), f"$.{label}"))


def _validate_provenance(system: SystemRecord, label: str, issues: list[ValidationIssue]) -> None:
    if not system.provenance:
        issues.append(
            ValidationIssue(
                "MISSING_PROVENANCE",
                "error",
                "at least one provenance record is required",
                f"$.{label}",
            )
        )


def _validate_parameter_claims(
    system: SystemRecord, label: str, issues: list[ValidationIssue], *, strict: bool
) -> None:
    severity = "error" if strict else "warning"
    claim_ids: set[str] = set()
    claims_by_semantics: dict[str, set[tuple[str, str]]] = {}
    for index, claim in enumerate(system.parameter_claims):
        claim_id = claim.get("claim_id")
        semantics = claim.get("semantics")
        source = claim.get("source")
        if not isinstance(claim_id, str) or not claim_id.strip():
            issues.append(
                ValidationIssue(
                    "PARAMETER_CLAIM_INVALID",
                    severity,
                    "claim_id is required",
                    f"$.{label}.parameters.claims[{index}]",
                )
            )
            continue
        if claim_id in claim_ids:
            issues.append(
                ValidationIssue(
                    "DUPLICATE_PARAMETER_CLAIM",
                    severity,
                    "claim_id must be unique",
                    f"$.{label}.parameters.claims[{index}]",
                )
            )
        claim_ids.add(claim_id)
        if not isinstance(semantics, str) or not isinstance(source, str):
            issues.append(
                ValidationIssue(
                    "PARAMETER_CLAIM_INVALID",
                    severity,
                    "claim semantics and source are required",
                    f"$.{label}.parameters.claims[{index}]",
                )
            )
            continue
        try:
            value = parse_decimal(
                claim.get("value"), field=f"$.{label}.parameters.claims[{index}].value"
            )
            unit = get_unit(claim.get("unit"))
        except (InputError, TypeError) as exc:
            issues.append(
                ValidationIssue(
                    getattr(exc, "code", "PARAMETER_CLAIM_INVALID"),
                    severity,
                    str(exc),
                    f"$.{label}.parameters.claims[{index}]",
                )
            )
            continue
        claim_identity = (decimal_string(value), unit.name)
        claims_by_semantics.setdefault(semantics, set()).add(claim_identity)
        selected = system.parameters.get(semantics)
        if selected is not None:
            selected_identity = (
                decimal_string(selected.measurement.value),
                get_unit(selected.measurement.unit).name,
            )
            if selected_identity != claim_identity:
                issues.append(
                    ValidationIssue(
                        "PARAMETER_CLAIM_SELECTION_MISMATCH",
                        severity,
                        "selected parameter observation does not match a provenance claim",
                        f"$.{label}.parameters.{semantics}",
                    )
                )
    if any(len(values) > 1 for values in claims_by_semantics.values()):
        issues.append(
            ValidationIssue(
                "PARAMETER_CLAIMS_CONFLICT",
                severity,
                "conflicting parameter claims require disputed status",
                f"$.{label}.parameters.claims",
            )
        )
        if system.parameter_status != "disputed":
            issues.append(
                ValidationIssue(
                    "PARAMETER_STATUS_NOT_SCOREABLE",
                    severity,
                    "conflicting claims must be marked disputed",
                    f"$.{label}.parameters",
                )
            )


def _validate_revision_bindings(comparison: ComparisonInput, issues: list[ValidationIssue]) -> None:
    workload_benchmark_revision = comparison.workload.get("benchmark_revision")
    candidate_revisions: set[str] = set()
    baseline_revisions: set[str] = set()
    for label, system, destination in (
        ("candidate", comparison.candidate, candidate_revisions),
        ("baseline", comparison.baseline, baseline_revisions),
    ):
        for record in system.provenance:
            if (
                record.model_revision
                and not any(
                    marker in record.model_revision.strip().lower()
                    for marker in (
                        "unknown",
                        "unavailable",
                        "not-provided",
                        "not provided",
                        "missing",
                    )
                )
                and record.model_revision.strip() != system.revision.strip()
            ):
                issues.append(
                    ValidationIssue(
                        "PROVENANCE_MODEL_REVISION_MISMATCH",
                        "error",
                        "provenance model_revision disagrees with system revision",
                        f"$.{label}.provenance",
                    )
                )
            if record.benchmark_revision:
                destination.add(record.benchmark_revision.strip())
    if not isinstance(workload_benchmark_revision, str) or not workload_benchmark_revision.strip():
        issues.append(
            ValidationIssue(
                "BENCHMARK_REVISION_MISSING",
                "error",
                "workload benchmark_revision is required",
                "$.workload",
            )
        )
    else:
        expected = workload_benchmark_revision.strip()
        for label, revisions in (
            ("candidate", candidate_revisions),
            ("baseline", baseline_revisions),
        ):
            if revisions and revisions != {expected}:
                issues.append(
                    ValidationIssue(
                        "PROVENANCE_BENCHMARK_REVISION_MISMATCH",
                        "error",
                        "provenance benchmark_revision disagrees with workload",
                        f"$.{label}.provenance",
                    )
                )


def _validate_sampling(
    measurement: Measurement,
    protocol: dict[str, Any],
    path: str,
    issues: list[ValidationIssue],
) -> None:
    repeat_count = protocol.get("repeat_count")
    if measurement.sample_count is None:
        issues.append(
            ValidationIssue(
                "SAMPLE_COUNT_MISSING", "error", "measured observation needs sample_count", path
            )
        )
    elif isinstance(repeat_count, int) and measurement.sample_count < repeat_count:
        issues.append(
            ValidationIssue(
                "SAMPLE_COUNT_BELOW_PROTOCOL",
                "error",
                "sample_count cannot be below protocol repeat_count",
                path,
            )
        )
    if measurement.statistic in TAIL_STATISTICS:
        policy = protocol.get("percentile_min_samples")
        minimum = policy.get(measurement.statistic) if isinstance(policy, dict) else None
        if minimum is None:
            issues.append(
                ValidationIssue(
                    "PERCENTILE_ADEQUACY_UNSPECIFIED",
                    "warning",
                    f"no protocol adequacy rule is declared for {measurement.statistic}",
                    path,
                )
            )
        elif measurement.sample_count is not None and measurement.sample_count < minimum:
            issues.append(
                ValidationIssue(
                    "TAIL_PERCENTILE_INSUFFICIENT",
                    "warning",
                    f"{measurement.statistic} has fewer than {minimum} samples",
                    path,
                )
            )


def _validate_evidence_class_consistency(
    comparison: ComparisonInput, issues: list[ValidationIssue]
) -> None:
    candidate_classes = {item.evidence_class for item in comparison.candidate.provenance}
    baseline_classes = {item.evidence_class for item in comparison.baseline.provenance}
    if candidate_classes != baseline_classes:
        issues.append(
            ValidationIssue(
                "EVIDENCE_CLASS_MISMATCH",
                "warning",
                "candidate and baseline evidence classes differ",
                "$.provenance",
            )
        )


def _require_string_keys(
    data: dict[str, Any], required: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    for key in sorted(required):
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(
                ValidationIssue(
                    "REQUIRED_FIELD_MISSING",
                    "error",
                    f"missing or invalid string field {key!r}",
                    path,
                )
            )


def _require_positive_protocol_field(
    name: str, protocol: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    value = protocol.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        valid = False
    else:
        try:
            valid = parse_decimal(value, field=f"$.protocol.{name}") > 0
        except InputError:
            valid = False
    if not valid:
        issues.append(
            ValidationIssue(
                "PROTOCOL_FIELD_INVALID",
                "error",
                f"{name} must be a positive numeric value",
                f"$.protocol.{name}",
            )
        )


def _require_protocol_field(
    name: str, protocol: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    if not isinstance(protocol.get(name), str) or not protocol[name].strip():
        issues.append(
            ValidationIssue(
                "PROTOCOL_FIELD_MISSING",
                "error",
                f"{name} is required for the selected scenario",
                "$.protocol",
            )
        )


def _validate_identity_bindings(
    system: SystemRecord, label: str, issues: list[ValidationIssue]
) -> None:
    artifact = system.model_artifact
    if artifact is None:
        return
    for context_name, context in (
        ("quality_context", system.quality_context),
        ("execution_system", system.execution_system),
    ):
        if context is None:
            continue
        for key in ("artifact_revision", "quantization", "dtype"):
            if key in context and key in artifact and context[key] != artifact[key]:
                issues.append(
                    ValidationIssue(
                        "ARTIFACT_CONTEXT_MISMATCH",
                        "error",
                        f"{context_name}.{key} disagrees with model_artifact",
                        f"$.{label}.{context_name}",
                    )
                )


def _validate_operating_envelope(
    system: SystemRecord, label: str, profile: Profile, issues: list[ValidationIssue]
) -> None:
    if system.operating_envelope is None:
        return
    try:
        envelope = OperatingEnvelope.from_dict(
            system.operating_envelope, path=f"$.{label}.operating_envelope"
        )
    except InputError as exc:
        issues.append(ValidationIssue(exc.code, "error", str(exc), exc.path or f"$.{label}"))
        return
    for warning_code in validate_envelope_adequacy(envelope):
        severity = (
            "error"
            if profile.mode != "parameter"
            and warning_code == "OPERATING_ENVELOPE_NO_OBSERVED_POINTS"
            else "warning"
        )
        issues.append(
            ValidationIssue(
                warning_code,
                severity,
                "operating envelope evidence is not sufficient for default observed-point analysis",
                f"$.{label}.operating_envelope",
            )
        )


def _slo_signature(envelope: OperatingEnvelope) -> set[str]:
    """Canonical SLO thresholds across observed goodput points (seconds)."""

    signatures: set[str] = set()
    for point in envelope.observed_points:
        if point.goodput is None or point.goodput_slo is None:
            continue
        parts = []
        for name in sorted(point.goodput_slo.thresholds):
            threshold = point.goodput_slo.thresholds[name]
            seconds = convert(threshold.value, threshold.unit, "s")
            parts.append(f"{name}={decimal_string(seconds)}s")
        signatures.add("|".join(parts))
    return signatures


def _parse_envelope(system: SystemRecord, label: str) -> OperatingEnvelope | None:
    if system.operating_envelope is None:
        return None
    try:
        return OperatingEnvelope.from_dict(
            system.operating_envelope, path=f"$.{label}.operating_envelope"
        )
    except InputError:
        return None


def _validate_quality_context_compatibility(
    comparison: ComparisonInput, issues: list[ValidationIssue]
) -> None:
    candidate = comparison.candidate.quality_context
    baseline = comparison.baseline.quality_context
    if candidate is not None and baseline is not None and candidate != baseline:
        issues.append(
            ValidationIssue(
                "QUALITY_CONTEXT_MISMATCH",
                "error",
                "candidate and baseline quality contexts differ; "
                "prompt/task/scorer conditions are not the same evaluation",
                "$.quality_context",
            )
        )


def _validate_envelope_compatibility(
    comparison: ComparisonInput, profile: Profile, issues: list[ValidationIssue]
) -> None:
    candidate = _parse_envelope(comparison.candidate, "candidate")
    baseline = _parse_envelope(comparison.baseline, "baseline")
    evidence_tier = comparison.protocol.get("evidence_tier")
    if (
        profile.mode != "parameter"
        and evidence_tier == "publication"
        and (candidate is None or baseline is None)
    ):
        issues.append(
            ValidationIssue(
                "OPERATING_ENVELOPE_MISSING",
                "error",
                "publication performance records need an operating envelope "
                "for candidate and baseline",
                "$.operating_envelope",
            )
        )
        return
    if candidate is None or baseline is None:
        return
    if candidate.scenario != baseline.scenario:
        issues.append(
            ValidationIssue(
                "SCENARIO_MISMATCH",
                "error",
                "candidate and baseline envelopes use different scenarios",
                "$.operating_envelope",
            )
        )
    protocol_scenario = comparison.protocol.get("scenario")
    if isinstance(protocol_scenario, str) and candidate.scenario != protocol_scenario:
        issues.append(
            ValidationIssue(
                "ENVELOPE_PROTOCOL_MISMATCH",
                "error",
                "operating envelope scenario disagrees with protocol scenario",
                "$.operating_envelope",
            )
        )
    for label, envelope in (("candidate", candidate), ("baseline", baseline)):
        if envelope.protocol_id != comparison.protocol.get("id") or str(
            envelope.protocol_version
        ) != str(comparison.protocol.get("version")):
            issues.append(
                ValidationIssue(
                    "ENVELOPE_PROTOCOL_MISMATCH",
                    "error",
                    f"{label} envelope protocol disagrees with top-level protocol",
                    f"$.{label}.operating_envelope",
                )
            )
        for point in envelope.points:
            if point.workload.get("id") != comparison.workload.get("id") or point.workload.get(
                "revision"
            ) != comparison.workload.get("revision"):
                issues.append(
                    ValidationIssue(
                        "ENVELOPE_WORKLOAD_MISMATCH",
                        "error",
                        f"{label} envelope point {point.point_id!r} disagrees "
                        "with top-level workload identity",
                        f"$.{label}.operating_envelope",
                    )
                )
                break
    if (candidate.protocol_id, candidate.protocol_version) != (
        baseline.protocol_id,
        baseline.protocol_version,
    ):
        issues.append(
            ValidationIssue(
                "ENVELOPE_PROTOCOL_MISMATCH",
                "error",
                "candidate and baseline envelopes use different protocols",
                "$.operating_envelope",
            )
        )
    slo_signatures = _slo_signature(candidate) | _slo_signature(baseline)
    if len(slo_signatures) > 1:
        issues.append(
            ValidationIssue(
                "GOODPUT_SLO_MISMATCH",
                "error",
                "goodput SLO thresholds differ; goodput values are not comparable",
                "$.operating_envelope",
            )
        )
    cache_states = {
        point.cache_state for point in (*candidate.observed_points, *baseline.observed_points)
    }
    if len(cache_states) > 1:
        issues.append(
            ValidationIssue(
                "CACHE_CONTEXT_MIXED"
                if evidence_tier != "publication"
                else "CACHE_CONTEXT_MISMATCH",
                "warning" if evidence_tier != "publication" else "error",
                "observed points mix cache states; goodput/latency are not comparable",
                "$.operating_envelope",
            )
        )


def _validate_publication_evidence(
    comparison: ComparisonInput, profile: Profile, issues: list[ValidationIssue]
) -> None:
    del profile
    if comparison.protocol.get("evidence_tier") != "publication":
        return
    for label, system in (
        ("candidate", comparison.candidate),
        ("baseline", comparison.baseline),
    ):
        if system.model_artifact is None:
            issues.append(
                ValidationIssue(
                    "MODEL_ARTIFACT_MISSING",
                    "error",
                    f"{label} publication record needs an explicit model artifact",
                    f"$.{label}.model_artifact",
                )
            )
        for index, record in enumerate(system.provenance):
            if record.evidence_class not in {"self_measured", "independent_reproduced"}:
                issues.append(
                    ValidationIssue(
                        "PUBLICATION_EVIDENCE_CLASS",
                        "error",
                        f"{label} publication record needs measured evidence, "
                        f"got {record.evidence_class!r}",
                        f"$.{label}.provenance[{index}]",
                    )
                )
