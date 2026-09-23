"""Versioned, original-row tensile band/event modeling choices.

The stable band is a modeling region, not a measured yield or fracture point.
The selector and all proposals read the unchanged input arrays. The bounded
legacy fit helper is intentionally reused for median, endpoint, OLS and Huber
geometry; lower-envelope and isotonic methods retain their distinct objectives.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from matcore.processing import Frame, ProcessingError, Scalar, StepResult
from matcore.processing._auto_yield_fit import (
    AutoYieldFitError,
    AutoYieldFitResult,
    _Candidate,
    _fit_candidate,
    _unconstrained_core_fit,
    fit_event_cores,
)
from matcore.processing._drop_recovery import DropEvent, detect_events

from .lower_composition import (
    LowerComponentClosure,
    connected_lower_closure,
    lower_suffix_minorant,
)
from .model_regions import (
    DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN as _MODEL_DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN,
)
from .model_regions import (
    DEFAULT_MAXIMUM_RANGE_OVER_PEAK as _MODEL_DEFAULT_MAXIMUM_RANGE_OVER_PEAK,
)
from .model_regions import (
    DEFAULT_MAXIMUM_STRESS_OVER_PEAK as _MODEL_DEFAULT_MAXIMUM_STRESS_OVER_PEAK,
)
from .model_regions import (
    DEFAULT_MINIMUM_BAND_ROWS as _MODEL_DEFAULT_MINIMUM_BAND_ROWS,
)
from .model_regions import (
    DEFAULT_MINIMUM_PROGRESS_SPAN as _MODEL_DEFAULT_MINIMUM_PROGRESS_SPAN,
)
from .model_regions import (
    ProgressBasis,
    StableBandSelection,
    _normalized_axis,
    select_stable_band,
)

DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN = _MODEL_DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN
DEFAULT_MAXIMUM_RANGE_OVER_PEAK = _MODEL_DEFAULT_MAXIMUM_RANGE_OVER_PEAK
DEFAULT_MAXIMUM_STRESS_OVER_PEAK = _MODEL_DEFAULT_MAXIMUM_STRESS_OVER_PEAK
DEFAULT_MINIMUM_BAND_ROWS = _MODEL_DEFAULT_MINIMUM_BAND_ROWS
DEFAULT_MINIMUM_PROGRESS_SPAN = _MODEL_DEFAULT_MINIMUM_PROGRESS_SPAN

AUTO_POLICY_V1 = "band_and_events_auto_v1"
AUTO_POLICY_V2 = "band_and_events_auto_v2"
SOURCE_EVENT_POLICY = "band_and_source_events_auto_v1"
AUTO_POLICIES = (AUTO_POLICY_V1, AUTO_POLICY_V2, SOURCE_EVENT_POLICY)
AUTO_POLICY = AUTO_POLICY_V2
MANUAL_POLICY = "manual_band_v1"
POLICIES = (*AUTO_POLICIES, MANUAL_POLICY)
METHODS = (
    "lower_envelope",
    "isotonic",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
)
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_TIME = "time"
DEFAULT_SOURCE_INDEX_COLUMN = "model_input_index"
DEFAULT_LOADING_FLOOR_FRACTION = 0.40
_COMPOSITION_V2_POLICIES = (AUTO_POLICY_V2, SOURCE_EVENT_POLICY)

_LEGACY_METHODS = {
    "lower_envelope": "lower_envelope_auto_v1",
    "isotonic": "isotonic_auto_v1",
    "median_plateau": "median_plateau_auto_v1",
    "linear": "linear_auto_v1",
    "least_squares": "least_squares_auto_v1",
    "robust_linear": "robust_linear_auto_v1",
}
_COMMON_OPTIONS = {
    "policy",
    "method",
    "strain",
    "stress",
    "time",
    "minimum_band_rows",
    "minimum_progress_span",
    "maximum_stress_over_peak",
    "maximum_range_over_peak",
    "maximum_gap_over_band_span",
    "loading_floor_fraction",
}
_MANUAL_OPTIONS = {"band_start", "band_end", "peak_row", "left_anchor"}
_SOURCE_EVENT_OPTIONS = {"source_elastic_end_index", "source_index_column"}
_NUMERIC_METHODS = ("median_plateau", "linear", "least_squares", "robust_linear")
_Decision = Literal[
    "band_fit",
    "band_subsumes_event",
    "band_supersedes_open_terminal",
    "band_supersedes_partial_continuation",
    "lower_component_pool_member",
    "kept_terminal_event",
    "kept_open_event_without_recovery",
    "kept_event_outside_band",
    "event_fit",
    "event_fit_infeasible_kept",
    "held_event_crosses_band",
    "held_unresolved_overlap",
]


@dataclass(frozen=True, slots=True)
class BandFitRecord:
    """Original-source evidence and one proposal decision for a fit region.

    ``core_start/core_end`` identify the common selected source evidence; the
    ``fit_rows_*`` fields distinguish the rows used by the chosen objective.
    ``source_cell_*`` record the bounds imposed before selecting its left anchor.
    A proposal is a read-only full-length copy and is composed only over its open
    anchor interval.
    """

    method: str
    region_kind: Literal["band", "event"]
    source_event: DropEvent | None
    peak_row: int
    core_start: int
    core_end: int
    fit_rows_start: int
    fit_rows_end: int
    left_anchor: int | None
    right_anchor: int
    source_cell_start: int
    source_cell_end: int
    decision: _Decision
    anchor_rule: str = "strict_target_upcrossing"
    reason: str | None = None
    target_stress: float | None = None
    unconstrained_level: float | None = None
    unconstrained_endpoints: tuple[float, float] | None = None
    constrained_endpoints: tuple[float, float] | None = None
    huber_delta: float | None = None
    fit_r_squared: float | None = None
    fit_rmse: float | None = None
    max_abs_distortion: float | None = None
    constraint_applied: bool = False
    proposal: NDArray[np.float64] | None = None


@dataclass(frozen=True, slots=True)
class BandModelComputation:
    """Pure source-row computation, exposed internally for independent checks."""

    values: NDArray[np.float64]
    selection: StableBandSelection
    events: tuple[DropEvent, ...]
    records: tuple[BandFitRecord, ...]
    model_end_row: int | None
    compositions: tuple[ModelComposition, ...]


@dataclass(frozen=True, slots=True)
class ModelComposition:
    """Source-row provenance for one v2 right-boundary or lower-pooling change."""

    kind: Literal["full_recovery_completion", "lower_connected_component"]
    event_intervals: tuple[tuple[int, int, str], ...]
    component_intervals: tuple[tuple[int, int], ...]
    outer_left: int
    outer_right: int
    released_internal_anchors: tuple[int, ...]
    newly_included_rows: tuple[int, int] | None
    newly_changed_points: int = 0
    max_additional_stress_change: float = 0.0
    includes_band: bool = False


@dataclass(slots=True)
class _ModelComponent:
    """One active proposal and the eligible original event rows connected to it."""

    proposal: BandFitRecord
    event_indices: set[int]
    is_band: bool


class _NoFeasibleAnchorError(AutoYieldFitError):
    """An anchor-only failure that may enter the versioned lower-pooling path."""


@dataclass(frozen=True, slots=True)
class _SourceEventCore:
    start: int
    right: int
    events: tuple[DropEvent, ...]


@dataclass(frozen=True, slots=True)
class _SourceEventFitRegion:
    core_start: int
    core_end: int
    fit_start: int
    fit_end: int
    left_anchor: int
    right_anchor: int
    source_events: tuple[DropEvent, ...]
    support_count: int
    anchor_rule: str
    reason: str | None
    target_stress: float | None
    unconstrained_level: float | None
    unconstrained_endpoints: tuple[float, float] | None
    constrained_endpoints: tuple[float, float] | None
    huber_delta: float | None
    fit_r_squared: float | None
    fit_rmse: float | None
    max_abs_distortion: float
    one_free_row: bool


@dataclass(frozen=True, slots=True)
class _SourceEventFitResult:
    values: NDArray[np.float64]
    regions: tuple[_SourceEventFitRegion, ...]
    protected_intervals: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _SourceEventPlan:
    component: _SourceEventCore
    fit_start: int
    left_anchor: int
    target_stress: float | None
    unconstrained_level: float | None
    unconstrained_endpoints: tuple[float, float] | None
    huber_delta: float | None
    anchor_rule: str
    reason: str | None
    crossing_prefix: bool
    one_free_row: bool


@dataclass(frozen=True, slots=True)
class _SourceEventIsotonicRegion:
    component: _SourceEventCore
    left_anchor: int
    fit_values: NDArray[np.float64]
    anchor_rule: str


def _real_vector(values: ArrayLike, *, what: str) -> NDArray[np.float64]:
    raw = np.asarray(values)
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ProcessingError(f"{what}은(는) 1차원 실수 배열이어야 합니다.")
    try:
        result = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"{what}을(를) 실수 배열로 읽을 수 없습니다.") from None
    if not np.all(np.isfinite(result)):
        raise ProcessingError(f"{what}에 유한하지 않은 값이 있습니다.")
    return result


def _json_number(value: Any, *, name: str, low: float, high: float) -> float:
    if type(value) not in (int, float):
        raise ProcessingError(f"{name}은(는) 유한한 JSON 숫자여야 합니다.")
    numeric = float(value)
    if not np.isfinite(numeric) or not low <= numeric <= high:
        raise ProcessingError(f"{name}은(는) {low} 이상 {high} 이하여야 합니다.")
    return numeric


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Resolve visible source references only for the explicit source-event policy."""
    prepared = dict(options)
    if prepared.get("policy") == SOURCE_EVENT_POLICY:
        prepared.setdefault("source_elastic_end_index", "@source_elastic_end_index")
        prepared.setdefault("source_index_column", DEFAULT_SOURCE_INDEX_COLUMN)
    return prepared


def _row_scalar(value: Any, *, name: str) -> int:
    if type(value) not in (int, float) or not np.isfinite(float(value)):
        raise ProcessingError(f"{name}은(는) 유한한 정수 행 위치여야 합니다.")
    numeric = float(value)
    if numeric < 0 or not numeric.is_integer() or numeric >= float(1 << 63):
        raise ProcessingError(f"{name}은(는) 0 이상의 정수 행 위치여야 합니다.")
    return int(numeric)


def _source_row_mapping(
    frame: Frame, options: dict[str, Any]
) -> tuple[int, NDArray[np.int64]]:
    elastic_end = _row_scalar(
        options.get("source_elastic_end_index"), name="source_elastic_end_index"
    )
    column = options["source_index_column"]
    if not isinstance(column, str) or not column.strip():
        raise ProcessingError("source_index_column은 비어 있지 않은 열 이름이어야 합니다.")
    if column not in frame.columns:
        raise ProcessingError(f"원행 대응 열 '{column}'이 현재 모델 입력에 없습니다.")
    if frame.units.get(column) != "1":
        raise ProcessingError(
            f"원행 대응 열 '{column}' 단위가 '1'이 아닙니다: {frame.units.get(column)!r}"
        )
    raw = np.asarray(frame.columns[column])
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ProcessingError("원행 대응 열은 유한한 1차원 정수 행 위치여야 합니다.")
    try:
        numeric = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError("원행 대응 열을 정수 행 위치로 읽을 수 없습니다.") from None
    if (
        not np.all(np.isfinite(numeric))
        or np.any(numeric < 0.0)
        or np.any(numeric >= float(1 << 63))
        or np.any(numeric != np.floor(numeric))
        or np.any(np.diff(numeric) <= 0.0)
    ):
        raise ProcessingError(
            "원행 대응 열은 음수가 없고 엄격히 증가하는 유한 정수여야 합니다."
        )
    return elastic_end, numeric.astype(np.int64)


