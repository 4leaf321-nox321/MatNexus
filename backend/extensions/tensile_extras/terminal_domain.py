"""Choose a reviewed or clearly abrupt terminal prefix for tensile models."""

from __future__ import annotations

from numbers import Integral
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_text

AUTO_POLICY = "terminal_loss_auto_v1"
PROGRESSIVE_POLICY = "terminal_loss_auto_v2"
MANUAL_POLICY = "manual_end_v1"
POLICIES = (AUTO_POLICY, PROGRESSIVE_POLICY, MANUAL_POLICY)
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_TIME = "time"
FIXED_OPTIONS: dict[str, Any] = {
    "profile_version": "1",
    "late_progress_fraction": 0.90,
    "support_window_rows": 5,
    "minimum_support_rows": 3,
    "support_tolerance_fraction": 0.10,
    "adjacent_loss_fraction": 0.20,
    "chain_first_loss_fraction": 0.10,
    "chain_max_rows": 3,
    "recovery_loss_fraction": 0.50,
    "gap_preceding_steps": 20,
    "gap_interval_ratio": 10.0,
    "gap_progress_fraction": 0.01,
    "stable_suffix_remaining_fraction": 0.02,
    "stable_suffix_load_fraction": 0.20,
    "stable_suffix_range_fraction": 0.10,
    "gradual_tail_fraction": 0.10,
    "gradual_tail_drop_fraction": 0.10,
}
PROGRESSIVE_OPTIONS: dict[str, Any] = {
    "profile_version": "2",
    "minimum_late_progress": 0.815,
    "score_grid_points": 251,
    "score_start_progress": 0.75,
    "sensitivity_start_progress": [0.70, 0.75, 0.80],
    "knot_start_progress": 0.80,
    "knot_max_progress": 0.985,
    "knot_end_margin_progress": 0.015,
    "knot_grid_points": 186,
    "minimum_post_pre_slope_ratio": 5.0,
    "minimum_hinge_sse_gain": 0.80,
    "minimum_candidate_loss_over_peak": 0.03,
    "minimum_rows_before_knot": 10,
    "minimum_rows_after_candidate": 10,
    "minimum_pre_knot_source_span": 0.03,
    "minimum_post_knot_source_span": 0.015,
    "near_optimal_sse_ratio": 1.05,
    "maximum_near_optimal_knot_span": 0.03,
    "maximum_sensitivity_knot_span": 0.03,
    "local_pre_knee_window_progress": 0.03,
    "local_pre_knee_grid_points": 31,
    "half_loss_fraction": 0.50,
    "maximum_rebound_fraction": 0.25,
    "stable_suffix_progress_span": 0.02,
    "stable_suffix_range_over_peak": 0.02,
    "stable_suffix_minimum_load_fraction": 0.20,
    "late_residual_mad_factor": 1.4826,
    "high_shape_loss_over_peak": 0.08,
    "substantial_decline_diagnostic_loss_fraction": 0.20,
}
PROGRESSIVE_FIXED_OPTIONS: dict[str, Any] = {
    **FIXED_OPTIONS,
    **PROGRESSIVE_OPTIONS,
}
LEGACY_OPTION_KEYS = frozenset(
    {"policy", "strain", "stress", "time", "end_index", *FIXED_OPTIONS}
)
PROGRESSIVE_OPTION_KEYS = frozenset(LEGACY_OPTION_KEYS | PROGRESSIVE_OPTIONS.keys())


def _resolve_options(
    options: dict[str, Any],
) -> tuple[str, str, str, str, int | None, dict[str, Any]]:
    allowed_options = (
        PROGRESSIVE_OPTION_KEYS
        if options.get("policy") == PROGRESSIVE_POLICY
        else LEGACY_OPTION_KEYS
    )
    unknown = sorted((key for key in options if key not in allowed_options), key=str)
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ProcessingError(f"지원하지 않는 말단 구간 옵션입니다: {names}.")

    fixed_options = (
        PROGRESSIVE_FIXED_OPTIONS
        if options.get("policy") == PROGRESSIVE_POLICY
        else FIXED_OPTIONS
    )
    for key, expected in fixed_options.items():
        if key in options:
            actual = options[key]
            if type(actual) is not type(expected) or actual != expected:
                raise ProcessingError(
                    f"'{key}' 정책은 {expected!r} 로 고정되어 있습니다. "
                    "다른 정책은 새 버전으로 정의해야 합니다."
                )

    policy = option_text(options, "policy", POLICIES)
    supplied = dict(options)
    supplied.setdefault("strain", DEFAULT_STRAIN)
    supplied.setdefault("stress", DEFAULT_STRESS)
    supplied.setdefault("time", DEFAULT_TIME)
    strain_name = option_text(supplied, "strain", ())
    stress_name = option_text(supplied, "stress", ())
    time_name = option_text(supplied, "time", ())

    end_index: int | None = None
    if policy == MANUAL_POLICY:
        if "end_index" not in options:
            raise ProcessingError("'manual_end_v1' 정책에는 검토한 'end_index' 가 필요합니다.")
        raw_end = options["end_index"]
        if isinstance(raw_end, bool) or not isinstance(raw_end, Integral):
            raise ProcessingError("'end_index' 는 bool 이 아닌 정수여야 합니다.")
        end_index = int(raw_end)
    elif "end_index" in options:
        raise ProcessingError("자동 정책은 'end_index' 를 받을 수 없습니다.")

    effective: dict[str, Any] = {
        "policy": policy,
        "strain": strain_name,
        "stress": stress_name,
        "time": time_name,
        **{
            key: value.copy() if isinstance(value, list) else value
            for key, value in fixed_options.items()
        },
    }
    if end_index is not None:
        effective["end_index"] = end_index
    return policy, strain_name, stress_name, time_name, end_index, effective


