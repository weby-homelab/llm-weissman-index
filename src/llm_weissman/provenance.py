"""Validation helpers for evidence and provenance records."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from .models import ProvenanceRecord

EVIDENCE_CLASSES = {
    "independent_reproduced",
    "self_measured",
    "vendor_reported",
    "paper_reported",
    "model_card",
    "derived",
    "unverified",
    "synthetic",
}


def provenance_issues(record: ProvenanceRecord, *, path: str) -> list[tuple[str, str, str]]:
    """Return ``(code, severity, message)`` tuples without fetching URLs."""

    issues: list[tuple[str, str, str]] = []
    if record.evidence_class not in EVIDENCE_CLASSES:
        issues.append(
            ("INVALID_EVIDENCE_CLASS", "error", f"unknown evidence class {record.evidence_class!r}")
        )
    if record.source_url is not None:
        try:
            parsed = urlparse(record.source_url)
            _port = parsed.port
            _host = parsed.hostname
        except ValueError:
            issues.append(("INVALID_PROVENANCE_URL", "error", "source_url is malformed"))
            parsed = None
        if parsed is None:
            return [(code, severity, f"{path}: {message}") for code, severity, message in issues]
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            issues.append(
                ("INVALID_PROVENANCE_URL", "error", "source_url must be an http(s) URL with a host")
            )
        if parsed.username or parsed.password:
            issues.append(
                ("PROVENANCE_URL_CREDENTIALS", "error", "source_url cannot contain credentials")
            )
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private or address.is_loopback or address.is_link_local
        ):
            issues.append(
                (
                    "PROVENANCE_PRIVATE_URL",
                    "warning",
                    "source_url points at a private or local address",
                )
            )
    if (
        record.evidence_class in {"self_measured", "independent_reproduced"}
        and not record.raw_log_digest
    ):
        issues.append(
            ("RAW_LOG_DIGEST_MISSING", "error", "measured evidence has no raw_log_digest")
        )
    if record.evidence_class in {"vendor_reported", "paper_reported", "model_card"} and (
        not record.source_url or not record.source_title
    ):
        issues.append(
            (
                "EXTERNAL_SOURCE_METADATA_MISSING",
                "error",
                "external evidence needs source_url and source_title",
            )
        )
    if record.evidence_class in {"vendor_reported", "paper_reported", "model_card"}:
        if not record.model_revision or any(
            marker in record.model_revision.strip().lower()
            for marker in ("unknown", "unavailable", "not-provided", "not provided", "missing")
        ):
            issues.append(
                ("MODEL_REVISION_MISSING", "error", "external evidence needs a model revision")
            )
        if not record.benchmark_revision or any(
            marker in record.benchmark_revision.strip().lower()
            for marker in ("unknown", "unavailable", "not-provided", "not provided", "missing")
        ):
            issues.append(
                (
                    "BENCHMARK_REVISION_MISSING",
                    "error",
                    "external evidence needs a benchmark revision",
                )
            )
    return [(code, severity, f"{path}: {message}") for code, severity, message in issues]
