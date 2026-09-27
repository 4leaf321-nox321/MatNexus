"""Record the first engineering peak while retaining the complete input frame.

The input may be a full engineering frame or a domain already selected by an
earlier stage.  This stage measures the first stress peak in its input, but it
is deliberately read-only: downstream source-order checks still need rows
after the peak when they are present.  A peak is usable only when the input
carries validated acquisition-row evidence and force/stress provide the same
positive peak under a positive proportional relationship.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

from .source_support_order_guard import _evidence_columns

DEFAULT_FORCE = "force"
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
OPTION_KEYS = frozenset({"force", "strain", "stress"})


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill source-channel defaults without mutating the recipe options."""

    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"source peak evidence에 알 수 없는 옵션이 있습니다: {names}.")
    prepared.setdefault("force", DEFAULT_FORCE)
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    return prepared


def source_peak_evidence(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Emit a source peak contract without selecting, sorting, or editing rows."""

    options = prepare_options(options)
    force_name = _column_name(options, "force", DEFAULT_FORCE)
    strain_name = _column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = _column_name(options, "stress", DEFAULT_STRESS)
    if len({force_name, strain_name, stress_name}) != 3:
        raise ProcessingError(
            "source peak evidence의 하중·변형률·응력 열은 서로 달라야 합니다."
        )

    force = _numeric_column(frame, force_name, "하중")
    strain = _numeric_column(frame, strain_name, "변형률")
    stress = _numeric_column(frame, stress_name, "응력")
    if force.size != strain.size or force.size != stress.size:
        raise ProcessingError(
            "source peak evidence의 하중·변형률·응력 열 행 수가 서로 다릅니다."
        )
    if force.size < 2:
        raise ProcessingError("source peak evidence에는 최소 2개 원행이 필요합니다.")
    _validate_frame_columns(frame, force.size)

    _require_unit(frame, force_name, "N", "하중")
    _require_unit(frame, strain_name, "1", "변형률")
    _require_unit(frame, stress_name, "Pa", "응력")

    evidence_columns = _evidence_columns(frame, force.size)
    if not evidence_columns:
        raise ProcessingError(
            "source peak evidence에는 취득 순서 증거 열이 필요합니다. "
            "source_row 또는 source_data_row/source_physical_line을 제공하세요."
        )

    stress_peak_index = int(np.argmax(stress))
    force_peak_index = int(np.argmax(force))
    if force_peak_index != stress_peak_index:
        raise ProcessingError(
            "원하중과 공칭응력의 첫 최대 위치가 일치하지 않아 source peak를 "
            "검증할 수 없습니다."
        )
    if stress_peak_index == 0:
        raise ProcessingError(
            "source peak evidence를 적용할 수 없습니다: 최대응력이 첫 원행에 있어 "
            "peak 앞 원행 지지가 부족합니다."
        )
    _validate_positive_proportional(
        force, stress, force_peak_index=force_peak_index, stress_peak_index=stress_peak_index
    )
    peak_stress = float(stress[stress_peak_index])

    scalars = (
        Scalar("source_peak_index", "원행 최대 공칭응력 위치", float(stress_peak_index), "1"),
        Scalar(
            "source_peak_strain",
            "원행 최대 공칭응력 변형률",
            float(strain[stress_peak_index]),
            "1",
            "strain",
        ),
        Scalar("source_peak_stress", "원행 최대 공칭응력", peak_stress, "Pa"),
        Scalar(
            "source_peak_order_evidence_code",
            "원행 취득 순서 증거 상태 (1=검증)",
            1.0,
            "1",
        ),
        Scalar(
            "source_peak_force_peak_match_code",
            "원하중·공칭응력 peak 일치 상태 (1=검증)",
            1.0,
            "1",
        ),
    )
    if not all(np.isfinite(item.value) for item in scalars):
        raise ProcessingError("source peak evidence 진단값이 유한하지 않습니다.")

    return StepResult(
        frame,
        notes=(
            f"현재 입력 원행 {force.size}개에서 첫 최대 공칭응력 원행 "
            f"{stress_peak_index}를 확인했습니다. 변형률 {strain[stress_peak_index]:.9g}, "
            f"응력 {peak_stress / 1e6:.9g} MPa 입니다.",
            f"취득 순서 증거: {', '.join(evidence_columns)} 열을 전체 입력 원행에서 "
            "유한한 정수·엄격 증가로 확인했습니다.",
            "원하중과 공칭응력이 양의 일정 비례이고 첫 peak 위치가 일치함을 "
            "확인했습니다. 이 단계는 원행을 선택·정렬·변경하지 않습니다.",
        ),
        scalars=scalars,
        effective_options=options,
    )


def _validate_positive_proportional(
    force: np.ndarray,
    stress: np.ndarray,
    *,
    force_peak_index: int,
    stress_peak_index: int,
) -> None:
    """Require positive maxima, shared zeros, and a positive constant ratio.

    Early matched negative force/stress values are valid source measurements
    (for example, preload rows).  The contract requires the proportionality
    factor and the selected maxima to be positive, matching the legacy
    pre-peak evidence semantics.
    """

    force_peak = float(force[force_peak_index])
    stress_peak = float(stress[stress_peak_index])
    if force_peak <= 0.0:
        raise ProcessingError(
            "원하중의 최대값이 양수가 아니어서 source peak를 검증할 수 없습니다: "
            f"{force_peak:.9g} N."
        )
    if stress_peak <= 0.0:
        raise ProcessingError(
            "공칭응력의 최대값이 양수가 아니어서 source peak를 검증할 수 없습니다: "
            f"{stress_peak:.9g} Pa."
        )
    nonzero = force != 0.0
    if np.any((~nonzero) & (stress != 0.0)):
        raise ProcessingError(
            "원하중이 0인 원행에 0이 아닌 공칭응력이 있어 하중·응력 비례를 "
            "검증하지 못했습니다."
        )
    ratios = stress[nonzero] / force[nonzero]
    if ratios.size == 0 or not np.all(np.isfinite(ratios)):
        raise ProcessingError("원하중·공칭응력의 비례 검증값이 유한하지 않습니다.")
    reference = float(np.median(ratios))
    if reference <= 0.0 or not np.allclose(ratios, reference, rtol=1e-9, atol=0.0):
        raise ProcessingError(
            "원하중과 공칭응력이 양의 일정 비례가 아니어서 source peak를 "
            "검증할 수 없습니다. 변환·단위를 확인하세요."
        )


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"source peak evidence의 '{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다."
        )
    return value


def _require_unit(frame: Frame, name: str, expected: str, what: str) -> None:
    frame.require(name, what=what)
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"source peak evidence의 {what} 열 '{name}' 단위는 '{expected}'이어야 합니다. "
            f"현재: {shown}."
        )


def _numeric_column(frame: Frame, name: str, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(name, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}' {what} 열을 숫자 배열로 읽을 수 없습니다.") from None
    if raw.ndim != 1 or np.iscomplexobj(raw) or not np.issubdtype(raw.dtype, np.number):
        raise ProcessingError(f"'{name}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        values: np.ndarray = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"'{name}' {what} 열을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if not np.all(np.isfinite(values)):
        raise ProcessingError(f"'{name}' {what} 열에 유한하지 않은 값이 있습니다.")
    return values


def _validate_frame_columns(frame: Frame, size: int) -> None:
    """Check the complete Frame shape before emitting source evidence."""

    if not frame.columns:
        raise ProcessingError("source peak evidence를 적용할 입력 열이 없습니다.")
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"입력 열 '{name}'을 숫자 배열로 읽을 수 없습니다."
            ) from None
        if (
            values.ndim != 1
            or np.iscomplexobj(values)
            or not np.issubdtype(values.dtype, np.number)
        ):
            raise ProcessingError(f"입력 열 '{name}'은 1차원 실수형 숫자여야 합니다.")
        if len(values) != size:
            raise ProcessingError(
                f"입력 열 '{name}'의 점 수가 맞지 않습니다: {len(values)}점, 기준 {size}점."
            )
        try:
            numeric = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"입력 열 '{name}'을 실수형 숫자로 읽을 수 없습니다."
            ) from None
        if not np.all(np.isfinite(numeric)):
            raise ProcessingError(f"입력 열 '{name}'에 유한하지 않은 값이 있습니다.")
