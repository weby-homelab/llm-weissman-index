"""Command-line interface for the LWI reference implementation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .digests import sha256_digest
from .errors import InputError
from .models import redact_untrusted
from .pareto import ParetoPoint, pareto_dominated
from .profiles import load_profile
from .report import evaluation_document, render_json, render_report
from .scoring import comparison_context_id, evaluate
from .validation import load_data_file, parse_comparison, validate_comparison


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lwi", description="Compute workload-specific LLM Weissman Index results."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate an input comparison record")
    validate.add_argument("file", type=Path)
    validate.add_argument("--profile", default="edge-v1")
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    for name, help_text in (
        ("compute", "compute an eligible LWI score"),
        ("report", "render a full LWI report"),
        ("context", "show the deterministic comparison context"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("file", type=Path)
        command.add_argument("--profile", required=True)
        command.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    pareto = commands.add_parser("pareto", help="show context-bound Pareto dominance")
    pareto.add_argument("files", nargs="+", type=Path)
    pareto.add_argument("--profile", required=True)
    pareto.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_profile(args.profile)
        if args.command == "pareto":
            return _run_pareto(args.files, profile, json_output=args.json)
        data = load_data_file(args.file)
        comparison = parse_comparison(data)
    except InputError as exc:
        _emit_error(exc, json_output=getattr(args, "json", False))
        return 2
    if args.command == "validate":
        report = validate_comparison(comparison, profile)
        payload = {
            "spec_version": comparison.spec_version,
            "schema_version": comparison.schema_version,
            "profile": {
                "id": profile.profile_id,
                "version": profile.version,
                "digest": profile.digest,
            },
            **report.to_dict(),
        }
        if args.json:
            sys.stdout.write(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
        else:
            sys.stdout.write("valid\n" if report.ok else "invalid\n")
            for issue in report.issues:
                sys.stdout.write(f"[{issue.severity}] {issue.code}: {issue.message}\n")
        return 0 if report.ok else 1
    if args.command == "context":
        validation = validate_comparison(comparison, profile)
        if validation.errors:
            payload = {
                "status": "invalid",
                "errors": [issue.to_dict() for issue in validation.errors],
                "warnings": [issue.to_dict() for issue in validation.warnings],
            }
            sys.stdout.write(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            return 1
        payload = {
            "comparison_context_id": comparison_context_id(comparison, profile),
            "profile": {
                "id": profile.profile_id,
                "version": profile.version,
                "digest": profile.digest,
            },
            "baseline": {
                "id": comparison.baseline.id,
                "revision": comparison.baseline.revision,
                "provider": comparison.baseline.provider,
                "model_id": comparison.baseline.model_id,
                "snapshot": comparison.baseline.snapshot,
                "measurement_digest": sha256_digest(comparison.baseline.to_dict()),
            },
            "workload": redact_untrusted(dict(comparison.workload)),
            "protocol": redact_untrusted(dict(comparison.protocol)),
            "measurement_environment": redact_untrusted(
                {
                    label: {
                        key: comparison.measurement_environment[label].get(key)
                        for key in profile.environment_comparison_keys
                    }
                    for label in ("candidate", "baseline")
                }
            ),
            "quality_transforms": redact_untrusted([item.to_dict() for item in profile.quality]),
            "metric_definitions": redact_untrusted([item.to_dict() for item in profile.metrics]),
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return 0
    evaluation = evaluate(comparison, profile)
    if args.command == "report" and not args.json:
        sys.stdout.write(render_report(evaluation, comparison, profile))
    else:
        document = evaluation_document(evaluation, comparison, profile)
        sys.stdout.write(render_json(document))
    return 0 if evaluation.status == "eligible" else 3


def _run_pareto(files: list[Path], profile: Any, *, json_output: bool) -> int:
    evaluations = []
    for file_path in files:
        comparison = parse_comparison(load_data_file(file_path))
        evaluation = evaluate(comparison, profile)
        if evaluation.status != "eligible" or evaluation.quality is None:
            payload = {
                "status": "invalid",
                "errors": [
                    {
                        "code": "PARETO_INPUT_INELIGIBLE",
                        "message": f"{file_path} is {evaluation.status}",
                    }
                ],
            }
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            return 3
        values = {"quality": evaluation.quality.candidate_aggregate, **evaluation.resource_ratios}
        # Resource ratios are already normalized so that larger is better.
        directions = {"quality": "higher_is_better"}
        directions.update({item.metric_id: "higher_is_better" for item in profile.metrics})
        evaluations.append(
            ParetoPoint(
                evaluation.candidate_id,
                evaluation.context_id,
                values,
                directions,
                evaluation.candidate_revision,
            )
        )
    flags = pareto_dominated(evaluations)
    payload = {
        "status": "eligible",
        "context_id": evaluations[0].context_id if evaluations else None,
        "pareto_dominated": flags,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


def _emit_error(error: InputError, *, json_output: bool) -> None:
    payload: dict[str, Any] = {
        "status": "invalid",
        "errors": [{"code": error.code, "message": str(error), "path": error.path}],
    }
    if json_output:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stderr.write(f"[{error.code}] {error}: {error.path}\n")


if __name__ == "__main__":
    raise SystemExit(main())
