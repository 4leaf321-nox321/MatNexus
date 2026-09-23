"""Guarded, acquired-row support for downstream tensile modeling."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

POLICY = "record_high_guarded_v1"
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
ALLOWANCE_W_SPAN_FACTOR = 1.0
ALLOWANCE_MAD_FACTOR = 6.0
MAD_NORMAL_SCALE = 1.4826
MAX_UNRECOVERED_FRACTION = 0.1
MODEL_INPUT_INDEX = "model_input_index"

OPTION_KEYS = frozenset(
    {
        "policy",
        "strain",
        "stress",
        "start_index",
        "end_index",
        "youngs_modulus",
        "elastic_intercept",
        "source_elastic_start_index",
        "source_elastic_end_index",
        "source_proof_left_index",
        "source_proof_right_index",
    }
)


@dataclass(frozen=True, slots=True)
class _GapRow:
    anchor: int
    row: int
    dx: float
    unloading_strain: float
    residual_strain: float
    flagged: bool


@dataclass(frozen=True, slots=True)
class _Scan:
    rows: np.ndarray
    gap_row_count: int
    backward_rows: tuple[_GapRow, ...]
    flagged_rows: tuple[_GapRow, ...]
    maximum_backstep: float


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill visible source-stage references only when the caller omitted them."""
    prepared = dict(options)
    policy = prepared.get("policy", POLICY)
    if policy != POLICY:
        raise ProcessingError(f"모델 입력 정책은 '{POLICY}' 만 지원합니다: {policy!r}.")
    prepared["policy"] = POLICY
    _reject_unknown(prepared)
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    prepared.setdefault("youngs_modulus", "@youngs_modulus")
    prepared.setdefault("elastic_intercept", "@elastic_intercept")
    prepared.setdefault("source_elastic_start_index", "@source_elastic_start_index")
    prepared.setdefault("source_elastic_end_index", "@source_elastic_end_index")
    prepared.setdefault("source_proof_left_index", "@source_proof_left_index")
    prepared.setdefault("source_proof_right_index", "@source_proof_right_index")
    return prepared