def _resolve_options(options: dict[str, Any]) -> dict[str, Any]:
    policy = options.get("policy", AUTO_POLICY)
    if policy not in POLICIES:
        raise ProcessingError(f"지원하지 않는 tensile.band_model 정책입니다: {policy!r}")
    allowed = _COMMON_OPTIONS | (_MANUAL_OPTIONS if policy == MANUAL_POLICY else set())
    if policy == SOURCE_EVENT_POLICY:
        allowed |= _SOURCE_EVENT_OPTIONS
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ProcessingError(
            f"정책 '{policy}'에서 허용되지 않는 옵션입니다: {', '.join(unknown)}"
        )

    method = options.get("method")
    if method not in METHODS:
        raise ProcessingError(
            f"tensile.band_model 방법을 여섯 선택지에서 지정해야 합니다: {method!r}"
        )
    strain = options.get("strain", DEFAULT_STRAIN)
    stress = options.get("stress", DEFAULT_STRESS)
    time = options.get("time", DEFAULT_TIME)
    if not isinstance(strain, str) or not strain:
        raise ProcessingError("strain은 비어 있지 않은 변형률 열 이름이어야 합니다.")
    if not isinstance(stress, str) or not stress:
        raise ProcessingError("stress는 비어 있지 않은 응력 열 이름이어야 합니다.")
    if time is not None and (not isinstance(time, str) or not time):
        raise ProcessingError("time은 초 단위 시간 열 이름 또는 null이어야 합니다.")
    if type(options.get("minimum_band_rows", DEFAULT_MINIMUM_BAND_ROWS)) is not int:
        raise ProcessingError("minimum_band_rows는 정수여야 합니다.")
    minimum_band_rows = int(options.get("minimum_band_rows", DEFAULT_MINIMUM_BAND_ROWS))
    if minimum_band_rows < 2:
        raise ProcessingError("minimum_band_rows는 2 이상이어야 합니다.")

    resolved: dict[str, Any] = {
        "policy": policy,
        "method": method,
        "strain": strain,
        "stress": stress,
        "time": time,
        "minimum_band_rows": minimum_band_rows,
        "minimum_progress_span": _json_number(
            options.get("minimum_progress_span", DEFAULT_MINIMUM_PROGRESS_SPAN),
            name="minimum_progress_span",
            low=0.0,
            high=1.0,
        ),
        "maximum_stress_over_peak": _json_number(
            options.get("maximum_stress_over_peak", DEFAULT_MAXIMUM_STRESS_OVER_PEAK),
            name="maximum_stress_over_peak",
            low=0.0,
            high=1.0,
        ),
        "maximum_range_over_peak": _json_number(
            options.get("maximum_range_over_peak", DEFAULT_MAXIMUM_RANGE_OVER_PEAK),
            name="maximum_range_over_peak",
            low=0.0,
            high=1.0,
        ),
        "maximum_gap_over_band_span": _json_number(
            options.get("maximum_gap_over_band_span", DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN),
            name="maximum_gap_over_band_span",
            low=0.0,
            high=1.0,
        ),
        "loading_floor_fraction": _json_number(
            options.get("loading_floor_fraction", DEFAULT_LOADING_FLOOR_FRACTION),
            name="loading_floor_fraction",
            low=0.0,
            high=1.0,
        ),
    }
    if policy == MANUAL_POLICY:
        for key in ("band_start", "band_end"):
            value = options.get(key)
            if type(value) is not int:
                raise ProcessingError(f"manual_band_v1에는 {key} 정수 행 위치가 필요합니다.")
            resolved[key] = value
        for key in ("peak_row", "left_anchor"):
            value = options.get(key)
            if value is not None and type(value) is not int:
                raise ProcessingError(f"{key}는 정수 행 위치 또는 null이어야 합니다.")
            resolved[key] = value
    if policy == SOURCE_EVENT_POLICY:
        resolved["source_elastic_end_index"] = _row_scalar(
            options.get("source_elastic_end_index"), name="source_elastic_end_index"
        )
        source_index_column = options.get("source_index_column", DEFAULT_SOURCE_INDEX_COLUMN)
        if not isinstance(source_index_column, str) or not source_index_column.strip():
            raise ProcessingError("source_index_column은 비어 있지 않은 열 이름이어야 합니다.")
        resolved["source_index_column"] = source_index_column
    return resolved


def _load_source(
    frame: Frame, options: dict[str, Any]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64] | None, str]:
    strain_key = options["strain"]
    stress_key = options["stress"]
    strain_raw = frame.require(strain_key, what="공학 변형률")
    stress_raw = frame.require(stress_key, what="공학 응력")
    if frame.units.get(strain_key) != "1":
        raise ProcessingError(
            f"'{strain_key}' 단위가 '1'이 아닙니다: {frame.units.get(strain_key)!r}"
        )
    if frame.units.get(stress_key) != "Pa":
        raise ProcessingError(
            f"'{stress_key}' 단위가 'Pa'가 아닙니다: {frame.units.get(stress_key)!r}"
        )
    strain = _real_vector(strain_raw, what=f"'{strain_key}'")
    stress = _real_vector(stress_raw, what=f"'{stress_key}'")
    if strain.size != stress.size or strain.size < 2:
        raise ProcessingError("변형률과 응력은 길이가 같고 관측 행이 2개 이상이어야 합니다.")
    for key, values in frame.columns.items():
        if len(values) != strain.size:
            raise ProcessingError(f"'{key}' 열 길이가 입력 원행 수와 다릅니다.")
    if np.any(np.diff(strain) <= 0.0):
        raise ProcessingError(f"'{strain_key}'은(는) 원행 순서에서 엄격히 증가해야 합니다.")

    time_key = options["time"]
    progress: NDArray[np.float64] | None = None
    progress_note = ""
    if time_key is not None and time_key in frame.columns:
        if frame.units.get(time_key) == "s":
            try:
                progress = _real_vector(frame.columns[time_key], what=f"초 단위 '{time_key}'")
                if progress.size != strain.size or np.any(np.diff(progress) <= 0.0):
                    progress = None
                    progress_note = "시간 진행축을 쓸 수 없어 공학 변형률로 대체했습니다."
            except ProcessingError:
                progress_note = (
                    "시간 진행축에 유한한 초 단위 값이 없어 공학 변형률로 대체했습니다."
                )
        else:
            progress_note = (
                f"'{time_key}' 단위가 초(s)가 아니어서 공학 변형률 진행축을 사용했습니다."
            )
    elif time_key is not None:
        progress_note = f"'{time_key}' 열이 없어 공학 변형률 진행축을 사용했습니다."
    return strain, stress, progress, progress_note


def _manual_selection(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    progress: NDArray[np.float64] | None,
    *,
    start: int,
    end: int,
    peak_row: int | None,
    maximum_gap_over_band_span: float,
) -> StableBandSelection:
    n = int(strain.size)
    if start < 0 or end >= n or end - start < 2:
        raise ProcessingError(
            "manual_band_v1의 band_start~band_end는 입력 범위 안에서 끝 행을 제외하고 "
            "적어도 2개의 적합 관측행을 포함해야 합니다."
        )
    if peak_row is None:
        peak_row = int(np.argmax(stress[:start])) if start > 0 else -1
    if peak_row < 0 or peak_row >= start or stress[peak_row] <= 0.0:
        raise ProcessingError(
            "manual_band_v1의 peak_row는 양의 응력인 band_start 앞 행이어야 합니다."
        )
    axis: NDArray[np.float64] = strain if progress is None else progress
    basis: ProgressBasis = "engineering_strain" if progress is None else "progress_channel"
    try:
        normalized = _normalized_axis(axis)
    except ValueError as exc:
        raise ProcessingError(f"수동 밴드 진행축을 정규화할 수 없습니다: {exc}") from None
    span = float(normalized[end] - normalized[start])
    if span <= 0.0:
        raise ProcessingError("수동 밴드 진행폭이 양수여야 합니다.")
    max_gap_ratio = float(np.max(np.diff(normalized[start : end + 1])) / span)
    if max_gap_ratio > maximum_gap_over_band_span:
        raise ProcessingError(
            "수동 밴드에 큰 원행 간격이 있습니다: "
            f"max_gap_ratio={max_gap_ratio:.6g} > {maximum_gap_over_band_span:.6g}."
        )
    band = stress[start : end + 1]
    return StableBandSelection(
        peak_row=peak_row,
        peak_stress=float(stress[peak_row]),
        band_start_row=start,
        band_end_row=end,
        progress_basis=basis,
        progress_span=span,
        max_gap_ratio=max_gap_ratio,
        source_row_count=n,
        band_min_stress=float(np.min(band)),
        band_max_stress=float(np.max(band)),
        band_median_stress=float(np.median(band)),
        reason="selected",
    )


def _loading_guard(
    stress: NDArray[np.float64], peak_row: int, loading_floor_fraction: float
) -> tuple[int, float]:
    peak = float(stress[peak_row])
    if peak <= 0.0:
        raise AutoYieldFitError("선택 봉우리 응력이 양수여야 합니다.")
    floor = loading_floor_fraction * peak
    qualifying = np.flatnonzero(stress[: peak_row + 1] >= floor)
    if qualifying.size == 0:
        raise AutoYieldFitError("봉우리 앞에서 보호할 하중 시작 행을 찾지 못했습니다.")
    return int(qualifying[0]), floor


def _method_evidence(
    method: str,
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    core_start: int,
    right: int,
    peak_row: int,
) -> tuple[float, float | None, tuple[float, float] | None, float | None]:
    right_value = float(stress[right])
    if method in ("lower_envelope", "isotonic", "linear"):
        if method == "lower_envelope":
            target = float(np.min(stress[peak_row + 1 : right + 1]))
        else:
            target = right_value
        return target, None, None, None
    core_x = strain[core_start:right]
    core_y = stress[core_start:right]
    if core_y.size < 2:
        raise AutoYieldFitError("선택 밴드의 원행 적합 점이 2개 미만입니다.")
    try:
        _fit, endpoints, c0, huber_delta = _unconstrained_core_fit(method, core_x, core_y)
    except AutoYieldFitError:
        raise
    if c0 is None:
        raise AutoYieldFitError("선택 방법의 원행 적합 시작값을 계산하지 못했습니다.")
    target = min(float(c0), right_value)
    return target, float(c0), endpoints, huber_delta


def _anchor_is_feasible(
    stress: NDArray[np.float64],
    *,
    method: str,
    left: int,
    right: int,
    target: float,
    rising_step_to_peak: bool = False,
) -> bool:
    if not (0 <= left < right < stress.size):
        return False
    if rising_step_to_peak:
        if not (
            float(stress[left + 1]) > float(stress[left])
            and float(stress[left]) <= min(target, float(stress[right]))
        ):
            return False
    elif not (float(stress[left]) <= target < float(stress[left + 1])):
        return False
    if float(stress[left]) > float(stress[right]):
        return False
    if method == "lower_envelope":
        return float(stress[left]) <= float(np.min(stress[left + 1 : right + 1]))
    return True


def _choose_anchor(
    stress: NDArray[np.float64],
    *,
    method: str,
    peak_row: int,
    right: int,
    target: float,
    guard_start: int,
    minimum_left: int,
    manual_left: int | None = None,
    rising_step_to_peak: bool = False,
) -> int:
    candidates = (
        [manual_left] if manual_left is not None else range(peak_row - 1, guard_start - 1, -1)
    )
    for candidate in candidates:
        if (
            candidate is None
            or candidate < max(guard_start, minimum_left)
            or candidate >= peak_row
        ):
            continue
        if _anchor_is_feasible(
            stress,
            method=method,
            left=candidate,
            right=right,
            target=target,
            rising_step_to_peak=rising_step_to_peak,
        ):
            return candidate
    raise _NoFeasibleAnchorError(
        "보호된 하중 시작 뒤, 봉우리 전에서 해당 방법의 상향 교차와 오른쪽 앵커를 "
        "함께 만족하는 관측 왼쪽 앵커를 찾지 못했습니다."
    )


def _readonly(values: NDArray[np.float64]) -> NDArray[np.float64]:
    result = np.asarray(values, dtype=np.float64).copy()
    result.setflags(write=False)
    return result


