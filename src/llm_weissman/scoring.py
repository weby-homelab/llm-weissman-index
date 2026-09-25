"""Scoring orchestration over validated comparison records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .digests import sha256_digest
from .errors import InputError
from .formula import compute_lwi
from .models import ComparisonInput, Measurement, SystemRecord, redact_untrusted
from .profiles import MetricDefinition, Profile
from .quality import QualityResult, aggregate_quality
from .units import DECIMAL_WORKING_PRECISION, convert, decimal_string
from .validation import ValidationIssue, validate_comparison

INCOMPLETE_CODES = {
    "REQUIRED_METRIC_MISSING",
    "ENVIRONMENT_CONTEXT_MISSING",
    "DATASET_CHECKSUM_MISSING",
    "PARAMETER_CLAIM_DISPUTED",
    "PARAMETER_STATUS_NOT_SCOREABLE",
    "PARAMETER_SEMANTICS_MISMATCH",
    "PARAMETER_CLAIM_SELECTION_MISMATCH",
    "MODEL_REVISION_MISSING",
    "BENCHMARK_REVISION_MISSING",
    "SAMPLE_COUNT_MISSING",
    "SAMPLE_COUNT_BELOW_PROTOCOL",
    "COST_METADATA_MISSING",
    "INVALID_COST_METADATA",
    "TOKEN_COUNT_MISSING",
    "RANDOM_SEED_MISSING",
}


@dataclass(frozen=True)
class Evaluation:
    status: str
    reason: str | None
    spec_version: str
    schema_version: str
    context_id: str
    profile_id: str
    profile_version: str
    profile_digest: str
    candidate_id: str
    baseline_id: str
    candidate_revision: str
    baseline_revision: str
    candidate_provider: str | None
    candidate_model_id: str | None
    candidate_snapshot: str | None
    baseline_provider: str | None
    baseline_model_id: str | None
    baseline_snapshot: str | None
    lwi: Decimal | None
    quality: QualityResult | None
    resource_ratios: dict[str, Decimal]
    raw_metrics: dict[str, dict[str, Any]]
    quality_gate: dict[str, Any]
    contributions: dict[str, dict[str, Any]]
    log_contribution_sum: Decimal | None
    uncertainty_status: str
    measurement_digests: dict[str, str]
    workload: dict[str, Any]
    protocol: dict[str, Any]
    measurement_environment: dict[str, Any]
    profile_policy: dict[str, Any]
    issues: tuple[ValidationIssue, ...]
    result_digest: str

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "spec_version": self.spec_version,
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "candidate": redact_untrusted(
                {
                    "id": self.candidate_id,
                    "revision": self.candidate_revision,
                    "provider": self.candidate_provider,
                    "model_id": self.candidate_model_id,
                    "snapshot": self.candidate_snapshot,
                }
            ),
            "baseline": redact_untrusted(
                {
                    "id": self.baseline_id,
                    "revision": self.baseline_revision,
                    "provider": self.baseline_provider,
                    "model_id": self.baseline_model_id,
                    "snapshot": self.baseline_snapshot,
                }
            ),
            "profile": {
                "id": self.profile_id,
                "version": self.profile_version,
                "digest": self.profile_digest,
            },
            "comparison_context_id": self.context_id,
            "lwi": decimal_string(self.lwi) if self.lwi is not None else None,
            "quality": self.quality.to_dict() if self.quality is not None else None,
            "resource_ratios": {
                key: decimal_string(value) for key, value in self.resource_ratios.items()
            },
            "raw_metrics": redact_untrusted(self.raw_metrics),
            "quality_gate": redact_untrusted(self.quality_gate),
            "contributions": _serialize_contributions(self.contributions),
            "log_contribution_sum": (
                decimal_string(self.log_contribution_sum)
                if self.log_contribution_sum is not None
                else None
            ),
            "uncertainty_status": self.uncertainty_status,
            "measurement_digests": self.measurement_digests,
            "workload": redact_untrusted(self.workload),
            "protocol": redact_untrusted(self.protocol),
            "measurement_environment": redact_untrusted(self.measurement_environment),
            "profile_policy": redact_untrusted(self.profile_policy),
            "warnings": [issue.to_dict() for issue in self.issues if issue.severity == "warning"],
            "errors": [issue.to_dict() for issue in self.issues if issue.severity == "error"],
            "result_digest": self.result_digest,
        }
        return result


def comparison_context_id(
    comparison: ComparisonInput,
    profile: Profile,
    *,
    baseline_measurement_digest: str | None = None,
) -> str:
    """Hash only fields that define direct comparability."""

    relevant_environment = {
        label: {
            key: redact_untrusted(comparison.measurement_environment[label].get(key))
            for key in profile.environment_comparison_keys
        }
        for label in ("candidate", "baseline")
    }
    actual_baseline_digest = sha256_digest(comparison.baseline.to_dict())
    if (
        baseline_measurement_digest is not None
        and baseline_measurement_digest != actual_baseline_digest
    ):
        raise InputError(
            "baseline measurement digest does not match input",
            code="BASELINE_DIGEST_MISMATCH",
        )
    candidate_quality_context = dict(comparison.candidate.quality_context or {})
    baseline_quality_context = dict(comparison.baseline.quality_context or {})
    shared_quality_context = (
        redact_untrusted(baseline_quality_context)
        if candidate_quality_context == baseline_quality_context
        else None
    )
    payload = {
        "spec_version": comparison.spec_version,
        "schema_version": comparison.schema_version,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "profile_digest": profile.digest,
        "workload": redact_untrusted(dict(comparison.workload)),
        "protocol": redact_untrusted(dict(comparison.protocol)),
        "environment": relevant_environment,
        "baseline_identity": {
            "id": comparison.baseline.id,
            "revision": comparison.baseline.revision,
            "provider": comparison.baseline.provider,
            "model_id": comparison.baseline.model_id,
            "snapshot": comparison.baseline.snapshot,
        },
        "baseline_measurement_digest": baseline_measurement_digest or actual_baseline_digest,
        "shared_quality_context": shared_quality_context,
        "quality_transforms": [item.to_dict() for item in profile.quality],
        "metric_definitions": [item.to_dict() for item in profile.metrics],
    }
    return sha256_digest(payload)


def evaluate(comparison: ComparisonInput, profile: Profile) -> Evaluation:
    report = validate_comparison(comparison, profile)
    issues = list(report.issues)
    measurement_digests = {
        "candidate": sha256_digest(comparison.candidate.to_dict()),
        "baseline": sha256_digest(comparison.baseline.to_dict()),
    }
    context_id = comparison_context_id(
        comparison,
        profile,
        baseline_measurement_digest=measurement_digests["baseline"],
    )
    quality_gate = {
        "minimum_retention": decimal_string(profile.quality_gate.minimum_retention),
        "observed_retention": None,
        "margin": None,
        "passed": None,
    }
    quality: QualityResult | None = None
    resource_ratios: dict[str, Decimal] = {}
    raw_metrics: dict[str, dict[str, Any]] = {}
    contributions: dict[str, dict[str, Any]] = {}
    log_contribution_sum: Decimal | None = None
    lwi: Decimal | None = None
    status = "eligible"
    reason: str | None = None
    uncertainty_status = _uncertainty_status(comparison)

    if not report.errors:
        try:
            quality = aggregate_quality(
                comparison.candidate.quality, comparison.baseline.quality, profile.quality
            )
            quality_gate["observed_retention"] = decimal_string(quality.retention)
            margin = quality.retention - profile.quality_gate.minimum_retention
            quality_gate["margin"] = decimal_string(margin)
            quality_gate["passed"] = quality.retention >= profile.quality_gate.minimum_retention
            resource_ratios, raw_metrics = _resource_ratios(comparison, profile)
            contributions = _log_contributions(quality, resource_ratios, profile)
            if all(item["log_contribution"] is not None for item in contributions.values()):
                log_contribution_sum = sum(
                    item["log_contribution"] for item in contributions.values()
                )
        except InputError as exc:
            issues.append(ValidationIssue(exc.code, "error", str(exc), "$.score"))
    if any(issue.severity == "error" for issue in issues):
        status = (
            "incomplete" if any(issue.code in INCOMPLETE_CODES for issue in issues) else "invalid"
        )
        reason = next(issue.code.lower() for issue in issues if issue.severity == "error")
    elif quality is not None and not bool(quality_gate["passed"]):
        status = "ineligible"
        reason = "quality_gate_failed"
    elif quality is not None and quality.quality_ratio == 0:
        status = "ineligible"
        reason = "zero_candidate_quality_utility"
    elif quality is not None:
        try:
            lwi = compute_lwi(
                quality.quality_ratio,
                resource_ratios,
                profile.quality_weight,
                profile.resource_weights,
            )
        except InputError as exc:
            issues.append(ValidationIssue(exc.code, "error", str(exc), "$.score"))
            status = "invalid"
            reason = exc.code.lower()
    result_payload = {
        "status": status,
        "reason": reason,
        "context_id": context_id,
        "profile_digest": profile.digest,
        "candidate": comparison.candidate.to_dict(),
        "baseline": comparison.baseline.to_dict(),
        "quality": quality.to_dict() if quality is not None else None,
        "lwi": decimal_string(lwi) if lwi is not None else None,
        "resource_ratios": {key: decimal_string(value) for key, value in resource_ratios.items()},
        "raw_metrics": raw_metrics,
        "quality_gate": quality_gate,
        "contributions": _serialize_contributions(contributions),
        "log_contribution_sum": (
            decimal_string(log_contribution_sum) if log_contribution_sum is not None else None
        ),
        "uncertainty_status": uncertainty_status,
        "issues": [issue.to_dict() for issue in issues],
        "measurement_digests": measurement_digests,
        "spec_version": comparison.spec_version,
        "schema_version": comparison.schema_version,
        "workload": redact_untrusted(dict(comparison.workload)),
        "protocol": redact_untrusted(dict(comparison.protocol)),
        "measurement_environment": redact_untrusted(
            {
                "candidate": dict(comparison.measurement_environment["candidate"]),
                "baseline": dict(comparison.measurement_environment["baseline"]),
            }
        ),
        "profile_policy": redact_untrusted(profile.canonical_dict),
    }
    return Evaluation(
        status=status,
        reason=reason,
        spec_version=comparison.spec_version,
        schema_version=comparison.schema_version,
        context_id=context_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_digest=profile.digest,
        candidate_id=comparison.candidate.id,
        baseline_id=comparison.baseline.id,
        candidate_revision=comparison.candidate.revision,
        baseline_revision=comparison.baseline.revision,
        candidate_provider=comparison.candidate.provider,
        candidate_model_id=comparison.candidate.model_id,
        candidate_snapshot=comparison.candidate.snapshot,
        baseline_provider=comparison.baseline.provider,
        baseline_model_id=comparison.baseline.model_id,
        baseline_snapshot=comparison.baseline.snapshot,
        lwi=lwi,
        quality=quality,
        resource_ratios=resource_ratios,
        raw_metrics=raw_metrics,
        quality_gate=quality_gate,
        contributions=contributions,
        log_contribution_sum=log_contribution_sum,
        uncertainty_status=uncertainty_status,
        measurement_digests=measurement_digests,
        workload=redact_untrusted(dict(comparison.workload)),
        protocol=redact_untrusted(dict(comparison.protocol)),
        measurement_environment=redact_untrusted(
            {
                "candidate": dict(comparison.measurement_environment["candidate"]),
                "baseline": dict(comparison.measurement_environment["baseline"]),
            }
        ),
        profile_policy=redact_untrusted(profile.canonical_dict),
        issues=tuple(issues),
        result_digest=sha256_digest(result_payload),
    )


def _resource_ratios(
    comparison: ComparisonInput, profile: Profile
) -> tuple[dict[str, Decimal], dict[str, dict[str, Any]]]:
    ratios: dict[str, Decimal] = {}
    raw_metrics: dict[str, dict[str, Any]] = {}
    for definition in profile.metrics:
        candidate_measurement = _metric_measurement(comparison.candidate, definition)
        baseline_measurement = _metric_measurement(comparison.baseline, definition)
        if candidate_measurement is None or baseline_measurement is None:
            raise InputError(
                f"required metric {definition.metric_id!r} is missing",
                code="REQUIRED_METRIC_MISSING",
            )
        candidate_value = convert(
            candidate_measurement.value, candidate_measurement.unit, definition.canonical_unit
        )
        baseline_value = convert(
            baseline_measurement.value, baseline_measurement.unit, definition.canonical_unit
        )
        if candidate_value <= 0 or baseline_value <= 0:
            raise InputError(
                f"metric {definition.metric_id!r} must be positive",
                code="NONPOSITIVE_PHYSICAL_METRIC",
            )
        with localcontext() as context:
            context.prec = DECIMAL_WORKING_PRECISION
            if definition.direction == "lower_is_better":
                ratios[definition.metric_id] = baseline_value / candidate_value
            else:
                ratios[definition.metric_id] = candidate_value / baseline_value
        raw_metrics[definition.metric_id] = {
            "candidate": candidate_measurement.to_dict(),
            "baseline": baseline_measurement.to_dict(),
            "candidate_canonical": decimal_string(candidate_value),
            "baseline_canonical": decimal_string(baseline_value),
            "canonical_unit": definition.canonical_unit,
            "direction": definition.direction,
        }
        if definition.parameter_semantics is not None:
            candidate_parameter = comparison.candidate.parameters[definition.parameter_semantics]
            baseline_parameter = comparison.baseline.parameters[definition.parameter_semantics]
            raw_metrics[definition.metric_id]["parameter_semantics"] = (
                definition.parameter_semantics
            )
            raw_metrics[definition.metric_id]["candidate_parameter_source"] = redact_untrusted(
                candidate_parameter.source
            )
            raw_metrics[definition.metric_id]["baseline_parameter_source"] = redact_untrusted(
                baseline_parameter.source
            )
            raw_metrics[definition.metric_id]["candidate_parameter_method"] = redact_untrusted(
                candidate_parameter.method
            )
            raw_metrics[definition.metric_id]["baseline_parameter_method"] = redact_untrusted(
                baseline_parameter.method
            )
            raw_metrics[definition.metric_id]["candidate_parameter_status"] = (
                comparison.candidate.parameter_status
            )
            raw_metrics[definition.metric_id]["baseline_parameter_status"] = (
                comparison.baseline.parameter_status
            )
    return ratios, raw_metrics


def _log_contributions(
    quality: QualityResult, resource_ratios: dict[str, Decimal], profile: Profile
) -> dict[str, dict[str, Any]]:
    contributions: dict[str, dict[str, Any]] = {}
    dimensions = {
        "quality": (quality.quality_ratio, profile.quality_weight),
        **{
            metric_id: (resource_ratios[metric_id], weight)
            for metric_id, weight in profile.resource_weights.items()
        },
    }
    with localcontext() as context:
        context.prec = DECIMAL_WORKING_PRECISION
        for dimension, (ratio, weight) in dimensions.items():
            log_contribution = None if ratio <= 0 else weight * ratio.ln()
            contributions[dimension] = {
                "ratio": ratio,
                "weight": weight,
                "log_contribution": log_contribution,
            }
    return contributions


def _serialize_contributions(
    contributions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str | None]]:
    return {
        dimension: {
            key: decimal_string(value) if isinstance(value, Decimal) else value
            for key, value in values.items()
        }
        for dimension, values in sorted(contributions.items())
    }


def _uncertainty_status(comparison: ComparisonInput) -> str:
    measurements = [item.raw for item in comparison.candidate.quality]
    measurements.extend(item.raw for item in comparison.baseline.quality)
    measurements.extend(comparison.candidate.metrics.values())
    measurements.extend(comparison.baseline.metrics.values())
    if measurements and all(
        measurement.confidence_level is not None
        and measurement.lower_bound is not None
        and measurement.upper_bound is not None
        for measurement in measurements
    ):
        return "available"
    return "unavailable"


def _metric_measurement(system: SystemRecord, definition: MetricDefinition) -> Measurement | None:
    if definition.parameter_semantics is not None:
        parameter = system.parameters.get(definition.parameter_semantics)
        return parameter.measurement if parameter else None
    return system.metrics.get(definition.metric_id)