def model_support(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Select strict record-high strain rows after checking every paired gap.

    This is a model-input projection. It leaves source measurements and the
    source-first E/Rp stages intact; it neither sorts nor smooths the input.
    """
    _reject_unknown(options)
    policy = options.get("policy", POLICY)
    if policy != POLICY:
        raise ProcessingError(f"모델 입력 정책은 '{POLICY}' 만 지원합니다: {policy!r}.")

    strain_key = _channel_name(options, "strain", DEFAULT_STRAIN)
    stress_key = _channel_name(options, "stress", DEFAULT_STRESS)
    strain, stress = _paired_columns(frame, strain_key, stress_key)
    row_count = int(strain.size)
    if row_count < 2:
        raise ProcessingError("모델 입력에는 최소 두 개의 원행이 필요합니다.")
    if MODEL_INPUT_INDEX in frame.columns:
        raise ProcessingError(
            f"파생 열 '{MODEL_INPUT_INDEX}' 이 이미 있습니다. 원래 열을 덮어쓰지 않습니다."
        )

    modulus = _finite_number(options.get("youngs_modulus"), "youngs_modulus")
    intercept = _finite_number(options.get("elastic_intercept"), "elastic_intercept")
    if modulus <= 0.0:
        raise ProcessingError("모델 입력 gap 검토에 쓸 원행 E는 양수여야 합니다.")

    elastic_start = _row_index(
        options.get("source_elastic_start_index"), "source_elastic_start_index"
    )
    elastic_end = _row_index(
        options.get("source_elastic_end_index"), "source_elastic_end_index"
    )
    proof_left = _row_index(options.get("source_proof_left_index"), "source_proof_left_index")
    proof_right = _row_index(
        options.get("source_proof_right_index"), "source_proof_right_index"
    )
    if elastic_start > elastic_end or elastic_end >= row_count:
        raise ProcessingError(
            f"원행 E 적합 경계 [{elastic_start}, {elastic_end}]가 현재 입력 행 범위를 "
            f"벗어납니다 (마지막 행 {row_count - 1})."
        )
    if proof_right != proof_left + 1 or proof_right >= row_count:
        raise ProcessingError(
            f"원행 내력 교점 경계 [{proof_left}, {proof_right}]가 현재 입력의 인접 원행 "
            "쌍이 아닙니다."
        )

    window_strain = strain[elastic_start : elastic_end + 1]
    window_stress = stress[elastic_start : elastic_end + 1]
    with np.errstate(over="ignore", invalid="ignore"):
        residual = window_stress - (modulus * window_strain + intercept)
    if not np.all(np.isfinite(residual)):
        raise ProcessingError("원행 E 구간의 모델 입력 guard 잔차가 유한하지 않습니다.")
    window_span = float(np.max(window_strain) - np.min(window_strain))
    residual_median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - residual_median)))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        mad_allowance = ALLOWANCE_MAD_FACTOR * MAD_NORMAL_SCALE * mad / modulus
    allowance = max(ALLOWANCE_W_SPAN_FACTOR * window_span, float(mad_allowance))
    if (
        not math.isfinite(window_span)
        or window_span <= 0.0
        or not math.isfinite(residual_median)
        or not math.isfinite(mad)
        or not math.isfinite(mad_allowance)
        or not math.isfinite(allowance)
    ):
        raise ProcessingError(
            "원행 E 구간에서 유한한 모델 입력 guard 허용폭을 계산할 수 없습니다."
        )

    start_index = (
        _row_index(options["start_index"], "start_index") if "start_index" in options else 0
    )
    end_index = (
        _row_index(options["end_index"], "end_index")
        if "end_index" in options
        else row_count - 1
    )
    if start_index > end_index or end_index >= row_count:
        raise ProcessingError(
            f"모델 입력 포함 범위 [{start_index}, {end_index}]가 현재 입력 행 범위를 "
            f"벗어납니다 (마지막 행 {row_count - 1})."
        )

    full_scan = _scan(strain, stress, 0, row_count - 1, modulus, allowance)
    selected_scan = (
        full_scan
        if start_index == 0 and end_index == row_count - 1
        else _scan(strain, stress, start_index, end_index, modulus, allowance)
    )
    if selected_scan.flagged_rows:
        first = selected_scan.flagged_rows[0]
        scope = f"[{start_index}, {end_index}]"
        raise ProcessingError(
            f"모델 입력 자동 선택을 보류합니다: 고정 paired-row guard가 범위 {scope}에서 "
            f"원행 {first.anchor}→{first.row}를 표시했습니다 "
            f"(dx={first.dx:.9g}, u={first.unloading_strain:.9g}, "
            f"r={first.residual_strain:.9g}, allowance={allowance:.9g}, "
            f"u/dx={first.unloading_strain / first.dx:.6g}). 측정 원인이나 재료 상태를 "
            f"확정하지 않습니다. 표시 행은 총 {len(selected_scan.flagged_rows)}개입니다. "
            "자동으로 자르지 않았습니다. 원행과 수동 모델 범위를 "
            "검토하세요."
        )

    selected_rows = selected_scan.rows
    if selected_rows.size < 2:
        raise ProcessingError(
            f"모델 입력 범위 [{start_index}, {end_index}]에서 기록 최고 행이 "
            f"{selected_rows.size}개뿐이어서 모델 구간을 만들지 않았습니다."
        )
    if np.any(np.diff(strain[selected_rows]) <= 0.0):
        raise ProcessingError("기록 최고 행 선택 결과가 엄격 증가하지 않습니다.")

    range_peak = start_index + int(np.argmax(stress[start_index : end_index + 1]))
    global_peak = int(np.argmax(stress))
    if not np.any(selected_rows == range_peak):
        raise ProcessingError(
            f"모델 입력 선택이 범위 안 첫 최대응력 원행 {range_peak}을 제외합니다. "
            "같은 최대응력의 뒤 행으로 대체하지 않았습니다. 수동 범위를 검토하세요."
        )

    elastic_rows_inside = max(
        0, min(elastic_end, end_index) - max(elastic_start, start_index) + 1
    )
    elastic_rows_total = elastic_end - elastic_start + 1
    proof_inside = start_index <= proof_left and proof_right <= end_index
    global_peak_inside = start_index <= global_peak <= end_index
    selected_row_set = set(int(row) for row in selected_rows)
    elastic_rows_retained = sum(
        row in selected_row_set for row in range(elastic_start, elastic_end + 1)
    )
    proof_rows_retained = sum(row in selected_row_set for row in (proof_left, proof_right))
    proof_pair_retained = proof_rows_retained == 2
    global_peak_retained = global_peak in selected_row_set
    excluded_full_flags = tuple(
        gap
        for gap in full_scan.flagged_rows
        if not (start_index <= gap.anchor <= end_index and start_index <= gap.row <= end_index)
    )

    effective_options = {
        "policy": POLICY,
        "strain": strain_key,
        "stress": stress_key,
        "start_index": start_index,
        "end_index": end_index,
        "youngs_modulus": modulus,
        "elastic_intercept": intercept,
        "source_elastic_start_index": elastic_start,
        "source_elastic_end_index": elastic_end,
        "source_proof_left_index": proof_left,
        "source_proof_right_index": proof_right,
    }
    selected_frame = frame.select(selected_rows).with_columns(
        {MODEL_INPUT_INDEX: selected_rows.astype(np.int64, copy=True)},
        {MODEL_INPUT_INDEX: "1"},
    )
    gap_count = selected_scan.gap_row_count
    backward_count = len(selected_scan.backward_rows)
    flagged_full_count = len(full_scan.flagged_rows)
    excluded_flag_count = len(excluded_full_flags)
    selected_count = int(selected_rows.size)
    omitted_count = end_index - start_index + 1 - selected_count
    notes = [
        f"{POLICY}: 현재 입력 원행 [{start_index}, {end_index}]에서 첫 행과 그 뒤 "
        "직전 유지 행보다 변형률이 엄격히 큰 원행만 남겼습니다. "
        f"{selected_count}행 유지, {omitted_count}행 제외, 기록 최고 gap {gap_count}행 "
        f"({backward_count}행은 실제 변형률 후퇴)입니다. 정렬·평활·보간은 하지 않았습니다.",
        f"원행 E 구간 [{elastic_start}, {elastic_end}] 중 이 모델 범위에는 "
        f"{elastic_rows_inside}/{elastic_rows_total}행이 들어 있고 그중 "
        f"{elastic_rows_retained}행을 실제 선택했습니다. 원행 내력 쌍 "
        f"[{proof_left}, {proof_right}]은 모델 범위에 "
        f"{'포함' if proof_inside else '포함되지 않으며'} 실제 선택에는 "
        f"{proof_rows_retained}/2행이 남았습니다. 전체 입력 첫 최대응력 행 "
        f"{global_peak}은 모델 범위에 {'포함' if global_peak_inside else '없고'}, "
        f"범위 안 첫 최대응력 행 {range_peak}은 실제 선택에 보존했습니다.",
        f"고정 guard: 허용 후퇴 r 상한 {allowance:.9g} 변형률, "
        f"전체 입력 표시 행 {flagged_full_count}개, 이 수동 범위가 끊어 둔 표시 경계 "
        f"{excluded_flag_count}개입니다. guard 통과는 계측 정상이나 재료 모델의 타당성을 "
        "인증하지 않습니다.",
    ]
    scalars = (
        Scalar("model_support_start_index", "모델 입력 시작 현재행", float(start_index), "1"),
        Scalar("model_support_end_index", "모델 입력 끝 현재행", float(end_index), "1"),
        Scalar(
            "model_support_selected_row_count",
            "모델 입력 유지 행 수",
            float(selected_count),
            "1",
        ),
        Scalar(
            "model_support_omitted_row_count",
            "모델 입력 제외 행 수",
            float(omitted_count),
            "1",
        ),
        Scalar(
            "model_support_record_high_gap_row_count",
            "기록 최고 gap 행 수",
            float(gap_count),
            "1",
        ),
        Scalar(
            "model_support_backward_gap_row_count",
            "변형률 후퇴 gap 행 수",
            float(backward_count),
            "1",
        ),
        Scalar(
            "model_support_guard_flagged_row_count", "선택 범위 guard 표시 행 수", 0.0, "1"
        ),
        Scalar(
            "model_support_full_guard_flagged_row_count",
            "전체 입력 guard 표시 행 수",
            float(flagged_full_count),
            "1",
        ),
        Scalar(
            "model_support_excluded_flagged_boundary_count",
            "수동 범위가 끊은 표시 경계 수",
            float(excluded_flag_count),
            "1",
        ),
        Scalar(
            "model_support_guard_allowance",
            "paired-row guard 허용 후퇴 상한",
            allowance,
            "1",
            "strain",
        ),
        Scalar(
            "model_support_max_backward_step",
            "최대 변형률 후퇴 폭",
            selected_scan.maximum_backstep,
            "1",
            "strain",
        ),
        Scalar(
            "model_support_elastic_rows_inside_count",
            "모델 범위 안 원행 E 적합 수",
            float(elastic_rows_inside),
            "1",
        ),
        Scalar(
            "model_support_elastic_rows_outside_count",
            "모델 범위 밖 원행 E 적합 수",
            float(elastic_rows_total - elastic_rows_inside),
            "1",
        ),
        Scalar(
            "model_support_elastic_rows_retained_count",
            "모델 입력에 남은 원행 E 적합 수",
            float(elastic_rows_retained),
            "1",
        ),
        Scalar(
            "model_support_proof_pair_inside",
            "원행 내력 쌍 범위 포함",
            float(proof_inside),
            "1",
        ),
        Scalar(
            "model_support_proof_pair_retained",
            "원행 내력 쌍 두 행 선택 유지",
            float(proof_pair_retained),
            "1",
        ),
        Scalar(
            "model_support_proof_rows_retained_count",
            "모델 입력에 남은 원행 내력 점 수",
            float(proof_rows_retained),
            "1",
        ),
        Scalar(
            "model_support_full_peak_inside",
            "전체 입력 첫 최대응력 범위 포함",
            float(global_peak_inside),
            "1",
        ),
        Scalar(
            "model_support_full_peak_retained",
            "전체 입력 첫 최대응력 행 선택 유지",
            float(global_peak_retained),
            "1",
        ),
        Scalar(
            "model_support_range_peak_index",
            "모델 범위 첫 최대응력 현재행",
            float(range_peak),
            "1",
        ),
    )
    return StepResult(
        selected_frame,
        notes=tuple(notes),
        scalars=scalars,
        effective_options=effective_options,
    )


def _scan(
    strain: np.ndarray,
    stress: np.ndarray,
    start_index: int,
    end_index: int,
    modulus: float,
    allowance: float,
) -> _Scan:
    selected = [start_index]
    backward: list[_GapRow] = []
    flagged: list[_GapRow] = []
    gap_count = 0
    maximum_backstep = 0.0
    for row in range(start_index + 1, end_index + 1):
        anchor = selected[-1]
        if strain[row] > strain[anchor]:
            selected.append(row)
            continue
        gap_count += 1
        dx = float(strain[anchor] - strain[row])
        if dx <= 0.0:
            continue
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            stress_release = float((stress[anchor] - stress[row]) / modulus)
            unloading = max(0.0, stress_release)
            residual = dx - unloading
        if (
            not math.isfinite(dx)
            or not math.isfinite(unloading)
            or not math.isfinite(residual)
        ):
            raise ProcessingError(
                f"모델 입력 guard 원행 {anchor}→{row}의 paired 좌표 차이가 유한하지 않습니다."
            )
        maximum_backstep = max(maximum_backstep, dx)
        is_flagged = residual > allowance and unloading < MAX_UNRECOVERED_FRACTION * dx
        item = _GapRow(anchor, row, dx, unloading, residual, is_flagged)
        backward.append(item)
        if is_flagged:
            flagged.append(item)
    return _Scan(
        np.asarray(selected, dtype=np.int64),
        gap_count,
        tuple(backward),
        tuple(flagged),
        maximum_backstep,
    )


def _paired_columns(
    frame: Frame, strain_key: str, stress_key: str
) -> tuple[np.ndarray, np.ndarray]:
    for name, values in frame.columns.items():
        column = np.asarray(values)
        if column.ndim != 1:
            raise ProcessingError(f"입력 열 '{name}'은 1차원이어야 합니다.")
    row_count = frame.length()
    if row_count == 0:
        raise ProcessingError("모델 입력에 현재 행이 없습니다.")
    for name, values in frame.columns.items():
        if np.asarray(values).size != row_count:
            raise ProcessingError(f"입력 열 '{name}'의 행 수가 다른 열과 일치하지 않습니다.")
    if frame.units.get(strain_key) != "1":
        raise ProcessingError(f"변형률 열 '{strain_key}'의 단위는 '1'이어야 합니다.")
    if frame.units.get(stress_key) != "Pa":
        raise ProcessingError(f"응력 열 '{stress_key}'의 단위는 'Pa'이어야 합니다.")
    strain = _numeric_column(frame, strain_key, what="변형률")
    stress = _numeric_column(frame, stress_key, what="응력")
    if strain.size != stress.size or strain.size != row_count:
        raise ProcessingError("모델 입력 변형률·응력·전체 열의 행 수가 서로 다릅니다.")
    if not np.all(np.isfinite(strain)) or not np.all(np.isfinite(stress)):
        raise ProcessingError(
            "모델 입력 변형률·응력에는 유한하지 않은 값이 있습니다. "
            "해당 원행을 건너뛰지 않습니다."
        )
    return strain, stress


def _numeric_column(frame: Frame, key: str, *, what: str) -> np.ndarray:
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


def _channel_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(f"'{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.") from None
    if not math.isfinite(number):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    return number


def _row_index(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ProcessingError(f"'{name}'은 유한한 정수 현재행 인덱스여야 합니다.")
    try:
        numeric = float(value)
    except OverflowError:
        raise ProcessingError(f"'{name}'은 유한한 정수 현재행 인덱스여야 합니다.") from None
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ProcessingError(f"'{name}'은 유한한 정수 현재행 인덱스여야 합니다.")
    index = int(numeric)
    if index < 0:
        raise ProcessingError(f"'{name}'은 0 이상이어야 합니다.")
    return index


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = set(options) - OPTION_KEYS
    if unknown:
        names = ", ".join(sorted(repr(name) for name in unknown))
        raise ProcessingError(f"모델 입력 단계에 알 수 없는 옵션이 있습니다: {names}.")