def _frame_arrays(frame: Frame) -> tuple[int, dict[str, np.ndarray]]:
    if not frame.columns:
        raise ProcessingError("말단 구간을 고를 곡선 열이 없습니다.")
    arrays: dict[str, np.ndarray] = {}
    expected_length: int | None = None
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"프레임 열 '{name}' 을 1차원 열로 읽을 수 없습니다."
            ) from None
        if values.ndim != 1:
            raise ProcessingError(f"프레임의 모든 열은 1차원이어야 합니다: '{name}'.")
        if expected_length is None:
            expected_length = len(values)
        elif len(values) != expected_length:
            raise ProcessingError(
                f"프레임 열의 점 수가 맞지 않습니다: '{name}' 은 {len(values)}점, "
                f"기준 열은 {expected_length}점입니다."
            )
        arrays[name] = values
    assert expected_length is not None
    if expected_length < 2:
        raise ProcessingError("말단 구간을 고르려면 프레임에 2점 이상 있어야 합니다.")
    return expected_length, arrays


def _real_values(values: np.ndarray, name: str, *, what: str) -> np.ndarray:
    if values.ndim != 1:
        raise ProcessingError(f"{what} 열 '{name}' 은 1차원이어야 합니다.")
    if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
        raise ProcessingError(f"{what} 열 '{name}' 은 실수형 숫자여야 합니다.")
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"{what} 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if not np.all(np.isfinite(result)):
        raise ProcessingError(f"{what} 열 '{name}' 에 유한하지 않은 값이 있습니다.")
    return result


def _require_unit(frame: Frame, name: str, expected: str, *, what: str) -> None:
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"{what} 열 '{name}' 의 단위는 '{expected}' 이어야 합니다. 현재 단위: {shown}."
        )


def _strictly_increasing(values: np.ndarray) -> bool:
    return bool(np.all(values[1:] > values[:-1]))


def _normalized(values: np.ndarray) -> np.ndarray | None:
    scale = max(abs(float(values[0])), abs(float(values[-1])))
    if scale == 0.0:
        return None
    scaled = values / scale
    span = float(scaled[-1] - scaled[0])
    if not np.isfinite(span) or span <= 0.0:
        return None
    progress: np.ndarray = (scaled - scaled[0]) / span
    if not np.all(np.isfinite(progress)) or not _strictly_increasing(progress):
        return None
    return progress


def _progress(
    arrays: dict[str, np.ndarray],
    frame: Frame,
    strain: np.ndarray,
    strain_name: str,
    time_name: str,
) -> tuple[np.ndarray, str, str | None]:
    time_reason: str | None = None
    if time_name not in arrays:
        time_reason = f"시간 열 '{time_name}' 이 없어 시간 진행축을 쓰지 않았습니다."
    elif frame.units.get(time_name) != "s":
        unit = frame.units.get(time_name)
        shown = "누락" if unit is None else repr(unit)
        time_reason = f"시간 열 '{time_name}' 의 단위가 {shown} 이므로 초로 읽지 않았습니다."
    else:
        try:
            time = _real_values(arrays[time_name], time_name, what="시간")
        except ProcessingError as exc:
            time_reason = str(exc)
        else:
            if not _strictly_increasing(time):
                time_reason = (
                    f"시간 열 '{time_name}' 이 원래 행 순서에서 엄격히 증가하지 않습니다."
                )
            else:
                normalized_time = _normalized(time)
                if normalized_time is not None:
                    return normalized_time, "time", None
                time_reason = f"시간 열 '{time_name}' 을 0~1 진행축으로 정규화할 수 없습니다."

    if _strictly_increasing(strain):
        normalized_strain = _normalized(strain)
        if normalized_strain is not None:
            return normalized_strain, "strain", time_reason
        strain_reason = f"변형률 열 '{strain_name}' 을 0~1 진행축으로 정규화할 수 없습니다."
    else:
        strain_reason = (
            f"변형률 열 '{strain_name}' 이 원래 행 순서에서 엄격히 증가하지 않습니다."
        )
    ordinal = np.arange(len(strain), dtype=float) / (len(strain) - 1)
    reason = f"{time_reason} {strain_reason} 행 순서를 진행축으로 사용했습니다."
    return ordinal, "ordinal", reason


