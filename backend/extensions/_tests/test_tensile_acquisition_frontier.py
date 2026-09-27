"""Atomic acquisition-frontier and source-pair provenance contracts."""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing
from matcore.processing import Frame, ProcessingError

extensions.load(Path(__file__).resolve().parents[1])
processing.load_builtin()
frontier = importlib.import_module("matnexus_ext.tensile_extras.acquisition_frontier")
proof = importlib.import_module("matnexus_ext.tensile_extras.source_proof")
full = importlib.import_module("matnexus_ext.tensile_extras.source_support_order_full")


def _case(*, pair: bool = False, notch: tuple[int, ...] = (70,), tail: int = 0) -> Frame:
    count = 205 + tail
    strain = np.arange(count, dtype=np.float64) / 1000.0
    for index in notch:
        strain[index] = strain[index - 1] - 0.0005
    stress = np.arange(count, dtype=np.float64) * 0.1 + 10.0
    stress[:20] = np.arange(20, dtype=np.float64) * 0.5
    if tail:
        stress[-tail:] = np.linspace(
            stress[-tail - 1] - 0.1, stress[-tail - 1] - 0.1 * tail, tail
        )
    columns = {
        "strain_engineering": strain,
        "stress_engineering": stress,
        "force": stress / 2.0,
        "displacement": strain * 0.05,
        "time": np.arange(count, dtype=np.float64),
        "marker": np.arange(count, dtype=np.float64) + 0.25,
    }
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "force": "N",
        "displacement": "m",
        "time": "1",
        "marker": "1",
    }
    if pair:
        columns["source_data_row"] = np.arange(1, count + 1, dtype=np.float64)
        columns["source_physical_line"] = np.arange(2, count + 2, dtype=np.float64)
        units.update(source_data_row="1", source_physical_line="1")
    else:
        columns["source_row"] = np.arange(1, count + 1, dtype=np.float64)
        units["source_row"] = "1"
    return Frame(columns, units)


def _options(frame: Frame) -> dict[str, float | int]:
    peak = int(np.argmax(frame.columns["stress_engineering"]))
    result = proof.source_proof_stress(
        frame,
        {
            "youngs_modulus": 1000.0,
            "start_index": 1,
            "end_index": peak,
            "search_start": 0.001,
            "offset_strain": 0.002,
        },
    )
    values = {scalar.key: scalar.value for scalar in result.scalars}
    return {
        "proof_left_index": int(values["source_proof_left_index"]),
        "proof_right_index": int(values["source_proof_right_index"]),
        "proof_strain": values["proof_strain"],
        "proof_stress": values["proof_stress"],
        "youngs_modulus": 1000.0,
        "source_elastic_end_index": 1,
        "elastic_window_end": 0.001,
        "offset_strain": 0.002,
    }


def _run(frame: Frame) -> object:
    return frontier.acquisition_frontier(frame, _options(frame))


def test_pair_rescue_preserves_raw_provenance_and_validates_full_path() -> None:
    frame = _case(pair=True, tail=3)
    before = {name: value.copy() for name, value in frame.columns.items()}
    options = _options(frame)
    result = frontier.acquisition_frontier(frame, options)
    selected = result.frame
    assert selected is not frame
    assert "source_data_row" not in selected.columns
    assert "source_physical_line" not in selected.columns
    retained = np.r_[0:70, 71:208]
    for name, raw in before.items():
        np.testing.assert_array_equal(frame.columns[name], raw)
        if name not in frontier.SOURCE_ROW_PAIR:
            np.testing.assert_array_equal(selected.columns[name], raw[retained])
    np.testing.assert_array_equal(
        selected.columns["source_data_row_original"], before["source_data_row"][retained]
    )
    np.testing.assert_array_equal(
        selected.columns["source_physical_line_original"],
        before["source_physical_line"][retained],
    )
    np.testing.assert_array_equal(
        selected.columns["source_row"], before["source_data_row"][retained]
    )
    assert selected.columns["source_row"][70] == 72
    assert "source_data_row=71" in " ".join(result.notes)
    assert "단위 '1'" in " ".join(result.notes)
    assert "초가 아닌 순번 cadence" in " ".join(result.notes)
    assert "source_data_row→source_data_row_original" in " ".join(result.notes)
    assert "독립 증거가 아닙니다" in " ".join(result.notes)
    checked = full.source_support_order_full(
        selected,
        {
            "proof_left_index": options["proof_left_index"],
            "proof_right_index": options["proof_right_index"],
            "proof_strain": options["proof_strain"],
        },
    )
    assert checked.frame is selected
    replay = frontier.acquisition_frontier(frame, dict(result.effective_options or {}))
    for name in selected.columns:
        np.testing.assert_array_equal(replay.frame.columns[name], selected.columns[name])


