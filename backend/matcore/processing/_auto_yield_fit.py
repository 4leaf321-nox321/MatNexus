"""Observed-anchor fits for automatic event-scoped yield-drop approximations.

This module is deliberately independent of ``Frame`` and the processing registry.
It receives original, row-ordered arrays and returns a copied stress vector plus
the fit evidence needed by the caller and independent checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class AutoYieldFitError(ValueError):
    """An automatic event fit cannot honor its observed anchors safely."""


@dataclass(frozen=True)
class AutoYieldRegion:
    """Fit evidence for one non-overlapping anchor-to-anchor region.

    ``core_start`` through ``core_end`` are the inclusive rows used by the model
    fit. ``right_anchor`` is the actual observation immediately after that core.
    Only rows strictly between the anchors can change.
    """

    left_anchor: int
    right_anchor: int
    core_start: int
    core_end: int
    c0: float | None
    target_stress: float
    unconstrained_endpoints: tuple[float, float] | None
    constrained_endpoints: tuple[float, float]
    huber_delta: float | None
    fit_r_squared: float
    fit_rmse: float
    max_abs_distortion: float
    constraint_applied: bool


@dataclass(frozen=True)
class AutoYieldFitResult:
    """Copied fitted curve and reproducible diagnostics for all selected cores."""

    values: np.ndarray
    regions: tuple[AutoYieldRegion, ...]
    protected_intervals: tuple[tuple[int, int], ...]
    preserve_boundary: int
    preserve_boundary_reason: str
    fit_r_squared: float
    fit_rmse: float
    max_abs_distortion: float


@dataclass(frozen=True)
class _Candidate:
    start: int
    right: int
    left: int
    c0: float | None
    target: float
    unconstrained_endpoints: tuple[float, float] | None
    huber_delta: float | None


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _weighted_line(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, *, enforce_nondecreasing: bool = True
) -> tuple[np.ndarray, float, float]:
    """Match the existing centered/scaled OLS fit, with optional IRLS weights."""
    center = float(np.mean(x))
    scale = float(np.max(np.abs(x - center)))
    if not np.isfinite(scale) or scale <= 0:
        raise AutoYieldFitError("코어의 변형률이 퇴화해 자동 직선을 계산할 수 없습니다.")
    z = (x - center) / scale
    total = float(np.sum(weights))
    if not np.isfinite(total) or total <= 0:
        raise AutoYieldFitError("자동 회귀 가중치 합이 유효하지 않습니다.")
    z_bar = float(np.sum(weights * z) / total)
    y_bar = float(np.sum(weights * y) / total)
    denominator = float(np.sum(weights * (z - z_bar) ** 2))
    if not np.isfinite(denominator) or denominator <= np.finfo(float).eps:
        raise AutoYieldFitError("코어의 변형률이 퇴화해 자동 회귀를 계산할 수 없습니다.")
    slope_z = float(np.sum(weights * (z - z_bar) * (y - y_bar)) / denominator)
    if enforce_nondecreasing:
        slope_z = max(0.0, slope_z)
    intercept_z = y_bar - slope_z * z_bar
    fitted = intercept_z + slope_z * z
    slope = slope_z / scale
    intercept = intercept_z - slope * center
    return fitted, slope, intercept


def _unconstrained_core_fit(
    method: str, x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, tuple[float, float] | None, float | None, float | None]:
    """Get the method's nondecreasing fit before endpoint-anchor constraints."""
    if method == "median_plateau":
        level = float(np.median(y))
        return np.full(y.shape, level, dtype=np.float64), (level, level), level, None
    if method == "linear":
        return np.empty(0, dtype=np.float64), None, None, None

    ones = np.ones(y.size, dtype=np.float64)
    ols, _slope, _intercept = _weighted_line(
        x, y, ones, enforce_nondecreasing=(method == "least_squares")
    )
    if method == "least_squares":
        return ols, (float(ols[0]), float(ols[-1])), float(ols[0]), None
    if method != "robust_linear":
        raise AutoYieldFitError(f"지원하지 않는 자동 앵커 방법입니다: {method}")

    residual = y - ols
    mad = float(np.median(np.abs(residual - float(np.median(residual)))))
    max_abs = float(np.max(np.abs(y))) if y.size else 0.0
    scale = max(1.4826 * mad, 1e-6 * max_abs, 1.0)
    delta = 1.345 * scale
    previous = ols
    converged = False
    for _iteration in range(100):
        residual = y - previous
        absolute = np.abs(residual)
        weights = np.ones_like(absolute)
        outside = absolute > delta
        weights[outside] = delta / absolute[outside]
        fitted, _slope, _intercept = _weighted_line(x, y, weights)
        if not np.all(np.isfinite(fitted)):
            raise AutoYieldFitError("Huber 자동 회귀 결과가 유한하지 않습니다.")
        change = float(np.max(np.abs(fitted - previous)))
        fit_scale = max(1.0, float(np.max(np.abs(fitted))), max_abs)
        previous = fitted
        if change <= 1e-10 * fit_scale:
            converged = True
            break
    if not converged:
        raise AutoYieldFitError("Huber 자동 회귀가 100회 반복 안에 수렴하지 않았습니다.")
    return previous, (float(previous[0]), float(previous[-1])), float(previous[0]), delta


