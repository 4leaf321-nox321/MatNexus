"""Fixed observed terminal anchors rescue only the source-event isotonic path."""

from __future__ import annotations

import json
import re
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions, processing
from matcore.processing import Frame, ProcessingError, Step
from matcore.processing._drop_recovery import detect_events

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = ROOT / "extensions"
FIXTURE = ROOT / "tests" / "fixtures" / "tensile_isotonic_terminal_join_cases.npz"
POLICY = "band_and_source_events_auto_v1"
BAND_MODEL = "tensile.band_model"
TARGETS = {
    85: {"prefix_end": 34, "start": 265, "terminal": 511, "left": 264},
    107: {"prefix_end": 22, "start": 3036, "terminal": 4668, "left": 3035},
    113: {"prefix_end": 59, "start": 2526, "terminal": 4557, "left": 2524},
    122: {"prefix_end": 56, "start": 2716, "terminal": 4470, "left": 2715},
}
CONTROLS = (0, 9, 11, 151, 156)
CHANNEL_UNITS = {
    "force": "N",
    "displacement": "m",
    "time": "s",
    "source_row": "1",
    "prepared_row": "1",
    "strain_engineering": "1",
    "stress_engineering": "Pa",
    "model_input_index": "1",
}

extensions.load(EXTENSIONS)
processing.load_builtin()
import_module("matnexus_ext.tensile_extras.band_model")


def _fixture_frame(case_id: int) -> tuple[Frame, float]:
    prefix = f"c{case_id:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as saved:
        columns = {key: saved[prefix + key].copy() for key in CHANNEL_UNITS}
        elastic_end = float(saved[prefix + "source_elastic_end_index"][0])
    return Frame(columns, dict(CHANNEL_UNITS)), elastic_end


def _assert_replay_equal(expected: Any, actual: Any) -> None:
    assert expected.plugin == actual.plugin == BAND_MODEL
    assert dict(expected.options) == dict(actual.options)
    assert [(s.key, s.value, s.si_unit, s.dimension) for s in expected.scalars] == [
        (s.key, s.value, s.si_unit, s.dimension) for s in actual.scalars
    ]
    assert list(expected.notes) == list(actual.notes)
    assert expected.frame.units == actual.frame.units
    assert list(expected.frame.columns) == list(actual.frame.columns)
    for key in expected.frame.columns:
        assert np.array_equal(expected.frame.columns[key], actual.frame.columns[key])


def _scalar_values(stage: Any) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in stage.scalars}


def _note_fields(note: str) -> dict[str, str]:
    return dict(re.findall(r"(?:^|\s)([a-z_]+)=([^\s;]+)", note))


@pytest.mark.parametrize("case_id", tuple(TARGETS))
def test_bounded_isotonic_rescue_uses_observed_terminal_and_replays(case_id: int) -> None:
    frame, elastic_end = _fixture_frame(case_id)
    original = {key: value.copy() for key, value in frame.columns.items()}
    source_rows = original["model_input_index"].astype(np.int64, copy=False)
    stress = original["stress_engineering"]
    options = {
        "policy": POLICY,
        "method": "isotonic",
        "source_elastic_end_index": elastic_end,
        "source_index_column": "model_input_index",
    }

    result = processing.apply([Step(BAND_MODEL, options)], frame)
    stage = result.stages[-1]
    output = stage.frame.columns["stress_engineering"]
    scalar_values = _scalar_values(stage)
    notes = list(stage.notes)

    assert scalar_values["band_model_source_event_isotonic_trigger_count"] == 1.0
    assert scalar_values["band_model_source_event_isotonic_fit_region_count"] >= 1.0
    trigger_notes = [note for note in notes if note.startswith("source_isotonic_trigger ")]
    assert len(trigger_notes) == 1
    trigger = _note_fields(trigger_notes[0])
    expected = TARGETS[case_id]
    assert int(trigger["model_prefix_end"]) == expected["prefix_end"]
    assert int(trigger["protected_terminal"]) == expected["terminal"]

    fit_notes = [
        note for note in notes if note.startswith("source_event_fit method=isotonic ")
    ]
    assert fit_notes
    trigger_fit = [
        fields
        for fields in map(_note_fields, fit_notes)
        if fields["core"].split("~")[0] == str(expected["start"])
        and int(fields["anchors"].split("~")[1]) == expected["terminal"]
    ]
    assert len(trigger_fit) == 1
    fit = trigger_fit[0]
    assert fit["anchors"] == f"{expected['left']}~{expected['terminal']}"
    assert fit["anchor_mode"] == "bounded_terminal_join"
    assert fit["objective"] == "equal_row_bounded_l2"

    editable = np.zeros(stress.size, dtype=bool)
    for note in fit_notes:
        fields = _note_fields(note)
        left, right = (int(value) for value in fields["anchors"].split("~"))
        assert output[left] == stress[left]
        assert output[right] == stress[right]
        assert np.all(np.diff(output[left : right + 1]) >= 0.0)
        if fields["editable_rows"] != "none":
            start, end = (int(value) for value in fields["editable_rows"].split("~"))
            editable[start : end + 1] = True
    changed = output != stress
    assert not np.any(changed & ~editable)
    assert scalar_values["band_model_source_event_isotonic_changed_points"] == float(
        np.count_nonzero(changed)
    )

    prefix = source_rows <= int(elastic_end)
    assert np.array_equal(output[prefix], stress[prefix])
    terminal_source = int(trigger["source_terminal"])
    protected_tail = source_rows >= terminal_source
    assert np.array_equal(output[protected_tail], stress[protected_tail])
    for key, values in original.items():
        if key != "stress_engineering":
            assert np.array_equal(stage.frame.columns[key], values)
        assert np.array_equal(frame.columns[key], values)

    replay_options = json.loads(json.dumps(dict(stage.options), ensure_ascii=False))
    replay = processing.apply(
        [Step(stage.plugin, replay_options)],
        Frame({key: value.copy() for key, value in original.items()}, dict(frame.units)),
    )
    _assert_replay_equal(stage, replay.stages[-1])