def _fit_region(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    *,
    method: str,
    region_kind: Literal["band", "event"],
    event: DropEvent | None,
    peak_row: int,
    core_start: int,
    right: int,
    source_cell_start: int,
    source_cell_end: int,
    loading_floor_fraction: float,
    manual_left: int | None = None,
) -> BandFitRecord:
    if region_kind == "band" and not (0 <= peak_row < core_start < right < stress.size):
        raise AutoYieldFitError(
            "밴드 적합 코어는 선행 봉우리 뒤, 오른쪽 앵커 앞이어야 합니다."
        )
    if region_kind == "event" and not (0 <= peak_row == core_start < right < stress.size):
        raise AutoYieldFitError("사건 적합 코어는 원행 사건 봉우리에서 시작해야 합니다.")
    if right - core_start < 2:
        raise AutoYieldFitError(
            "오른쪽 관측 앵커를 뺀 적합 코어에는 원행이 2개 이상 필요합니다."
        )
    if (
        source_cell_start < 0
        or source_cell_end >= stress.size
        or source_cell_start > source_cell_end
    ):
        raise AutoYieldFitError("원행 적합 셀 경계가 입력 범위에 맞지 않습니다.")
    guard_start, _floor = _loading_guard(stress, peak_row, loading_floor_fraction)
    target, c0, unconstrained_endpoints, huber_delta = _method_evidence(
        method, strain, stress, core_start, right, peak_row
    )
    use_event_peak_rising_step = region_kind == "event" and target >= float(stress[peak_row])
    left = _choose_anchor(
        stress,
        method=method,
        peak_row=peak_row,
        right=right,
        target=target,
        guard_start=guard_start,
        minimum_left=source_cell_start,
        manual_left=manual_left,
        rising_step_to_peak=use_event_peak_rising_step,
    )

    try:
        if method in _NUMERIC_METHODS:
            candidate = _Candidate(
                start=core_start,
                right=right,
                left=left,
                c0=c0,
                target=target,
                unconstrained_endpoints=unconstrained_endpoints,
                huber_delta=huber_delta,
            )
            proposed, region = _fit_candidate(strain, stress, candidate, method)
            return BandFitRecord(
                method=method,
                region_kind=region_kind,
                source_event=event,
                peak_row=peak_row,
                core_start=core_start,
                core_end=right - 1,
                fit_rows_start=core_start,
                fit_rows_end=right - 1,
                left_anchor=left,
                right_anchor=right,
                source_cell_start=source_cell_start,
                source_cell_end=source_cell_end,
                decision="band_fit" if region_kind == "band" else "event_fit",
                anchor_rule=(
                    "rising_step_before_event_peak_target_at_or_above_peak"
                    if use_event_peak_rising_step
                    else "strict_target_upcrossing"
                ),
                target_stress=target,
                unconstrained_level=c0,
                unconstrained_endpoints=region.unconstrained_endpoints,
                constrained_endpoints=region.constrained_endpoints,
                huber_delta=region.huber_delta,
                fit_r_squared=region.fit_r_squared,
                fit_rmse=region.fit_rmse,
                max_abs_distortion=region.max_abs_distortion,
                constraint_applied=region.constraint_applied,
                proposal=_readonly(proposed),
            )

        proposed = stress.copy()
        left_value = float(stress[left])
        right_value = float(stress[right])
        if method == "lower_envelope":
            source = stress[left + 1 : right + 1]
            suffix = np.minimum.accumulate(source[::-1])[::-1]
            proposed[left + 1 : right] = suffix[:-1]
            fit_start, fit_end = left + 1, right - 1
            endpoints = None
            applied = False
        elif method == "isotonic":
            from matcore.processing.tensile import _isotonic

            interior = stress[left + 1 : right]
            levels = np.asarray(_isotonic(interior), dtype=np.float64)
            proposed[left + 1 : right] = np.clip(levels, left_value, right_value)
            fit_start, fit_end = left + 1, right - 1
            endpoints = (float(proposed[left + 1]), float(proposed[right - 1]))
            applied = bool(np.any((levels < left_value) | (levels > right_value)))
        else:
            raise AutoYieldFitError(f"지원하지 않는 모델 방법입니다: {method}")
        local = proposed[left : right + 1]
        if not np.all(np.isfinite(local)) or np.any(np.diff(local) < 0.0):
            raise AutoYieldFitError("계산한 영향 구간이 유한한 비감소 곡선이 아닙니다.")
        if proposed[left] != stress[left] or proposed[right] != stress[right]:
            raise AutoYieldFitError("계산한 모델이 관측 앵커를 바꾸었습니다.")
        fit_y = stress[fit_start : fit_end + 1]
        fit_z = proposed[fit_start : fit_end + 1]
        residual = fit_y - fit_z
        total = float(np.sum((fit_y - float(np.mean(fit_y))) ** 2))
        error = float(np.sum(residual**2))
        r_squared = (
            1.0
            if total == 0.0 and error == 0.0
            else 0.0
            if total == 0.0
            else 1.0 - error / total
        )
        rmse = float(np.sqrt(np.mean(residual**2)))
        return BandFitRecord(
            method=method,
            region_kind=region_kind,
            source_event=event,
            peak_row=peak_row,
            core_start=core_start,
            core_end=right - 1,
            fit_rows_start=fit_start,
            fit_rows_end=fit_end,
            left_anchor=left,
            right_anchor=right,
            source_cell_start=source_cell_start,
            source_cell_end=source_cell_end,
            decision="band_fit" if region_kind == "band" else "event_fit",
            anchor_rule=(
                "rising_step_before_event_peak_target_at_or_above_peak"
                if use_event_peak_rising_step
                else "strict_target_upcrossing"
            ),
            target_stress=target,
            constrained_endpoints=endpoints,
            fit_r_squared=r_squared,
            fit_rmse=rmse,
            max_abs_distortion=float(np.max(np.abs(local - stress[left : right + 1]))),
            constraint_applied=applied,
            proposal=_readonly(proposed),
        )
    except (np.linalg.LinAlgError, FloatingPointError) as exc:
        raise AutoYieldFitError(f"원행 적합 계산이 실패했습니다: {exc}") from None


def _event_record(
    method: str,
    event: DropEvent,
    *,
    decision: _Decision,
    reason: str | None,
    cell_start: int,
    cell_end: int,
    band_start: int,
    band_end: int,
) -> BandFitRecord:
    return BandFitRecord(
        method=method,
        region_kind="event",
        source_event=event,
        peak_row=event.peak_index,
        core_start=event.peak_index,
        core_end=max(event.peak_index, event.end_index - 1),
        fit_rows_start=event.peak_index,
        fit_rows_end=max(event.peak_index, event.end_index - 1),
        left_anchor=None,
        right_anchor=event.end_index,
        source_cell_start=cell_start,
        source_cell_end=cell_end,
        decision=decision,
        reason=reason,
    )


def _can_supersede_closed_partial_continuation(
    event: DropEvent,
    *,
    influence_start: int,
    band_start: int,
    band_end: int,
) -> bool:
    """Whether the band contains a closed partial event's observed rebound onset."""
    recovery = event.recovery_index
    return (
        event.kind == "partial_recovery"
        and not event.end_at_observation_boundary
        and recovery is not None
        and influence_start <= event.peak_index <= event.trough_index < recovery
        and recovery < band_start <= band_end < event.end_index
    )


def _compose_records(
    stress: NDArray[np.float64], records: list[BandFitRecord]
) -> NDArray[np.float64]:
    result = stress.copy()
    occupied = np.zeros(stress.size, dtype=bool)
    for record in records:
        if record.proposal is None or record.left_anchor is None:
            continue
        left, right = record.left_anchor, record.right_anchor
        proposal = record.proposal
        if proposal.shape != stress.shape:
            raise ProcessingError("원행 적합 제안 길이가 원응력과 다릅니다.")
        if proposal[left] != stress[left] or proposal[right] != stress[right]:
            raise ProcessingError("원행 적합 제안이 관측 앵커와 일치하지 않습니다.")
        interior = np.arange(left + 1, right, dtype=int)
        if interior.size and np.any(occupied[interior]):
            raise ProcessingError("독립 원행 적합 영향 구간이 겹쳐 조합할 수 없습니다.")
        if interior.size:
            occupied[interior] = True
            result[interior] = proposal[interior]
    if not np.all(np.isfinite(result)):
        raise ProcessingError("조합한 응력에 유한하지 않은 값이 있습니다.")
    return result


def _full_recovery_completions(
    events: tuple[DropEvent, ...], *, band_start: int, band_end: int
) -> tuple[DropEvent, ...]:
    """Find original full events whose rebound is in B and observed end follows it."""
    return tuple(
        event
        for event in events
        if event.kind == "full_recovery"
        and not event.end_at_observation_boundary
        and event.recovery_index is not None
        and band_start <= event.peak_index <= event.trough_index
        and event.trough_index < event.recovery_index <= band_end < event.end_index
    )


def _eligible_pool_event(event: DropEvent) -> bool:
    return event.kind == "full_recovery" or (
        event.kind == "partial_recovery"
        and event.recovery_index is not None
        and not event.end_at_observation_boundary
    )


def _lower_pool_proposal(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    events: tuple[DropEvent, ...],
    components: list[_ModelComponent],
    *,
    root_component: int,
    failed_event_index: int,
    loading_floor_fraction: float,
) -> tuple[
    BandFitRecord,
    ModelComposition,
    NDArray[np.float64],
    int,
    LowerComponentClosure,
]:
    """Build one lower proposal from a bounded original-event component closure."""
    failed = events[failed_event_index]
    intervals_list: list[tuple[int, int]] = []
    for component in components:
        left = component.proposal.left_anchor
        if left is None:
            raise _NoFeasibleAnchorError("연결 모델 성분에 관측 왼쪽 앵커가 없습니다.")
        intervals_list.append((left, component.proposal.right_anchor))
    intervals = tuple(intervals_list)
    memberships = tuple(tuple(sorted(component.event_indices)) for component in components)
    closure = connected_lower_closure(
        events,
        intervals,
        memberships,
        root_component=root_component,
        failed_event=failed_event_index,
    )
    if closure is None:
        raise _NoFeasibleAnchorError("실패 사건까지 닿는 닫힌 원행 사건 연결 성분이 없습니다.")

    included = [components[index] for index in closure.component_indices]
    earliest = min(included, key=lambda component: component.proposal.peak_row)
    template = earliest.proposal
    assert template.left_anchor is not None
    old_left = min(
        int(component.proposal.left_anchor)
        for component in included
        if component.proposal.left_anchor is not None
    )
    source_cell_start = template.source_cell_start
    peak = template.peak_row
    right = failed.end_index
    guard_start, _floor = _loading_guard(stress, peak, loading_floor_fraction)

    def suffix_feasible(candidate: int) -> bool:
        return max(guard_start, source_cell_start) <= candidate < peak < right and float(
            stress[candidate]
        ) <= float(np.min(stress[candidate + 1 : right + 1]))

    left = old_left
    target = float(np.min(stress[peak + 1 : right + 1]))
    if not suffix_feasible(left):
        left = -1
        for candidate in range(old_left - 1, max(guard_start, source_cell_start) - 1, -1):
            if _anchor_is_feasible(
                stress,
                method="lower_envelope",
                left=candidate,
                right=right,
                target=target,
            ):
                left = candidate
                break
        if left < 0:
            raise _NoFeasibleAnchorError(
                "원자료 suffix 최소값이 기존 바깥 앵커를 넘고, 보호구간 안에서 "
                "더 이른 하측 앵커를 찾지 못했습니다."
            )

    try:
        proposed = lower_suffix_minorant(stress, left=left, right=right)
    except ValueError as exc:
        raise _NoFeasibleAnchorError(str(exc)) from None
    local = proposed[left : right + 1]
    if (
        not np.all(np.isfinite(local))
        or np.any(local <= 0.0)
        or np.any(np.diff(local) < 0.0)
        or np.any(local > stress[left : right + 1])
        or proposed[left] != stress[left]
        or proposed[right] != stress[right]
    ):
        raise _NoFeasibleAnchorError(
            "원자료 연결 suffix 모델이 관측 경계와 하측 비감소 조건을 만족하지 않습니다."
        )

    includes_band = any(component.is_band for component in included)
    region_kind: Literal["band", "event"] = "band" if includes_band else "event"
    decision: _Decision = "band_fit" if includes_band else "event_fit"
    new_record = BandFitRecord(
        method="lower_envelope",
        region_kind=region_kind,
        source_event=None if includes_band else failed,
        peak_row=peak,
        core_start=template.core_start,
        core_end=right - 1,
        fit_rows_start=left + 1,
        fit_rows_end=right - 1,
        left_anchor=left,
        right_anchor=right,
        source_cell_start=source_cell_start,
        source_cell_end=right,
        decision=decision,
        anchor_rule="connected_component_source_suffix_minorant",
        reason="연결된 eligible 원행 사건을 원응력 suffix 최소값으로 한 번 다시 적합했습니다.",
        target_stress=target,
        max_abs_distortion=float(np.max(np.abs(local - stress[left : right + 1]))),
        proposal=_readonly(proposed),
    )
    old_right = max(component.proposal.right_anchor for component in included)
    composition = ModelComposition(
        kind="lower_connected_component",
        event_intervals=tuple(
            (events[index].peak_index, events[index].end_index, events[index].kind)
            for index in closure.event_indices
        ),
        component_intervals=tuple(
            (component.proposal.left_anchor, component.proposal.right_anchor)
            for component in included
            if component.proposal.left_anchor is not None
        ),
        outer_left=left,
        outer_right=right,
        released_internal_anchors=tuple(
            sorted(
                {
                    component.proposal.right_anchor
                    for component in included
                    if component.proposal.right_anchor < right
                }
            )
        ),
        newly_included_rows=(old_right + 1, right) if old_right < right else None,
        includes_band=includes_band,
    )
    return new_record, composition, proposed, old_right, closure


