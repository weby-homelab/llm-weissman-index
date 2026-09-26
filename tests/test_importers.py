from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.importers import import_explicit_metrics


def _raw() -> dict[str, object]:
    return {
        "p95_ttft_ms": "12.5",
        "sample_count": 100,
        "mean_tpot_ms": "3.25",
        "vendor_extension": "preserve-name-only",
    }


def _mapping() -> dict[str, dict[str, str]]:
    return {
        "ttft": {
            "source_field": "p95_ttft_ms",
            "unit": "ms",
            "statistic": "p95",
            "semantic": "ttft",
            "sample_count_field": "sample_count",
        },
        "tpot": {
            "source_field": "mean_tpot_ms",
            "unit": "ms",
            "statistic": "mean",
            "semantic": "tpot",
            "sample_count_field": "sample_count",
        },
    }


def test_explicit_import_preserves_provenance_mapping_and_unknown_names() -> None:
    imported = import_explicit_metrics(
        _raw(),
        source_tool="vllm",
        source_tool_version="0.30.0",
        raw_artifact_digest="sha256:" + "a" * 64,
        field_mapping=_mapping(),
    )
    assert imported.metrics["ttft"].value == Decimal("12.5")
    assert imported.metrics["ttft"].sample_count == 100
    assert imported.unknown_fields == ("vendor_extension",)
    document = imported.to_dict()
    assert document["source_tool_version"] == "0.30.0"
    assert document["raw_artifact_digest_status"] == "claimed_external_unverified"
    assert document["field_mapping"]["ttft"]["source_field"] == "p95_ttft_ms"


def test_importer_computes_local_digest_and_rejects_claim_mismatch() -> None:
    artifact = b"local benchmark artifact"
    imported = import_explicit_metrics(
        _raw(),
        source_tool="vllm",
        source_tool_version="0.30.0",
        field_mapping=_mapping(),
        raw_artifact_bytes=artifact,
    )
    expected = "sha256:" + hashlib.sha256(artifact).hexdigest()
    assert imported.raw_artifact_digest == expected
    assert imported.raw_artifact_digest_status == "locally_verified"

    with pytest.raises(InputError, match="does not match locally computed digest"):
        import_explicit_metrics(
            _raw(),
            source_tool="vllm",
            source_tool_version="0.30.0",
            field_mapping=_mapping(),
            raw_artifact_digest="sha256:" + "a" * 64,
            raw_artifact_bytes=artifact,
        )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"raw_artifact_digest": "sha256:not-a-digest"}, "sha256 digest"),
        ({"field_mapping": {}}, "cannot be empty"),
        (
            {
                "field_mapping": {
                    "ttft": {"source_field": "missing", "unit": "ms", "statistic": "p95"}
                }
            },
            "absent",
        ),
    ],
)
def test_import_contract_rejects_ambiguous_or_incomplete_artifacts(
    changes: dict[str, object], message: str
) -> None:
    kwargs: dict[str, object] = {
        "source_tool": "vllm",
        "source_tool_version": "0.30.0",
        "raw_artifact_digest": "sha256:" + "a" * 64,
        "field_mapping": _mapping(),
    }
    kwargs.update(changes)
    with pytest.raises(InputError, match=message):
        import_explicit_metrics(_raw(), **kwargs)


def test_importer_never_maps_by_similar_name() -> None:
    mapping = {"latency": {"source_field": "p95_ttft_ms", "unit": "ms", "statistic": "p95"}}
    imported = import_explicit_metrics(
        _raw(),
        source_tool="fixture",
        source_tool_version="1",
        raw_artifact_digest="sha256:" + "b" * 64,
        field_mapping=mapping,
    )
    assert "latency" in imported.metrics
    assert imported.metrics["latency"].statistic == "p95"