@pytest.mark.parametrize("case_id", CONTROLS)
def test_accepted_isotonic_legacy_controls_remain_exact(case_id: int) -> None:
    frame, elastic_end = _fixture_frame(case_id)
    original = {key: value.copy() for key, value in frame.columns.items()}
    prefix = f"c{case_id:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as saved:
        expected_stress = saved[prefix + "legacy_stress_engineering"].copy()
    options = {
        "policy": POLICY,
        "method": "isotonic",
        "source_elastic_end_index": elastic_end,
        "source_index_column": "model_input_index",
    }

    result = processing.apply([Step(BAND_MODEL, options)], frame)
    stage = result.stages[-1]
    assert np.array_equal(stage.frame.columns["stress_engineering"], expected_stress)
    assert not any(note.startswith("source_isotonic_trigger ") for note in stage.notes)
    for key, values in original.items():
        if key != "stress_engineering":
            assert np.array_equal(stage.frame.columns[key], values)
        assert np.array_equal(frame.columns[key], values)

    replay_options = json.loads(json.dumps(dict(stage.options), ensure_ascii=False))
    replay = processing.apply(
        [Step(stage.plugin, replay_options)],
        Frame({key: value.copy() for key, value in original.items()}, dict(frame.units)),
    )
    _assert_replay_equal(stage, replay.stages[-1])


def test_crossing_source_e_boundary_remains_an_explicit_hold() -> None:
    frame, _elastic_end = _fixture_frame(85)
    source_rows = frame.columns["model_input_index"].astype(np.int64, copy=False)
    events = detect_events(frame.columns["stress_engineering"], 0.005, 0.005, 0.05)
    crossing = next(event for event in events if 300 <= event.peak_index < event.end_index)
    options = {
        "policy": POLICY,
        "method": "isotonic",
        "source_elastic_end_index": float(source_rows[crossing.peak_index + 1]),
        "source_index_column": "model_input_index",
    }

    with pytest.raises(ProcessingError, match="source-E 경계를 지나는 닫힌 회복 사건"):
        processing.apply([Step(BAND_MODEL, options)], frame)


def test_infeasible_outer_anchor_order_remains_a_hold() -> None:
    frame, _elastic_end = _fixture_frame(85)
    source_rows = frame.columns["model_input_index"].astype(np.int64, copy=False)
    options = {
        "policy": POLICY,
        "method": "isotonic",
        # The trigger component starts at row 301.  With P=300, its only
        # admissible left anchor is row 300, whose raw stress exceeds y[511].
        "source_elastic_end_index": float(source_rows[300]),
        "source_index_column": "model_input_index",
    }

    with pytest.raises(ProcessingError, match="비감소 왼쪽 관측 앵커를 찾지 못했습니다"):
        processing.apply([Step(BAND_MODEL, options)], frame)