def compute_band_model(
    engineering_strain: ArrayLike,
    engineering_stress: ArrayLike,
    progress: ArrayLike | None = None,
    *,
    method: str,
    policy: str = AUTO_POLICY,
    minimum_band_rows: int = DEFAULT_MINIMUM_BAND_ROWS,
    minimum_progress_span: float = DEFAULT_MINIMUM_PROGRESS_SPAN,
    maximum_stress_over_peak: float = DEFAULT_MAXIMUM_STRESS_OVER_PEAK,
    maximum_range_over_peak: float = DEFAULT_MAXIMUM_RANGE_OVER_PEAK,
    maximum_gap_over_band_span: float = DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN,
    loading_floor_fraction: float = DEFAULT_LOADING_FLOOR_FRACTION,
    band_start: int | None = None,
    band_end: int | None = None,
    peak_row: int | None = None,
    left_anchor: int | None = None,
) -> BandModelComputation:
    """Compute one method's edits and source-bound records without mutating inputs.

    The function is an internal verification seam. In automatic mode, a missing
    band is represented as an unchanged result; the registered wrapper delegates
    that case to the exact same-method legacy profile.
    """
    if method not in METHODS or policy not in POLICIES:
        raise ProcessingError("모델 방법과 정책을 지원 목록에서 지정해야 합니다.")
    strain = _real_vector(engineering_strain, what="공학 변형률")
    stress = _real_vector(engineering_stress, what="공학 응력")
    if strain.size != stress.size or strain.size < 2:
        raise ProcessingError("변형률과 응력은 길이가 같고 관측 행이 2개 이상이어야 합니다.")
    if np.any(np.diff(strain) <= 0.0):
        raise ProcessingError("공학 변형률은 원행 순서에서 엄격히 증가해야 합니다.")
    try:
        floor_fraction = _json_number(
            loading_floor_fraction,
            name="loading_floor_fraction",
            low=0.0,
            high=1.0,
        )
        minimum_gap = _json_number(
            maximum_gap_over_band_span,
            name="maximum_gap_over_band_span",
            low=0.0,
            high=1.0,
        )
        if type(minimum_band_rows) is not int or minimum_band_rows < 2:
            raise ProcessingError("minimum_band_rows는 2 이상의 정수여야 합니다.")
        if policy == MANUAL_POLICY:
            if band_start is None or band_end is None:
                raise ProcessingError("manual_band_v1에는 band_start와 band_end가 필요합니다.")
            if type(band_start) is not int or type(band_end) is not int:
                raise ProcessingError("manual_band_v1 band 경계는 정수 행 위치여야 합니다.")
            # The selector validates the source vectors and positive global maximum.
            selection = _manual_selection(
                strain,
                stress,
                None if progress is None else _real_vector(progress, what="진행축"),
                start=band_start,
                end=band_end,
                peak_row=peak_row,
                maximum_gap_over_band_span=minimum_gap,
            )
        else:
            selection = select_stable_band(
                strain,
                stress,
                progress,
                minimum_band_rows=minimum_band_rows,
                minimum_progress_span=minimum_progress_span,
                maximum_stress_over_peak=maximum_stress_over_peak,
                maximum_range_over_peak=maximum_range_over_peak,
                maximum_gap_over_band_span=minimum_gap,
            )
    except (ValueError, TypeError) as exc:
        raise ProcessingError(f"안정 밴드 입력을 검증할 수 없습니다: {exc}") from None

    if selection.reason == "not_found":
        unchanged = _readonly(stress)
        return BandModelComputation(unchanged, selection, (), (), None, ())
    if selection.reason != "selected":
        raise ProcessingError(
            "안정 밴드 후보가 원행 지지 간격을 만족하지 않습니다: "
            f"reason={selection.reason}, max_gap_ratio={selection.max_gap_ratio}."
        )
    assert selection.band_start_row is not None and selection.band_end_row is not None
    band_start_row = selection.band_start_row
    band_end_row = selection.band_end_row
    peak = selection.peak_row
    if not peak < band_start_row < band_end_row:
        raise ProcessingError("안정 밴드와 선행 봉우리의 원행 순서가 맞지 않습니다.")
    if band_end_row - band_start_row < 2:
        raise ProcessingError("오른쪽 관측 앵커를 뺀 밴드 적합 코어에 원행이 2개 미만입니다.")

    events = tuple(detect_events(stress, 0.005, 0.005, 0.05))
    completed_events = (
        _full_recovery_completions(events, band_start=band_start_row, band_end=band_end_row)
        if policy in _COMPOSITION_V2_POLICIES
        else ()
    )
    model_end_row = max((event.end_index for event in completed_events), default=band_end_row)
    records: list[BandFitRecord] = []
    compositions: list[ModelComposition] = []
    try:
        band_record = _fit_region(
            strain,
            stress,
            method=method,
            region_kind="band",
            event=None,
            peak_row=peak,
            core_start=band_start_row,
            right=model_end_row,
            source_cell_start=0,
            source_cell_end=model_end_row,
            loading_floor_fraction=floor_fraction,
            manual_left=left_anchor if policy == MANUAL_POLICY else None,
        )
    except AutoYieldFitError as exc:
        raise ProcessingError(f"선택 밴드 {method} 원행 적합을 보류합니다: {exc}") from None
    records.append(band_record)
    assert band_record.left_anchor is not None
    influence_start = band_record.left_anchor
    if model_end_row > band_end_row:
        compositions.append(
            ModelComposition(
                kind="full_recovery_completion",
                event_intervals=tuple(
                    (event.peak_index, event.end_index, event.kind)
                    for event in completed_events
                ),
                component_intervals=((influence_start, band_end_row),),
                outer_left=influence_start,
                outer_right=model_end_row,
                released_internal_anchors=(band_end_row,),
                newly_included_rows=(band_end_row + 1, model_end_row),
                includes_band=True,
            )
        )

    pre_boundary = 0
    post_boundary = model_end_row
    event_records: list[BandFitRecord] = []
    band_component = _ModelComponent(band_record, set(), True)
    components = [band_component]
    pending_pool_measurements: list[tuple[int, int, int, NDArray[np.float64]]] = []
    if model_end_row > band_end_row:
        unrelated = [
            event
            for event in events
            if event not in completed_events
            and event.end_index > band_end_row
            and event.peak_index <= model_end_row
        ]
        if unrelated:
            event = unrelated[0]
            raise ProcessingError(
                "full_recovery_completion_interrupted_by_other_event: "
                f"peak={event.peak_index}, end={event.end_index}, "
                f"model_influence={influence_start}~{model_end_row}."
            )
    for event_index, event in enumerate(events):
        overlaps = event.peak_index <= model_end_row and event.end_index > influence_start
        contained = event.peak_index >= influence_start and event.end_index <= model_end_row
        open_terminal = event.kind == "terminal_unrecovered" or (
            event.kind == "partial_recovery" and event.end_at_observation_boundary
        )
        if contained:
            band_component.event_indices.add(event_index)
            event_records.append(
                _event_record(
                    method,
                    event,
                    decision="band_subsumes_event",
                    reason="원행 사건 전체가 실제 모델 영향 구간 안에 있습니다.",
                    cell_start=0,
                    cell_end=model_end_row,
                    band_start=influence_start,
                    band_end=model_end_row,
                )
            )
            continue
        if overlaps:
            if model_end_row == band_end_row and _can_supersede_closed_partial_continuation(
                event,
                influence_start=influence_start,
                band_start=band_start_row,
                band_end=band_end_row,
            ):
                band_component.event_indices.add(event_index)
                event_records.append(
                    _event_record(
                        method,
                        event,
                        decision="band_supersedes_partial_continuation",
                        reason=(
                            "닫힌 부분회복의 봉우리·골·반등 시작은 밴드 영향 안에 있어 "
                            "밴드가 원행 R까지만 다룹니다. 원행 continuation "
                            f"{band_end_row + 1}~{event.end_index}은 뒤이은 사건의 "
                            "원자료 기준 적합 입력으로 남습니다. 그 후속 사건의 "
                            "별도 영향 구간은 적합 결과에 따라 변경될 수 있습니다."
                        ),
                        cell_start=0,
                        cell_end=model_end_row,
                        band_start=influence_start,
                        band_end=model_end_row,
                    )
                )
                continue
            if (
                open_terminal
                and influence_start <= event.peak_index < model_end_row
                and event.end_index >= model_end_row
            ):
                event_records.append(
                    _event_record(
                        method,
                        event,
                        decision="band_supersedes_open_terminal",
                        reason=(
                            "선택 밴드의 선행 봉우리와 말단 미회복/열린 부분회복 "
                            "영향이 겹칩니다."
                        ),
                        cell_start=0,
                        cell_end=model_end_row,
                        band_start=influence_start,
                        band_end=model_end_row,
                    )
                )
                continue
            if event.recovery_index is not None:
                event_records.append(
                    _event_record(
                        method,
                        event,
                        decision="held_event_crosses_band",
                        reason=(
                            "회복 사건이 모델 영향 경계를 가로질러 원행 셀에 "
                            "분리할 수 없습니다."
                        ),
                        cell_start=0,
                        cell_end=model_end_row,
                        band_start=influence_start,
                        band_end=model_end_row,
                    )
                )
                raise ProcessingError(
                    f"recovered_event_crosses_band_influence: peak={event.peak_index}, "
                    f"recovery={event.recovery_index}, end={event.end_index}, "
                    f"band_influence={influence_start}~{model_end_row}."
                )
            event_records.append(
                _event_record(
                    method,
                    event,
                    decision="held_unresolved_overlap",
                    reason="미회복 사건이 선택 영향 경계를 가로질러 별도 적합하지 않았습니다.",
                    cell_start=0,
                    cell_end=model_end_row,
                    band_start=influence_start,
                    band_end=model_end_row,
                )
            )
            continue

        if event.recovery_index is None:
            decision: _Decision = (
                "kept_terminal_event"
                if event.kind == "terminal_unrecovered"
                else "kept_open_event_without_recovery"
            )
            event_records.append(
                _event_record(
                    method,
                    event,
                    decision=decision,
                    reason="선택 밴드 밖의 미회복 사건은 원응력 그대로 보존했습니다.",
                    cell_start=0 if event.end_index <= influence_start else model_end_row,
                    cell_end=event.end_index,
                    band_start=influence_start,
                    band_end=model_end_row,
                )
            )
            if event.end_index <= influence_start:
                pre_boundary = max(pre_boundary, event.end_index)
            continue

        before_band = event.end_index <= influence_start
        cell_start = pre_boundary if before_band else post_boundary
        cell_end = event.end_index
        try:
            event_record = _fit_region(
                strain,
                stress,
                method=method,
                region_kind="event",
                event=event,
                peak_row=event.peak_index,
                core_start=event.peak_index,
                right=event.end_index,
                source_cell_start=cell_start,
                source_cell_end=cell_end,
                loading_floor_fraction=floor_fraction,
            )
        except _NoFeasibleAnchorError as exc:
            can_pool = (
                policy in _COMPOSITION_V2_POLICIES
                and method == "lower_envelope"
                and _eligible_pool_event(event)
            )
            if not can_pool:
                raise ProcessingError(
                    "disjoint_recovered_event_fit_infeasible: "
                    f"method={method}, peak={event.peak_index}, end={event.end_index}, "
                    f"cell={cell_start}~{cell_end}, reason={exc}"
                ) from None

            roots = [
                index
                for index, component in enumerate(components)
                if component.proposal.right_anchor == cell_start
            ]
            if not roots:
                raise ProcessingError(
                    "lower_connected_component_unavailable: no immediately preceding "
                    f"modeled component at source boundary {cell_start}; "
                    f"peak={event.peak_index}, end={event.end_index}, reason={exc}"
                ) from None
            root_component = max(roots, key=lambda index: components[index].proposal.peak_row)
            baseline_values = _compose_records(stress, [*records, *event_records])
            try:
                pooled, composition, _proposal, _old_right, closure = _lower_pool_proposal(
                    strain,
                    stress,
                    events,
                    components,
                    root_component=root_component,
                    failed_event_index=event_index,
                    loading_floor_fraction=floor_fraction,
                )
            except _NoFeasibleAnchorError as pool_exc:
                raise ProcessingError(
                    "lower_connected_component_infeasible: "
                    f"method={method}, peak={event.peak_index}, end={event.end_index}, "
                    f"cell={cell_start}~{cell_end}, anchor_failure={exc}, "
                    f"pool_failure={pool_exc}"
                ) from None

            consumed = set(closure.component_indices)
            consumed_proposals = {id(components[index].proposal) for index in consumed}
            member_reason = (
                "이 원행 제안은 source-event 연결 성분의 단일 하측 적합에 포함되었습니다."
            )
            closure_event_ids = {id(events[index]) for index in closure.event_indices}
            for bucket in (records, event_records):
                for record_index, record in enumerate(bucket):
                    if id(record) in consumed_proposals:
                        bucket[record_index] = replace(
                            record,
                            decision="lower_component_pool_member",
                            reason=member_reason,
                            proposal=None,
                        )
            for record_index, record in enumerate(event_records):
                if (
                    record.source_event is not None
                    and id(record.source_event) in closure_event_ids
                    and record.decision == "band_supersedes_partial_continuation"
                ):
                    event_records[record_index] = replace(
                        record,
                        decision="lower_component_pool_member",
                        reason=(
                            "닫힌 부분회복의 원행 continuation이 뒤의 닫힌 적격 사건과 "
                            "연결되어 하나의 원응력 하측 조합으로 재계산되었습니다."
                        ),
                    )

            event_records.append(
                _event_record(
                    method,
                    event,
                    decision="lower_component_pool_member",
                    reason="앵커-only 보류 뒤 닫힌 원행 사건 연결 성분으로 다시 적합했습니다.",
                    cell_start=cell_start,
                    cell_end=cell_end,
                    band_start=influence_start,
                    band_end=model_end_row,
                )
            )
            if pooled.region_kind == "band":
                records.append(pooled)
            else:
                event_records.append(pooled)
            composition_index = len(compositions)
            compositions.append(composition)
            assert pooled.left_anchor is not None
            pending_pool_measurements.append(
                (
                    composition_index,
                    (
                        composition.newly_included_rows[0]
                        if composition.newly_included_rows is not None
                        else pooled.right_anchor
                    ),
                    pooled.right_anchor,
                    baseline_values,
                )
            )
            remaining = [
                component
                for index, component in enumerate(components)
                if index not in consumed
            ]
            remaining.append(
                _ModelComponent(
                    proposal=pooled,
                    event_indices=set(closure.event_indices),
                    is_band=pooled.region_kind == "band",
                )
            )
            components = remaining
        except AutoYieldFitError as exc:
            raise ProcessingError(
                "disjoint_recovered_event_fit_infeasible: "
                f"method={method}, peak={event.peak_index}, end={event.end_index}, "
                f"cell={cell_start}~{cell_end}, reason={exc}"
            ) from None
        else:
            event_records.append(event_record)
            components.append(_ModelComponent(event_record, {event_index}, False))
        if before_band:
            pre_boundary = max(pre_boundary, event.end_index)
        else:
            post_boundary = max(post_boundary, event.end_index)

    records.extend(event_records)
    values = _compose_records(stress, records)
    for composition_index, left, right, baseline in pending_pool_measurements:
        additional = values[left:right] - baseline[left:right]
        compositions[composition_index] = replace(
            compositions[composition_index],
            newly_changed_points=int(np.count_nonzero(additional)),
            max_additional_stress_change=(
                0.0 if additional.size == 0 else float(np.max(np.abs(additional)))
            ),
        )
    reported_model_end = model_end_row
    for composition in compositions:
        if composition.kind == "lower_connected_component" and composition.includes_band:
            reported_model_end = max(reported_model_end, composition.outer_right)
    result_values = _readonly(values)
    return BandModelComputation(
        result_values,
        selection,
        events,
        tuple(records),
        reported_model_end,
        tuple(compositions),
    )


