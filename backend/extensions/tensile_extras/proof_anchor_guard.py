"""Read-only verification of the paired proof anchor on a plastic curve.

The true-plastic conversion writes the proof point as ``x=0`` and
``stress_true=proof_stress * (1 + proof_strain)``.  A later duplicate policy
can replace that row without changing the x coordinate.  This opt-in stage
checks the row after sorting and stops before any monotone lift or resampling
can hide the replacement.

The stress comparison accepts only a fixed floating-point roundoff allowance:
``64 \N{MULTIPLICATION SIGN} float64 epsilon \N{MULTIPLICATION SIGN} scale``,
where ``scale`` is the larger of 1, the expected magnitude, and the observed
magnitude.  The same bound with ``scale=1`` is used for the zero-origin check.
These constants are numerical safeguards, not data-tuned engineering
tolerances.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

DEFAULT_X = "strain_true_plastic"
DEFAULT_STRESS = "stress_true"
ROUND_OFF_EPSILON_MULTIPLIER = 64.0
_FLOAT_EPSILON = np.finfo(np.float64).eps
ROUND_OFF_BOUND_DESCRIPTION = (
    "64 \N{MULTIPLICATION SIGN} float64 epsilon \N{MULTIPLICATION SIGN} scale"
)
ORIGIN_ROUNDOFF_TOLERANCE = ROUND_OFF_EPSILON_MULTIPLIER * _FLOAT_EPSILON
OPTION_KEYS = frozenset({"proof_stress", "proof_strain", "x", "stress"})


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill the plastic-axis defaults and reject misspelled options."""
    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"proof anchor guard에 알 수 없는 옵션이 있습니다: {names}.")
    prepared.setdefault("x", DEFAULT_X)
    prepared.setdefault("stress", DEFAULT_STRESS)
    return prepared


def proof_anchor_guard(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Verify the first true stress against its independent proof formula.

    The input frame is returned by identity.  No column is sorted, copied back,
    clipped, or otherwise changed by this stage.
    """
    options = prepare_options(options)
    x_key = _column_name(options, "x", DEFAULT_X)
    stress_key = _column_name(options, "stress", DEFAULT_STRESS)
    if x_key == stress_key:
        raise ProcessingError("proof anchor guard의 x 열과 응력 열은 서로 달라야 합니다.")

    proof_stress = _finite_number(options.get("proof_stress"), "proof_stress")
    if proof_stress <= 0.0:
        raise ProcessingError(f"proof_stress는 양수여야 합니다: {proof_stress:.9g} Pa.")
    proof_strain = _finite_number(options.get("proof_strain"), "proof_strain")
    if proof_strain < 0.0:
        raise ProcessingError(f"proof_strain은 0 이상이어야 합니다: {proof_strain:.9g}.")

    _require_unit(frame, x_key, "1", "x")
    _require_unit(frame, stress_key, "Pa", "응력")
    x = _numeric_column(frame, x_key, "x")
    stress = _numeric_column(frame, stress_key, "응력")
    if x.size != stress.size:
        raise ProcessingError(
            f"proof anchor guard의 x·응력 열 길이가 서로 다릅니다 ({x.size} 대 {stress.size})."
        )
    if x.size == 0:
        raise ProcessingError("proof anchor guard에 입력 행이 없습니다.")

    if np.any(np.diff(x) <= 0.0):
        raise ProcessingError(
            f"'{x_key}'은 엄격히 증가해야 합니다. proof anchor guard는 정렬·중복 제거를 "
            "하지 않습니다."
        )
    origin = float(x[0])
    if abs(origin) > ORIGIN_ROUNDOFF_TOLERANCE:
        raise ProcessingError(
            f"'{x_key}'의 첫 값은 0이어야 합니다: 관측 {origin:.9g}, 예상 0, "
            f"차이 {origin:+.9g}. 허용값은 고정된 부동소수점 반올림 폭 "
            f"{ORIGIN_ROUNDOFF_TOLERANCE:.3g} 이하입니다."
        )

    with np.errstate(over="ignore", invalid="ignore"):
        expected = proof_stress * (1.0 + proof_strain)
    if not math.isfinite(expected):
        raise ProcessingError("proof_stress·(1+proof_strain) 계산 결과가 유한하지 않습니다.")

    observed = float(stress[0])
    error = observed - expected
    tolerance = _stress_roundoff_tolerance(expected, observed)
    if abs(error) > tolerance:
        raise ProcessingError(
            "proof anchor의 첫 진응력이 일치하지 않습니다: "
            f"관측 {observed:.9g} Pa, 예상 {expected:.9g} Pa, "
            f"차이(관측-예상) {error:+.9g} Pa ({error / 1e6:+.9g} MPa), "
            f"고정 반올림 허용값 {tolerance:.3g} Pa를 초과했습니다."
        )

    effective_options = {
        "proof_stress": proof_stress,
        "proof_strain": proof_strain,
        "x": x_key,
        "stress": stress_key,
    }
    notes = (
        f"proof anchor 검증 통과: '{x_key}' 첫 값 {origin:.9g}는 0의 고정 "
        f"반올림 허용값 안이고, '{stress_key}' 관측 {observed:.9g} Pa와 "
        f"예상 {expected:.9g} Pa의 차이 {error:+.9g} Pa도 "
        f"{ROUND_OFF_BOUND_DESCRIPTION} bound 이내입니다.",
        "읽기 전용 단계라 입력 Frame과 모든 열 값을 변경하지 않았습니다. "
        "단조화·재샘플링 전에 proof anchor를 확인합니다.",
    )
    scalars = (
        Scalar("proof_anchor_expected_stress", "proof anchor 예상 진응력", expected, "Pa"),
        Scalar("proof_anchor_observed_stress", "proof anchor 관측 진응력", observed, "Pa"),
        Scalar("proof_anchor_error_pa", "proof anchor 차이 (관측-예상)", error, "Pa"),
        Scalar("proof_anchor_verified_code", "proof anchor 검증 상태 (1=검증)", 1.0, "1"),
    )
    return StepResult(
        frame,
        notes=notes,
        scalars=scalars,
        effective_options=effective_options,
    )


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"proof anchor guard의 '{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다."
        )
    return value


def _require_unit(frame: Frame, name: str, expected: str, what: str) -> None:
    frame.require(name, what=what)
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"proof anchor guard의 {what} 열 '{name}' 단위는 '{expected}' 이어야 합니다. "
            f"현재: {shown}."
        )


def _numeric_column(frame: Frame, key: str, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(key, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 숫자 배열로 읽을 수 없습니다.") from None
    if raw.ndim != 1 or np.iscomplexobj(raw) or not np.issubdtype(raw.dtype, np.number):
        raise ProcessingError(f"'{key}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        numeric = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 실수형 숫자로 읽을 수 없습니다.") from None
    if not np.all(np.isfinite(numeric)):
        raise ProcessingError(f"'{key}' {what} 열에 유한하지 않은 값이 있습니다.")
    return numeric


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.") from None
    if not math.isfinite(number):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    return number


def _stress_roundoff_tolerance(expected: float, observed: float) -> float:
    scale = max(1.0, abs(expected), abs(observed))
    return ROUND_OFF_EPSILON_MULTIPLIER * _FLOAT_EPSILON * scale
