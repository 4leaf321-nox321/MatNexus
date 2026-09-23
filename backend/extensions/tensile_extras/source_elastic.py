"""Elastic modulus on a source-row interval, without changing the input frame."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult
from matcore.processing.tensile import elastic_modulus as _core_elastic_modulus

AUTO_POLICY = "auto_rows_v1"
MANUAL_POLICY = "manual_rows"
POLICIES = (AUTO_POLICY, MANUAL_POLICY)
AUTO_LOW_FRACTION = 0.10
AUTO_HIGH_FRACTION = 0.40
MIN_FIT_ROWS = 5
MIN_R_SQUARED = 0.98

_STRAIN = "strain_engineering"
_STRESS = "stress_engineering"
_EPS = np.finfo(np.float64).eps
_TINY = np.finfo(np.float64).tiny


@dataclass(frozen=True)
class _RawFit:
    count: int
    strain_low: float | None
    strain_high: float | None
    slope: float | None
    intercept: float | None
    r_squared: float | None
    accepted: bool
    reason: str


def source_elastic_modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Measure E on original acquired rows and return the exact input frame.

    ``auto_rows_v1`` uses the first global stress maximum and the original-row
    envelope of pre-peak rows in the 10--40% stress band. A globally strict
    strain input delegates to the existing public elastic-modulus function so
    its scalar and note behavior remains exact. Non-strict inputs fit the
    complete envelope in acquisition order, including any local reversals.
    """
    policy = _validated_policy(options)
    strain_key, stress_key = _channel_keys(options)
    strain, stress = _pair(frame, strain_key, stress_key)

    if policy == AUTO_POLICY:
        if not np.all(np.isfinite(stress)):
            raise ProcessingError(
                "원행 자동 탄성 창의 최대 응력을 고를 수 없습니다 — 응력 열에 "
                "유한하지 않은 값이 있습니다. 결측 행을 조용히 건너뛰지 않습니다."
            )
        members = _band_members(stress)
        if _strictly_increasing(strain):
            core = _core_elastic_modulus(
                frame,
                {"method": "auto", "strain": strain_key, "stress": stress_key},
            )
            return _augment_core_result(
                frame,
                core,
                policy=policy,
                strain_key=strain_key,
                stress_key=stress_key,
                source_rows=members,
                strain=strain,
            )
        if members.size == 0:
            return _no_band_result(
                frame,
                policy=policy,
                strain_key=strain_key,
                stress_key=stress_key,
            )
        if members.size < MIN_FIT_ROWS:
            return _short_band_result(
                frame,
                policy=policy,
                strain_key=strain_key,
                stress_key=stress_key,
                members=members,
                strain=strain,
            )
        start_index = int(members[0])
        end_index = int(members[-1])
    else:
        start_index = _row_index(options.get("start_index"), name="start_index")
        end_index = _row_index(options.get("end_index"), name="end_index")
        if start_index > end_index:
            raise ProcessingError(
                f"수동 원행 탄성 구간 시작({start_index})은 "
                f"끝({end_index})보다 클 수 없습니다."
            )
        if end_index >= strain.size:
            raise ProcessingError(
                f"수동 원행 탄성 구간 끝({end_index})이 현재 입력의 마지막 행 "
                f"{strain.size - 1}을 벗어납니다."
            )

    rows = np.arange(start_index, end_index + 1, dtype=np.int64)
    fit_strain = strain[rows]
    fit_stress = stress[rows]
    _require_finite_pairs(fit_strain, fit_stress, start_index, end_index)

    # A hand-selected interval can use the core implementation when that
    # interval itself is strictly increasing, even if another part of the
    # source input is not.
    if (
        policy == MANUAL_POLICY
        and fit_strain.size >= MIN_FIT_ROWS
        and _strictly_increasing(fit_strain)
    ):
        selected_frame = frame.select(rows)
        low = float(np.min(fit_strain))
        high = float(np.max(fit_strain))
        core = _core_elastic_modulus(
            selected_frame,
            {
                "method": "linear_regression",
                "minimum_strain": low,
                "maximum_strain": high,
                "strain": strain_key,
                "stress": stress_key,
            },
        )
        return _augment_core_result(
            frame,
            core,
            policy=policy,
            strain_key=strain_key,
            stress_key=stress_key,
            source_rows=rows,
            strain=strain,
            selected_rows=(start_index, end_index),
        )

    fit = _centered_ols(fit_strain, fit_stress)
    nonincreasing_steps = _nonincreasing_steps(fit_strain)
    output_scalars = _raw_scalars(
        fit,
        start_index=start_index,
        end_index=end_index,
        nonincreasing_steps=nonincreasing_steps,
        include_window=True,
    )
    note = _raw_note(
        fit,
        policy=policy,
        start_index=start_index,
        end_index=end_index,
        nonincreasing_steps=nonincreasing_steps,
    )
    effective_options = _effective_options(
        policy, strain_key, stress_key, start_index=start_index, end_index=end_index
    )
    return StepResult(
        frame,
        notes=(note,),
        scalars=output_scalars,
        effective_options=effective_options,
    )