def _constrained_endpoints(
    t: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    lower: float,
    upper: float,
) -> tuple[tuple[float, float], bool]:
    """Solve weighted line fitting over ``lower <= a <= b <= upper``."""
    if not lower <= upper:
        raise AutoYieldFitError("앵커 응력이 감소해 비감소 코어를 연결할 수 없습니다.")
    left_basis = 1.0 - t
    right_basis = t
    design = np.column_stack((left_basis, right_basis))
    root_weights = np.sqrt(weights)
    try:
        unconstrained = np.linalg.lstsq(
            design * root_weights[:, None], y * root_weights, rcond=None
        )[0]
    except np.linalg.LinAlgError as exc:
        raise AutoYieldFitError("앵커 제약 직선의 최소제곱을 계산할 수 없습니다.") from exc

    def feasible(a: float, b: float) -> bool:
        return lower <= a <= b <= upper

    def loss(a: float, b: float) -> float:
        residual = y - (left_basis * a + right_basis * b)
        return float(np.sum(weights * residual**2))

    candidates: list[tuple[str, float, float]] = []
    if feasible(float(unconstrained[0]), float(unconstrained[1])):
        candidates.append(("unconstrained", float(unconstrained[0]), float(unconstrained[1])))

    denominator = float(np.sum(weights * right_basis**2))
    if denominator <= 0 or not np.isfinite(denominator):
        raise AutoYieldFitError("앵커 제약 직선의 오른쪽 가중치가 유효하지 않습니다.")
    b_at_lower = float(np.sum(weights * right_basis * (y - left_basis * lower)) / denominator)
    b_at_lower = min(upper, max(lower, b_at_lower))
    candidates.append(("left_edge", lower, b_at_lower))

    denominator = float(np.sum(weights * left_basis**2))
    if denominator <= 0 or not np.isfinite(denominator):
        raise AutoYieldFitError("앵커 제약 직선의 왼쪽 가중치가 유효하지 않습니다.")
    a_at_upper = float(np.sum(weights * left_basis * (y - right_basis * upper)) / denominator)
    a_at_upper = min(upper, max(lower, a_at_upper))
    candidates.append(("right_edge", a_at_upper, upper))

    diagonal = float(np.sum(weights * y) / np.sum(weights))
    diagonal = min(upper, max(lower, diagonal))
    candidates.append(("diagonal", diagonal, diagonal))

    _index, chosen = min(
        enumerate(candidates), key=lambda entry: (loss(entry[1][1], entry[1][2]), entry[0])
    )
    name, a, b = chosen
    constrained = name != "unconstrained"
    return (float(a), float(b)), constrained


def _fit_statistics(y: np.ndarray, fitted: np.ndarray) -> tuple[float, float]:
    residual = y - fitted
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    error = float(np.sum(residual**2))
    score = 1.0 if total == 0 and error == 0 else 0.0 if total == 0 else 1.0 - error / total
    rmse = float(np.sqrt(np.mean(residual**2)))
    if not np.isfinite(score) or not np.isfinite(rmse):
        raise AutoYieldFitError("자동 코어 적합 점수가 유한하지 않습니다.")
    return score, rmse


