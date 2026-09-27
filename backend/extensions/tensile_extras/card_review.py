"""Read-only boundary evidence between numerical processing and card review.

This opt-in stage consumes diagnostics emitted by earlier processing steps.  It
does not change the curve or approve a material card, a material property, or a
solver deck.  Its only purpose is to make the numerical causes that require a
human card review explicit at the boundary before resampling.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

MODEL_CHANGED_POINTS = "model_card_changed_points"
BEYOND_SOURCE_NECK = "card_domain_beyond_source_neck"
EFFECT_INFO_KNOWN = "card_domain_effect_info_known"
EFFECT_TRUNCATED = "card_domain_effect_truncated"
MONOTONE_POINTS = "monotone_points"
MONOTONE_MAX_LIFT = "monotone_max_lift"

OPTION_KEYS = frozenset(
    {
        MODEL_CHANGED_POINTS,
        BEYOND_SOURCE_NECK,
        EFFECT_INFO_KNOWN,
        EFFECT_TRUNCATED,
        MONOTONE_POINTS,
        MONOTONE_MAX_LIFT,
    }
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Wire every required diagnostic to its upstream scalar by default."""

    prepared = dict(options)
    _reject_unknown(prepared)
    for name in OPTION_KEYS:
        reference = f"@{name}"
        if name in prepared and (
            not isinstance(prepared[name], str) or prepared[name] != reference
        ):
            raise ProcessingError(
                f"카드 검토 evidence의 '{name}' 옵션은 upstream 참조 {reference!r}만 "
                "허용합니다. 숫자나 다른 참조를 직접 넣지 마세요."
            )
        prepared[name] = reference
    return prepared


def card_review_evidence(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Emit card-review causes while returning ``frame`` by exact identity.

    All six inputs are required.  A missing or malformed upstream diagnostic is
    an error rather than an assumed zero, because zero here would falsely make
    an incomplete numerical history look safe to review.
    """

    _reject_unknown(options)
    changed_points = _count(options, MODEL_CHANGED_POINTS)
    beyond_source_neck = _binary(options, BEYOND_SOURCE_NECK)
    effect_info_known = _binary(options, EFFECT_INFO_KNOWN)
    effect_truncated = _binary(options, EFFECT_TRUNCATED)
    monotone_points = _count(options, MONOTONE_POINTS)
    monotone_max_lift = _nonnegative(options, MONOTONE_MAX_LIFT)
    _validate_monotone_consistency(monotone_points, monotone_max_lift)

    model_edit = int(changed_points > 0)
    scope = int(
        beyond_source_neck
        or effect_truncated
        or (not effect_info_known and changed_points > 0)
    )
    monotone_adjust = int(monotone_points > 0)
    observed_risk = int(bool(model_edit or scope or monotone_adjust))

    notes = (
        "수치 후보가 있어 카드 검토가 필요합니다. 이 단계는 읽기 전용 경계 증거이며 "
        "물리 타당성 승인과 별개입니다.",
        "effect_info_known=0은 model stress changed but effect scope metadata absent인 "
        "경우에만 범위 원인으로 반영합니다. 모델 응력이 바뀌지 않은 uniform source-neck "
        "후보의 선택적 metadata 부재는 그 자체로 범위 위험이 아닙니다.",
        "card_review_observed_risk_code=0 은 관측된 자동 처리 원인이 없다는 뜻일 뿐, "
        "카드 승인·재료 승인·solver 승인이 아닙니다 (0 is not card/material/solver approval).",
        f"monotone_max_lift={monotone_max_lift:.12g}는 단조 보정의 최대 절대 변화 진단이며 "
        "positive lift 승인값이 아닙니다 (absolute change diagnostic, not positive lift).",
    )
    scalars = (
        Scalar(
            "card_review_required_code",
            "카드 검토 필요 상태 (1=수치 후보)",
            1.0,
            "1",
        ),
        Scalar(
            "card_review_model_edit_code",
            "카드 검토 모델 변경 원인 (1=변경점 있음)",
            float(model_edit),
            "1",
        ),
        Scalar(
            "card_review_scope_code",
            (
                "카드 검토 범위 원인 (1=모델 응력 변경·"
                "effect scope metadata absent 또는 범위 초과)"
            ),
            float(scope),
            "1",
        ),
        Scalar(
            "card_review_monotone_adjust_code",
            "카드 검토 단조 보정 원인 (1=보정점 있음)",
            float(monotone_adjust),
            "1",
        ),
        Scalar(
            "card_review_observed_risk_code",
            "카드 검토 관측 위험 상태 (1=원인 있음)",
            float(observed_risk),
            "1",
        ),
    )
    return StepResult(frame, notes=notes, scalars=scalars)


def _number(options: dict[str, Any], name: str) -> float:
    value = options.get(name)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.") from None
    if not math.isfinite(result):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.")
    return result


def _count(options: dict[str, Any], name: str) -> int:
    value = _number(options, name)
    if value < 0.0 or not value.is_integer():
        raise ProcessingError(f"'{name}' 는 0 이상인 정수여야 합니다.")
    return int(value)


def _binary(options: dict[str, Any], name: str) -> int:
    value = _number(options, name)
    if value not in (0.0, 1.0):
        raise ProcessingError(f"'{name}' 는 정확히 0 또는 1이어야 합니다.")
    return int(value)


def _nonnegative(options: dict[str, Any], name: str) -> float:
    value = _number(options, name)
    if value < 0.0:
        raise ProcessingError(f"'{name}' 는 0 이상이어야 합니다.")
    return value


def _validate_monotone_consistency(points: int, max_lift: float) -> None:
    points_zero = points == 0
    max_zero = max_lift == 0.0
    if points_zero != max_zero:
        raise ProcessingError(
            "'monotone_points' 와 'monotone_max_lift' 가 일관되지 않습니다: "
            f"점 수={points}, 최대 절대 변화={max_lift:.12g}. "
            "점 수가 0이면 최대 변화도 정확히 0이어야 합니다."
        )


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = sorted(set(options) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"카드 검토 evidence에 알 수 없는 옵션이 있습니다: {names}.")


__all__ = ["card_review_evidence", "prepare_options"]
