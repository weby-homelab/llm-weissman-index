"""Deterministic canonicalization and SHA-256 identities."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .units import decimal_string

PUBLIC_MEASUREMENT_DIGEST_SEMANTICS = "normalized_public_record_v1"


def canonicalize(value: Any) -> Any:
    """Normalize nested data before hashing or serializing it."""

    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def public_measurement_digest(value: Any) -> str:
    """Hash a normalized public record, never the raw artifact bytes.

    The domain marker makes this digest distinct from profile, context, and
    result digests.  It is a privacy-safe public representation identity, not
    proof of raw-artifact integrity; callers must track raw verification
    separately.
    """

    return sha256_digest(
        {
            "digest_semantics": PUBLIC_MEASUREMENT_DIGEST_SEMANTICS,
            "record": value,
        }
    )