def _diagnostic_scalars(
    source: NDArray[np.float64],
    values: NDArray[np.float64],
    selection: StableBandSelection,
    left_anchor: int | None,
    model_end_row: int | None,
    compositions: tuple[ModelComposition, ...] = (),
) -> tuple[Scalar, ...]:
    peak = selection.peak_row
    band_start = -1 if selection.band_start_row is None else selection.band_start_row
    band_end = -1 if selection.band_end_row is None else selection.band_end_row
    support = 0 if selection.band_start_row is None else band_end - band_start + 1
    span = 0.0 if selection.progress_span is None else float(selection.progress_span)
    gap_ratio = 0.0 if selection.max_gap_ratio is None else float(selection.max_gap_ratio)
    lower_compositions = tuple(
        composition
        for composition in compositions
        if composition.kind == "lower_connected_component"
    )
    released_anchors = {
        anchor
        for composition in compositions
        for anchor in composition.released_internal_anchors
    }
    return (
        Scalar("band_model_peak_index", "원응력 최댓값 행 위치", float(peak), "1"),
        Scalar(
            "band_model_band_start_index", "모델 밴드 시작 행 위치", float(band_start), "1"
        ),
        Scalar("band_model_band_end_index", "선택 밴드 오른쪽 끝 원행", float(band_end), "1"),
        Scalar(
            "band_model_model_end_index",
            "밴드 연결 모델 영향 오른쪽 관측 앵커 행 위치",
            float(-1 if model_end_row is None else model_end_row),
            "1",
        ),
        Scalar(
            "band_model_left_anchor_index",
            "모델 영향 왼쪽 관측 앵커 행 위치",
            float(-1 if left_anchor is None else left_anchor),
            "1",
        ),
        Scalar("band_model_support_rows", "밴드 원행 지지 수", float(support), "1"),
        Scalar("band_model_progress_span", "밴드 정규화 진행폭", span, "1"),
        Scalar("band_model_max_gap_ratio", "밴드 최대 원행 간격 비율", gap_ratio, "1"),
        Scalar(
            "band_model_released_internal_anchor_count",
            "해제한 내부 모델 앵커 수",
            float(len(released_anchors)),
            "1",
        ),
        Scalar(
            "band_model_lower_composition_count",
            "하측 연결 조합 수",
            float(len(lower_compositions)),
            "1",
        ),
        Scalar(
            "band_model_lower_composition_changed_points",
            "하측 연결 조합 신규 구간의 최종 변경 점 수",
            float(sum(composition.newly_changed_points for composition in lower_compositions)),
            "1",
        ),
        Scalar(
            "band_model_lower_composition_max_additional_change",
            "하측 연결 조합 신규 구간 최종 최대 응력 변화",
            max(
                (
                    composition.max_additional_stress_change
                    for composition in lower_compositions
                ),
                default=0.0,
            ),
            "Pa",
        ),
        Scalar(
            "band_model_changed_points",
            "모델 단계 변경 점 수",
            float(np.count_nonzero(values != source)),
            "1",
        ),
        Scalar(
            "band_model_peak_depression",
            "원봉우리 행 모델 응력 감소",
            float(source[peak] - values[peak]),
            "Pa",
        ),
        Scalar(
            "band_model_max_stress_change",
            "최대 원응력 변경 폭",
            float(np.max(np.abs(values - source))),
            "Pa",
        ),
    )


def _source_event_cores(events: tuple[DropEvent, ...]) -> list[_SourceEventCore]:
    components: list[_SourceEventCore] = []
    for event in sorted(events, key=lambda item: (item.peak_index, item.end_index)):
        if components and event.peak_index <= components[-1].right:
            previous = components[-1]
            components[-1] = _SourceEventCore(
                previous.start,
                max(previous.right, event.end_index),
                (*previous.events, event),
            )
        else:
            components.append(_SourceEventCore(event.peak_index, event.end_index, (event,)))
    return components


def _protected_anchor_overlap(
    left: int,
    right: int,
    protected: tuple[tuple[int, int], ...],
) -> tuple[int, int] | None:
    for start, end in protected:
        if start <= left <= end:
            return start, end
        if start <= right <= end and right != start:
            return start, end
        if max(left + 1, start) <= min(right - 1, end):
            return start, end
    return None


def _source_event_plan(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    component: _SourceEventCore,
    *,
    method: str,
    preserve_boundary: int,
    protected: tuple[tuple[int, int], ...],
) -> _SourceEventPlan:
    start, right = component.start, component.right
    crossing_prefix = start <= preserve_boundary < right
    if crossing_prefix:
        fit_start = preserve_boundary + 1
        if fit_start >= right:
            raise AutoYieldFitError(
                "경계 사건에 편집 관측행이 없어 one-row 또는 다중행 적합을 할 수 없습니다."
            )
        if float(stress[preserve_boundary]) > float(stress[right]):
            raise AutoYieldFitError(
                "경계 사건의 고정 관측 앵커 응력이 감소해 비감소 접합을 만들 수 없습니다."
            )
        conflict = _protected_anchor_overlap(preserve_boundary, right, protected)
        if conflict is not None:
            raise AutoYieldFitError(
                f"경계 사건 영향 구간이 보호 말단 구간 {conflict[0]}~{conflict[1]}과 겹칩니다."
            )
        support_count = right - fit_start
        if support_count == 1:
            return _SourceEventPlan(
                component,
                fit_start,
                preserve_boundary,
                None,
                None,
                None,
                None,
                "one_observed_free_row",
                "one_observed_free_row",
                True,
                True,
            )
        target, c0, endpoints, huber_delta = _method_evidence(
            method, strain, stress, fit_start, right, start
        )
        return _SourceEventPlan(
            component,
            fit_start,
            preserve_boundary,
            target,
            c0,
            endpoints,
            huber_delta,
            "editable_domain_fixed_prefix_anchor",
            "crossing event fit uses only mutable post-prefix rows",
            True,
            False,
        )

    if right - start < 2:
        raise AutoYieldFitError(
            f"core index {start}~{right} 에 자동 적합 점이 2개 미만입니다."
        )
    target, c0, endpoints, huber_delta = _method_evidence(
        method, strain, stress, start, right, start
    )
    left: int | None = None
    for candidate in range(start - 1, preserve_boundary - 1, -1):
        if float(stress[candidate]) <= target:
            left = candidate
            break
    anchor_rule = "strict_target"
    reason: str | None = None
    if left is not None:
        conflict = _protected_anchor_overlap(left, right, protected)
        if conflict is not None:
            raise AutoYieldFitError(
                f"영향 구간이 보호 말단 구간 {conflict[0]}~{conflict[1]}과 겹칩니다."
            )
    else:
        right_value = float(stress[right])
        for candidate in range(start - 1, preserve_boundary - 1, -1):
            if float(stress[candidate]) > right_value:
                continue
            if _protected_anchor_overlap(candidate, right, protected) is not None:
                continue
            left = candidate
            break
        if left is None:
            raise AutoYieldFitError(
                f"core index {start}~{right} 에서 보존 경계 뒤의 bounded observed anchor를 "
                "찾지 못했습니다."
            )
        anchor_rule = "bounded_observed_anchor"
        reason = "strict unconstrained target had no eligible raw left anchor"
    return _SourceEventPlan(
        component,
        start,
        left,
        target,
        c0,
        endpoints,
        huber_delta,
        anchor_rule,
        reason,
        False,
        False,
    )


def _source_event_plan_proposal(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    plan: _SourceEventPlan,
    *,
    method: str,
) -> tuple[NDArray[np.float64], _SourceEventFitRegion]:
    right = plan.component.right
    support_count = right - plan.fit_start
    if plan.one_free_row:
        if support_count != 1:
            raise AutoYieldFitError("one_observed_free_row 진단과 적합 행 수가 다릅니다.")
        row = plan.fit_start
        left_value = float(stress[plan.left_anchor])
        right_value = float(stress[right])
        if method == "linear":
            fraction = float(
                (strain[row] - strain[plan.left_anchor])
                / (strain[right] - strain[plan.left_anchor])
            )
            ordinate = left_value + (right_value - left_value) * fraction
        else:
            ordinate = float(np.clip(stress[row], left_value, right_value))
        proposed = stress.copy()
        proposed[row] = ordinate
        local = proposed[plan.left_anchor : right + 1]
        if (
            not np.all(np.isfinite(local))
            or np.any(np.diff(local) < 0.0)
            or proposed[plan.left_anchor] != stress[plan.left_anchor]
            or proposed[right] != stress[right]
        ):
            raise AutoYieldFitError(
                "one_observed_free_row가 고정 관측 앵커 사이에서 "
                "비감소 접합을 만들지 못했습니다."
            )
        region = _SourceEventFitRegion(
            core_start=plan.component.start,
            core_end=right - 1,
            fit_start=row,
            fit_end=row,
            left_anchor=plan.left_anchor,
            right_anchor=right,
            source_events=plan.component.events,
            support_count=1,
            anchor_rule=plan.anchor_rule,
            reason=plan.reason,
            target_stress=None,
            unconstrained_level=None,
            unconstrained_endpoints=None,
            constrained_endpoints=None,
            huber_delta=None,
            fit_r_squared=None,
            fit_rmse=None,
            max_abs_distortion=abs(ordinate - float(stress[row])),
            one_free_row=True,
        )
        return proposed, region

    assert plan.target_stress is not None
    candidate = _Candidate(
        start=plan.fit_start,
        right=right,
        left=plan.left_anchor,
        c0=plan.unconstrained_level,
        target=plan.target_stress,
        unconstrained_endpoints=plan.unconstrained_endpoints,
        huber_delta=plan.huber_delta,
    )
    proposed, fit = _fit_candidate(strain, stress, candidate, method)
    region = _SourceEventFitRegion(
        core_start=plan.component.start,
        core_end=right - 1,
        fit_start=plan.fit_start,
        fit_end=right - 1,
        left_anchor=plan.left_anchor,
        right_anchor=right,
        source_events=plan.component.events,
        support_count=support_count,
        anchor_rule=plan.anchor_rule,
        reason=plan.reason,
        target_stress=fit.target_stress,
        unconstrained_level=fit.c0,
        unconstrained_endpoints=fit.unconstrained_endpoints,
        constrained_endpoints=fit.constrained_endpoints,
        huber_delta=fit.huber_delta,
        fit_r_squared=fit.fit_r_squared,
        fit_rmse=fit.fit_rmse,
        max_abs_distortion=fit.max_abs_distortion,
        one_free_row=False,
    )
    return proposed, region


