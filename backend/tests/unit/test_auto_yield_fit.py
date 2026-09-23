"""Pure observed-anchor contracts for automatic event fits."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from matcore.processing._auto_yield_fit import (
    AutoYieldFitError,
    AutoYieldFitResult,
    fit_event_cores,
)


def _fit(
    stress: Sequence[float],
    core_intervals: list[tuple[int, int]],
    *,
    method: str,
    preserve_boundary: int = 0,
    protected_intervals: list[tuple[int, int]] | None = None,
) -> AutoYieldFitResult:
    values = np.asarray(stress, dtype=np.float64)
    strain = np.arange(values.size, dtype=np.float64)
    return fit_event_cores(
        strain,
        values,
        core_intervals,
        protected_intervals or [],
        preserve_boundary,
        method,
        preserve_boundary_reason="test boundary",
    )


@pytest.mark.parametrize(
    "method", ("median_plateau", "linear", "least_squares", "robust_linear")
)
def test_automatic_fit_preserves_observed_anchors_and_changes_only_inside(method: str) -> None:
    original = np.asarray([0, 5, 10, 20, 100, 1, 75, 90, 100, 110], dtype=np.float64)
    result = _fit(original.tolist(), [(4, 8)], method=method)
    region = result.regions[0]

    assert (region.left_anchor, region.right_anchor) == (3, 8)
    assert (region.core_start, region.core_end) == (4, 7)
    assert result.values[region.left_anchor] == original[region.left_anchor]
    assert result.values[region.right_anchor] == original[region.right_anchor]
    np.testing.assert_array_equal(result.values[:4], original[:4])
    np.testing.assert_array_equal(result.values[9:], original[9:])
    assert np.all(np.diff(result.values[3:9]) >= 0)
    assert np.all(np.isfinite(result.values))
    assert np.isfinite(region.fit_r_squared)
    assert np.isfinite(region.fit_rmse)
    assert region.max_abs_distortion == pytest.approx(
        float(np.max(np.abs(result.values[3:9] - original[3:9])))
    )


def test_constrained_ols_matches_independent_edge_solution_and_huber_scale() -> None:
    original = np.asarray([-10, 0, 0, 10, 10, 10, 20], dtype=np.float64)
    x = np.arange(original.size, dtype=np.float64)
    core_x = x[1:5]
    core_y = original[1:5]
    t = (core_x - core_x[0]) / (core_x[-1] - core_x[0])
    expected_a = float(np.sum((1 - t) * (core_y - t * 10)) / np.sum((1 - t) ** 2))

    ols = _fit(original.tolist(), [(1, 5)], method="least_squares")
    ols_region = ols.regions[0]
    assert ols_region.left_anchor == 0
    assert ols_region.right_anchor == 5
    assert ols_region.unconstrained_endpoints is not None
    assert ols_region.unconstrained_endpoints[0] > original[0]
    assert ols_region.unconstrained_endpoints[1] > original[5]
    assert ols_region.constrained_endpoints == pytest.approx((expected_a, 10.0))
    assert ols_region.constraint_applied
    np.testing.assert_allclose(
        ols.values[1:5], expected_a + (10.0 - expected_a) * t, rtol=0, atol=1e-12
    )

    # Huber's fixed delta is calculated from unconstrained OLS residuals, even
    # though each final IRLS weighted solve respects the anchor bounds.
    ols_unconstrained = np.polyval(np.polyfit(core_x, core_y, 1), core_x)
    residual = core_y - ols_unconstrained
    mad = float(np.median(np.abs(residual - np.median(residual))))
    expected_delta = 1.345 * max(1.4826 * mad, 1e-6 * float(np.max(np.abs(core_y))), 1.0)
    huber = _fit(original.tolist(), [(1, 5)], method="robust_linear")
    huber_region = huber.regions[0]
    assert huber_region.huber_delta == pytest.approx(expected_delta, rel=1e-12, abs=1e-12)
    assert huber_region.constrained_endpoints[0] >= original[0]
    assert huber_region.constrained_endpoints[0] <= huber_region.constrained_endpoints[1]
    assert huber_region.constrained_endpoints[1] <= original[5]
    assert np.all(np.diff(huber.values[0:6]) >= 0)


def test_overlapping_influence_regions_merge_and_fit_from_original_values() -> None:
    original = [0, 5, 10, 100, 50, 70, 100, 45, 80, 100, 110]
    result = _fit(
        original,
        [(3, 6), (6, 9)],
        method="median_plateau",
    )

    assert len(result.regions) == 1
    region = result.regions[0]
    assert (region.core_start, region.core_end, region.right_anchor) == (3, 8, 9)
    assert result.values[region.left_anchor] == original[region.left_anchor]
    assert result.values[region.right_anchor] == original[region.right_anchor]


def test_terminal_first_peak_can_be_the_exact_right_anchor_and_remains_protected() -> None:
    original = [0, 10, 20, 30, 100, 50, 75, 100, 80, 70]
    result = _fit(
        original,
        [(4, 7)],
        method="linear",
        preserve_boundary=2,
        protected_intervals=[(7, 9)],
    )

    region = result.regions[0]
    assert region.right_anchor == 7
    assert result.values[7] == original[7]
    np.testing.assert_array_equal(result.values[7:], original[7:])
    assert result.protected_intervals == ((7, 9),)
    assert np.all(np.diff(result.values[region.left_anchor : region.right_anchor + 1]) >= 0)


def test_missing_anchor_protected_overlap_and_too_small_core_hold_atomically() -> None:
    no_anchor = [0, 60, 70, 80, 100, 20, 60, 50]
    with pytest.raises(AutoYieldFitError, match="앵커를 찾지 못했습니다"):
        _fit(no_anchor, [(4, 7)], method="linear", preserve_boundary=1)

    protected = [0, 10, 20, 30, 100, 50, 75, 100, 80, 70]
    with pytest.raises(AutoYieldFitError, match="겹칩니다"):
        _fit(
            protected,
            [(4, 7)],
            method="median_plateau",
            preserve_boundary=2,
            protected_intervals=[(5, 6)],
        )

    with pytest.raises(AutoYieldFitError, match="2개 미만"):
        _fit([0, 10, 20, 30, 100, 100], [(4, 5)], method="least_squares")


def test_no_core_returns_an_unchanged_copy() -> None:
    original = np.asarray([0, 10, 20, 30], dtype=np.float64)
    result = _fit(original.tolist(), [], method="robust_linear")

    np.testing.assert_array_equal(result.values, original)
    assert result.values is not original
    assert result.regions == ()
    assert result.fit_r_squared == 1.0
    assert result.fit_rmse == 0.0
