"""모델 소성 시작점 — 오프셋 교점을 별도 값으로 보존한다."""

from __future__ import annotations

from typing import Any

from matcore.processing import Frame, Scalar, StepResult
from matcore.processing.tensile import proof_stress


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Use the pipeline's measured modulus only when the recipe omitted E."""
    prepared = dict(options)
    if "youngs_modulus" not in prepared:
        prepared["youngs_modulus"] = "@youngs_modulus"
    return prepared


def model_anchor(frame: Frame, options: dict[str, Any]) -> StepResult:
    """내장 오프셋 계산을 재사용하되 모델 시작점 이름으로 값만 낸다."""
    result = proof_stress(frame, options)
    labels = {
        "proof_stress": "모델 소성 시작 응력",
        "proof_strain": "모델 소성 시작 변형률",
        "proof_offset": "모델 소성 시작 오프셋",
    }
    scalars = tuple(
        Scalar(
            f"model_{value.key}",
            labels[value.key],
            value.value,
            value.si_unit,
            value.dimension,
        )
        for value in result.scalars
    )
    note = "이 교점은 모델 소성 곡선의 시작점이며, 원곡선에서 계산한 Rp 를 대체하지 않습니다."
    return StepResult(
        frame=result.frame,
        notes=(*result.notes, note),
        scalars=scalars,
        effective_options=result.effective_options,
    )