def _endpoint_line(t: np.ndarray, a: float, b: float) -> np.ndarray:
    fitted = a + (b - a) * t
    fitted[0] = a
    fitted[-1] = b
    return fitted


def _prepare_candidate(
    strain: np.ndarray,
    stress: np.ndarray,
    core: tuple[int, int],
    preserve_boundary: int,
    protected: tuple[tuple[int, int], ...],
    method: str,
) -> _Candidate:
    start, right = core
    if right - start < 2:
        raise AutoYieldFitError(
            f"core index {start}~{right} 에 자동 적합 점이 2개 미만입니다."
        )
    core_x = strain[start:right]
    core_y = stress[start:right]
    _unconstrained, endpoints, c0, huber_delta = _unconstrained_core_fit(
        method, core_x, core_y
    )
    if method == "linear":
        target = float(stress[right])
    else:
        assert c0 is not None
        target = min(c0, float(stress[right]))

    left: int | None = None
    for row in range(start - 1, preserve_boundary - 1, -1):
        if float(stress[row]) <= target:
            left = row
            break
    if left is None:
        raise AutoYieldFitError(
            f"core index {start}~{right} 에서 보존 경계 index {preserve_boundary} 뒤의 "
            f"응력 {target:.6g} Pa 이하 왼쪽 앵커를 찾지 못했습니다."
        )

    for protected_start, protected_end in protected:
        if protected_start <= left <= protected_end:
            raise AutoYieldFitError(
                f"왼쪽 앵커 index {left} 가 보호 말단 구간 "
                f"{protected_start}~{protected_end} 안에 있습니다."
            )
        # The first row of the protected terminal is allowed as the right anchor:
        # its measured value is used exactly and no later sample enters the fit.
        if protected_start <= right <= protected_end and right != protected_start:
            raise AutoYieldFitError(
                f"오른쪽 앵커 index {right} 가 보호 말단 구간의 첫 행이 아닙니다."
            )
        if max(left + 1, protected_start) <= min(right - 1, protected_end):
            raise AutoYieldFitError(
                f"영향 구간 index {left + 1}~{right - 1} 이 보호 말단 구간 "
                f"{protected_start}~{protected_end} 과 겹칩니다."
            )
    return _Candidate(start, right, left, c0, target, endpoints, huber_delta)