def _source_event_a2_fit(
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    targets: tuple[DropEvent, ...],
    protected: list[tuple[int, int]],
    preserve_boundary: int,
    method: str,
) -> tuple[_SourceEventFitResult | None, str | None]:
    """Apply A2 only when a crossing suffix or target-blocked bounded anchor exists."""
    if method not in _NUMERIC_METHODS:
        return None, None
    protected_tuple = tuple(protected)
    components = _source_event_cores(targets)
    if not components:
        return None, None

    trigger_seen = any(
        component.start <= preserve_boundary < component.right
        and component.right > preserve_boundary + 1
        for component in components
    )
    plans: list[_SourceEventPlan] = []
    try:
        for _ in range(len(components)):
            plans = []
            for component in components:
                plan = _source_event_plan(
                    strain,
                    stress,
                    component,
                    method=method,
                    preserve_boundary=preserve_boundary,
                    protected=protected_tuple,
                )
                plans.append(plan)
                trigger_seen = (
                    trigger_seen
                    or plan.crossing_prefix
                    or (plan.anchor_rule == "bounded_observed_anchor")
                )
            merge_at = next(
                (
                    index
                    for index in range(len(plans) - 1)
                    if plans[index + 1].left_anchor <= plans[index].component.right
                ),
                None,
            )
            if merge_at is None:
                break
            first, second = components[merge_at : merge_at + 2]
            components[merge_at : merge_at + 2] = [
                _SourceEventCore(
                    first.start,
                    max(first.right, second.right),
                    (*first.events, *second.events),
                )
            ]
        else:
            return None, "source-event influence closure did not converge"

        if not trigger_seen:
            return None, None
        proposals = [
            _source_event_plan_proposal(strain, stress, plan, method=method) for plan in plans
        ]
    except AutoYieldFitError as exc:
        return None, str(exc) if trigger_seen else None

    values = stress.copy()
    regions: list[_SourceEventFitRegion] = []
    previous_right = -1
    for plan, (proposed, region) in zip(plans, proposals, strict=True):
        if plan.left_anchor < previous_right:
            return None, "source-event fitted influence intervals still overlap after closure"
        values[plan.left_anchor + 1 : plan.component.right] = proposed[
            plan.left_anchor + 1 : plan.component.right
        ]
        previous_right = plan.component.right
        regions.append(region)
    values.setflags(write=False)
    return _SourceEventFitResult(values, tuple(regions), protected_tuple), None


def _legacy_source_event_fit(
    fitted: AutoYieldFitResult,
    targets: tuple[DropEvent, ...],
) -> _SourceEventFitResult:
    regions = tuple(
        _SourceEventFitRegion(
            core_start=region.core_start,
            core_end=region.core_end,
            fit_start=region.core_start,
            fit_end=region.core_end,
            left_anchor=region.left_anchor,
            right_anchor=region.right_anchor,
            source_events=tuple(
                event
                for event in targets
                if event.peak_index <= region.core_end and event.end_index >= region.core_start
            ),
            support_count=region.core_end - region.core_start + 1,
            anchor_rule="fit_event_cores",
            reason=None,
            target_stress=region.target_stress,
            unconstrained_level=region.c0,
            unconstrained_endpoints=region.unconstrained_endpoints,
            constrained_endpoints=region.constrained_endpoints,
            huber_delta=region.huber_delta,
            fit_r_squared=region.fit_r_squared,
            fit_rmse=region.fit_rmse,
            max_abs_distortion=region.max_abs_distortion,
            one_free_row=False,
        )
        for region in fitted.regions
    )
    return _SourceEventFitResult(
        np.asarray(fitted.values, dtype=np.float64), regions, fitted.protected_intervals
    )


def _source_event_no_band_result(
    frame: Frame,
    options: dict[str, Any],
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    selection: StableBandSelection,
    progress_note: str,
    *,
    elastic_end: int,
    source_rows: NDArray[np.int64],
) -> StepResult:
    """Fit closed events after the mapped source-E prefix when no band exists."""
    detected = tuple(detect_events(stress, 0.005, 0.005, 0.05))
    recovered = tuple(
        event
        for event in detected
        if event.kind == "full_recovery"
        or (
            event.kind == "partial_recovery"
            and event.recovery_index is not None
            and not event.end_at_observation_boundary
        )
    )
    prefix_rows = np.flatnonzero(source_rows <= elastic_end)
    prefix_end = int(prefix_rows[-1]) if prefix_rows.size else -1
    preserve_boundary = prefix_end if prefix_end >= 0 else 0
    preserve_reason = (
        f"mapped source E end row {elastic_end}; model prefix ends at current row {prefix_end}"
        if prefix_end >= 0
        else "source E window precedes this model scope; preserve first current row as anchor"
    )
    excluded = tuple(event for event in recovered if event.end_index <= prefix_end)
    crossing_noops = tuple(
        event
        for event in recovered
        if prefix_end >= 0
        and event.peak_index <= prefix_end < event.end_index
        and event.end_index == prefix_end + 1
        and float(stress[prefix_end]) <= float(stress[event.end_index])
    )
    crossing_noop_ids = {id(event) for event in crossing_noops}
    targets = tuple(
        event
        for event in recovered
        if event.end_index > prefix_end and id(event) not in crossing_noop_ids
    )
    fit_preserve_boundary = max(
        preserve_boundary,
        max((event.end_index for event in crossing_noops), default=preserve_boundary),
    )
    fit_preserve_reason = preserve_reason
    if crossing_noops:
        completion_rows = tuple(event.end_index for event in crossing_noops)
        fit_preserve_reason += (
            f"; preserve no-editable-row recovery completions {completion_rows} as anchors"
        )
    protected = [
        (event.peak_index, event.end_index)
        for event in detected
        if event.kind == "terminal_unrecovered" or event.end_at_observation_boundary
    ]
    try:
        legacy_fit: AutoYieldFitResult = fit_event_cores(
            strain,
            stress,
            [(event.peak_index, event.end_index) for event in targets],
            protected,
            fit_preserve_boundary,
            options["method"],
            preserve_boundary_reason=fit_preserve_reason,
        )
        fitted = _legacy_source_event_fit(legacy_fit, targets)
    except AutoYieldFitError as exc:
        a2_fitted, a2_failure = _source_event_a2_fit(
            strain,
            stress,
            targets,
            protected,
            fit_preserve_boundary,
            options["method"],
        )
        if a2_fitted is not None:
            fitted = a2_fitted
        else:
            reason = str(exc)
            if a2_failure is not None:
                reason += f"; A2 attempt={a2_failure}"
            no_op_bounds = tuple(
                (
                    event.peak_index,
                    event.end_index,
                    int(source_rows[event.peak_index]),
                    int(source_rows[event.end_index]),
                )
                for event in crossing_noops
            )
            raise ProcessingError(
                "band_and_source_events_auto_v1 recovered-event fit held: "
                f"source E end={elastic_end}, mapped model prefix end={prefix_end}, "
                f"eligible targets={len(targets)}, excluded-in-prefix={len(excluded)}, "
                f"crossing_no_editable_rows={len(crossing_noops)} {no_op_bounds}, "
                f"reason={reason}"
            ) from None

    values = np.asarray(fitted.values, dtype=np.float64)
    if prefix_end >= 0 and not np.array_equal(
        values[: prefix_end + 1], stress[: prefix_end + 1]
    ):
        raise ProcessingError(
            "원행 E 모델 prefix를 원응력 그대로 보존하지 못해 사건 적합을 보류합니다."
        )
    for start, end in fitted.protected_intervals:
        if not np.array_equal(values[start : end + 1], stress[start : end + 1]):
            raise ProcessingError(
                f"말단 보호 원행을 보존하지 못해 사건 적합을 보류합니다: {start}~{end}."
            )
    for event in crossing_noops:
        if values[event.end_index] != stress[event.end_index]:
            raise ProcessingError(
                "crossing_no_editable_rows completion anchor를 보존하지 못해 "
                "사건 적합을 보류합니다: "
                f"{event.end_index}."
            )

    output_columns = dict(frame.columns)
    output_columns[options["stress"]] = values.copy()
    output_frame = Frame(output_columns, dict(frame.units))
    notes = [
        "선택 가능한 안정 밴드가 없어 source-event 정책의 no-band 경로를 사용했습니다. "
        f"source E 끝 원행={elastic_end}, 현재 모델 입력에서 E prefix 끝 행={prefix_end}; "
        f"보존 경계={preserve_boundary} ({preserve_reason}).",
        f"검출 사건 {len(detected)}개 중 닫힌 회복 사건 {len(recovered)}개를 확인했습니다. "
        f"E prefix 안의 닫힌 회복 사건 {len(excluded)}개는 적합 대상에서 제외했습니다. "
        f"경계 양 끝만 맞닿아 편집 가능한 원행이 없는 crossing_no_editable_rows "
        f"사건은 {len(crossing_noops)}개로 그대로 두었습니다. "
        f"남은 적합 대상 {len(targets)}개는 "
        "원사건 경계를 유지합니다. 경계 사건의 목적함수에는 실제로 변경 가능한 관측행만 "
        "넣고, E prefix 끝 P와 별도로 no-op 완료 행 R도 적합 "
        f"보존 경계={fit_preserve_boundary}로 유지합니다.",
        f"원자료 적합 결과 {len(fitted.regions)}개 영향 구간; 보호 말단 구간="
        f"{fitted.protected_intervals or '없음'}. E prefix와 보호 구간은 원응력 그대로입니다.",
    ]
    for event in detected:
        source_interval = (
            int(source_rows[event.peak_index]),
            int(source_rows[event.end_index]),
        )
        if event in excluded:
            decision = "E prefix 안의 닫힌 회복 사건 — 적합 대상 제외"
        elif id(event) in crossing_noop_ids:
            decision = (
                "crossing_no_editable_rows — 경계 양 끝만 있고 y[P]≤y[R]여서 "
                "양 끝과 전체 사건을 원응력 그대로 보존"
            )
        elif event in targets:
            region = next(
                (item for item in fitted.regions if event in item.source_events), None
            )
            if region is None:
                decision = "E 경계 뒤 닫힌 원사건 — 적합 영향 구간에서 처리"
            else:
                decision = (
                    f"전체 원사건을 유지하고 편집 적합행 {region.fit_start}~"
                    f"{region.fit_end} ({region.support_count}개)를 사용"
                )
        elif event.kind == "terminal_unrecovered" or event.end_at_observation_boundary:
            decision = "열린/말단 사건 — 관측 원행 보존"
        else:
            decision = "닫힌 회복 사건이 아니므로 적합 대상 아님"
        notes.append(
            f"원행 사건 kind={event.kind}, 현재 모델 입력 행="
            f"{event.peak_index}~{event.end_index}, source 원행={source_interval[0]}~"
            f"{source_interval[1]}: {decision}."
        )
    one_free_row_count = 0
    bounded_anchor_count = 0
    for region in fitted.regions:
        original_events = (
            ",".join(f"{event.peak_index}~{event.end_index}" for event in region.source_events)
            or "none"
        )
        source_events = (
            ",".join(
                f"{int(source_rows[event.peak_index])}~{int(source_rows[event.end_index])}"
                for event in region.source_events
            )
            or "none"
        )
        bounded_anchor_count += region.anchor_rule == "bounded_observed_anchor"
        details = (
            f"source_event_fit method={options['method']} original_events={original_events} "
            f"source_events={source_events} "
            f"core={region.core_start}~{region.core_end} "
            f"editable_rows={region.fit_start}~{region.fit_end} "
            f"source_editable_rows={int(source_rows[region.fit_start])}~"
            f"{int(source_rows[region.fit_end])} "
            f"support_count={region.support_count} "
            f"anchors={region.left_anchor}~{region.right_anchor} "
            f"source_anchors={int(source_rows[region.left_anchor])}~"
            f"{int(source_rows[region.right_anchor])} "
            f"anchor_mode={region.anchor_rule}"
        )
        if region.one_free_row:
            one_free_row_count += 1
            objective = (
                "endpoint_interpolation"
                if options["method"] == "linear"
                else "clipped_scalar_objective"
            )
            notes.append(
                f"{details} reason=one_observed_free_row objective={objective} "
                "quality=not_reported."
            )
            continue
        reason = f" reason={region.reason};" if region.reason else ""
        quality = ""
        if region.fit_r_squared is not None and region.fit_rmse is not None:
            quality = f" R²={region.fit_r_squared:.6g}, RMSE={region.fit_rmse:.6g} Pa;"
        notes.append(
            f"{details};{reason}{quality} maximum_change={region.max_abs_distortion:.6g} Pa."
        )
    if not targets:
        notes.append(
            "E prefix 뒤에 적합할 닫힌 회복 사건이 없어 원응력을 그대로 반환했습니다."
        )
    if progress_note:
        notes.append(progress_note)

    scalars = (
        *_diagnostic_scalars(stress, values, selection, None, None),
        Scalar(
            "band_model_source_elastic_end_index",
            "원자료 E 끝 원행 위치",
            float(elastic_end),
            "1",
        ),
        Scalar(
            "band_model_source_elastic_prefix_end_index",
            "현재 모델 입력에서 E prefix 끝 행 위치",
            float(prefix_end),
            "1",
        ),
        Scalar(
            "band_model_source_event_recovered_count",
            "검출된 닫힌 회복 사건 수",
            float(len(recovered)),
            "1",
        ),
        Scalar(
            "band_model_source_event_excluded_in_elastic_count",
            "E prefix 안에서 제외한 닫힌 사건 수",
            float(len(excluded)),
            "1",
        ),
        Scalar(
            "band_model_source_event_target_count",
            "E prefix 뒤 적합 대상 닫힌 사건 수",
            float(len(targets)),
            "1",
        ),
        Scalar(
            "band_model_source_event_crossing_noop_count",
            "경계에 편집 행이 없어 그대로 둔 사건 수",
            float(len(crossing_noops)),
            "1",
        ),
        Scalar(
            "band_model_source_event_fit_region_count",
            "자동 사건 적합 영향 구간 수",
            float(len(fitted.regions)),
            "1",
        ),
        Scalar(
            "band_model_source_event_one_free_row_region_count",
            "관측 자유행이 하나뿐인 퇴화 적합 구간 수",
            float(one_free_row_count),
            "1",
        ),
        Scalar(
            "band_model_source_event_bounded_anchor_count",
            "bounded observed anchor 규칙을 쓴 적합 구간 수",
            float(bounded_anchor_count),
            "1",
        ),
    )
    return StepResult(
        output_frame,
        notes=tuple(notes),
        scalars=scalars,
        effective_options=options,
    )


