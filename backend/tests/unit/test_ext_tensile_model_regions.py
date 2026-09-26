"""The pure model-region selector preserves and explains source-row choices."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from matcore import extensions

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
extensions.load(EXTENSIONS)
select_stable_band = import_module(
    "matnexus_ext.tensile_extras.model_regions"
).select_stable_band


def _curve(plateau_rows: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    stress = np.asarray([100.0, *([80.0] * plateau_rows)])
    strain = np.linspace(-0.1, 0.1, stress.size)
    return strain, stress


class TestStableBandSelector:
    def test_selects_original_postpeak_rows_and_preserves_negative_toe_input(self) -> None:
        strain = np.linspace(-0.1, 0.1, 23)
        stress = np.asarray([10.0, 100.0, *([80.0] * 21)])
        strain_before = strain.copy()
        stress_before = stress.copy()

        result = select_stable_band(strain, stress)

        assert result.reason == "selected"
        assert result.peak_row == 1
        assert result.peak_stress == 100.0
        assert result.band_start_row == 2
        assert result.band_end_row == 22
        assert result.source_row_count == 23
        assert result.progress_basis == "engineering_strain"
        assert result.progress_span == pytest.approx(20.0 / 22.0)
        assert result.max_gap_ratio == pytest.approx(1.0 / 20.0)
        assert result.band_min_stress == 80.0
        assert result.band_max_stress == 80.0
        assert result.band_median_stress == 80.0
        np.testing.assert_array_equal(strain, strain_before)
        np.testing.assert_array_equal(stress, stress_before)

    @pytest.mark.parametrize(
        ("plateau_rows", "expected_reason", "expected_start"),
        [(19, "not_found", None), (20, "selected", 1)],
    )
    def test_requires_the_minimum_count_of_original_contiguous_rows(
        self, plateau_rows: int, expected_reason: str, expected_start: int | None
    ) -> None:
        strain, stress = _curve(plateau_rows)

        result = select_stable_band(strain, stress)

        assert result.reason == expected_reason
        assert result.band_start_row == expected_start

    def test_equal_span_candidates_choose_the_earliest_start_and_end(self) -> None:
        stress = np.asarray([100.0, *([80.0] * 20), 95.0, *([80.0] * 20)])
        strain = np.linspace(-0.1, 0.5, stress.size)
        progress = np.arange(stress.size, dtype=float)

        result = select_stable_band(strain, stress, progress)

        assert result.reason == "selected"
        assert (result.band_start_row, result.band_end_row) == (1, 20)
        assert result.progress_basis == "progress_channel"

    def test_even_band_median_partitions_both_middle_source_values(self) -> None:
        random = np.random.default_rng(17)
        for _trial in range(10):
            permutation = random.permutation(100)
        stress = np.asarray([100.0, *(80.0 + permutation / 100.0)])
        strain = np.linspace(-0.1, 0.5, stress.size)

        result = select_stable_band(strain, stress)

        assert (result.band_start_row, result.band_end_row) == (1, 100)
        assert result.band_median_stress == pytest.approx(80.495)

    def test_best_gap_unsupported_band_is_returned_without_using_a_shorter_band(self) -> None:
        stress = np.asarray([100.0, *([80.0] * 20), 95.0, *([80.0] * 20)])
        strain = np.linspace(-0.1, 0.5, stress.size)
        progress = np.asarray(
            [
                0.0,
                *np.linspace(0.01, 0.10, 10),
                *np.linspace(0.50, 0.80, 10),
                0.81,
                *np.linspace(0.82, 1.0, 20),
            ]
        )

        result = select_stable_band(strain, stress, progress)

        assert result.reason == "insufficient_support"
        assert (result.band_start_row, result.band_end_row) == (1, 20)
        assert result.progress_span == pytest.approx(0.79)
        assert result.max_gap_ratio is not None
        assert result.max_gap_ratio > 0.10

    def test_uses_valid_progress_normalized_over_this_input_and_falls_back_when_invalid(
        self,
    ) -> None:
        strain, stress = _curve(20)
        progress = np.arange(stress.size, dtype=float) * 5.0 + 500.0
        progress_before = progress.copy()

        result = select_stable_band(strain, stress, progress)
        invalid_progress = progress.copy()
        invalid_progress[5] = invalid_progress[4]
        invalid_progress_before = invalid_progress.copy()
        fallback = select_stable_band(strain, stress, invalid_progress)

        assert result.progress_basis == "progress_channel"
        assert result.progress_span == pytest.approx(0.95)
        assert fallback.progress_basis == "engineering_strain"
        assert fallback.progress_span == pytest.approx(0.95)
        np.testing.assert_array_equal(progress, progress_before)
        np.testing.assert_array_equal(invalid_progress, invalid_progress_before)

    @pytest.mark.parametrize(
        ("strain", "stress", "message"),
        [
            ([0.0], [1.0], "At least two"),
            ([0.0, 0.0], [1.0, 2.0], "strictly increasing"),
            ([0.0, 1.0], [0.0, -1.0], "positive maximum"),
            ([0.0, 1.0], [1.0], "equal length"),
            ([[0.0, 1.0], [2.0, 3.0]], [1.0, 2.0], "one-dimensional"),
            ([0.0, 1.0], [1.0, np.nan], "finite values"),
            ([0.0 + 1.0j, 1.0 + 2.0j], [1.0, 2.0], "real numeric"),
            ([False, True], [1.0, 2.0], "real numeric"),
        ],
    )
    def test_validates_required_source_arrays(
        self, strain: Any, stress: Any, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            select_stable_band(strain, stress)

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("minimum_band_rows", True),
            ("minimum_band_rows", 1),
            ("minimum_band_rows", 20.0),
            ("minimum_progress_span", True),
            ("minimum_progress_span", float("nan")),
            ("minimum_progress_span", -0.01),
            ("minimum_progress_span", 1.01),
            ("maximum_stress_over_peak", True),
            ("maximum_stress_over_peak", float("inf")),
            ("maximum_stress_over_peak", 1.01),
            ("maximum_range_over_peak", True),
            ("maximum_range_over_peak", float("nan")),
            ("maximum_range_over_peak", -0.01),
            ("maximum_gap_over_band_span", True),
            ("maximum_gap_over_band_span", float("inf")),
            ("maximum_gap_over_band_span", 1.01),
        ],
    )
    def test_rejects_boolean_nonfinite_and_out_of_bounds_thresholds(
        self, name: str, value: Any
    ) -> None:
        strain, stress = _curve(20)

        with pytest.raises(ValueError):
            select_stable_band(strain, stress, **{name: value})