def _fit_candidate(
    strain: np.ndarray,
    stress: np.ndarray,
    candidate: _Candidate,
    method: str,
) -> tuple[np.ndarray, AutoYieldRegion]:
    left = candidate.left
    right = candidate.right
    start = candidate.start
    core_end = right - 1
    core_x = strain[start:right]
    core_y = stress[start:right]
    left_value = float(stress[left])
    right_value = float(stress[right])
    if right_value < left_value:
        raise AutoYieldFitError(
            f"앵커 응력이 {left_value:.6g} Pa에서 {right_value:.6g} Pa로 내려가 "
            "비감소 접합을 만들 수 없습니다."
        )

    constraint_applied = False
    if method == "linear":
        span = float(strain[right] - strain[left])
        if span <= 0:
            raise AutoYieldFitError(
                "관측 앵커 변형률이 증가하지 않아 직선을 만들 수 없습니다."
            )
        fitted_core = left_value + (right_value - left_value) * (
            (core_x - float(strain[left])) / span
        )
        endpoints = (float(fitted_core[0]), float(fitted_core[-1]))
    elif method == "median_plateau":
        assert candidate.c0 is not None
        level = min(right_value, max(left_value, candidate.c0))
        fitted_core = np.full(core_y.shape, level, dtype=np.float64)
        endpoints = (level, level)
        constraint_applied = level != candidate.c0
    else:
        if core_x.size < 2:
            raise AutoYieldFitError("자동 회귀 core 는 관측점 2점 이상이 필요합니다.")
        delta_x = float(core_x[-1] - core_x[0])
        if delta_x <= 0:
            raise AutoYieldFitError("자동 회귀 core 변형률이 엄격히 증가하지 않습니다.")
        t = (core_x - float(core_x[0])) / delta_x
        if method == "robust_linear":
            assert candidate.huber_delta is not None
            # Restart from the nondecreasing unconstrained Huber fit. Every IRLS
            # update itself solves the observed-anchor constrained weighted LS.
            initial, _endpoints, _c0, _delta = _unconstrained_core_fit(
                "robust_linear", core_x, core_y
            )
            previous = initial
            converged = False
            fitted_core = previous
            endpoints = (float(previous[0]), float(previous[-1]))
            for _iteration in range(100):
                residual = core_y - previous
                absolute = np.abs(residual)
                weights = np.ones_like(absolute)
                outside = absolute > candidate.huber_delta
                weights[outside] = candidate.huber_delta / absolute[outside]
                endpoints, constraint_applied = _constrained_endpoints(
                    t, core_y, weights, left_value, right_value
                )
                fitted_core = _endpoint_line(t, endpoints[0], endpoints[1])
                if not np.all(np.isfinite(fitted_core)):
                    raise AutoYieldFitError("Huber 앵커 적합 결과가 유한하지 않습니다.")
                change = float(np.max(np.abs(fitted_core - previous)))
                fit_scale = max(
                    1.0, float(np.max(np.abs(fitted_core))), float(np.max(np.abs(core_y)))
                )
                previous = fitted_core
                if change <= 1e-10 * fit_scale:
                    converged = True
                    break
            if not converged:
                raise AutoYieldFitError(
                    "Huber 앵커 적합이 100회 반복 안에 수렴하지 않았습니다."
                )
        else:  # least_squares
            weights = np.ones(core_y.size, dtype=np.float64)
            endpoints, constraint_applied = _constrained_endpoints(
                t, core_y, weights, left_value, right_value
            )
            fitted_core = _endpoint_line(t, endpoints[0], endpoints[1])

    if not np.all(np.isfinite(fitted_core)):
        raise AutoYieldFitError("자동 앵커 코어 계산 결과가 유한하지 않습니다.")
    score, rmse = _fit_statistics(core_y, fitted_core)
    proposed = stress.copy()
    left_span = float(strain[start] - strain[left])
    if left_span <= 0:
        raise AutoYieldFitError("왼쪽 앵커와 core 변형률이 증가하지 않습니다.")
    if start > left + 1:
        ramp_rows = np.arange(left + 1, start, dtype=int)
        fraction = (strain[ramp_rows] - strain[left]) / left_span
        proposed[ramp_rows] = left_value + fraction * (float(fitted_core[0]) - left_value)
    proposed[start:right] = fitted_core
    # The final core sample and observed right anchor are adjacent rows. The right
    # ramp therefore has no unmeasured interpolation points to synthesize.
    proposed[left] = stress[left]
    proposed[right] = stress[right]

    local = proposed[left : right + 1]
    if np.any(np.diff(local) < 0):
        raise AutoYieldFitError(
            f"영향 구간 index {left}~{right} 에 하강이 남아 자동 앵커 적합을 보류합니다."
        )
    if proposed[left] != stress[left] or proposed[right] != stress[right]:
        raise AutoYieldFitError("자동 앵커 적합이 관측 앵커 값을 바꾸었습니다.")
    max_abs_distortion = float(
        np.max(np.abs(proposed[left : right + 1] - stress[left : right + 1]))
    )
    region = AutoYieldRegion(
        left_anchor=left,
        right_anchor=right,
        core_start=start,
        core_end=core_end,
        c0=candidate.c0,
        target_stress=candidate.target,
        unconstrained_endpoints=candidate.unconstrained_endpoints,
        constrained_endpoints=(float(endpoints[0]), float(endpoints[1])),
        huber_delta=candidate.huber_delta,
        fit_r_squared=score,
        fit_rmse=rmse,
        max_abs_distortion=max_abs_distortion,
        constraint_applied=constraint_applied,
    )
    return proposed, region


