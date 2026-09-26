"""Pure source-row selection for a stable lower-stress modeling region."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

DEFAULT_MINIMUM_BAND_ROWS = 20
DEFAULT_MINIMUM_PROGRESS_SPAN = 0.10
DEFAULT_MAXIMUM_STRESS_OVER_PEAK = 0.90
DEFAULT_MAXIMUM_RANGE_OVER_PEAK = 0.02
DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN = 0.10

ProgressBasis = Literal["progress_channel", "engineering_strain"]
SelectionReason = Literal["selected", "not_found", "insufficient_support"]


@dataclass(frozen=True, slots=True)
class StableBandSelection:
    """Immutable diagnostics for one contiguous band in the incoming rows."""

    peak_row: int
    peak_stress: float
    band_start_row: int | None
    band_end_row: int | None
    progress_basis: ProgressBasis
    progress_span: float | None
    max_gap_ratio: float | None
    source_row_count: int
    band_min_stress: float | None
    band_max_stress: float | None
    band_median_stress: float | None
    reason: SelectionReason


def _real_vector(values: ArrayLike, *, name: str) -> NDArray[np.float64]:
    try:
        raw = np.asarray(values)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a one-dimensional real numeric array.") from None
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional.")
    if not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ValueError(f"{name} must contain real numeric values.")
    try:
        numeric = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} cannot be represented as real numeric values.") from None
    if not np.all(np.isfinite(numeric)):
        raise ValueError(f"{name} must contain only finite values.")
    return numeric


def _usable_progress(
    values: ArrayLike | None, *, row_count: int
) -> NDArray[np.float64] | None:
    if values is None:
        return None
    try:
        progress = _real_vector(values, name="progress")
    except ValueError:
        return None
    if progress.size != row_count or not np.all(progress[1:] > progress[:-1]):
        return None
    return progress


def _normalized_axis(axis: NDArray[np.float64]) -> NDArray[np.float64]:
    """Normalize a strict finite axis without overflowing its endpoint span."""
    scale = max(abs(float(axis[0])), abs(float(axis[-1])))
    if scale == 0.0:
        raise ValueError("The progress axis must have a positive span.")
    scaled = axis / scale
    span = float(scaled[-1] - scaled[0])
    if not np.isfinite(span) or span <= 0.0:
        raise ValueError("The progress axis cannot be normalized to a finite span.")
    normalized: NDArray[np.float64] = np.asarray((scaled - scaled[0]) / span, dtype=np.float64)
    normalized[0] = 0.0
    normalized[-1] = 1.0
    if not np.all(np.isfinite(normalized)) or not np.all(normalized[1:] > normalized[:-1]):
        raise ValueError("The normalized progress axis must remain strictly increasing.")
    return normalized


def _validated_fraction(
    value: float,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite JSON number.")
    numeric = float(value)
    if not np.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum} and {maximum}.")
    return numeric


def select_stable_band(
    engineering_strain: ArrayLike,
    engineering_stress: ArrayLike,
    progress: ArrayLike | None = None,
    *,
    minimum_band_rows: int = DEFAULT_MINIMUM_BAND_ROWS,
    minimum_progress_span: float = DEFAULT_MINIMUM_PROGRESS_SPAN,
    maximum_stress_over_peak: float = DEFAULT_MAXIMUM_STRESS_OVER_PEAK,
    maximum_range_over_peak: float = DEFAULT_MAXIMUM_RANGE_OVER_PEAK,
    maximum_gap_over_band_span: float = DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN,
) -> StableBandSelection:
    """Select the longest qualifying post-peak band without changing source rows.

    The value and range limits are fractions of the first global stress maximum.
    Progress is normalized across this incoming prefix only. An unusable optional
    progress channel falls back to the already-validated engineering strain.
    """
    if type(minimum_band_rows) is not int or minimum_band_rows < 2:
        raise ValueError("minimum_band_rows must be an integer of at least 2.")
    minimum_progress_span = _validated_fraction(
        minimum_progress_span,
        name="minimum_progress_span",
        minimum=0.0,
        maximum=1.0,
    )
    maximum_stress_over_peak = _validated_fraction(
        maximum_stress_over_peak,
        name="maximum_stress_over_peak",
        minimum=0.0,
        maximum=1.0,
    )
    maximum_range_over_peak = _validated_fraction(
        maximum_range_over_peak,
        name="maximum_range_over_peak",
        minimum=0.0,
        maximum=1.0,
    )
    maximum_gap_over_band_span = _validated_fraction(
        maximum_gap_over_band_span,
        name="maximum_gap_over_band_span",
        minimum=0.0,
        maximum=1.0,
    )

    strain = _real_vector(engineering_strain, name="engineering_strain")
    stress = _real_vector(engineering_stress, name="engineering_stress")
    if strain.size != stress.size:
        raise ValueError("engineering_strain and engineering_stress must have equal length.")
    if strain.size < 2:
        raise ValueError("At least two source rows are required.")
    if not np.all(strain[1:] > strain[:-1]):
        raise ValueError("engineering_strain must be strictly increasing in source order.")

    peak_row = int(np.argmax(stress))
    peak_stress = float(stress[peak_row])
    if peak_stress <= 0.0:
        raise ValueError("engineering_stress must have a positive maximum.")

    progress_values = _usable_progress(progress, row_count=int(strain.size))
    basis: ProgressBasis = (
        "progress_channel" if progress_values is not None else "engineering_strain"
    )
    axis = strain if progress_values is None else progress_values
    try:
        normalized_progress = _normalized_axis(axis)
    except ValueError:
        if progress_values is None:
            raise
        basis = "engineering_strain"
        normalized_progress = _normalized_axis(strain)

    value_limit = maximum_stress_over_peak * peak_stress
    range_limit = maximum_range_over_peak * peak_stress
    left = peak_row + 1
    maxima: deque[int] = deque()
    minima: deque[int] = deque()
    best_start: int | None = None
    best_end: int | None = None
    best_span = -1.0

    for right in range(peak_row + 1, int(stress.size)):
        while maxima and stress[maxima[-1]] <= stress[right]:
            maxima.pop()
        maxima.append(right)
        while minima and stress[minima[-1]] >= stress[right]:
            minima.pop()
        minima.append(right)

        while left <= right and (
            stress[minima[0]] <= 0.0
            or stress[maxima[0]] > value_limit
            or stress[maxima[0]] - stress[minima[0]] > range_limit
        ):
            if maxima[0] == left:
                maxima.popleft()
            if minima[0] == left:
                minima.popleft()
            left += 1

        if right - left + 1 < minimum_band_rows:
            continue
        span = float(normalized_progress[right] - normalized_progress[left])
        if span < minimum_progress_span:
            continue
        if span > best_span or (
            span == best_span
            and best_start is not None
            and best_end is not None
            and (left, right) < (best_start, best_end)
        ):
            best_start = left
            best_end = right
            best_span = span

    if best_start is None or best_end is None:
        return StableBandSelection(
            peak_row=peak_row,
            peak_stress=peak_stress,
            band_start_row=None,
            band_end_row=None,
            progress_basis=basis,
            progress_span=None,
            max_gap_ratio=None,
            source_row_count=int(strain.size),
            band_min_stress=None,
            band_max_stress=None,
            band_median_stress=None,
            reason="not_found",
        )

    band_stress = stress[best_start : best_end + 1]
    band_span = float(normalized_progress[best_end] - normalized_progress[best_start])
    max_gap = float(np.max(np.diff(normalized_progress[best_start : best_end + 1])))
    max_gap_ratio = max_gap / band_span
    middle = band_stress.size // 2
    ordered = np.partition(band_stress.copy(), (middle - 1, middle))
    if band_stress.size % 2:
        median_stress = float(ordered[middle])
    else:
        lower = float(ordered[middle - 1])
        upper = float(ordered[middle])
        median_stress = lower + (upper - lower) / 2.0

    reason: SelectionReason = (
        "insufficient_support" if max_gap_ratio > maximum_gap_over_band_span else "selected"
    )
    return StableBandSelection(
        peak_row=peak_row,
        peak_stress=peak_stress,
        band_start_row=best_start,
        band_end_row=best_end,
        progress_basis=basis,
        progress_span=band_span,
        max_gap_ratio=max_gap_ratio,
        source_row_count=int(strain.size),
        band_min_stress=float(np.min(band_stress)),
        band_max_stress=float(np.max(band_stress)),
        band_median_stress=median_stress,
        reason=reason,
    )
