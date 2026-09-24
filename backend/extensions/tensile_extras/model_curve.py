"""Upper-envelope model curve for engineering tensile stress."""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_text

from .model_effect import effect_scalars

METHOD = "upper_envelope_auto_v1"
METHODS = (METHOD,)
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
FIXED_OPTIONS = {
    "domain": "all_input_rows",
    "tail_policy": "hold_running_max",
    "profile_version": "1",
}
OPTION_KEYS = frozenset({"method", "strain", "stress", *FIXED_OPTIONS})


def _options(options: dict[str, Any]) -> tuple[str, str, str, dict[str, str]]:
    unknown = sorted((key for key in options if key not in OPTION_KEYS), key=str)
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ProcessingError(f"지원하지 않는 소성 모델 공칭곡선 옵션입니다: {names}.")

    for key, expected in FIXED_OPTIONS.items():
        supplied_value = options.get(key)
        if key in options and (
            not isinstance(supplied_value, str) or supplied_value != expected
        ):
            raise ProcessingError(
                f"'{key}' 정책은 '{expected}' 로 고정되어 있습니다. "
                "이 레시피의 정책을 바꾸려면 별도 계산 방법이 필요합니다."
            )

    method = option_text(options, "method", METHODS)
    supplied = dict(options)
    supplied.setdefault("strain", DEFAULT_STRAIN)
    supplied.setdefault("stress", DEFAULT_STRESS)
    strain = option_text(supplied, "strain", ())
    stress = option_text(supplied, "stress", ())
    effective = {
        "method": method,
        "strain": strain,
        "stress": stress,
        **FIXED_OPTIONS,
    }
    return method, strain, stress, effective


def _numeric_column(frame: Frame, name: str, *, what: str) -> np.ndarray:
    raw = frame.require(name, what=what)
    try:
        values = np.asarray(raw)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"{what} 열 '{name}' 은 1차원 실수형 숫자 배열이어야 합니다."
        ) from None
    if values.ndim != 1:
        raise ProcessingError(f"{what} 열 '{name}' 은 1차원이어야 합니다.")
    if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
        raise ProcessingError(f"{what} 열 '{name}' 은 실수형 숫자여야 합니다.")
    try:
        numeric = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"{what} 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if not np.all(np.isfinite(numeric)):
        raise ProcessingError(f"{what} 열 '{name}' 에 유한하지 않은 값이 있습니다.")
    return numeric


def _require_unit(frame: Frame, name: str, expected: str, *, what: str) -> None:
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"{what} 열 '{name}' 의 단위는 '{expected}' 이어야 합니다. 현재 단위: {shown}. "
            "단위 변환은 이 단계에서 하지 않습니다."
        )


def model_curve(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Raise every engineering-stress drop to the preceding running maximum."""
    _, strain_name, stress_name, effective = _options(options)
    _require_unit(frame, strain_name, "1", what="변형률")
    _require_unit(frame, stress_name, "Pa", what="응력")

    strain = _numeric_column(frame, strain_name, what="변형률")
    stress = _numeric_column(frame, stress_name, what="응력")
    if len(strain) != len(stress):
        raise ProcessingError(
            f"변형률 열 '{strain_name}' 과 응력 열 '{stress_name}' 의 점 수가 다릅니다 "
            f"({len(strain)} 대 {len(stress)})."
        )
    if len(strain) < 2:
        raise ProcessingError("변형률과 응력은 원래 행 순서로 2점 이상 있어야 합니다.")
    if np.any(strain[1:] <= strain[:-1]):
        raise ProcessingError(
            f"변형률 열 '{strain_name}' 이 원래 행 순서에서 엄격히 증가하지 않습니다. "
            "원래 측정 행 순서를 검토하세요. 이 단계는 자동 정렬하지 않습니다."
        )
    if not np.any(stress > 0.0):
        raise ProcessingError(
            "응력 열에 양수인 값이 없습니다. 상측 포락선을 만들 수 없습니다."
        )

    # The operation is intentionally unconditional: no drop threshold gates it.
    envelope = np.maximum.accumulate(stress)
    changed = envelope != stress
    changed_points = int(np.count_nonzero(changed))
    with np.errstate(over="ignore", invalid="ignore"):
        raises = envelope - stress
    if not np.all(np.isfinite(raises)):
        raise ProcessingError(
            "포락선 응력 차이가 숫자 범위를 벗어나 진단값을 만들 수 없습니다."
        )

    peak_index = int(np.argmax(stress))
    peak_stress = float(stress[peak_index])
    peak_strain = float(strain[peak_index])
    max_raise = float(np.max(raises))
    end_raise = float(raises[-1])
    scalar_values = (
        ("model_curve_changed_points", float(changed_points), "1", None),
        ("model_curve_peak_stress", peak_stress, "Pa", None),
        ("model_curve_peak_strain", peak_strain, "1", "strain"),
        ("model_curve_peak_index", float(peak_index), "1", None),
        ("model_curve_max_raise", max_raise, "Pa", None),
        ("model_curve_end_raise", end_raise, "Pa", None),
    )
    if not all(np.isfinite(value) for _, value, _, _ in scalar_values):
        raise ProcessingError("상측 포락선의 진단값이 유한하지 않습니다.")

    result_frame = (
        frame.with_columns({stress_name: envelope}, {stress_name: "Pa"})
        if changed_points
        else frame
    )
    change_note = f"응력 변경 {changed_points}점" if changed_points else "응력 변경 없음"
    notes = (
        f"전체 입력 행의 공칭 변형률 구간 {strain[0]:.6g}~{strain[-1]:.6g} 에 "
        f"상측 포락선을 적용했습니다. {change_note}.",
        "기록된 끝은 물리적 파단점으로 추정하지 않으며, "
        "포락선 평탄부를 실제 완전소성으로 판정하지 않습니다.",
    )
    labels = {
        "model_curve_changed_points": "변경 점 수",
        "model_curve_peak_stress": "입력 응력 최댓값",
        "model_curve_peak_strain": "입력 응력 최댓값 변형률",
        "model_curve_peak_index": "입력 행 위치 (0부터)",
        "model_curve_max_raise": "최대 응력 올림 폭",
        "model_curve_end_raise": "기록 끝 응력 올림 폭",
    }
    scalars = tuple(
        Scalar(key, labels[key], value, unit, dimension)
        for key, value, unit, dimension in scalar_values
    )
    return StepResult(
        frame=result_frame,
        notes=notes,
        scalars=scalars + effect_scalars(strain, stress, envelope),
        effective_options=effective,
    )
