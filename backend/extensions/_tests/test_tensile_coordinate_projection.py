"""Focused tests for the pure tensile coordinate projection helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from matcore.processing import ProcessingError

HELPER_PATH = (
    Path(__file__).resolve().parents[1] / "tensile_extras" / "coordinate_projection.py"
)
HELPER_SPEC = importlib.util.spec_from_file_location(
    "_matnexus_tensile_coordinate_projection_test", HELPER_PATH
)
if HELPER_SPEC is None or HELPER_SPEC.loader is None:
    raise RuntimeError(f"unable to load coordinate projection helper: {HELPER_PATH}")
HELPER_MODULE = importlib.util.module_from_spec(HELPER_SPEC)
sys.modules[HELPER_SPEC.name] = HELPER_MODULE
HELPER_SPEC.loader.exec_module(HELPER_MODULE)
project_model_stress = HELPER_MODULE.project_model_stress


def test_feasible_fixed_seam_moves_only_the_editable_row() -> None:
    strain = [0.0, 0.01, 0.02, 0.03]
    raw = np.asarray([0.0, 95.0, 100.0, 100.0])
    modeled = np.asarray([0.0, 80.0, 100.0, 100.0])

    projected, diagnostics = project_model_stress(strain, raw, modeled, 1000.0, 0.0)

    assert diagnostics.changed_count == 1
    assert diagnostics.first_affected_row == diagnostics.last_affected_row == 1
    assert projected[1] > modeled[1]
    np.testing.assert_array_equal(projected[[0, 2, 3]], modeled[[0, 2, 3]])
    assert projected[1] <= raw[1]


def test_internal_editable_jump_preserves_original_non_decreasing_pairs() -> None:
    strain = [0.0, 0.01, 0.02, 0.03, 0.04]
    raw = np.asarray([0.0, 95.0, 110.0, 110.0, 100.0])
    modeled = np.asarray([0.0, 80.0, 100.0, 80.0, 100.0])

    projected, diagnostics = project_model_stress(strain, raw, modeled, 1000.0, 0.0)

    assert diagnostics.changed_count == 2
    assert diagnostics.first_affected_row == 1
    assert diagnostics.last_affected_row == 3
    # The modeled 100 -> 80 reversal is historical and is not a shape
    # constraint.  The neighboring original nondecreasing pairs remain so.
    assert projected[1] <= projected[2]
    assert projected[2] > projected[3]
    assert projected[3] <= projected[4]
    assert np.all(projected[1:4] >= np.minimum(raw[1:4], modeled[1:4]))
    assert np.all(projected[1:4] <= np.maximum(raw[1:4], modeled[1:4]))


def test_fixed_raw_reversal_is_held_with_row_diagnostics() -> None:
    strain = [0.01, 0.02, 0.03]
    raw = np.asarray([100.0, 0.0, 20.0])

    with pytest.raises(ProcessingError, match=r"rows 1->2.*fixed-fixed"):
        project_model_stress(strain, raw, raw, 1000.0, 0.0)


def test_impossible_fixed_anchors_are_held() -> None:
    strain = [0.01, 0.02, 0.03]
    raw = np.asarray([0.0, 50.0, 200.0])
    modeled = np.asarray([0.0, 100.0, 200.0])

    with pytest.raises(ProcessingError, match=r"rows 1->2.*infeasible"):
        project_model_stress(strain, raw, modeled, 1000.0, 0.0)


def test_valid_model_is_bit_exact_no_op() -> None:
    strain = [0.01, 0.02, 0.03]
    raw = np.asarray([0.0, 10.0, 10.0])
    modeled = np.asarray([0.0, 5.0, 5.0])

    projected, diagnostics = project_model_stress(strain, raw, modeled, 1000.0, 0.0)

    np.testing.assert_array_equal(projected, modeled)
    assert projected.tobytes() == modeled.tobytes()
    assert diagnostics.changed_count == 0
    assert diagnostics.max_abs_change == 0.0
    assert diagnostics.first_affected_row is None
    assert diagnostics.last_affected_row is None


def test_lower_envelope_preserves_raw_upper_bound_and_interval() -> None:
    strain = [0.0, 0.01, 0.02, 0.03]
    raw = np.asarray([0.0, 10.0, 10.0, 10.0])
    modeled = np.asarray([0.0, 10.0, 15.0, 5.0])

    projected, diagnostics = project_model_stress(
        strain,
        raw,
        modeled,
        1000.0,
        0.015,
        method="lower_envelope",
    )

    assert diagnostics.changed_count == 2
    editable = modeled != raw
    assert np.all(projected[editable] <= raw[editable])
    assert np.all(projected[editable] >= np.minimum(raw, modeled)[editable])
    assert np.all(projected[editable] <= np.maximum(raw, modeled)[editable])
    # The original 15 -> 5 reversal is not rejected or repaired solely for
    # engineering-stress shape.
    assert projected[2] > projected[3]


def test_both_constraints_cap_left_stress_and_keep_true_plastic_order() -> None:
    strain = np.asarray([0.01, 0.02])
    raw = np.asarray([0.0, 0.0])
    modeled = np.asarray([2.0, 2.0])

    projected, _ = project_model_stress(strain, raw, modeled, 1.0, 0.0)

    assert projected[0] <= projected[1]
    assert np.any(projected != modeled)
    coordinate = np.log1p(strain) - (1.0 + strain) * projected
    assert coordinate[1] > coordinate[0]


def test_lower_envelope_preserves_shape_across_inactive_proof_seam() -> None:
    strain = np.asarray([0.0, 0.01, 0.02, 0.03])
    raw = np.asarray([50.0, 60.0, 100.0, 120.0])
    modeled = np.asarray([50.0, 100.0, 110.0, 120.0])

    projected, _ = project_model_stress(
        strain,
        raw,
        modeled,
        100_000.0,
        0.005,
        method="lower_envelope",
    )

    np.testing.assert_array_equal(projected[0], modeled[0])
    assert projected[1] >= projected[0]
    assert projected[1] <= raw[1]
    coordinate = np.log1p(strain) - (1.0 + strain) * projected / 100_000.0
    assert np.all(np.diff(coordinate[1:]) > 0.0)


def test_lower_envelope_rejects_infeasible_fixed_proof_seam_shape() -> None:
    with pytest.raises(ProcessingError, match=r"rows 0->1.*infeasible.*shape"):
        project_model_stress(
            [0.0, 0.01, 0.02, 0.03],
            np.asarray([50.0, 40.0, 100.0, 120.0]),
            np.asarray([50.0, 100.0, 110.0, 120.0]),
            100_000.0,
            0.005,
            method="lower_envelope",
        )


def test_historical_decrease_at_editable_seam_is_allowed() -> None:
    strain = np.asarray([0.01, 0.02, 0.03])
    raw = np.asarray([100.0, 70.0, 80.0])
    modeled = np.asarray([100.0, 80.0, 150.0])

    projected, _ = project_model_stress(strain, raw, modeled, 1000.0, 0.0)

    assert projected[0] > projected[1]
    assert projected[1] <= projected[2]
    coordinate = np.log1p(strain) - (1.0 + strain) * projected / 1000.0
    assert np.all(np.diff(coordinate) > 0.0)


@pytest.mark.parametrize("scale", [1e-100, 1e100])
def test_editable_boundary_roundtrip_is_stable_across_scales(scale: float) -> None:
    strain = np.asarray([0.005, 0.015])
    raw = np.asarray([50.0, 30.0]) * scale
    modeled = np.asarray([0.0, 30.0]) * scale

    projected, _ = project_model_stress(
        strain,
        raw,
        modeled,
        1000.0 * scale,
        0.0,
    )

    assert np.all(np.isfinite(projected))
    assert projected[0] >= min(raw[0], modeled[0])
    assert projected[0] <= max(raw[0], modeled[0])
    coordinate = np.log1p(strain) - (1.0 + strain) * projected / (1000.0 * scale)
    assert coordinate[1] > coordinate[0]


def test_shape_boundary_repair_uses_the_active_lower_side() -> None:
    strain = np.asarray([0.0078377191931228, 0.01580380128769327])
    raw = np.asarray([0.02504769071292907, 0.02717171316652414])
    modeled = np.asarray([0.00005606967857590406, 0.033674273720941984])

    projected, _ = project_model_stress(strain, raw, modeled, 1.0, -1.0)

    assert np.all(projected >= np.minimum(raw, modeled))
    assert np.all(projected <= np.maximum(raw, modeled))
    assert projected[0] <= projected[1]
    coordinate = np.log1p(strain) - (1.0 + strain) * projected
    assert coordinate[1] > coordinate[0]
