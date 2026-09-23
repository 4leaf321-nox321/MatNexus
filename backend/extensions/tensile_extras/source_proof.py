"""Offset-yield intersection on adjacent original acquisition rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

POLICY = "first_positive_forward_v1"
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_OFFSET = 0.002
OPTION_KEYS = frozenset(
    {
        "policy",
        "youngs_modulus",
        "offset_strain",
        "start_index",
        "end_index",
        "search_start",
        "search_end",
        "strain",
        "stress",
    }
)


@dataclass(frozen=True)
class _Crossing:
    left_index: int
    right_index: int
    fraction: float
    strain: float
    stress: float
    coincident_residual: bool


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Add visible references only when the recipe omits those inputs."""
    prepared = dict(options)
    policy = prepared.get("policy", POLICY)
    if policy != POLICY:
        raise ProcessingError(f"원행 내력 정책은 '{POLICY}' 만 지원합니다: {policy!r}.")
    prepared["policy"] = POLICY
    _reject_unknown(prepared)
    prepared.setdefault("youngs_modulus", "@youngs_modulus")
    prepared.setdefault("start_index", "@source_elastic_end_index")
    prepared.setdefault("search_start", "@elastic_window_end")
    return prepared


def source_proof_stress(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Find the first positive offset crossing on a forward adjacent source pair.

    Both points must remain inside the selected inclusive source-row and strain
    bounds. No sorting, smoothing, origin shift, or interpolation across omitted
    source rows is performed.
    """
    _reject_unknown(options)
    policy = options.get("policy", POLICY)
    if policy != POLICY:
        raise ProcessingError(f"원행 내력 정책은 '{POLICY}' 만 지원합니다: {policy!r}.")

    strain_key = _channel_name(options, "strain", DEFAULT_STRAIN)
    stress_key = _channel_name(options, "stress", DEFAULT_STRESS)
    strain, stress = _pair(frame, strain_key, stress_key)

    modulus = _finite_number(options.get("youngs_modulus"), "youngs_modulus")
    if modulus <= 0.0:
        raise ProcessingError("원행 내력 계산의 탄성계수는 양수여야 합니다.")
    offset = _finite_number(options.get("offset_strain", DEFAULT_OFFSET), "offset_strain")
    if offset < 0.0:
        raise ProcessingError("원행 내력 계산의 오프셋 변형률은 0 이상이어야 합니다.")

    start_index = _row_index(options.get("start_index"), "start_index")
    end_index = (
        _row_index(options["end_index"], "end_index")
        if "end_index" in options
        else int(strain.size - 1)
    )
    if start_index >= strain.size:
        raise ProcessingError(
            f"원행 내력 시작 인덱스 {start_index}가 입력의 마지막 행 "
            f"{strain.size - 1}을 벗어납니다."
        )
    if end_index >= strain.size:
        raise ProcessingError(
            f"원행 내력 끝 인덱스 {end_index}가 입력의 마지막 행 "
            f"{strain.size - 1}을 벗어납니다."
        )
    if start_index > end_index:
        raise ProcessingError(
            f"원행 내력 시작 인덱스({start_index})가 끝 인덱스({end_index})보다 큽니다."
        )

    x = strain[start_index : end_index + 1]
    y = stress[start_index : end_index + 1]
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ProcessingError(
            f"원행 내력 검색 구간 [{start_index}, {end_index}]에 유한하지 않은 "
            "변형률·응력이 있습니다. 원행을 건너뛰지 않습니다."
        )

    search_start = _finite_number(options.get("search_start"), "search_start")
    search_end = (
        _finite_number(options["search_end"], "search_end")
        if "search_end" in options
        else float(np.max(x))
    )
    if search_start > search_end:
        raise ProcessingError(
            f"원행 내력 변형률 검색 시작({search_start})이 끝({search_end})보다 큽니다."
        )

    with np.errstate(over="ignore", invalid="ignore"):
        residual = y - modulus * (x - offset)
    if not np.all(np.isfinite(residual)):
        raise ProcessingError("원행 내력 잔차 계산이 유한하지 않습니다.")

    if x.size >= 2:
        left_x = x[:-1]
        right_x = x[1:]
        left_residual = residual[:-1]
        right_residual = residual[1:]
        both_in_search = (
            (left_x >= search_start)
            & (left_x <= search_end)
            & (right_x >= search_start)
            & (right_x <= search_end)
        )
        forward = both_in_search & (right_x > left_x)
        backward = both_in_search & (right_x < left_x)
        equal_strain = both_in_search & (right_x == left_x)
        residual_bracket = (left_residual >= 0.0) & (right_residual <= 0.0)
        forward_indices = np.flatnonzero(forward)
        backward_crossing_count = int(np.count_nonzero(backward & residual_bracket))
        equal_crossing_count = int(np.count_nonzero(equal_strain & residual_bracket))
        crossing_offsets = np.flatnonzero(forward & residual_bracket)
    else:
        left_x = right_x = left_residual = right_residual = np.empty(0, dtype=np.float64)
        forward_indices = crossing_offsets = np.empty(0, dtype=np.int64)
        backward_crossing_count = 0
        equal_crossing_count = 0

    positive_crossing_count = 0
    nonpositive_crossing_count = 0
    coincident_count = 0
    selected: _Crossing | None = None
    for pair_offset in crossing_offsets:
        left_d = float(left_residual[pair_offset])
        right_d = float(right_residual[pair_offset])
        coincident = left_d == 0.0 and right_d == 0.0
        if coincident:
            fraction = 0.0
            coincident_count += 1
        else:
            denominator = left_d - right_d
            if not math.isfinite(denominator) or denominator <= 0.0:
                raise ProcessingError("원행 내력 교점 보간 분모가 유한한 양수가 아닙니다.")
            fraction = left_d / denominator
            if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
                raise ProcessingError("원행 내력 교점 보간 비율이 유한 구간을 벗어났습니다.")

        left_index = start_index + int(pair_offset)
        right_index = left_index + 1
        with np.errstate(over="ignore", invalid="ignore"):
            proof_strain = float(
                x[pair_offset] + fraction * (x[pair_offset + 1] - x[pair_offset])
            )
            proof_stress = float(
                y[pair_offset] + fraction * (y[pair_offset + 1] - y[pair_offset])
            )
        if not math.isfinite(proof_strain) or not math.isfinite(proof_stress):
            raise ProcessingError("원행 내력 보간 결과가 유한하지 않습니다.")

        candidate = _Crossing(
            left_index=left_index,
            right_index=right_index,
            fraction=float(fraction),
            strain=proof_strain,
            stress=proof_stress,
            coincident_residual=coincident,
        )
        if proof_stress > 0.0:
            positive_crossing_count += 1
            if selected is None:
                selected = candidate
        else:
            nonpositive_crossing_count += 1

    effective_options = {
        "policy": POLICY,
        "youngs_modulus": modulus,
        "offset_strain": offset,
        "start_index": start_index,
        "end_index": end_index,
        "search_start": search_start,
        "search_end": search_end,
        "strain": strain_key,
        "stress": stress_key,
    }
    diagnostic_scalars: list[Scalar] = [
        Scalar(
            "source_proof_search_start_index", "내력 검색 시작 원행", float(start_index), "1"
        ),
        Scalar("source_proof_search_end_index", "내력 검색 끝 원행", float(end_index), "1"),
        Scalar(
            "source_proof_search_start_strain",
            "내력 검색 시작 변형률",
            search_start,
            "1",
            "strain",
        ),
        Scalar(
            "source_proof_search_end_strain", "내력 검색 끝 변형률", search_end, "1", "strain"
        ),
        Scalar(
            "source_proof_forward_eligible_pair_count",
            "내력 검색 전진 인접 원행 쌍 수",
            float(forward_indices.size),
            "1",
        ),
        Scalar(
            "source_proof_backward_crossing_candidate_count",
            "내력 검색 역행 교점 후보 수",
            float(backward_crossing_count),
            "1",
        ),
        Scalar(
            "source_proof_equal_strain_crossing_candidate_count",
            "내력 검색 같은 변형률 교점 후보 수",
            float(equal_crossing_count),
            "1",
        ),
        Scalar(
            "source_proof_positive_crossing_candidate_count",
            "내력 검색 양수 전진 교점 후보 수",
            float(positive_crossing_count),
            "1",
        ),
        Scalar(
            "source_proof_nonpositive_crossing_candidate_count",
            "내력 검색 비양수 전진 교점 후보 수",
            float(nonpositive_crossing_count),
            "1",
        ),
        Scalar(
            "source_proof_coincident_forward_residual_segment_count",
            "내력 검색 전진 일치 잔차 선분 수",
            float(coincident_count),
            "1",
        ),
    ]

    if selected is None:
        if nonpositive_crossing_count:
            reason = (
                f"전진 잔차 교점 후보 {nonpositive_crossing_count}개가 있었지만 "
                "보간 내력이 양수가 아니어서 값을 내지 않았습니다."
            )
        elif backward_crossing_count or equal_crossing_count:
            reason = (
                "잔차 교점은 있었지만 변형률이 감소하거나 같아지는 선분뿐이어서 "
                "내력을 내지 않았습니다."
            )
        else:
            reason = (
                "검색 구간에 양수 내력을 주는 전진 잔차 교점이 없습니다. 외삽하지 않았습니다."
            )
        diagnostics = _diagnostic_note(
            start_index,
            end_index,
            search_start,
            search_end,
            int(forward_indices.size),
            backward_crossing_count,
            equal_crossing_count,
            positive_crossing_count,
            nonpositive_crossing_count,
            coincident_count,
        )
        raise ProcessingError(f"{reason} {diagnostics}")

    scalars = [*diagnostic_scalars]
    scalars.extend(
        (
            Scalar("proof_stress", "항복강도", selected.stress, "Pa"),
            Scalar("proof_strain", "항복 변형률", selected.strain, "1", "strain"),
            Scalar("proof_offset", "오프셋", offset, "1", "strain"),
            Scalar(
                "source_proof_left_index",
                "내력 교점 왼쪽 원행 (현재 입력, 0부터)",
                float(selected.left_index),
                "1",
            ),
            Scalar(
                "source_proof_right_index",
                "내력 교점 오른쪽 원행 (현재 입력, 0부터)",
                float(selected.right_index),
                "1",
            ),
        )
    )
    notes = (
        f"원행 오프셋 선 교점: {selected.left_index}→{selected.right_index} 원행, "
        f"t={selected.fraction:.9g}, 변형률 {selected.strain:.9g}, "
        f"내력 {selected.stress / 1e6:.9g} MPa. 첫 양수 전진 교점을 선택했습니다.",
        _diagnostic_note(
            start_index,
            end_index,
            search_start,
            search_end,
            int(forward_indices.size),
            backward_crossing_count,
            equal_crossing_count,
            positive_crossing_count,
            nonpositive_crossing_count,
            coincident_count,
        ),
    )
    return StepResult(
        frame,
        notes=notes,
        scalars=tuple(scalars),
        effective_options=effective_options,
    )


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = set(options) - OPTION_KEYS
    if unknown:
        names = ", ".join(sorted(repr(name) for name in unknown))
        raise ProcessingError(f"원행 내력 단계에 알 수 없는 옵션이 있습니다: {names}.")


def _channel_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(f"'{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ProcessingError(f"'{name}' 는 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}' 는 유한한 숫자여야 합니다.") from None
    if not math.isfinite(number):
        raise ProcessingError(f"'{name}' 는 유한한 숫자여야 합니다.")
    return number


def _row_index(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ProcessingError(f"'{name}' 은 유한한 정수 행 인덱스여야 합니다.")
    try:
        numeric = float(value)
    except OverflowError:
        raise ProcessingError(f"'{name}' 은 유한한 정수 행 인덱스여야 합니다.") from None
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ProcessingError(f"'{name}' 은 유한한 정수 행 인덱스여야 합니다.")
    index = int(numeric)
    if index < 0:
        raise ProcessingError(f"'{name}' 은 0 이상이어야 합니다.")
    return index


def _pair(frame: Frame, strain_key: str, stress_key: str) -> tuple[np.ndarray, np.ndarray]:
    strain_unit = frame.units.get(strain_key)
    stress_unit = frame.units.get(stress_key)
    if strain_unit not in (None, "1"):
        raise ProcessingError(
            f"'{strain_key}' 는 무차원 변형률이어야 합니다. 현재 단위: {strain_unit!r}."
        )
    if stress_unit not in (None, "Pa"):
        raise ProcessingError(
            f"'{stress_key}' 는 Pa 응력이어야 합니다. 현재 단위: {stress_unit!r}."
        )
    strain = _numeric_column(frame, strain_key, "변형률")
    stress = _numeric_column(frame, stress_key, "응력")
    if strain.size != stress.size:
        raise ProcessingError(
            f"원행 내력 변형률·응력 열 길이가 서로 다릅니다 ({strain.size} 대 {stress.size})."
        )
    if strain.size == 0:
        raise ProcessingError("원행 내력 검색에 입력 행이 없습니다.")
    return strain, stress


def _numeric_column(frame: Frame, key: str, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(key, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 숫자 배열로 읽을 수 없습니다.") from None
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ProcessingError(f"'{key}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        return np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 실수형 숫자로 읽을 수 없습니다.") from None


def _diagnostic_note(
    start_index: int,
    end_index: int,
    search_start: float,
    search_end: float,
    forward_pair_count: int,
    backward_crossing_count: int,
    equal_crossing_count: int,
    positive_crossing_count: int,
    nonpositive_crossing_count: int,
    coincident_count: int,
) -> str:
    return (
        f"현재 입력 원행 [{start_index}, {end_index}], 변형률 [{search_start:.9g}, "
        f"{search_end:.9g}]에서 전진 적격 인접 쌍 {forward_pair_count}개, "
        f"역행 잔차 교점 후보 {backward_crossing_count}개, 같은 변형률 교점 후보 "
        f"{equal_crossing_count}개, 양수 전진 후보 {positive_crossing_count}개, "
        f"비양수 전진 후보 {nonpositive_crossing_count}개, 일치 잔차 선분 "
        f"{coincident_count}개입니다. 일치 선분은 양수·비양수 후보 수에 포함됩니다. "
        "두 경계 행은 모두 원래 입력에서 인접해야 하며, 잔차 선에는 E 절편을 더하지 않습니다."
    )
