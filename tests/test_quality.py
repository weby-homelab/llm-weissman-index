from decimal import Decimal

import pytest

from llm_weissman.errors import InputError
from llm_weissman.models import Measurement, QualityObservation
from llm_weissman.profiles import Profile, QualityDefinition, load_profile
from llm_weissman.quality import aggregate_quality, transform_quality


def _observation(value: str, metric_id: str = "task_accuracy") -> QualityObservation:
    return QualityObservation(
        metric_id=metric_id,
        raw=Measurement(Decimal(value), "1", "mean", sample_count=100),
    )


def test_bounded_quality_uses_explicit_identity_transform() -> None:
    definition = load_profile("edge-v1").quality[0]
    assert transform_quality(_observation("0.8"), definition) == Decimal("0.8")


def test_zero_candidate_utility_is_explicit_and_not_epsilon() -> None:
    profile = load_profile("edge-v1")
    result = aggregate_quality(
        (_observation("0"),),
        (_observation("0.8"),),
        profile.quality,
    )
    assert result.candidate_aggregate == Decimal("0")
    assert result.quality_ratio == Decimal("0")
    assert result.log_ratio is None


def test_zero_baseline_utility_is_rejected() -> None:
    profile = load_profile("edge-v1")
    with pytest.raises(InputError, match="baseline quality utility"):
        aggregate_quality(
            (_observation("0.8"),),
            (_observation("0"),),
            profile.quality,
        )


def test_interval_scale_cannot_be_divided_without_transform() -> None:
    definition = QualityDefinition(
        metric_id="reward",
        weight=Decimal("1"),
        raw_direction="higher_is_better",
        scale_type="interval_scale",
        raw_unit="1",
        valid_range=(Decimal("0"), Decimal("100")),
        utility_transform="identity",
        utility_transform_version="1",
        utility_floor=Decimal("0"),
        utility_ceiling=Decimal("100"),
        source="test policy",
    )
    with pytest.raises(InputError, match="cannot use identity utility"):
        transform_quality(_observation("60", metric_id="reward"), definition)


def test_profile_digest_changes_when_policy_changes() -> None:
    profile = load_profile("edge-v1")
    changed = dict(profile.canonical_dict)
    changed["policy_statement"] = "changed policy"
    assert Profile.from_dict(changed).digest != profile.digest


def test_profile_rejects_conflicting_duplicate_metric_weights() -> None:
    profile = load_profile("edge-v1")
    changed = dict(profile.canonical_dict)
    changed["weights"] = {
        "quality": "0.55",
        "metrics": {"latency": "0.20", "throughput": "0.10", "peak_memory": "0.15"},
    }
    with pytest.raises(InputError, match="disagrees"):
        Profile.from_dict(changed)


def test_zero_weight_quality_task_cannot_zero_the_aggregate() -> None:
    profile = load_profile("edge-v1")
    zero_weight = QualityDefinition(
        metric_id="unused",
        weight=Decimal("0"),
        raw_direction="higher_is_better",
        scale_type="bounded_rate",
        raw_unit="1",
        valid_range=(Decimal("0"), Decimal("1")),
        utility_transform="identity",
        utility_transform_version="1",
        utility_floor=Decimal("0"),
        utility_ceiling=Decimal("1"),
        source="test",
    )
    result = aggregate_quality(
        (_observation("0.8"), _observation("0", metric_id="unused")),
        (_observation("0.8"), _observation("0", metric_id="unused")),
        (profile.quality[0], zero_weight),
    )
    assert result.quality_ratio == Decimal("1")