def _policy(options: dict[str, Any]) -> str:
    policy = options.get("policy", AUTO_POLICY)
    if policy not in POLICIES:
        raise ProcessingError(
            f"원행 탄성 정책은 {', '.join(POLICIES)} 중 하나여야 합니다: {policy!r}."
        )
    return str(policy)


def _validated_policy(options: dict[str, Any]) -> str:
    policy = _policy(options)
    if policy == AUTO_POLICY and ("start_index" in options or "end_index" in options):
        raise ProcessingError(
            "자동 원행 탄성 정책에서는 start_index와 end_index를 지정할 수 없습니다."
        )
    allowed = {"policy", "strain", "stress"}
    if policy == MANUAL_POLICY:
        allowed.update(("start_index", "end_index"))
    unknown = set(options) - allowed
    if unknown:
        names = ", ".join(sorted(repr(name) for name in unknown))
        raise ProcessingError(f"원행 탄성 단계에 알 수 없는 옵션이 있습니다: {names}.")
    return policy


def _channel_keys(options: dict[str, Any]) -> tuple[str, str]:
    strain_key = _channel_name(options, "strain", _STRAIN)
    stress_key = _channel_name(options, "stress", _STRESS)
    return strain_key, stress_key


def _channel_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(f"'{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _pair(frame: Frame, strain_key: str, stress_key: str) -> tuple[np.ndarray, np.ndarray]:
    strain_unit = frame.units.get(strain_key)
    stress_unit = frame.units.get(stress_key)
    if strain_unit not in (None, "1"):
        raise ProcessingError(
            f"'{strain_key}' 는 무차원 변형률이어야 하는데 단위가 '{strain_unit}' 입니다."
        )
    if stress_unit not in (None, "Pa"):
        raise ProcessingError(
            f"'{stress_key}' 는 Pa 여야 하는데 단위가 '{stress_unit}' 입니다."
        )
    try:
        strain = np.asarray(frame.require(strain_key, what="변형률"), dtype=np.float64)
        stress = np.asarray(frame.require(stress_key, what="응력"), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ProcessingError("원행 탄성 창의 변형률·응력은 실수 배열이어야 합니다.") from exc
    if strain.ndim != 1 or stress.ndim != 1 or strain.size != stress.size:
        raise ProcessingError("원행 탄성 창의 변형률·응력 열 길이가 서로 맞지 않습니다.")
    if strain.size == 0:
        raise ProcessingError("원행 탄성 창에 입력 행이 없습니다.")
    return strain, stress


def _band_members(stress: np.ndarray) -> np.ndarray:
    peak_index = int(np.argmax(stress))
    peak = float(stress[peak_index])
    if not math.isfinite(peak) or peak <= 0:
        return np.empty(0, dtype=np.int64)
    prefix = stress[: peak_index + 1]
    inside = (prefix >= AUTO_LOW_FRACTION * peak) & (prefix <= AUTO_HIGH_FRACTION * peak)
    return np.flatnonzero(inside).astype(np.int64, copy=False)


def _strictly_increasing(values: np.ndarray) -> bool:
    return bool(
        values.size > 0 and np.all(np.isfinite(values)) and np.all(np.diff(values) > 0)
    )


def _row_index(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ProcessingError(f"수동 원행 {name}은 유한한 정수 인덱스여야 합니다.")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ProcessingError(f"수동 원행 {name}은 유한한 정수 인덱스여야 합니다.") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ProcessingError(f"수동 원행 {name}은 유한한 정수 인덱스여야 합니다.")
    index = int(numeric)
    if index < 0:
        raise ProcessingError(f"수동 원행 {name}은 0 이상이어야 합니다: {index}.")
    return index


def _require_finite_pairs(
    strain: np.ndarray, stress: np.ndarray, start_index: int, end_index: int
) -> None:
    if not np.all(np.isfinite(strain)) or not np.all(np.isfinite(stress)):
        raise ProcessingError(
            f"원행 탄성 구간 [{start_index}, {end_index}]에 유한하지 않은 변형률·응력이 "
            "있습니다. 해당 행을 조용히 제외하지 않습니다."
        )


def _centered_ols(strain: np.ndarray, stress: np.ndarray) -> _RawFit:
    count = int(strain.size)
    if count == 0:
        return _RawFit(0, None, None, None, None, None, False, "선택된 원행이 없습니다")

    low = float(np.min(strain))
    high = float(np.max(strain))
    span = float(strain[-1] - strain[0])
    mean_x = float(np.mean(strain))
    mean_y = float(np.mean(stress))
    centered_x = strain - mean_x
    centered_y = stress - mean_y
    sxx = float(np.dot(centered_x, centered_x))
    if not math.isfinite(sxx) or not math.isfinite(mean_x) or not math.isfinite(mean_y):
        raise ProcessingError("원행 최소제곱 계산 중 유한하지 않은 중심값이 생겼습니다.")

    slope: float | None = None
    intercept: float | None = None
    r_squared: float | None = None
    if sxx > 0:
        sxy = float(np.dot(centered_x, centered_y))
        slope = sxy / sxx
        intercept = mean_y - slope * mean_x
        if not math.isfinite(sxy) or not math.isfinite(slope) or not math.isfinite(intercept):
            raise ProcessingError("원행 최소제곱 기울기·절편이 유한하지 않습니다.")
        residual = stress - (slope * strain + intercept)
        sse = float(np.dot(residual, residual))
        sst = float(np.dot(centered_y, centered_y))
        if not math.isfinite(sse) or not math.isfinite(sst):
            raise ProcessingError("원행 최소제곱 잔차가 유한하지 않습니다.")
        if sst > 0:
            r_squared = 1.0 - sse / sst
            if not math.isfinite(r_squared):
                raise ProcessingError("원행 최소제곱 R²가 유한하지 않습니다.")

    reasons: list[str] = []
    if count < MIN_FIT_ROWS:
        reasons.append(f"원행이 {count}개라 최소 {MIN_FIT_ROWS}개보다 적음")
    distinct = int(np.unique(strain).size)
    if distinct < MIN_FIT_ROWS:
        reasons.append(f"서로 다른 변형률이 {distinct}개라 최소 {MIN_FIT_ROWS}개보다 적음")
    if not math.isfinite(span) or span <= 0:
        reasons.append("첫 행에서 끝 행까지 변형률 폭이 양수가 아님")

    x_scale = float(np.max(np.abs(strain)))
    sxx_floor = _EPS * count * max(x_scale * x_scale, span * span, _TINY)
    if not math.isfinite(sxx_floor) or sxx <= sxx_floor:
        reasons.append("중심 변형률 제곱합이 수치 하한 이하임")

    slope_floor = math.inf
    if span > 0:
        y_scale = max(float(np.max(np.abs(stress))), 1.0)
        slope_floor = _EPS * count * y_scale / span
    if slope is None or not math.isfinite(slope) or slope <= slope_floor:
        reasons.append("기울기가 유한한 양수 수치 하한을 넘지 않음")
    if r_squared is None or r_squared < MIN_R_SQUARED:
        reasons.append(f"R²가 {MIN_R_SQUARED:.2f} 이상이 아님")

    return _RawFit(
        count=count,
        strain_low=low,
        strain_high=high,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        accepted=not reasons,
        reason="; ".join(reasons) if reasons else "",
    )


def _augment_core_result(
    frame: Frame,
    core: StepResult,
    *,
    policy: str,
    strain_key: str,
    stress_key: str,
    source_rows: np.ndarray,
    strain: np.ndarray,
    selected_rows: tuple[int, int] | None = None,
) -> StepResult:
    start_index: int | None
    end_index: int | None
    if selected_rows is None and source_rows.size:
        start_index, end_index = int(source_rows[0]), int(source_rows[-1])
    else:
        start_index, end_index = selected_rows or (None, None)

    extra: list[Scalar] = []
    nonincreasing_steps = 0
    if start_index is not None and end_index is not None:
        selected_strain = strain[start_index : end_index + 1]
        nonincreasing_steps = _nonincreasing_steps(selected_strain)
        extra.extend(_provenance_scalars(start_index, end_index, nonincreasing_steps))
    else:
        extra.append(
            Scalar(
                "source_elastic_nonincreasing_step_count",
                "원행 E 구간 비증가 단계 수",
                0.0,
                "1",
            )
        )

    provenance = _provenance_note(
        policy,
        strain_key,
        stress_key,
        start_index,
        end_index,
        nonincreasing_steps,
    )
    return StepResult(
        frame,
        notes=(*core.notes, provenance),
        scalars=(*core.scalars, *extra),
        effective_options=_effective_options(
            policy,
            strain_key,
            stress_key,
            start_index=start_index,
            end_index=end_index,
        ),
    )


def _no_band_result(
    frame: Frame, *, policy: str, strain_key: str, stress_key: str
) -> StepResult:
    note = (
        "최대 응력의 10~40% 구간에 원행 지지점이 없어 탄성계수를 내지 않았습니다. "
        "다른 구간을 대신 고르지 않았습니다."
    )
    return StepResult(
        frame,
        notes=(note, _provenance_note(policy, strain_key, stress_key, None, None, 0)),
        scalars=(
            Scalar("elastic_point_count", "탄성 구간 점 수", 0.0, "1"),
            Scalar(
                "source_elastic_nonincreasing_step_count",
                "원행 E 구간 비증가 단계 수",
                0.0,
                "1",
            ),
        ),
        effective_options=_effective_options(policy, strain_key, stress_key),
    )


def _short_band_result(
    frame: Frame,
    *,
    policy: str,
    strain_key: str,
    stress_key: str,
    members: np.ndarray,
    strain: np.ndarray,
) -> StepResult:
    start_index = int(members[0])
    end_index = int(members[-1])
    selected_strain = strain[start_index : end_index + 1]
    if not np.all(np.isfinite(selected_strain)):
        raise ProcessingError(
            f"원행 탄성 구간 [{start_index}, {end_index}]에 유한하지 않은 변형률이 "
            "있습니다. 해당 행을 조용히 제외하지 않습니다."
        )
    nonincreasing_steps = _nonincreasing_steps(selected_strain)
    return StepResult(
        frame,
        notes=(
            f"최대 응력의 10~40% 원행 지지점이 {members.size}개로 최소 "
            f"{MIN_FIT_ROWS}개보다 적어 탄성계수를 내지 않았습니다. "
            "더 넓은 구간이나 다른 원행을 대신 고르지 않았습니다.",
            _provenance_note(
                policy,
                strain_key,
                stress_key,
                start_index,
                end_index,
                nonincreasing_steps,
            ),
        ),
        scalars=(
            Scalar("elastic_point_count", "탄성 구간 점 수", float(members.size), "1"),
            *_provenance_scalars(start_index, end_index, nonincreasing_steps),
        ),
        effective_options=_effective_options(
            policy,
            strain_key,
            stress_key,
            start_index=start_index,
            end_index=end_index,
        ),
    )


def _raw_scalars(
    fit: _RawFit,
    *,
    start_index: int,
    end_index: int,
    nonincreasing_steps: int,
    include_window: bool,
) -> tuple[Scalar, ...]:
    scalars = [
        Scalar("elastic_point_count", "탄성 구간 점 수", float(fit.count), "1"),
        *_provenance_scalars(start_index, end_index, nonincreasing_steps),
    ]
    if include_window and fit.strain_low is not None and fit.strain_high is not None:
        scalars.extend(
            (
                Scalar("elastic_window_start", "탄성 구간 시작", fit.strain_low, "1"),
                Scalar("elastic_window_end", "탄성 구간 끝", fit.strain_high, "1"),
            )
        )
    if fit.slope is not None and math.isfinite(fit.slope):
        if fit.accepted:
            assert fit.intercept is not None
            scalars.extend(
                (
                    Scalar("youngs_modulus", "탄성계수", fit.slope, "Pa"),
                    Scalar("elastic_intercept", "탄성 절편", fit.intercept, "Pa"),
                )
            )
        else:
            scalars.append(
                Scalar("elastic_slope_reference", "참고 기울기(믿을 수 없음)", fit.slope, "Pa")
            )
    if fit.r_squared is not None and fit.count >= MIN_FIT_ROWS:
        scalars.append(Scalar("elastic_r_squared", "탄성 구간 R²", fit.r_squared, "1"))
    return tuple(scalars)


def _raw_note(
    fit: _RawFit,
    *,
    policy: str,
    start_index: int,
    end_index: int,
    nonincreasing_steps: int,
) -> str:
    prefix = (
        f"{policy}: 현재 입력 원행 [{start_index}, {end_index}]의 {fit.count}개를 "
        f"원래 순서로 적합했습니다(비증가 단계 {nonincreasing_steps}개)."
    )
    if fit.accepted and fit.slope is not None and fit.r_squared is not None:
        return (
            f"{prefix} 기울기 {fit.slope / 1e9:.6g} GPa, "
            f"R²={fit.r_squared:.6f}. 원행은 유지했으며 이 값은 자동으로 물성 타당성을 "
            "판정하지 않습니다."
        )
    details = fit.reason or "수치 조건을 만족하지 못함"
    if fit.slope is not None and fit.r_squared is not None:
        return (
            f"{prefix} 탄성계수를 내지 않았습니다: {details}. "
            f"참고 기울기 {fit.slope / 1e9:.6g} GPa, R²={fit.r_squared:.6f}."
        )
    return f"{prefix} 탄성계수를 내지 않았습니다: {details}."


def _provenance_scalars(
    start_index: int, end_index: int, nonincreasing_steps: int
) -> tuple[Scalar, ...]:
    return (
        Scalar(
            "source_elastic_start_index",
            "원행 E 시작 인덱스 (현재 입력, 0부터)",
            float(start_index),
            "1",
        ),
        Scalar(
            "source_elastic_end_index",
            "원행 E 끝 인덱스 (현재 입력, 0부터)",
            float(end_index),
            "1",
        ),
        Scalar(
            "source_elastic_nonincreasing_step_count",
            "원행 E 구간 비증가 단계 수",
            float(nonincreasing_steps),
            "1",
        ),
    )


def _nonincreasing_steps(strain: np.ndarray) -> int:
    return int(np.count_nonzero(np.diff(strain) <= 0)) if strain.size > 1 else 0


def _provenance_note(
    policy: str,
    strain_key: str,
    stress_key: str,
    start_index: int | None,
    end_index: int | None,
    nonincreasing_steps: int,
) -> str:
    if start_index is None or end_index is None:
        bounds = "선택된 원행 구간 없음"
    else:
        bounds = f"현재 입력 원행 [{start_index}, {end_index}]"
    return (
        f"원행 탄성 정책 {policy} (v1), {bounds}; 변형률 열 '{strain_key}', "
        f"응력 열 '{stress_key}', 비증가 단계 {nonincreasing_steps}개. "
        "인덱스는 현재 입력 프레임 기준이며 원본 행 배열은 바꾸지 않았습니다."
    )


def _effective_options(
    policy: str,
    strain_key: str,
    stress_key: str,
    *,
    start_index: int | None = None,
    end_index: int | None = None,
) -> dict[str, Any]:
    effective: dict[str, Any] = {
        "policy": policy,
        "strain": strain_key,
        "stress": stress_key,
    }
    if policy == MANUAL_POLICY:
        if start_index is None or end_index is None:
            raise ProcessingError("수동 원행 탄성 재생 옵션에 경계가 없습니다.")
        effective["start_index"] = start_index
        effective["end_index"] = end_index
    return effective