def _source_event_isotonic_no_band_result(
    frame: Frame,
    options: dict[str, Any],
    strain: NDArray[np.float64],
    stress: NDArray[np.float64],
    selection: StableBandSelection,
    progress_note: str,
    *,
    elastic_end: int,
    source_rows: NDArray[np.int64],
    legacy_error: ProcessingError,
) -> StepResult:
    """Rescue only the raw-PAVA conflict with an observed protected terminal."""
    from matcore.processing.tensile import _isotonic

    def held(reason: str) -> None:
        raise ProcessingError(
            "legacy isotonic_auto_v1 hold preserved; fixed-terminal source-event "
            f"rescue unavailable: {reason}; legacy reason: {legacy_error}"
        ) from None

    if (
        strain.size != stress.size
        or source_rows.size != stress.size
        or strain.size < 2
        or not np.all(np.isfinite(strain))
        or not np.all(np.isfinite(stress))
        or np.any(np.diff(strain) <= 0.0)
        or np.any(np.diff(source_rows) <= 0)
    ):
        held("원행 변형률 또는 source-row 대응이 유효하지 않습니다")

    prefix_positions = np.flatnonzero(source_rows <= elastic_end)
    prefix_end = int(prefix_positions[-1]) if prefix_positions.size else -1
    if prefix_end < 0:
        held("현재 입력에 매핑된 source-E prefix가 없습니다")
    preserve_boundary = prefix_end

    detected = tuple(detect_events(stress, 0.005, 0.005, 0.05))
    recovered = tuple(event for event in detected if _eligible_pool_event(event))
    excluded = tuple(event for event in recovered if event.end_index <= prefix_end)
    crossing = tuple(
        event for event in recovered if event.peak_index <= prefix_end < event.end_index
    )
    if crossing:
        crossings = tuple((event.peak_index, event.end_index) for event in crossing)
        held(f"source-E 경계를 지나는 닫힌 회복 사건을 보호합니다: {crossings}")

    targets = tuple(event for event in recovered if event.end_index > prefix_end)
    components = _source_event_cores(targets)
    protected_events = tuple(
        event
        for event in detected
        if event.kind == "terminal_unrecovered" or event.end_at_observation_boundary
    )
    protected = tuple((event.peak_index, event.end_index) for event in protected_events)
    if not components or not protected_events:
        held("닫힌 회복 성분 또는 관측 말단 보호 구간이 없습니다")

    trigger_matches: list[tuple[_SourceEventCore, DropEvent, float]] = []
    for terminal in protected_events:
        terminal_row = terminal.peak_index
        if terminal_row + 1 > terminal.end_index or terminal_row + 1 >= stress.size:
            continue
        if float(stress[terminal_row + 1]) >= float(stress[terminal_row]):
            continue
        ending = [component for component in components if component.right == terminal_row]
        if len(ending) != 1:
            continue
        component = ending[0]
        if component.start <= prefix_end:
            continue
        raw = stress[component.start : terminal_row + 1]
        unbounded = np.asarray(_isotonic(raw), dtype=np.float64)
        if unbounded.size != raw.size or not np.all(np.isfinite(unbounded)):
            held("말단 원성분의 동일행 PAVA 결과가 유효하지 않습니다")
        lift = float(unbounded[-1] - stress[terminal_row])
        if lift > 0.0:
            trigger_matches.append((component, terminal, lift))
    if len(trigger_matches) != 1:
        held(
            "source 원행의 닫힌 성분 하나가 보호 말단 시작에서 끝나고, "
            "동일행 PAVA가 그 말단 값을 올리는 유일한 접합을 찾지 못했습니다"
        )

    trigger_component, terminal_event, trigger_lift = trigger_matches[0]
    trigger_events = {id(event) for event in trigger_component.events}

    def choose_left(component: _SourceEventCore) -> int:
        right_value = float(stress[component.right])
        for candidate in range(component.start - 1, preserve_boundary - 1, -1):
            if float(stress[candidate]) > right_value:
                continue
            if _protected_anchor_overlap(candidate, component.right, protected) is not None:
                continue
            return candidate
        raise ProcessingError(
            f"원행 성분 {component.start}~{component.right}에서 source-E 뒤의 "
            "보호구간 밖 비감소 왼쪽 관측 앵커를 찾지 못했습니다."
        )

    # Recompute every merged interval from the unchanged source observations.
    merge_count = 0
    plans: list[tuple[_SourceEventCore, int]] = []
    while True:
        plans = [(component, choose_left(component)) for component in components]
        conflict: tuple[int, int] | None = None
        for right_index in range(1, len(plans)):
            left_anchor = plans[right_index][1]
            overlapping = [
                index for index in range(right_index) if left_anchor <= plans[index][0].right
            ]
            if overlapping:
                conflict = (min(overlapping), right_index)
                break
        if conflict is None:
            break
        first, last = conflict
        merged_events = tuple(
            event for component, _left in plans[first : last + 1] for event in component.events
        )
        merged = _SourceEventCore(
            plans[first][0].start,
            plans[last][0].right,
            merged_events,
        )
        components = [*components[:first], merged, *components[last + 1 :]]
        merge_count += 1
        if merge_count > len(recovered):
            held("원행 성분 접합이 유한 단계 안에 닫히지 않았습니다")

    values = stress.copy()
    editable = np.zeros(stress.size, dtype=bool)
    regions: list[_SourceEventIsotonicRegion] = []
    released_internal_anchors = 0
    for component, left in plans:
        right = component.right
        if not (preserve_boundary <= left < component.start <= right < stress.size):
            held(
                f"최종 원행 성분/앵커 순서가 유효하지 않습니다: "
                f"{component.start}~{right}, L={left}, P={prefix_end}"
            )
        if float(stress[left]) > float(stress[right]):
            held(f"고정 관측 앵커 응력이 감소합니다: L={left}, R={right}")
        fit_start, fit_end = left + 1, right - 1
        raw_interior = stress[fit_start:right]
        levels = np.asarray(_isotonic(raw_interior), dtype=np.float64)
        fitted = np.clip(levels, float(stress[left]), float(stress[right]))
        local = np.concatenate(
            (np.asarray([stress[left]], dtype=np.float64), fitted, np.asarray([stress[right]]))
        )
        if not np.all(np.isfinite(local)) or np.any(np.diff(local) < 0.0):
            held(f"고정 관측 성분 {left}~{right}의 비감소 적합에 실패했습니다")
        if np.any(editable[fit_start:right]):
            held(f"최종 편집 성분이 행을 공유합니다: {left}~{right}")
        values[fit_start:right] = fitted
        editable[fit_start:right] = True
        rule = (
            "bounded_terminal_join"
            if any(id(event) in trigger_events for event in component.events)
            else "bounded_observed_anchor"
        )
        regions.append(_SourceEventIsotonicRegion(component, left, fitted.copy(), rule))
        released_internal_anchors += max(len(component.events) - 1, 0)

    if prefix_end >= 0 and not np.array_equal(
        values[: prefix_end + 1], stress[: prefix_end + 1]
    ):
        held("source-E model prefix 원응력이 바뀌었습니다")
    for start, end in protected:
        if not np.array_equal(values[start : end + 1], stress[start : end + 1]):
            held(f"보호 말단 원행이 바뀌었습니다: {start}~{end}")
    if not np.array_equal(values[~editable], stress[~editable]):
        held("선언한 열린 fit 구간 밖 원응력이 바뀌었습니다")

    changed = int(np.count_nonzero(values[editable] != stress[editable]))
    residual = values[editable] - stress[editable]
    maximum_distortion = float(np.max(np.abs(residual))) if residual.size else 0.0
    rmse = float(np.sqrt(np.mean(residual**2))) if residual.size else 0.0
    unedited_edges = ~(editable[:-1] | editable[1:])
    unedited_declines = int(np.count_nonzero((np.diff(values) < 0.0) & unedited_edges))

    output_columns = dict(frame.columns)
    output_columns[options["stress"]] = values.copy()
    output_frame = Frame(output_columns, dict(frame.units))
    terminal_row = terminal_event.peak_index
    trigger_note = (
        f"source_isotonic_trigger model_prefix_end={prefix_end} "
        f"source_prefix_end={int(source_rows[prefix_end])} "
        f"minimal_component={trigger_component.start}~{trigger_component.right} "
        f"source_component={int(source_rows[trigger_component.start])}~"
        f"{int(source_rows[trigger_component.right])} "
        f"protected_terminal={terminal_row} "
        f"source_terminal={int(source_rows[terminal_row])} "
        f"raw_terminal_pa={float(stress[terminal_row]):.12g} "
        f"unbounded_pava_terminal_pa="
        f"{float(stress[terminal_row] + trigger_lift):.12g} "
        f"unbounded_lift_pa={trigger_lift:.12g}."
    )
    notes = [
        "legacy isotonic_auto_v1 no-band 계산이 보류되어 source-event 고정 말단 "
        f"접합 경로를 적용했습니다. 기존 보류 사유: {legacy_error}",
        trigger_note,
        f"source-E prefix 0~{prefix_end} (source row {int(source_rows[0])}~"
        f"{int(source_rows[prefix_end])})와 보호 말단 {protected}를 원응력 그대로 "
        "보존했습니다. 선언한 열린 편집구간 밖 응력도 원행과 같습니다.",
    ]
    for region in regions:
        component = region.component
        right = component.right
        fit_start, fit_end = region.left_anchor + 1, right - 1
        original_events = ",".join(
            f"{event.peak_index}~{event.end_index}" for event in component.events
        )
        source_events = ",".join(
            f"{int(source_rows[event.peak_index])}~{int(source_rows[event.end_index])}"
            for event in component.events
        )
        if fit_start <= fit_end:
            source_fit = f"{int(source_rows[fit_start])}~{int(source_rows[fit_end])}"
            region_residual = values[fit_start : fit_end + 1] - stress[fit_start : fit_end + 1]
            region_changed = int(
                np.count_nonzero(
                    values[fit_start : fit_end + 1] != stress[fit_start : fit_end + 1]
                )
            )
            region_max = float(np.max(np.abs(region_residual)))
            region_rmse = float(np.sqrt(np.mean(region_residual**2)))
            fit_rows = f"{fit_start}~{fit_end}"
            support_count = fit_end - fit_start + 1
        else:
            source_fit = "none"
            region_changed = 0
            region_max = 0.0
            region_rmse = 0.0
            fit_rows = "none"
            support_count = 0
        notes.append(
            f"source_event_fit method=isotonic original_events={original_events} "
            f"source_events={source_events} core={component.start}~{right - 1} "
            f"editable_rows={fit_rows} source_editable_rows={source_fit} "
            f"support_count={support_count} anchors={region.left_anchor}~{right} "
            f"source_anchors={int(source_rows[region.left_anchor])}~"
            f"{int(source_rows[right])} anchor_mode={region.anchor_rule} "
            f"objective=equal_row_bounded_l2 changed_points={region_changed} "
            f"max_abs_distortion_pa={region_max:.12g} rmse_pa={region_rmse:.12g}."
        )
    notes.append(
        f"적합된 열린 원행 구간의 전체 변경점={changed}, 최대 절대 왜곡="
        f"{maximum_distortion:.12g} Pa, RMSE={rmse:.12g} Pa; 적합하지 않은 "
        f"인접 원행에 남은 하강={unedited_declines}개입니다. 보호된 prefix/tail을 포함한 "
        "전체 곡선의 단조성을 주장하지 않습니다."
    )
    if progress_note:
        notes.append(progress_note)

    scalars = (
        *_diagnostic_scalars(stress, values, selection, None, None),
        Scalar(
            "band_model_source_elastic_end_index",
            "원자료 E 끝 원행 위치",
            float(elastic_end),
            "1",
        ),
        Scalar(
            "band_model_source_elastic_prefix_end_index",
            "현재 모델 입력에서 E prefix 끝 행 위치",
            float(prefix_end),
            "1",
        ),
        Scalar(
            "band_model_source_event_recovered_count",
            "검출된 닫힌 회복 사건 수",
            float(len(recovered)),
            "1",
        ),
        Scalar(
            "band_model_source_event_excluded_in_elastic_count",
            "E prefix 안에서 제외한 닫힌 사건 수",
            float(len(excluded)),
            "1",
        ),
        Scalar(
            "band_model_source_event_target_count",
            "E prefix 뒤 적합 대상 닫힌 사건 수",
            float(len(targets)),
            "1",
        ),
        Scalar(
            "band_model_source_event_fit_region_count",
            "자동 사건 적합 영향 구간 수",
            float(len(regions)),
            "1",
        ),
        Scalar(
            "band_model_source_event_isotonic_trigger_count",
            "고정 관측 말단 접합 게이트 통과 수",
            1.0,
            "1",
        ),
        Scalar(
            "band_model_source_event_isotonic_fit_region_count",
            "등위회귀 적합 연결 성분 수",
            float(len(regions)),
            "1",
        ),
        Scalar(
            "band_model_source_event_isotonic_released_anchor_count",
            "연결 성분에서 해제한 내부 앵커 수",
            float(released_internal_anchors),
            "1",
        ),
        Scalar(
            "band_model_source_event_isotonic_changed_points",
            "등위회귀 열린 구간 변경 원행 수",
            float(changed),
            "1",
        ),
        Scalar(
            "band_model_source_event_isotonic_max_abs_distortion",
            "등위회귀 최대 절대 왜곡",
            maximum_distortion,
            "Pa",
        ),
        Scalar(
            "band_model_source_event_isotonic_rmse",
            "등위회귀 열린 구간 RMSE",
            rmse,
            "Pa",
        ),
        Scalar(
            "band_model_source_event_isotonic_remaining_unedited_declines",
            "적합하지 않은 인접 원행에 남은 하강 수",
            float(unedited_declines),
            "1",
        ),
    )
    return StepResult(
        output_frame,
        notes=tuple(notes),
        scalars=scalars,
        effective_options=options,
    )


