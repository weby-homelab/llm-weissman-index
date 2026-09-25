"""Machine-readable and human-readable LWI reports."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from .models import ComparisonInput, redact_untrusted
from .profiles import Profile
from .scoring import Evaluation


def evaluation_document(
    evaluation: Evaluation, comparison: ComparisonInput, profile: Profile
) -> dict[str, Any]:
    document = evaluation.to_dict()
    document.update(
        {
            "workload": redact_untrusted(dict(comparison.workload)),
            "protocol": redact_untrusted(dict(comparison.protocol)),
            "measurement_environment": {
                "candidate": redact_untrusted(
                    dict(comparison.measurement_environment["candidate"])
                ),
                "baseline": redact_untrusted(dict(comparison.measurement_environment["baseline"])),
            },
            "provenance": {
                "candidate": [item.to_dict() for item in comparison.candidate.provenance],
                "baseline": [item.to_dict() for item in comparison.baseline.provenance],
            },
            "raw_quality": {
                "candidate": [item.to_dict() for item in comparison.candidate.quality],
                "baseline": [item.to_dict() for item in comparison.baseline.quality],
            },
            "parameter_metadata": {
                "candidate": _parameter_metadata(comparison.candidate),
                "baseline": _parameter_metadata(comparison.baseline),
            },
            "profile_policy": redact_untrusted(profile.canonical_dict),
            "pareto_dominated": None,
        }
    )
    return document


def render_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_report(evaluation: Evaluation, comparison: ComparisonInput, profile: Profile) -> str:
    lines = [
        "LLM Weissman Index report",
        f"candidate: {comparison.candidate.id} ({comparison.candidate.revision})",
        f"baseline: {comparison.baseline.id} ({comparison.baseline.revision})",
        f"candidate provider/model: {comparison.candidate.provider} / "
        f"{comparison.candidate.model_id} @ {comparison.candidate.snapshot}",
        f"baseline provider/model: {comparison.baseline.provider} / "
        f"{comparison.baseline.model_id} @ {comparison.baseline.snapshot}",
        f"workload: {comparison.workload.get('id')} @ {comparison.workload.get('revision')}",
        f"benchmark revision: {comparison.workload.get('benchmark_revision')}",
        f"protocol: {comparison.protocol.get('id')} v{comparison.protocol.get('version')}",
        f"profile: {profile.profile_id} v{profile.version}",
        f"profile digest: {profile.digest}",
        f"comparison context ID: {evaluation.context_id}",
        f"status: {evaluation.status}",
    ]
    if evaluation.reason:
        lines.append(f"reason: {evaluation.reason}")
    score = _human_decimal(evaluation.lwi) if evaluation.lwi is not None else "unavailable"
    lines.append(f"LWI: {score}")
    lines.append("")
    lines.append("Quality")
    if evaluation.quality is None:
        lines.append("  unavailable: validation did not produce a quality aggregate")
    else:
        lines.append("  raw observations:")
        for label, system in (
            ("candidate", comparison.candidate),
            ("baseline", comparison.baseline),
        ):
            for observation in system.quality:
                lines.append(f"    {label} {observation.metric_id}: {observation.raw.to_dict()}")
        lines.append(
            f"  retention: {_human_decimal(evaluation.quality.retention)} "
            f"(candidate aggregate {_human_decimal(evaluation.quality.candidate_aggregate)}, "
            f"baseline aggregate {_human_decimal(evaluation.quality.baseline_aggregate)})"
        )
        lines.append(f"  ratio: {_human_decimal(evaluation.quality.quality_ratio)}")
        for metric_id in sorted(evaluation.quality.candidate_utilities):
            lines.append(
                f"  {metric_id}: candidate "
                f"{_human_decimal(evaluation.quality.candidate_utilities[metric_id])}; "
                f"baseline {_human_decimal(evaluation.quality.baseline_utilities[metric_id])}"
            )
    lines.append("")
    lines.append("Resource ratios")
    if evaluation.resource_ratios:
        for metric_id, ratio in evaluation.resource_ratios.items():
            lines.append(f"  {metric_id}: {_human_decimal(ratio)}")
    else:
        lines.append("  unavailable")
    if comparison.candidate.parameters or comparison.baseline.parameters:
        lines.append("")
        lines.append("Parameter metadata")
        for label, system in (
            ("candidate", comparison.candidate),
            ("baseline", comparison.baseline),
        ):
            lines.append(f"  {label} status: {system.parameter_status}")
            for name, parameter in system.parameters.items():
                lines.append(f"  {label} {name}: {redact_untrusted(parameter.to_dict())}")
    lines.append("")
    lines.append(
        "Quality gate: "
        f"threshold {evaluation.quality_gate['minimum_retention']}; "
        f"observed {evaluation.quality_gate['observed_retention']}; "
        f"margin {evaluation.quality_gate['margin']}; "
        f"passed {evaluation.quality_gate['passed']}"
    )
    lines.append("")
    lines.append("Raw metrics")
    if evaluation.raw_metrics:
        for metric_id, values in evaluation.raw_metrics.items():
            lines.append(
                f"  {metric_id}: candidate {values['candidate']} -> "
                f"{values['candidate_canonical']} "
                f"{values['canonical_unit']}; baseline {values['baseline']} -> "
                f"{values['baseline_canonical']} {values['canonical_unit']}"
            )
    else:
        lines.append("  unavailable")
    lines.append("")
    lines.append("Provenance")
    for label, system in (("candidate", comparison.candidate), ("baseline", comparison.baseline)):
        classes = ", ".join(sorted({item.evidence_class for item in system.provenance}))
        lines.append(f"  {label}: {classes}")
        for item in system.provenance:
            safe_record = item.to_dict()
            if safe_record.get("source_url"):
                lines.append(f"    {safe_record['source_url']}")
            lines.append(
                f"    source={safe_record.get('source_title')} "
                f"retrieved={safe_record.get('retrieved_at')} "
                f"model_revision={safe_record.get('model_revision')} "
                f"benchmark_revision={safe_record.get('benchmark_revision')}"
            )
    lines.append("")
    lines.append(f"candidate measurement digest: {evaluation.measurement_digests['candidate']}")
    lines.append(f"baseline measurement digest: {evaluation.measurement_digests['baseline']}")
    if evaluation.issues:
        lines.append("")
        lines.append("Issues")
        for issue in evaluation.issues:
            lines.append(f"  [{issue.severity}] {issue.code}: {issue.message}")
    lines.append("")
    lines.append(f"result digest: {evaluation.result_digest}")
    return "\n".join(lines) + "\n"


def _human_decimal(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    return format(value, ".6g")


def _parameter_metadata(system: Any) -> dict[str, Any]:
    return {
        "status": system.parameter_status,
        "observations": redact_untrusted(
            {name: item.to_dict() for name, item in system.parameters.items()}
        ),
        "claims": redact_untrusted(list(system.parameter_claims)),
        "cost_metadata": system.cost_metadata.to_dict() if system.cost_metadata else None,
    }