def fit_event_cores(
    strain: np.ndarray,
    stress: np.ndarray,
    core_intervals: list[tuple[int, int]],
    protected_intervals: list[tuple[int, int]],
    preserve_boundary: int,
    method: str,
    *,
    preserve_boundary_reason: str,
) -> AutoYieldFitResult:
    """Fit recovered event cores without changing observed anchor or protected rows.

    Event intervals include their observed end row. For each merged core ``S~R``,
    the model sees raw rows ``S~R-1`` and preserves raw row ``R`` as the right
    anchor. The nearest eligible left anchor is selected from raw rows before S,
    no earlier than ``preserve_boundary``. Overlapping influence regions are merged
    and refit from the original arrays before any edits are returned.
    """
    x = np.asarray(strain, dtype=np.float64)
    y = np.asarray(stress, dtype=np.float64)
    if x.ndim != 1 or y.ndim != 1 or x.size != y.size:
        raise AutoYieldFitError("변형률과 응력은 길이가 같은 1차원 배열이어야 합니다.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise AutoYieldFitError("자동 앵커 적합 입력에 유한하지 않은 값이 있습니다.")
    if x.size < 2 or np.any(np.diff(x) <= 0):
        raise AutoYieldFitError("자동 앵커 적합 변형률은 원행에서 엄격히 증가해야 합니다.")
    if method not in ("median_plateau", "linear", "least_squares", "robust_linear"):
        raise AutoYieldFitError(f"지원하지 않는 자동 앵커 방법입니다: {method}")
    if not 0 <= preserve_boundary < x.size:
        raise AutoYieldFitError("자동 앵커 보존 경계가 관측 범위 밖입니다.")

    protected = tuple(_merge_intervals(protected_intervals))
    for start, end in (*core_intervals, *protected):
        if start < 0 or end < start or end >= x.size:
            raise AutoYieldFitError(f"자동 앵커 구간이 관측 범위 밖입니다: {start}~{end}.")
    cores = _merge_intervals(core_intervals)
    if not cores:
        values = y.copy()
        values.setflags(write=False)
        return AutoYieldFitResult(
            values,
            (),
            protected,
            preserve_boundary,
            preserve_boundary_reason,
            1.0,
            0.0,
            0.0,
        )

    # Each merge reduces the number of cores; hence this loop is finite.
    for _iteration in range(len(cores)):
        candidates = [
            _prepare_candidate(x, y, core, preserve_boundary, protected, method)
            for core in cores
        ]
        merge_at: int | None = None
        for index in range(len(candidates) - 1):
            if candidates[index + 1].left <= candidates[index].right:
                merge_at = index
                break
        if merge_at is None:
            break
        cores[merge_at : merge_at + 2] = [
            (cores[merge_at][0], max(cores[merge_at + 1][1], candidates[merge_at + 1].right))
        ]
    else:
        raise AutoYieldFitError("겹치는 자동 영향 구간을 유한 단계 안에 병합하지 못했습니다.")

    candidates = [
        _prepare_candidate(x, y, core, preserve_boundary, protected, method) for core in cores
    ]
    values = y.copy()
    fitted_regions: list[AutoYieldRegion] = []
    core_observed: list[np.ndarray] = []
    core_fitted: list[np.ndarray] = []
    for candidate in candidates:
        proposed, region = _fit_candidate(x, y, candidate, method)
        values[candidate.left + 1 : candidate.right] = proposed[
            candidate.left + 1 : candidate.right
        ]
        fitted_regions.append(region)
        core_observed.append(y[region.core_start : region.core_end + 1])
        core_fitted.append(proposed[region.core_start : region.core_end + 1])

    for start, end in protected:
        if np.any(values[start : end + 1] != y[start : end + 1]):
            raise AutoYieldFitError(
                f"자동 앵커 적합이 보호 말단 구간 {start}~{end} 을 바꾸었습니다."
            )
    observed = np.concatenate(core_observed)
    fitted = np.concatenate(core_fitted)
    score, rmse = _fit_statistics(observed, fitted)
    distortion = max(region.max_abs_distortion for region in fitted_regions)
    values.setflags(write=False)
    return AutoYieldFitResult(
        values,
        tuple(fitted_regions),
        protected,
        preserve_boundary,
        preserve_boundary_reason,
        score,
        rmse,
        distortion,
    )