def band_model(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Select one stable original-row band and compose method-specific proposals."""
    resolved = _resolve_options(options)
    strain, stress, progress, progress_note = _load_source(frame, resolved)
    policy = resolved["policy"]
    source_elastic_end: int | None = None
    source_rows: NDArray[np.int64] | None = None
    if policy == SOURCE_EVENT_POLICY:
        source_elastic_end, source_rows = _source_row_mapping(frame, resolved)
    if policy == MANUAL_POLICY:
        selection = _manual_selection(
            strain,
            stress,
            progress,
            start=resolved["band_start"],
            end=resolved["band_end"],
            peak_row=resolved["peak_row"],
            maximum_gap_over_band_span=resolved["maximum_gap_over_band_span"],
        )
    else:
        try:
            selection = select_stable_band(
                strain,
                stress,
                progress,
                minimum_band_rows=resolved["minimum_band_rows"],
                minimum_progress_span=resolved["minimum_progress_span"],
                maximum_stress_over_peak=resolved["maximum_stress_over_peak"],
                maximum_range_over_peak=resolved["maximum_range_over_peak"],
                maximum_gap_over_band_span=resolved["maximum_gap_over_band_span"],
            )
        except (ValueError, TypeError) as exc:
            raise ProcessingError(f"안정 밴드 원행 입력을 검증할 수 없습니다: {exc}") from None

    if selection.reason == "not_found":
        if policy == SOURCE_EVENT_POLICY and resolved["method"] in _NUMERIC_METHODS:
            assert source_elastic_end is not None and source_rows is not None
            return _source_event_no_band_result(
                frame,
                resolved,
                strain,
                stress,
                selection,
                progress_note,
                elastic_end=source_elastic_end,
                source_rows=source_rows,
            )
        # Preserve the exact numerical compatibility path: do not even run the
        # new source-event detector when the automatic selector found no band.
        from matcore.processing.tensile import yield_drop

        try:
            legacy = yield_drop(
                frame,
                {
                    "method": _LEGACY_METHODS[resolved["method"]],
                    "strain": resolved["strain"],
                    "stress": resolved["stress"],
                },
            )
        except ProcessingError as exc:
            if policy == SOURCE_EVENT_POLICY and resolved["method"] == "isotonic":
                assert source_elastic_end is not None and source_rows is not None
                return _source_event_isotonic_no_band_result(
                    frame,
                    resolved,
                    strain,
                    stress,
                    selection,
                    progress_note,
                    elastic_end=source_elastic_end,
                    source_rows=source_rows,
                    legacy_error=exc,
                )
            raise
        legacy_stress = _real_vector(
            legacy.frame.require(resolved["stress"], what="원응력"), what="기존 자동 결과"
        )
        notes = list(legacy.notes)
        notes.append(
            "안정 밴드가 선택되지 않아 같은 방법의 legacy *_auto_v1 단계에 "
            "원입력을 그대로 위임했습니다."
        )
        if progress_note:
            notes.append(progress_note)
        return StepResult(
            legacy.frame,
            notes=tuple(notes),
            scalars=legacy.scalars
            + _diagnostic_scalars(stress, legacy_stress, selection, None, None),
            effective_options=resolved,
        )
    if selection.reason != "selected":
        raise ProcessingError(
            "선택 밴드 후보가 최대 원행 간격 지지 조건을 만족하지 않습니다: "
            f"reason={selection.reason}, max_gap_ratio={selection.max_gap_ratio}."
        )

    result = compute_band_model(
        strain,
        stress,
        progress,
        method=resolved["method"],
        policy=policy,
        minimum_band_rows=resolved["minimum_band_rows"],
        minimum_progress_span=resolved["minimum_progress_span"],
        maximum_stress_over_peak=resolved["maximum_stress_over_peak"],
        maximum_range_over_peak=resolved["maximum_range_over_peak"],
        maximum_gap_over_band_span=resolved["maximum_gap_over_band_span"],
        loading_floor_fraction=resolved["loading_floor_fraction"],
        band_start=resolved.get("band_start"),
        band_end=resolved.get("band_end"),
        peak_row=resolved.get("peak_row"),
        left_anchor=resolved.get("left_anchor"),
    )
    left_anchor = next(
        (
            record.left_anchor
            for record in result.records
            if record.region_kind == "band" and record.decision == "band_fit"
        ),
        None,
    )
    columns = {key: value for key, value in frame.columns.items()}
    columns[resolved["stress"]] = np.asarray(result.values, dtype=np.float64).copy()
    output_frame = Frame(columns, dict(frame.units))
    result_band_start = result.selection.band_start_row
    result_band_end = result.selection.band_end_row
    assert result_band_start is not None and result_band_end is not None
    notes = [
        f"방법={resolved['method']}, 정책={policy}, "
        f"원행 봉우리 p={result.selection.peak_row}, "
        f"선택 B={result_band_start}~{result_band_end}; 실제 적합 코어와 영향 구간은 "
        f"방법별 기록을 따릅니다. 밴드 연결 모델의 오른쪽 관측 앵커 "
        f"R_model={result.model_end_row}, "
        f"왼쪽 관측 앵커 L={left_anchor}.",
        "원응력 최댓값·밴드 통계는 측정 provenance이고, 선택한 곡선은 별도 모델 근사입니다. "
        "이 단계는 물리적 하항복점이나 파단을 판정하지 않습니다.",
    ]
    for record in result.records:
        event = record.source_event
        if record.region_kind == "band" and record.proposal is not None:
            notes.append(
                f"{record.method}: 원행 core {record.core_start}~{record.core_end}, "
                f"영향 {record.left_anchor}~{record.right_anchor}, 관측 앵커 "
                f"({record.left_anchor},{stress[record.left_anchor]:.6g} Pa)·"
                f"({record.right_anchor},{stress[record.right_anchor]:.6g} Pa); "
                f"원행 밴드 적합 {record.fit_rows_start}~{record.fit_rows_end}."
            )
        elif event is not None:
            notes.append(
                f"원행 사건 peak={event.peak_index}, kind={event.kind}, "
                f"행={event.peak_index}~{event.end_index}: {record.decision}"
                + (f" ({record.reason})" if record.reason else "")
                + (
                    f"; core={record.core_start}~{record.core_end}, "
                    f"influence={record.left_anchor}~{record.right_anchor}"
                    if record.proposal is not None
                    else ""
                )
                + "."
            )
    for composition in result.compositions:
        if composition.kind == "full_recovery_completion":
            notes.append(
                f"원행 full_recovery 사건 {composition.event_intervals}의 완료 관측행에 맞춰 "
                f"모델 오른쪽 앵커를 선택 밴드 끝 {result_band_end}에서 "
                f"{composition.outer_right}로 확장했습니다. 선택 밴드와 통계는 그대로입니다."
            )
        elif composition.kind == "lower_connected_component":
            notes.append(
                "하측 연결 조합: 원행 사건 "
                f"{composition.event_intervals}, 모델 성분 {composition.component_intervals}; "
                f"바깥 관측 앵커 L={composition.outer_left}, R={composition.outer_right}; "
                f"해제한 내부 앵커={composition.released_internal_anchors}; "
                f"새 영향 행={composition.newly_included_rows}; "
                f"직전 pool 기준 대비 신규 open span의 최종 곡선 변경="
                f"{composition.newly_changed_points}행, "
                f"최대 응력 변화={composition.max_additional_stress_change:.6g} Pa. "
                "뒤이은 연결 pool은 이 span을 다시 바꿀 수 있어 값은 최종 곡선을 "
                "기준으로 계산합니다. 모든 제안은 원응력에서 한 번 다시 계산했습니다."
            )
    edited_intervals = [
        (record.left_anchor, record.right_anchor)
        for record in result.records
        if record.proposal is not None and record.left_anchor is not None
    ]
    outside_decreases = 0
    for row in np.flatnonzero(np.diff(result.values) < 0.0):
        if not any(
            start <= int(row) and int(row) + 1 <= end for start, end in edited_intervals
        ):
            outside_decreases += 1
    notes.append(
        f"전체 입력이 아니라 각 선언 영향 구간만 확인했습니다. 편집 영역 밖에 원행 하강 "
        f"{outside_decreases}개가 남아 있습니다."
    )
    if progress_note:
        notes.append(progress_note)
    return StepResult(
        output_frame,
        notes=tuple(notes),
        scalars=_diagnostic_scalars(
            stress,
            result.values,
            result.selection,
            left_anchor,
            result.model_end_row,
            result.compositions,
        ),
        effective_options=resolved,
    )