def test_source_row_rescue_and_noop_identity() -> None:
    frame = _case()
    result = _run(frame)
    assert result.frame.columns["source_row"][70] == 72
    assert {s.key: s.value for s in result.scalars}[frontier.REMOVED_POINTS_KEY] == 1
    clean = _case(notch=())
    assert _run(clean).frame is clean


def test_removed_large_source_row_identity_is_not_rounded() -> None:
    frame = _case()
    frame.columns["source_row"] += 10_000_000_000
    result = _run(frame)
    assert "source_row=10000000071" in " ".join(result.notes)


def test_seconds_and_independent_regular_displacement_are_accepted() -> None:
    frame = _case()
    frame.units["time"] = "s"
    frame.columns["displacement"] = np.arange(205, dtype=np.float64) * 0.01
    result = _run(frame)
    assert result.frame.length() == 204
    assert "독립 변위의 국소 양의 간격" in " ".join(result.notes)


@pytest.mark.parametrize("bad", ["equal", "multirow", "deep", "stress", "force"])
def test_any_ineligible_reversal_prevents_partial_deletion(bad: str) -> None:
    frame = _case(notch=(70, 120))
    if bad == "equal":
        frame.columns["strain_engineering"][120] = frame.columns["strain_engineering"][119]
    elif bad == "multirow":
        frame.columns["strain_engineering"][121] = (
            frame.columns["strain_engineering"][120] - 0.0001
        )
    elif bad == "deep":
        frame.columns["strain_engineering"][120] = (
            frame.columns["strain_engineering"][119] - 0.002
        )
    elif bad == "stress":
        frame.columns["stress_engineering"][120] = (
            frame.columns["stress_engineering"][119] - 0.01
        )
        frame.columns["force"][120] = frame.columns["stress_engineering"][120] / 2
    else:
        frame.columns["force"][120] = frame.columns["force"][119] - 0.01
    with pytest.raises(ProcessingError):
        _run(frame)
    assert len(frame.columns["strain_engineering"]) == 205


@pytest.mark.parametrize(
    "bad",
    ["time", "time_elsewhere", "time_unit", "displacement", "displacement_equal", "proof"],
)
def test_invalid_independent_evidence_or_proof_holds(bad: str) -> None:
    frame = _case()
    options = _options(frame)
    if bad == "time":
        frame.columns["time"][70] += 10
    elif bad == "time_elsewhere":
        frame.columns["time"][150] = frame.columns["time"][149]
    elif bad == "time_unit":
        frame.units["time"] = "ms"
    elif bad == "displacement":
        frame.columns["displacement"] = np.arange(205, dtype=np.float64) * 0.01
        frame.columns["displacement"][70] -= 0.02
    elif bad == "displacement_equal":
        frame.columns["displacement"] = np.arange(205, dtype=np.float64) * 0.01
        frame.columns["displacement"][70] = frame.columns["displacement"][69]
    else:
        options["proof_strain"] += 0.001
    with pytest.raises(ProcessingError):
        frontier.acquisition_frontier(frame, options)


def test_pair_collision_and_inconsistent_source_row_rejected() -> None:
    frame = _case(pair=True)
    frame.columns["source_data_row_original"] = frame.columns["source_data_row"].copy()
    frame.units["source_data_row_original"] = "1"
    with pytest.raises(ProcessingError, match="예약"):
        _run(frame)
    frame = _case(pair=True)
    frame.columns["source_row"] = frame.columns["source_data_row"] + 40
    frame.units["source_row"] = "1"
    with pytest.raises(ProcessingError, match="일치"):
        _run(frame)


def test_source_row_gap_elsewhere_cannot_hide_prior_deletion() -> None:
    frame = _case()
    frame.columns["source_row"][150:] += 1
    with pytest.raises(ProcessingError, match="기존 행 누락"):
        _run(frame)


def test_above_budget_holds_all_rows() -> None:
    frame = _case(notch=(70, 90, 110))
    with pytest.raises(ProcessingError, match="1%"):
        _run(frame)