def _median(values: np.ndarray) -> float:
    ordered = np.sort(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float(ordered[middle - 1] / 2.0 + ordered[middle] / 2.0)


def _drop_chain(stress: np.ndarray, index: int, local_load: float) -> tuple[int, str] | None:
    adjacent_limit = stress[index] - FIXED_OPTIONS["adjacent_loss_fraction"] * local_load
    if stress[index + 1] <= adjacent_limit:
        return index + 1, "adjacent"

    first_limit = stress[index] - FIXED_OPTIONS["chain_first_loss_fraction"] * local_load
    if stress[index + 1] > first_limit:
        return None
    for rows in (2, 3):
        end = index + rows
        if end >= len(stress):
            continue
        chain = stress[index + 1 : end + 1]
        if np.any(chain[1:] > chain[:-1]):
            continue
        if stress[end] <= adjacent_limit:
            return end, f"chain_{rows}"
    return None


def _gap_error(
    progress: np.ndarray, basis: str, index: int, end: int
) -> ProcessingError | None:
    if basis == "ordinal":
        return None
    increments = np.diff(progress)
    for row in range(index + 1, end + 1):
        step_index = row - 1
        prior = increments[
            max(0, step_index - FIXED_OPTIONS["gap_preceding_steps"]) : step_index
        ]
        positive = prior[prior > 0.0]
        if not len(positive):
            continue
        local = _median(positive)
        step = float(increments[step_index])
        if (
            step > FIXED_OPTIONS["gap_interval_ratio"] * local
            and step > FIXED_OPTIONS["gap_progress_fraction"]
        ):
            return ProcessingError(
                "ambiguous_sampling_gap: "
                f"후보 유지 행 {index} 의 손실 연결에서 입력 행 {row - 1}→{row} 진행 간격 "
                f"{step:.6g} 이 직전 간격 중앙값 {local:.6g} 의 10배 초과이며 "
                "전체 진행 폭의 1%보다 큽니다. 급락이 이 간격 안의 어느 위치에서 시작했는지 "
                "관측만으로 정할 수 없어 자동 자르기를 보류합니다."
            )
    return None


def _automatic_end(
    stress: np.ndarray, progress: np.ndarray, basis: str
) -> tuple[int | None, list[str], bool]:
    notes: list[str] = []
    n = len(stress)
    min_index = FIXED_OPTIONS["minimum_support_rows"] - 1
    for index in range(min_index, n - 1):
        if progress[index] < FIXED_OPTIONS["late_progress_fraction"]:
            continue
        local = _median(
            stress[max(0, index - FIXED_OPTIONS["support_window_rows"] + 1) : index + 1]
        )
        if local <= 0.0 or stress[index] <= 0.0:
            continue
        if abs(stress[index] - local) > FIXED_OPTIONS["support_tolerance_fraction"] * local:
            continue
        chain = _drop_chain(stress, index, local)
        if chain is None:
            continue
        end, kind = chain
        # Recovery after the shortest qualifying low row makes this an internal event.
        midpoint = stress[index] * 0.5 + stress[end] * 0.5
        if np.any(stress[end:] > midpoint):
            continue

        gap_error = _gap_error(progress, basis, index, end)
        if gap_error is not None:
            raise gap_error

        suffix = stress[index + 1 :]
        remaining = 1.0 - progress[index]
        stable_loaded = (
            remaining > FIXED_OPTIONS["stable_suffix_remaining_fraction"]
            and _median(suffix) >= FIXED_OPTIONS["stable_suffix_load_fraction"] * local
            and np.min(suffix)
            >= np.max(suffix) - FIXED_OPTIONS["stable_suffix_range_fraction"] * local
        )
        if stable_loaded:
            raise ProcessingError(
                "ambiguous_stable_low_suffix: "
                f"후보 유지 행 {index} 뒤에 진행 폭 {remaining:.6g} 의 안정된 "
                "하중 구간이 남습니다. "
                "의도된 하측 모델 구간일 수 있어 자동 자르기를 보류합니다."
            )

        first_loss_fraction = float((stress[index] - stress[index + 1]) / local)
        total_loss_fraction = float((stress[index] - stress[end]) / local)
        notes.extend(
            (
                f"결정 applied ({kind}); 후보 유지 행 {index}, 첫 제외 행 {index + 1}, "
                f"마지막 연결 행 {end}.",
                f"후보 행 응력 {stress[index]:.6g} Pa, 첫 제외 응력 "
                f"{stress[index + 1]:.6g} Pa, 끝 연결 응력 {stress[end]:.6g} Pa, "
                f"국소 기준 L={local:.6g} Pa, 첫 손실/L={first_loss_fraction:.6g}, "
                f"총 손실/L={total_loss_fraction:.6g}.",
            )
        )
        return index, notes, False
    return None, notes, _gradual_unresolved(stress, progress)


def _gradual_unresolved(stress: np.ndarray, progress: np.ndarray) -> bool:
    source_max = max(0.0, float(np.max(stress)))
    if source_max <= 0.0:
        return False
    first_late = int(
        np.searchsorted(progress, FIXED_OPTIONS["late_progress_fraction"], side="left")
    )
    threshold = FIXED_OPTIONS["gradual_tail_drop_fraction"] * source_max
    with np.errstate(over="ignore", invalid="ignore"):
        return bool(stress[-1] <= stress[first_late] - threshold)


def _progress_notes(basis: str, reason: str | None, strain_strict: bool) -> tuple[str, ...]:
    descriptions = {"time": "시간(s)", "strain": "변형률", "ordinal": "원래 행 순서"}
    notes = [f"진행축 {descriptions[basis]} 을 사용해 0~1 로 정규화했습니다."]
    if reason:
        notes.append(f"진행축 대체 이유: {reason}")
    if basis == "ordinal":
        notes.append("행 순서 진행축은 실제 시간·변형률 간격을 증명하지 않습니다.")
    if not strain_strict:
        notes.append(
            "변형률은 원래 행 순서에서 엄격히 증가하지 않습니다. "
            "뒤의 모델 단계는 자체 순서 검사를 합니다."
        )
    return tuple(notes)


def _ols_fit(
    design: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray] | None:
    try:
        coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank != design.shape[1] or not np.all(np.isfinite(coefficients)):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        residual = values - design @ coefficients
        sse = float(np.sum(residual * residual))
    if not np.isfinite(sse) or not np.all(np.isfinite(residual)):
        return None
    return coefficients, sse, residual


def _progressive_fit(
    progress: np.ndarray,
    stress: np.ndarray,
    peak: float,
    end_index: int,
    start: float,
    options: dict[str, Any],
) -> dict[str, float] | None:
    end_progress = float(progress[end_index])
    if not start < end_progress or peak <= 0.0:
        return None
    score_progress = np.linspace(start, end_progress, options["score_grid_points"])
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        score_stress = (
            np.interp(score_progress, progress[: end_index + 1], stress[: end_index + 1])
            / peak
        )
    if not np.all(np.isfinite(score_stress)):
        return None

    line_design = np.column_stack((np.ones_like(score_progress), score_progress))
    line_result = _ols_fit(line_design, score_stress)
    if line_result is None:
        return None
    _, line_sse, _ = line_result
    if line_sse <= 0.0:
        return None

    knot_upper = min(
        options["knot_max_progress"],
        end_progress - options["knot_end_margin_progress"],
    )
    if knot_upper < options["knot_start_progress"]:
        return None
    knots = np.linspace(
        options["knot_start_progress"], knot_upper, options["knot_grid_points"]
    )
    trials: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    best: tuple[float, float, np.ndarray, np.ndarray] | None = None
    for knot in knots:
        design = np.column_stack(
            (
                np.ones_like(score_progress),
                score_progress,
                np.maximum(0.0, score_progress - knot),
            )
        )
        result = _ols_fit(design, score_stress)
        if result is None:
            continue
        coefficients, sse, residual = result
        trial = (sse, float(knot), coefficients, residual)
        trials.append(trial)
        # Strict comparison keeps the earliest exact SSE tie.
        if best is None or sse < best[0]:
            best = trial
    if best is None:
        return None

    hinge_sse, knot, coefficients, residual = best
    candidate_index = int(np.searchsorted(progress[: end_index + 1], knot, side="right") - 1)
    first_source_index = int(np.searchsorted(progress[: end_index + 1], start, side="left"))
    before_rows = int(
        np.count_nonzero(
            (progress[: end_index + 1] >= start) & (progress[: end_index + 1] <= knot)
        )
    )
    after_rows = end_index - candidate_index
    pre_span = float(progress[candidate_index] - progress[first_source_index])
    post_span = float(progress[end_index] - progress[candidate_index])
    post_slope = float(coefficients[1] + coefficients[2])
    pre_slope = float(coefficients[1])
    slope_ratio = abs(post_slope) / max(abs(pre_slope), 0.001)
    gain = (line_sse - hinge_sse) / line_sse
    candidate_loss = (float(stress[candidate_index]) - float(stress[end_index])) / peak
    late_residual = residual[score_progress >= knot]
    late_center = float(np.median(late_residual))
    late_mad = float(
        options["late_residual_mad_factor"] * np.median(np.abs(late_residual - late_center))
    )
    near_knots = [
        one_knot
        for one_sse, one_knot, _, _ in trials
        if one_sse <= options["near_optimal_sse_ratio"] * hinge_sse
    ]
    if not near_knots:
        return None
    metrics = {
        "knot_progress": knot,
        "raw_fit_pre_progress_span": float(knot - start),
        "raw_fit_post_progress_span": float(end_progress - knot),
        "candidate_index": float(candidate_index),
        "pre_slope_per_progress": pre_slope,
        "post_slope_per_progress": post_slope,
        "slope_magnitude_ratio": float(slope_ratio),
        "line_sse": line_sse,
        "hinge_sse": hinge_sse,
        "hinge_sse_gain": float(gain),
        "remaining_loss_over_peak": float(candidate_loss),
        "source_rows_before_knot": float(before_rows),
        "source_rows_after_candidate": float(after_rows),
        "raw_source_pre_progress_span": pre_span,
        "raw_source_post_progress_span": post_span,
        "detrended_late_residual_mad_over_peak": late_mad,
        "near_optimal_knot_low_progress": min(near_knots),
        "near_optimal_knot_high_progress": max(near_knots),
        "near_optimal_knot_span_progress": max(near_knots) - min(near_knots),
    }
    return metrics if all(np.isfinite(value) for value in metrics.values()) else None


def _progressive_gaps(
    progress: np.ndarray, end_index: int, options: dict[str, Any]
) -> tuple[list[tuple[int, float, tuple[float, ...]]], float]:
    increments = np.diff(progress[: end_index + 1])
    end_progress = float(progress[end_index])
    starts = tuple(float(value) for value in options["sensitivity_start_progress"])
    significant: list[tuple[int, float, tuple[float, ...]]] = []
    maximum_intersecting_gap = 0.0
    for step_index, step in enumerate(increments):
        windows = tuple(
            start
            for start in starts
            if float(progress[step_index]) < end_progress
            and float(progress[step_index + 1]) > start
        )
        if not windows:
            continue
        maximum_intersecting_gap = max(maximum_intersecting_gap, float(step))
        prior = increments[
            max(0, step_index - FIXED_OPTIONS["gap_preceding_steps"]) : step_index
        ]
        positive = prior[prior > 0.0]
        if not len(positive):
            continue
        local = _median(positive)
        if (
            step > FIXED_OPTIONS["gap_interval_ratio"] * local
            and step > FIXED_OPTIONS["gap_progress_fraction"]
        ):
            significant.append((step_index, float(step), windows))
    return significant, maximum_intersecting_gap


def _progressive_terminal_end(
    stress: np.ndarray,
    progress: np.ndarray,
    basis: str,
    old_end: int,
    options: dict[str, Any],
) -> tuple[int, bool, tuple[str, ...], dict[str, float]]:
    peak = max(0.0, float(np.max(stress)))
    diagnostics: dict[str, float] = {"old_end_index": float(old_end)}
    reasons: list[str] = []
    base_fit: dict[str, float] | None = None
    sensitivity_fits: list[dict[str, float]] = []
    gaps: list[tuple[int, float, tuple[float, ...]]] = []
    max_gap = 0.0
    rebound = False
    stable_suffix = False

    if basis == "ordinal":
        reasons.append("gradual_progress_axis_unavailable")
    elif peak <= 0.0:
        reasons.append("positive_source_peak_unavailable")
    elif float(progress[old_end]) <= options["minimum_late_progress"]:
        reasons.append("insufficient_late_progress")
    else:
        base_fit = _progressive_fit(
            progress, stress, peak, old_end, options["score_start_progress"], options
        )
        if base_fit is None:
            reasons.append("base_fit_rank_or_support_unavailable")
        else:
            diagnostics.update(base_fit)
            candidate_index = int(base_fit["candidate_index"])
            local_start = max(
                options["score_start_progress"],
                base_fit["knot_progress"] - options["local_pre_knee_window_progress"],
            )
            local_progress = np.linspace(
                local_start,
                base_fit["knot_progress"],
                options["local_pre_knee_grid_points"],
            )
            local_samples = np.interp(
                local_progress, progress[: old_end + 1], stress[: old_end + 1]
            )
            local_pre = float(np.median(local_samples))
            candidate_load = float(stress[candidate_index])
            diagnostics["local_pre_knee_stress_pa"] = local_pre
            diagnostics["candidate_stress_pa"] = candidate_load
            if local_pre > 0.0:
                diagnostics["candidate_loss_over_local_pre_knee"] = (
                    candidate_load - float(stress[old_end])
                ) / local_pre
            late_mad = base_fit["detrended_late_residual_mad_over_peak"]
            if late_mad > 0.0:
                diagnostics["late_loss_to_residual_mad"] = (
                    base_fit["remaining_loss_over_peak"] / late_mad
                )

            for start in options["sensitivity_start_progress"]:
                fit = _progressive_fit(progress, stress, peak, old_end, start, options)
                if fit is None:
                    reasons.append(f"sensitivity_fit_unavailable_{start:.2f}")
                    continue
                sensitivity_fits.append(fit)
                if (
                    fit["source_rows_before_knot"] < options["minimum_rows_before_knot"]
                    or fit["source_rows_after_candidate"]
                    < options["minimum_rows_after_candidate"]
                    or fit["raw_source_pre_progress_span"]
                    < options["minimum_pre_knot_source_span"]
                    or fit["raw_source_post_progress_span"]
                    < options["minimum_post_knot_source_span"]
                ):
                    reasons.append(f"insufficient_sensitivity_support_{start:.2f}")
            if len(sensitivity_fits) == len(options["sensitivity_start_progress"]):
                knots = [fit["knot_progress"] for fit in sensitivity_fits]
                sensitivity_spread = max(knots) - min(knots)
                diagnostics["sensitivity_knot_spread"] = sensitivity_spread
                diagnostics["sensitivity_knot_start_0_70"] = knots[0]
                diagnostics["sensitivity_knot_start_0_75"] = knots[1]
                diagnostics["sensitivity_knot_start_0_80"] = knots[2]
                if sensitivity_spread > options["maximum_sensitivity_knot_span"]:
                    reasons.append("knot_window_sensitivity_over_0.03")

            gaps, max_gap = _progressive_gaps(progress, old_end, options)
            diagnostics["intersecting_gap_count"] = float(len(gaps))
            diagnostics["maximum_scored_window_gap_progress"] = max_gap
            if gaps:
                reasons.append("significant_intersecting_progress_gap")
                diagnostics["first_intersecting_gap_row"] = float(gaps[0][0])

            if (
                base_fit["near_optimal_knot_span_progress"]
                > options["maximum_near_optimal_knot_span"]
            ):
                reasons.append("ambiguous_near_optimal_knots")
            if (
                base_fit["source_rows_before_knot"] < options["minimum_rows_before_knot"]
                or base_fit["source_rows_after_candidate"]
                < options["minimum_rows_after_candidate"]
            ):
                reasons.append("insufficient_original_row_support")
            if (
                base_fit["raw_source_pre_progress_span"]
                < options["minimum_pre_knot_source_span"]
                or base_fit["raw_source_post_progress_span"]
                < options["minimum_post_knot_source_span"]
            ):
                reasons.append("insufficient_original_progress_span")
            if base_fit["post_slope_per_progress"] >= 0.0:
                reasons.append("post_slope_nonnegative")
            if base_fit["slope_magnitude_ratio"] < options["minimum_post_pre_slope_ratio"]:
                reasons.append("slope_ratio_below_5")
            if base_fit["hinge_sse_gain"] < options["minimum_hinge_sse_gain"]:
                reasons.append("hinge_gain_below_0.8")
            if (
                base_fit["remaining_loss_over_peak"]
                < options["minimum_candidate_loss_over_peak"]
            ):
                reasons.append("remaining_loss_below_0.03_peak")
            if candidate_load <= 0.0 or local_pre <= 0.0:
                reasons.append("nonpositive_candidate_or_local_loaded_force")

            loss = candidate_load - float(stress[old_end])
            half_loss = candidate_load - options["half_loss_fraction"] * loss
            crossings = np.flatnonzero(stress[candidate_index + 1 : old_end + 1] <= half_loss)
            if len(crossings):
                first_half_index = candidate_index + 1 + int(crossings[0])
                rebound = bool(
                    np.max(stress[first_half_index : old_end + 1])
                    > candidate_load - options["maximum_rebound_fraction"] * loss
                )
            diagnostics["post_half_loss_recovery"] = float(rebound)
            if rebound:
                reasons.append("post_half_loss_recovery")

            stable_start_progress = base_fit["knot_progress"] + 0.5 * (
                float(progress[old_end]) - base_fit["knot_progress"]
            )
            suffix_start = int(
                np.searchsorted(progress[: old_end + 1], stable_start_progress, side="left")
            )
            final_half = stress[suffix_start : old_end + 1]
            stable_suffix = bool(
                len(final_half) > 1
                and float(progress[old_end] - progress[suffix_start])
                >= options["stable_suffix_progress_span"]
                and (float(np.max(final_half)) - float(np.min(final_half))) / peak
                <= options["stable_suffix_range_over_peak"]
                and _median(final_half)
                >= options["stable_suffix_minimum_load_fraction"] * candidate_load
            )
            diagnostics["stable_loaded_final_suffix"] = float(stable_suffix)
            if stable_suffix:
                reasons.append("stable_loaded_final_suffix")

    # Keep notes deterministic and concise when a gate is detected more than once.
    reasons = list(dict.fromkeys(reasons))
    selected = not reasons and base_fit is not None
    end_index = int(base_fit["candidate_index"]) if selected and base_fit else old_end
    diagnostics["onset_status_code"] = float(selected)
    notes: list[str] = []
    if selected and base_fit is not None:
        shape = (
            "high_shape"
            if base_fit["remaining_loss_over_peak"] >= options["high_shape_loss_over_peak"]
            else "moderate_shape"
        )
        notes.append(
            "결정 progressive_terminal_loss_onset; v1 끝 행 "
            f"{old_end} 에서 연속 힌지의 근사 가속 시작 후보 행 {end_index} 까지 "
            "앞당겼습니다. "
            f"형상 선별 수준은 {shape} 이며 파단 판정은 아닙니다."
        )
    else:
        reason_text = ", ".join(reasons) if reasons else "progressive_fit_unavailable"
        notes.append(
            f"결정 progressive_terminal_loss_retained; v1 끝 행 {old_end} 를 유지했습니다. "
            f"v2 보류 이유: {reason_text}."
        )
        if base_fit is not None:
            source_peak_loss = (peak - float(stress[old_end])) / peak if peak > 0.0 else 0.0
            shape_reasons = {
                "post_slope_nonnegative",
                "slope_ratio_below_5",
                "hinge_gain_below_0.8",
            }
            if source_peak_loss >= options[
                "substantial_decline_diagnostic_loss_fraction"
            ] and shape_reasons.intersection(reasons):
                notes.append(
                    "진단 substantial_preterminal_loss_no_distinct_onset; v1 끝까지 "
                    "양의 원응력 최댓값 대비 큰 손실은 있었지만, v2는 구별되는 말단 가속 "
                    "시작을 받아들이지 않았습니다. 이 중립 진단은 연속 감소와 긴 저응력 "
                    "평탄부를 구별하지 않습니다."
                )
    if base_fit is not None:
        candidate_index = int(base_fit["candidate_index"])
        notes.append(
            f"진단 후보 행 {candidate_index}, 기준 끝 행 {old_end}, knot 진행도 "
            f"{base_fit['knot_progress']:.6g}, 전/후 기울기 "
            f"{base_fit['pre_slope_per_progress']:.6g}/"
            f"{base_fit['post_slope_per_progress']:.6g}, "
            f"기울기비 {base_fit['slope_magnitude_ratio']:.6g}, 힌지 SSE 개선 "
            f"{base_fit['hinge_sse_gain']:.6g}, 후보~기준 끝 손실/P "
            f"{base_fit['remaining_loss_over_peak']:.6g}, 원래 행 지지 "
            f"{int(base_fit['source_rows_before_knot'])}/"
            f"{int(base_fit['source_rows_after_candidate'])}, "
            f"원래 진행폭 {base_fit['raw_source_pre_progress_span']:.6g}/"
            f"{base_fit['raw_source_post_progress_span']:.6g}."
        )
        if gaps:
            row, gap, windows = gaps[0]
            note_windows = ", ".join(f"{window:.2f}" for window in windows)
            notes.append(
                f"진단 입력 간격 {row}→{row + 1} 진행 폭 {gap:.6g} 이 점수 구간 "
                f"{note_windows} 과 교차합니다."
            )
        if "local_pre_knee_stress_pa" in diagnostics:
            notes.append(
                f"진단 국소 무릎 전 기준응력 "
                f"{diagnostics['local_pre_knee_stress_pa']:.6g} Pa, "
                f"후반 힌지 잔차 MAD/P "
                f"{base_fit['detrended_late_residual_mad_over_peak']:.6g}. "
                "이 MAD 는 힌지 적합 잔차의 산포이며 센서 잡음 측정값이 아닙니다."
            )
            if "late_loss_to_residual_mad" in diagnostics:
                notes.append(
                    f"진단 후보~끝 응력 손실/MAD "
                    f"{diagnostics['late_loss_to_residual_mad']:.6g}."
                )
            else:
                notes.append(
                    "진단 손실/MAD 는 후반 힌지 잔차 MAD 가 0 이어서 계산하지 않았습니다."
                )
    return (
        end_index,
        selected,
        tuple(notes),
        {key: value for key, value in diagnostics.items() if np.isfinite(value)},
    )


def _progressive_scalars(diagnostics: dict[str, float]) -> tuple[Scalar, ...]:
    labels = {
        "old_end_index": ("terminal_domain_v2_old_end_index", "v2 기준 끝 행 위치", "1"),
        "onset_status_code": (
            "terminal_domain_v2_onset_status_code",
            "v2 가속 시작 적용 코드",
            "1",
        ),
        "candidate_index": (
            "terminal_domain_v2_candidate_index",
            "v2 가속 시작 후보 행 위치",
            "1",
        ),
        "knot_progress": ("terminal_domain_v2_knot_progress", "v2 힌지 무릎 진행도", "1"),
        "raw_fit_pre_progress_span": (
            "terminal_domain_v2_raw_fit_pre_progress_span",
            "v2 적합창 무릎 전 진행폭",
            "1",
        ),
        "raw_fit_post_progress_span": (
            "terminal_domain_v2_raw_fit_post_progress_span",
            "v2 적합창 무릎 후 진행폭",
            "1",
        ),
        "pre_slope_per_progress": (
            "terminal_domain_v2_pre_slope_per_progress",
            "v2 무릎 전 기울기",
            "1",
        ),
        "post_slope_per_progress": (
            "terminal_domain_v2_post_slope_per_progress",
            "v2 무릎 후 기울기",
            "1",
        ),
        "slope_magnitude_ratio": (
            "terminal_domain_v2_slope_magnitude_ratio",
            "v2 기울기 크기비",
            "1",
        ),
        "hinge_sse_gain": ("terminal_domain_v2_hinge_sse_gain", "v2 힌지 SSE 개선", "1"),
        "remaining_loss_over_peak": (
            "terminal_domain_v2_remaining_loss_over_peak",
            "v2 후보~끝 하중 손실/양의 최댓값",
            "1",
        ),
        "local_pre_knee_stress_pa": (
            "terminal_domain_v2_local_pre_knee_stress",
            "v2 국소 무릎 전 기준응력",
            "Pa",
        ),
        "candidate_stress_pa": (
            "terminal_domain_v2_candidate_stress",
            "v2 가속 시작 후보 응력",
            "Pa",
        ),
        "candidate_loss_over_local_pre_knee": (
            "terminal_domain_v2_loss_over_local_pre_knee",
            "v2 손실/국소 무릎 전 하중",
            "1",
        ),
        "detrended_late_residual_mad_over_peak": (
            "terminal_domain_v2_late_residual_mad_over_peak",
            "v2 후반 힌지 잔차 MAD/양의 최댓값",
            "1",
        ),
        "late_loss_to_residual_mad": (
            "terminal_domain_v2_loss_to_residual_mad",
            "v2 손실/후반 힌지 잔차 MAD",
            "1",
        ),
        "source_rows_before_knot": (
            "terminal_domain_v2_source_rows_before_knot",
            "v2 무릎 전 원래 행 수",
            "1",
        ),
        "source_rows_after_candidate": (
            "terminal_domain_v2_source_rows_after_candidate",
            "v2 후보 뒤 원래 행 수",
            "1",
        ),
        "raw_source_pre_progress_span": (
            "terminal_domain_v2_source_pre_progress_span",
            "v2 무릎 전 원래 진행폭",
            "1",
        ),
        "raw_source_post_progress_span": (
            "terminal_domain_v2_source_post_progress_span",
            "v2 후보 뒤 원래 진행폭",
            "1",
        ),
        "near_optimal_knot_low_progress": (
            "terminal_domain_v2_near_optimal_knot_low",
            "v2 근최적 무릎 하한",
            "1",
        ),
        "near_optimal_knot_high_progress": (
            "terminal_domain_v2_near_optimal_knot_high",
            "v2 근최적 무릎 상한",
            "1",
        ),
        "near_optimal_knot_span_progress": (
            "terminal_domain_v2_near_optimal_knot_span",
            "v2 근최적 무릎 폭",
            "1",
        ),
        "sensitivity_knot_spread": (
            "terminal_domain_v2_sensitivity_knot_spread",
            "v2 점수 시작 민감도 무릎 폭",
            "1",
        ),
        "intersecting_gap_count": (
            "terminal_domain_v2_intersecting_gap_count",
            "v2 점수 구간 교차 큰 간격 수",
            "1",
        ),
        "maximum_scored_window_gap_progress": (
            "terminal_domain_v2_max_scored_gap",
            "v2 점수 구간 최대 원래 간격",
            "1",
        ),
        "post_half_loss_recovery": (
            "terminal_domain_v2_post_half_loss_recovery",
            "v2 절반 손실 뒤 회복 여부",
            "1",
        ),
        "stable_loaded_final_suffix": (
            "terminal_domain_v2_stable_loaded_suffix",
            "v2 안정 하중 끝 구간 여부",
            "1",
        ),
    }
    return tuple(
        Scalar(key, label, diagnostics[source], unit)
        for source, (key, label, unit) in labels.items()
        if source in diagnostics and np.isfinite(diagnostics[source])
    )


def terminal_domain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Retain a manual or supported abrupt-loss prefix for model methods."""
    policy, strain_name, stress_name, time_name, manual_end, effective = _resolve_options(
        options
    )
    n, arrays = _frame_arrays(frame)
    frame.require(strain_name, what="변형률")
    frame.require(stress_name, what="응력")
    _require_unit(frame, strain_name, "1", what="변형률")
    _require_unit(frame, stress_name, "Pa", what="응력")
    strain = _real_values(arrays[strain_name], strain_name, what="변형률")
    stress = _real_values(arrays[stress_name], stress_name, what="응력")
    strain_strict = _strictly_increasing(strain)
    progress, basis, fallback_reason = _progress(arrays, frame, strain, strain_name, time_name)

    progress_notes = _progress_notes(basis, fallback_reason, strain_strict)
    decision_code: float
    unresolved = False
    candidate_notes: tuple[str, ...] = ()
    end_index: int | None
    if policy == MANUAL_POLICY:
        assert manual_end is not None
        if manual_end < 1 or manual_end >= n:
            raise ProcessingError(
                f"'end_index' 는 현재 입력 프레임에서 1~{n - 1} 사이의 정수여야 합니다: "
                f"{manual_end}."
            )
        end_index = manual_end
        decision_code = 2.0
        if end_index == n - 1:
            candidate_notes = (
                f"결정 applied (manual_end_v1); 현재 입력 행 0~{end_index} 를 "
                "모두 유지했습니다.",
            )
        else:
            candidate_notes = (
                f"결정 applied (manual_end_v1); 현재 입력 행 0~{end_index} 를 유지하고 "
                f"{end_index + 1}~{n - 1} 을 제외합니다.",
            )
    elif policy == PROGRESSIVE_POLICY:
        v1_end, automatic_notes, unresolved = _automatic_end(stress, progress, basis)
        old_end = n - 1 if v1_end is None else v1_end
        decision_code = 0.0 if v1_end is None else 1.0
        if v1_end is None:
            candidate_notes = (
                f"결정 no_abrupt_terminal_loss; 현재 입력 행 0~{n - 1} 을 모두 유지했습니다.",
            )
        else:
            candidate_notes = tuple(automatic_notes)
        end_index, progressive_selected, progressive_notes, progressive_diagnostics = (
            _progressive_terminal_end(stress, progress, basis, old_end, effective)
        )
        candidate_notes = (*candidate_notes, *progressive_notes)
        if progressive_selected:
            decision_code = 3.0
            unresolved = False
    else:
        end_index, automatic_notes, unresolved = _automatic_end(stress, progress, basis)
        if end_index is None:
            end_index = n - 1
            decision_code = 0.0
            candidate_notes = (
                f"결정 no_abrupt_terminal_loss; 현재 입력 행 0~{n - 1} 을 모두 유지했습니다.",
            )
        else:
            decision_code = 1.0
            candidate_notes = tuple(automatic_notes)

    if policy == MANUAL_POLICY:
        selected = frame if end_index == n - 1 else frame.select(np.arange(end_index + 1))
    elif decision_code in {1.0, 3.0}:
        selected = frame.select(np.arange(end_index + 1))
    else:
        selected = frame

    notes = [f"정책 {policy}.", *progress_notes, *candidate_notes]
    if unresolved and policy in {AUTO_POLICY, PROGRESSIVE_POLICY}:
        first_late = int(
            np.searchsorted(progress, FIXED_OPTIONS["late_progress_fraction"], side="left")
        )
        notes.append(
            "결정 gradual_tail_unresolved; 마지막 진행축 10% 구간 첫 응력 "
            f"{stress[first_late]:.6g} Pa 에서 끝 응력 {stress[-1]:.6g} Pa 까지 "
            "양의 원응력 최댓값의 10% 이상 감소했지만 이 급락 정책은 완만한 끝 감소를 "
            "자르지 않습니다. 말단이 물리적으로 유효하다고 판정한 것은 아닙니다."
        )
    notes.append("말단 구간 선택은 모델용 기록 범위이며 네킹이나 파단을 판정하지 않습니다.")

    scalar_values: tuple[Scalar, ...] = (
        Scalar(
            "terminal_domain_end_index", "모델 구간 끝 행 위치 (0부터)", float(end_index), "1"
        ),
        Scalar(
            "terminal_domain_end_strain",
            "모델 구간 끝 변형률",
            float(strain[end_index]),
            "1",
            "strain",
        ),
        Scalar(
            "terminal_domain_removed_points",
            "제외한 말단 점 수",
            float(n - end_index - 1),
            "1",
        ),
        Scalar("terminal_domain_input_points", "입력 점 수", float(n), "1"),
        Scalar("terminal_domain_input_end_load", "입력 끝 응력", float(stress[-1]), "Pa"),
        Scalar("terminal_domain_decision_code", "말단 결정 코드", decision_code, "1"),
        Scalar(
            "terminal_domain_strain_strict",
            "입력 변형률 엄격 증가 여부",
            float(strain_strict),
            "1",
        ),
        Scalar(
            "terminal_domain_progress_basis_code",
            "진행축 코드",
            {"ordinal": 0.0, "strain": 1.0, "time": 2.0}[basis],
            "1",
        ),
    )
    if policy == PROGRESSIVE_POLICY:
        scalar_values += _progressive_scalars(progressive_diagnostics)
    if not all(np.isfinite(scalar.value) for scalar in scalar_values):
        raise ProcessingError("말단 구간 진단값이 유한하지 않습니다.")
    return StepResult(
        frame=selected,
        notes=tuple(notes),
        scalars=scalar_values,
        effective_options=effective,
    )
