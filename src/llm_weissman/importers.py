"""Explicit, non-guessing adapters for preserved benchmark artifacts.

The adapter accepts a caller-supplied field map rather than treating similar
upstream names as equivalent.  It never fetches an artifact and never drops
unmapped source fields; only their names are retained in the normalized result
to avoid copying arbitrary payloads into reports.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import InputError
from .models import Measurement, redact_untrusted

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string", code="REQUIRED_FIELD", path=field)
    return value


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object", code="WRONG_TYPE", path=field)
    if any(not isinstance(key, str) for key in value):
        raise InputError(f"{field} keys must be strings", code="WRONG_TYPE", path=field)
    return value


@dataclass(frozen=True)
class ImportedMetrics:
    source_tool: str
    source_tool_version: str
    raw_artifact_digest: str
    raw_artifact_digest_status: str
    field_mapping: Mapping[str, Mapping[str, str]]
    metrics: Mapping[str, Measurement]
    unknown_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_tool": redact_untrusted(self.source_tool),
            "source_tool_version": redact_untrusted(self.source_tool_version),
            "raw_artifact_digest": self.raw_artifact_digest,
            "raw_artifact_digest_status": self.raw_artifact_digest_status,
            "field_mapping": redact_untrusted(
                {name: dict(mapping) for name, mapping in sorted(self.field_mapping.items())}
            ),
            "metrics": {
                name: measurement.to_dict() for name, measurement in sorted(self.metrics.items())
            },
            "unknown_fields": list(self.unknown_fields),
        }


def import_explicit_metrics(
    raw: Mapping[str, Any],
    *,
    source_tool: str,
    source_tool_version: str,
    field_mapping: Mapping[str, Mapping[str, str]],
    raw_artifact_digest: str | None = None,
    raw_artifact_bytes: bytes | bytearray | memoryview | None = None,
) -> ImportedMetrics:
    """Normalize only fields explicitly mapped by the artifact producer.

    ``field_mapping`` entries require ``source_field``, ``unit`` and
    ``statistic``.  An optional ``sample_count_field`` points at a separate
    integer in the same raw object.  No field is inferred from its name. If
    ``raw_artifact_bytes`` is present, the importer computes the digest itself
    and rejects a conflicting caller claim. Without bytes, a supplied digest is
    retained as an explicitly unverified external claim.
    """

    raw_data = _mapping(raw, field="raw")
    if not field_mapping:
        raise InputError("field_mapping cannot be empty", code="IMPORT_MAPPING_MISSING")
    if raw_artifact_bytes is not None and not isinstance(
        raw_artifact_bytes, (bytes, bytearray, memoryview)
    ):
        raise InputError(
            "raw_artifact_bytes must be bytes",
            code="WRONG_TYPE",
            path="raw_artifact_bytes",
        )
    if raw_artifact_digest is not None:
        raw_artifact_digest = _string(raw_artifact_digest, field="raw_artifact_digest")
        if not _DIGEST_PATTERN.fullmatch(raw_artifact_digest):
            raise InputError(
                "raw_artifact_digest must be a sha256 digest",
                code="INVALID_ARTIFACT_DIGEST",
                path="raw_artifact_digest",
            )
    if raw_artifact_bytes is not None:
        computed_digest = "sha256:" + hashlib.sha256(bytes(raw_artifact_bytes)).hexdigest()
        if raw_artifact_digest is not None and raw_artifact_digest != computed_digest:
            raise InputError(
                "raw_artifact_digest does not match locally computed digest",
                code="ARTIFACT_DIGEST_MISMATCH",
                path="raw_artifact_digest",
            )
        raw_artifact_digest = computed_digest
        digest_status = "locally_verified"
    elif raw_artifact_digest is not None:
        digest_status = "claimed_external_unverified"
    else:
        raise InputError(
            "raw_artifact_digest or raw_artifact_bytes is required",
            code="ARTIFACT_DIGEST_MISSING",
            path="raw_artifact_digest",
        )
    normalized_mapping: dict[str, dict[str, str]] = {}
    metrics: dict[str, Measurement] = {}
    used_source_fields: set[str] = set()
    allowed_mapping_keys = {"source_field", "unit", "statistic", "semantic", "sample_count_field"}
    for metric_id, raw_mapping in field_mapping.items():
        metric_id = _string(metric_id, field="metric_id")
        mapping = _mapping(raw_mapping, field=f"field_mapping.{metric_id}")
        unexpected = sorted(set(mapping) - allowed_mapping_keys)
        if unexpected:
            raise InputError(
                f"unexpected mapping fields: {', '.join(unexpected)}",
                code="UNEXPECTED_FIELD",
                path=f"field_mapping.{metric_id}",
            )
        source_field = _string(mapping.get("source_field"), field="source_field")
        if source_field in used_source_fields:
            raise InputError(
                "one source field cannot map to multiple metrics",
                code="DUPLICATE_SOURCE_FIELD",
                path=f"field_mapping.{metric_id}",
            )
        used_source_fields.add(source_field)
        if source_field not in raw_data:
            raise InputError(
                f"mapped source field {source_field!r} is absent",
                code="IMPORT_FIELD_MISSING",
                path=f"field_mapping.{metric_id}",
            )
        unit = _string(mapping.get("unit"), field="unit")
        statistic = _string(mapping.get("statistic"), field="statistic")
        sample_count_field = mapping.get("sample_count_field")
        measurement_data: dict[str, Any] = {
            "value": raw_data[source_field],
            "unit": unit,
            "statistic": statistic,
        }
        if sample_count_field is not None:
            sample_count_field = _string(sample_count_field, field="sample_count_field")
            if sample_count_field not in raw_data:
                raise InputError(
                    f"sample count field {sample_count_field!r} is absent",
                    code="IMPORT_FIELD_MISSING",
                    path=f"field_mapping.{metric_id}",
                )
            measurement_data["sample_count"] = raw_data[sample_count_field]
            used_source_fields.add(sample_count_field)
        metrics[metric_id] = Measurement.from_dict(
            measurement_data, path=f"normalized.metrics.{metric_id}"
        )
        normalized_mapping[metric_id] = {
            key: value for key, value in mapping.items() if isinstance(value, str)
        }
    unknown_fields = tuple(sorted(set(raw_data) - used_source_fields))
    return ImportedMetrics(
        source_tool=_string(source_tool, field="source_tool"),
        source_tool_version=_string(source_tool_version, field="source_tool_version"),
        raw_artifact_digest=raw_artifact_digest,
        raw_artifact_digest_status=digest_status,
        field_mapping=normalized_mapping,
        metrics=metrics,
        unknown_fields=unknown_fields,
    )
