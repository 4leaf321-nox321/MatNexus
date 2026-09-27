"""Focused tests for the opt-in tensile coordinate-projected integration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, StepResult
from matcore.processing.tensile import proof_stress

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    strain: list[float],
    stress: list[float],
    *,
    source_rows: list[float] | None = None,
) -> Frame:
    values = np.asarray(strain, dtype=np.float64)
    source = (
        np.arange(100, 100 + len(values), dtype=np.float64)
        if source_rows is None
        else np.asarray(source_rows, dtype=np.float64)
    )
    return Frame(
        {
            "strain_engineering": values,
            "stress_engineering": np.asarray(stress, dtype=np.float64),
            "source_row": source,
        },
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_row": "1",
        },
    )


def _coordinate_options(
    *,
    proof_strain: float,
    proof_stress: float,
    method: str = "linear",
    end_strain: float | None = None,
) -> dict[str, object]:
    options: dict[str, object] = {
        "strain": "strain_engineering",
        "stress": "stress_engineering",
        "snapshot": "stress_engineering_source_snapshot",
        "source_index": "source_row",
        "youngs_modulus": 1000.0,
        "proof_strain": proof_strain,
        "proof_stress": proof_stress,
        "offset_strain": 0.002,
        "method": method,
    }
    if end_strain is not None:
        options["end_strain"] = end_strain
    return options


def _scalar(result: StepResult, key: str) -> float:
    return next(item.value for item in result.scalars if item.key == key)


def test_registration_places_snapshot_and_projection_in_model_order() -> None:
    snapshot = registry.get("tensile.source_stress_snapshot")
    band = registry.get("tensile.band_model")
    anchor = registry.get("tensile.model_anchor")
    projection = registry.get("tensile.coordinate_projected_v1")
    domain = registry.get("tensile.effective_card_domain")

    assert snapshot.order == 81
    assert band.order == 82
    assert snapshot.order < band.order
    assert anchor.order < projection.order < domain.order
    assert projection.version == "1"
    method = next(param for param in projection.params if param.name == "method")
    assert "bounded" in method.choices
    assert "upper_envelope" in method.choices
    assert {item.key for item in projection.makes_values} == {
        "coordinate_projected_correction_count",
        "coordinate_projected_max_abs_change",
        "coordinate_projected_first_source_row",
        "coordinate_projected_last_source_row",
    }
    assert all(len(item.key) <= 50 for item in projection.makes_values)


def test_source_snapshot_copies_stress_and_keeps_source_rows() -> None:
    frame = _frame([0.0, 0.01, 0.02], [0.0, 10.0, 20.0])
    plugin = registry.get("tensile.source_stress_snapshot")

    result = plugin.fn(frame, plugin.prepare_options({}) or {})

    assert (
        result.frame.columns["stress_engineering_source_snapshot"]
        is not frame.columns["stress_engineering"]
    )
    np.testing.assert_array_equal(
        result.frame.columns["stress_engineering_source_snapshot"],
        frame.columns["stress_engineering"],
    )
    np.testing.assert_array_equal(result.frame.columns["source_row"], [100.0, 101.0, 102.0])
    assert result.frame.units["stress_engineering_source_snapshot"] == "Pa"
    assert result.effective_options == {
        "strain": "strain_engineering",
        "stress": "stress_engineering",
        "snapshot": "stress_engineering_source_snapshot",
    }


@pytest.mark.parametrize(
    ("stress", "strain", "message"),
    [
        ([0.0, np.nan, 20.0], [0.0, 0.01, 0.02], "유한"),
        ([0.0, 10.0, 20.0], [0.0, 0.01, 0.01], "엄격히 증가"),
    ],
)
def test_source_snapshot_rejects_nonfinite_or_nonincreasing_input(
    stress: list[float], strain: list[float], message: str
) -> None:
    frame = _frame(strain, stress)
    plugin = registry.get("tensile.source_stress_snapshot")

    with pytest.raises(ProcessingError, match=message):
        plugin.fn(frame, plugin.prepare_options({}) or {})


def test_source_snapshot_rejects_collision_without_overwriting() -> None:
    frame = _frame([0.0, 0.01], [0.0, 10.0])
    frame.columns["stress_engineering_source_snapshot"] = np.asarray([3.0, 4.0])
    frame.units["stress_engineering_source_snapshot"] = "Pa"
    plugin = registry.get("tensile.source_stress_snapshot")

    with pytest.raises(ProcessingError, match="이미 있습니다"):
        plugin.fn(frame, plugin.prepare_options({}) or {})


def test_coordinate_projection_changes_only_model_rows_and_reports_source_range() -> None:
    raw = [
        0.0,
        20.0,
        30.0,
        10.0,
        16.25509559,
        24.82646041,
        6.18213353,
        37.19524063,
        34.58422785,
        39.04824132,
        32.4308688,
    ]
    modeled = [
        0.0,
        20.0,
        30.0,
        10.0,
        46.25509559,
        44.82646041,
        36.18213353,
        27.19524063,
        29.58422785,
        39.04824132,
        32.4308688,
    ]
    source_frame = _frame([i / 100.0 for i in range(11)], raw)
    snapshot_plugin = registry.get("tensile.source_stress_snapshot")
    snapshot_result = snapshot_plugin.fn(
        source_frame, snapshot_plugin.prepare_options({}) or {}
    )
    modeled_frame = snapshot_result.frame.with_columns(
        {"stress_engineering": np.asarray(modeled, dtype=np.float64)}, {}
    )
    # The tail reversal is outside the explicit card bound.  It must remain a
    # fixed source/model row while the modeled run after proof is projected.
    options = _coordinate_options(
        proof_strain=0.024,
        proof_stress=22.0,
        method="linear",
        end_strain=0.09,
    )
    projection = registry.get("tensile.coordinate_projected_v1")

    result = projection.fn(modeled_frame, options)

    corrected = result.frame.columns["stress_engineering"]
    assert _scalar(result, "coordinate_projected_correction_count") == 4.0
    assert _scalar(result, "coordinate_projected_first_source_row") == 104.0
    assert _scalar(result, "coordinate_projected_last_source_row") == 108.0
    assert _scalar(result, "coordinate_projected_max_abs_change") > 0.0
    np.testing.assert_array_equal(corrected[:4], np.asarray(modeled[:4]))
    np.testing.assert_array_equal(corrected[9:], np.asarray(modeled[9:]))
    assert np.all(corrected[4:9] >= np.minimum(raw[4:9], modeled[4:9]))
    assert np.all(corrected[4:9] <= np.maximum(raw[4:9], modeled[4:9]))
    true_plastic = (
        np.log1p(source_frame.columns["strain_engineering"])
        - corrected * (1.0 + source_frame.columns["strain_engineering"]) / 1000.0
    )
    assert np.all(np.diff(true_plastic[3:10]) > 0.0)
    assert "별도 모델" in " ".join(result.notes)
    assert result.effective_options["method"] == "linear"
    assert result.effective_options["end_strain"] == 0.09

    proof = proof_stress(
        result.frame,
        {
            "strain": "strain_engineering",
            "stress": "stress_engineering",
            "youngs_modulus": 1000.0,
            "offset_strain": 0.002,
        },
    )
    assert _scalar(proof, "proof_strain") == pytest.approx(0.024)
    assert _scalar(proof, "proof_stress") == pytest.approx(22.0)


def test_coordinate_projection_noop_preserves_model_stress_bytes() -> None:
    stress = np.asarray([0.0, 80.0, 100.0, 100.0, 20.0], dtype=np.float64)
    frame = _frame([0.0, 0.01, 0.02, 0.03, 0.04], stress.tolist())
    snapshot_plugin = registry.get("tensile.source_stress_snapshot")
    snapshot_result = snapshot_plugin.fn(frame, snapshot_plugin.prepare_options({}) or {})
    projection = registry.get("tensile.coordinate_projected_v1")
    options = _coordinate_options(proof_strain=0.038, proof_stress=36.0)

    result = projection.fn(snapshot_result.frame, options)

    assert result.frame is snapshot_result.frame
    assert result.frame.columns["stress_engineering"].tobytes() == stress.tobytes()
    assert _scalar(result, "coordinate_projected_correction_count") == 0.0
    assert _scalar(result, "coordinate_projected_max_abs_change") == 0.0
    assert _scalar(result, "coordinate_projected_first_source_row") == -1.0
    assert _scalar(result, "coordinate_projected_last_source_row") == -1.0
    assert "byte-identical" in " ".join(result.notes)


def test_coordinate_projection_holds_when_model_proof_moves() -> None:
    raw = [
        0.0,
        20.0,
        30.0,
        10.0,
        16.25509559,
        24.82646041,
        6.18213353,
        37.19524063,
        34.58422785,
        39.04824132,
        32.4308688,
    ]
    modeled = [
        0.0,
        20.0,
        30.0,
        10.0,
        46.25509559,
        44.82646041,
        36.18213353,
        27.19524063,
        29.58422785,
        39.04824132,
        32.4308688,
    ]
    frame = _frame([i / 100.0 for i in range(11)], raw)
    snapshot_plugin = registry.get("tensile.source_stress_snapshot")
    snapshot_result = snapshot_plugin.fn(frame, snapshot_plugin.prepare_options({}) or {})
    modeled_frame = snapshot_result.frame.with_columns(
        {"stress_engineering": np.asarray(modeled, dtype=np.float64)}, {}
    )
    projection = registry.get("tensile.coordinate_projected_v1")

    with pytest.raises(ProcessingError, match="proof anchor가 이동했습니다"):
        projection.fn(
            modeled_frame,
            _coordinate_options(
                proof_strain=0.023,
                proof_stress=21.0,
                method="linear",
                end_strain=0.09,
            ),
        )
