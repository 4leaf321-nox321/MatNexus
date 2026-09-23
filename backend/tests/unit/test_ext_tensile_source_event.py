"""Source-E-aware no-band event handling uses original source row evidence."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step
from matcore.processing._drop_recovery import DropEvent, detect_events

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = ROOT / "extensions"
FIXTURE = ROOT / "tests" / "fixtures" / "tensile_source_event_cases.npz"
RECIPE_ROOT = EXTENSIONS / "tensile_extras" / "recipes"
RECIPE_V1 = RECIPE_ROOT / "source_measurement_model_v1_examples.json"
RECIPE_V2 = RECIPE_ROOT / "source_measurement_model_v2_examples.json"
POLICY = "band_and_source_events_auto_v1"
SOURCE_E = "tensile.source_elastic_modulus"
SOURCE_RP = "tensile.source_proof_stress"
MODEL_SUPPORT = "tensile.model_support"
BAND_MODEL = "tensile.band_model"
METHODS = ("median_plateau", "linear", "least_squares", "robust_linear")
DEFECT_CASES = (52, 55, 56, 101, 109, 110, 112, 113, 114, 117, 121, 124, 125, 126)
ACTUAL_CASES = (11, *DEFECT_CASES)
NOOP_CROSSING_CASES = (101, 112, 125)
NO_POST_E_TARGET_CASES = (109, 110, 114, 121)
extensions.load(EXTENSIONS)
processing.load_builtin()
BAND_IMPLEMENTATION = import_module("matnexus_ext.tensile_extras.band_model")


def _fixture_frame(case_id: int) -> tuple[Frame, dict[str, float]]:
    prefix = f"c{case_id:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as archive:
        columns = {
            key: archive[prefix + key].copy()
            for key in (
                "force",
                "displacement",
                "time",
                "source_row",
                "prepared_row",
                "strain_engineering",
                "stress_engineering",
            )
        }
        expected = {
            "source_elastic_end_index": float(archive[prefix + "source_elastic_end_index"][0]),
            "youngs_modulus": float(archive[prefix + "source_youngs_modulus"][0]),
            "proof_stress": float(archive[prefix + "source_proof_stress"][0]),
            "proof_strain": float(archive[prefix + "source_proof_strain"][0]),
            "source_proof_left_index": float(archive[prefix + "source_proof_left_index"][0]),
            "source_proof_right_index": float(archive[prefix + "source_proof_right_index"][0]),
        }
    units = {
        "force": "N",
        "displacement": "m",
        "time": "s",
        "source_row": "1",
        "prepared_row": "1",
        "strain_engineering": "1",
        "stress_engineering": "Pa",
    }
    return Frame(columns, units), expected


def _source_prefix(frame: Frame) -> processing.PipelineResult:
    return processing.apply(
        [
            Step(SOURCE_E, {}),
            Step(SOURCE_RP, {"offset_strain": 0.002}),
            Step("tensile.necking_candidate", {}),
            Step(MODEL_SUPPORT, {}),
        ],
        frame,
    )


def _scalars(stage: Any) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in stage.scalars}


def _assert_source_measurements(
    result: processing.PipelineResult, expected: dict[str, float]
) -> None:
    e_stage, rp_stage = result.stages[0], result.stages[1]
    e_values = _scalars(e_stage)
    rp_values = _scalars(rp_stage)
    assert e_values["source_elastic_end_index"] == expected["source_elastic_end_index"]
    assert e_values["youngs_modulus"] == pytest.approx(
        expected["youngs_modulus"], rel=1e-9, abs=1.0
    )
    assert rp_values["proof_stress"] == pytest.approx(
        expected["proof_stress"], rel=1e-9, abs=1.0
    )
    assert rp_values["proof_strain"] == pytest.approx(
        expected["proof_strain"], rel=1e-9, abs=1e-12
    )
    assert rp_values["source_proof_left_index"] == expected["source_proof_left_index"]
    assert rp_values["source_proof_right_index"] == expected["source_proof_right_index"]


def _simple_frame(
    mapping: Any = (0, 1, 2, 3), *, stress: Any = (1.0, 2.0, 3.0, 4.0), map_unit: str = "1"
) -> Frame:
    y = np.asarray(stress, dtype=np.float64)
    x = np.arange(y.size, dtype=np.float64) / max(y.size - 1, 1)
    columns = {
        "strain_engineering": x,
        "stress_engineering": y,
        "model_input_index": np.asarray(mapping),
        "force": y.copy(),
        "displacement": x.copy(),
    }
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "model_input_index": map_unit,
        "force": "N",
        "displacement": "m",
    }
    return Frame(columns, units)


class TestSourceEventRegistration:
    def test_policy_is_explicit_without_replacing_the_default(self) -> None:
        plugin = registry.get(BAND_MODEL)
        params = {param.name: param for param in plugin.params}
        assert params["policy"].default == "band_and_events_auto_v2"
        assert POLICY in params["policy"].choices
        assert params["source_elastic_end_index"].default == "@source_elastic_end_index"
        assert params["source_index_column"].default == "model_input_index"
        assert params["source_index_column"].when == {"policy": (POLICY,)}
        assert "원자료" in params["source_elastic_end_index"].label
        values = {item.key: item for item in plugin.makes_values}
        assert "원자료" in values["band_model_source_elastic_end_index"].label
        assert "현재 모델 입력" in values["band_model_source_elastic_prefix_end_index"].label

    def test_v2_recipe_changes_only_stable_band_policy(self) -> None:
        old = json.loads(RECIPE_V1.read_text(encoding="utf-8"))
        new = json.loads(RECIPE_V2.read_text(encoding="utf-8"))
        assert old["schema"] == "matnexus.tensile.source_measurement_model_v1_examples/1"
        assert new["schema"] == "matnexus.tensile.source_measurement_model_v2_examples/1"
        assert len(new["recipes"]) == len(old["recipes"]) == 7
        for old_recipe, new_recipe in zip(old["recipes"], new["recipes"], strict=True):
            expected = json.loads(json.dumps(old_recipe))
            expected["key"] = expected["key"].replace(
                "source_measurement_model_v1_", "source_measurement_model_v2_"
            )
            for step in expected["steps"]:
                if step["plugin"] == BAND_MODEL:
                    step["options"]["policy"] = POLICY
            assert new_recipe["key"] == expected["key"]
            assert new_recipe["steps"] == expected["steps"]
            band_steps = [step for step in new_recipe["steps"] if step["plugin"] == BAND_MODEL]
            assert len(band_steps) in (0, 1)
            if band_steps:
                assert band_steps[0]["options"]["policy"] == POLICY


class TestActualSourceEventCases:
    @pytest.mark.parametrize("case_id", ACTUAL_CASES)
    @pytest.mark.parametrize("method", METHODS)
    def test_measured_prefix_events_are_not_fit_targets(
        self, case_id: int, method: str
    ) -> None:
        frame, expected = _fixture_frame(case_id)
        before = {key: values.copy() for key, values in frame.columns.items()}
        steps = [
            Step(SOURCE_E, {}),
            Step(SOURCE_RP, {"offset_strain": 0.002}),
            Step("tensile.necking_candidate", {}),
            Step(MODEL_SUPPORT, {}),
            Step(BAND_MODEL, {"policy": POLICY, "method": method}),
        ]
        try:
            result = processing.apply(steps, frame)
        except ProcessingError as error:
            pytest.fail(f"A2 source-event candidate held case {case_id}/{method}: {error}")
        _assert_source_measurements(result, expected)
        support_frame = result.stages[-2].frame
        band_stage = result.stages[-1]
        values = _scalars(band_stage)
        assert values["band_model_band_start_index"] == -1.0
        mapping = support_frame.columns["model_input_index"].astype(np.int64)
        e_end = int(expected["source_elastic_end_index"])
        prefix = np.flatnonzero(mapping <= e_end)
        prefix_end = int(prefix[-1]) if prefix.size else -1
        if prefix_end >= 0:
            np.testing.assert_array_equal(
                band_stage.frame.columns["stress_engineering"][: prefix_end + 1],
                support_frame.columns["stress_engineering"][: prefix_end + 1],
            )
        source_events = detect_events(
            support_frame.columns["stress_engineering"], 0.005, 0.005, 0.05
        )
        expected_excluded_count = sum(
            event.end_index <= prefix_end
            and (
                event.kind == "full_recovery"
                or (
                    event.kind == "partial_recovery"
                    and event.recovery_index is not None
                    and not event.end_at_observation_boundary
                )
            )
            for event in source_events
        )
        assert values["band_model_source_event_excluded_in_elastic_count"] == float(
            expected_excluded_count
        )
        for event in source_events:
            if event.kind == "terminal_unrecovered" or event.end_at_observation_boundary:
                np.testing.assert_array_equal(
                    band_stage.frame.columns["stress_engineering"][
                        event.peak_index : event.end_index + 1
                    ],
                    support_frame.columns["stress_engineering"][
                        event.peak_index : event.end_index + 1
                    ],
                )
            if (
                event.kind in ("full_recovery", "partial_recovery")
                and event.recovery_index is not None
                and not event.end_at_observation_boundary
                and event.peak_index <= prefix_end < event.end_index
                and event.end_index == prefix_end + 1
                and support_frame.columns["stress_engineering"][prefix_end]
                <= support_frame.columns["stress_engineering"][event.end_index]
            ):
                assert (
                    band_stage.frame.columns["stress_engineering"][event.end_index]
                    == support_frame.columns["stress_engineering"][event.end_index]
                )
        for key, values_before in support_frame.columns.items():
            if key != "stress_engineering":
                np.testing.assert_array_equal(band_stage.frame.columns[key], values_before)
        assert values["band_model_source_event_target_count"] > 0.0 or np.array_equal(
            band_stage.frame.columns["stress_engineering"],
            support_frame.columns["stress_engineering"],
        )
        if case_id in NOOP_CROSSING_CASES:
            assert values["band_model_source_event_crossing_noop_count"] == 1.0
            assert "crossing_no_editable_rows" in " ".join(band_stage.notes)
        if case_id in NO_POST_E_TARGET_CASES:
            assert values["band_model_source_event_target_count"] == 0.0
            np.testing.assert_array_equal(
                band_stage.frame.columns["stress_engineering"],
                support_frame.columns["stress_engineering"],
            )
        for key, values_before in before.items():
            np.testing.assert_array_equal(frame.columns[key], values_before)

        if case_id == 11:
            assert values["band_model_source_event_one_free_row_region_count"] == 1.0
            output_stress = band_stage.frame.columns["stress_engineering"]
            source_stress = support_frame.columns["stress_engineering"]
            if method == "linear":
                x = support_frame.columns["strain_engineering"]
                expected_row = source_stress[69] + (source_stress[71] - source_stress[69]) * (
                    x[70] - x[69]
                ) / (x[71] - x[69])
            else:
                expected_row = np.clip(source_stress[70], source_stress[69], source_stress[71])
            assert output_stress[70] == pytest.approx(expected_row, rel=1e-12, abs=1e-6)
            detail = next(note for note in band_stage.notes if "source_event_fit" in note)
            assert "original_events=67~71" in detail
            assert "editable_rows=70~70" in detail
            assert "support_count=1" in detail
            assert "anchors=69~71" in detail
            assert "quality=not_reported" in detail
            assert "R²=" not in detail and "RMSE=" not in detail
        if case_id == 112 and method in ("least_squares", "robust_linear"):
            assert values["band_model_source_event_bounded_anchor_count"] >= 1.0
            expected_component = (
                "original_events=155~158,158~161,161~166,166~170,170~175,175~181"
            )
            assert any(
                expected_component in note
                and "core=155~180" in note
                and "editable_rows=155~180" in note
                and "support_count=26" in note
                and "anchors=154~181" in note
                and "anchor_mode=bounded_observed_anchor" in note
                for note in band_stage.notes
            )

    def test_case125_maps_E_end326_to_nearest_retained_row325(self) -> None:
        frame, expected = _fixture_frame(125)
        result = _source_prefix(frame)
        _assert_source_measurements(result, expected)
        mapping = result.frame.columns["model_input_index"].astype(np.int64)
        assert expected["source_elastic_end_index"] == 326.0
        assert np.max(mapping[mapping <= 326]) == 325
        assert 326 not in mapping

    def test_json_replay_uses_resolved_source_E_and_mapping_options(self) -> None:
        frame, expected = _fixture_frame(110)
        steps = [
            Step(SOURCE_E, {}),
            Step(SOURCE_RP, {"offset_strain": 0.002}),
            Step("tensile.necking_candidate", {}),
            Step(MODEL_SUPPORT, {}),
            Step(BAND_MODEL, {"policy": POLICY, "method": "median_plateau"}),
        ]
        first = processing.apply(steps, frame)
        band_stage = first.stages[-1]
        assert (
            band_stage.options["source_elastic_end_index"]
            == expected["source_elastic_end_index"]
        )
        assert band_stage.options["source_index_column"] == "model_input_index"
        replay_steps = [
            Step(stage.plugin, json.loads(json.dumps(stage.options))) for stage in first.stages
        ]
        replay = processing.apply(replay_steps, frame)
        assert replay.stages[-1].options == band_stage.options
        assert _scalars(replay.stages[-1]) == _scalars(band_stage)
        for key, values in band_stage.frame.columns.items():
            np.testing.assert_array_equal(replay.stages[-1].frame.columns[key], values)


class TestSourceEventBoundaries:
    @pytest.mark.parametrize("case_id", NOOP_CROSSING_CASES)
    def test_closed_E_crossing_with_no_editable_row_is_diagnosed_and_preserved(
        self, case_id: int
    ) -> None:
        frame, expected = _fixture_frame(case_id)
        source_prefix = _source_prefix(frame)
        support = source_prefix.stages[-1].frame
        mapping = support.columns["model_input_index"].astype(np.int64)
        e_end = int(expected["source_elastic_end_index"])
        prefix_end = int(np.flatnonzero(mapping <= e_end)[-1])
        stress = support.columns["stress_engineering"]
        events = detect_events(stress, 0.005, 0.005, 0.05)
        crossings = [
            event
            for event in events
            if event.kind in ("full_recovery", "partial_recovery")
            and event.recovery_index is not None
            and not event.end_at_observation_boundary
            and event.peak_index <= prefix_end < event.end_index
        ]
        noop = [
            event
            for event in crossings
            if event.end_index == prefix_end + 1
            and stress[prefix_end] <= stress[event.end_index]
        ]
        assert len(noop) == 1
        event = noop[0]
        assert event.peak_index <= prefix_end < event.end_index
        assert event.end_index == prefix_end + 1
        assert stress[prefix_end] <= stress[event.end_index]
        result = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": e_end,
                    },
                )
            ],
            support,
        )
        values = _scalars(result.stages[-1])
        assert values["band_model_source_event_crossing_noop_count"] == 1.0
        assert values["band_model_source_event_excluded_in_elastic_count"] >= 0.0
        notes = " ".join(result.stages[-1].notes)
        assert "crossing_no_editable_rows" in notes
        assert f"{event.peak_index}~{event.end_index}" in notes
        output_stress = result.frame.columns["stress_engineering"]
        np.testing.assert_array_equal(
            output_stress[: prefix_end + 1], stress[: prefix_end + 1]
        )
        np.testing.assert_array_equal(
            output_stress[event.peak_index : event.end_index + 1],
            stress[event.peak_index : event.end_index + 1],
        )

    def test_crossing_with_multiple_editable_rows_keeps_full_event_bounds(self) -> None:
        stress = np.asarray([1, 2, 3, 4, 5, 10, 6, 7, 8, 9, 10, 11, 12], dtype=np.float64)
        frame = _simple_frame(np.arange(stress.size), stress=stress)
        events = detect_events(stress, 0.005, 0.005, 0.05)
        event = next(event for event in events if event.kind == "full_recovery")
        assert event.peak_index <= 7 < event.end_index
        assert event.end_index > 8
        result = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": 7,
                    },
                )
            ],
            frame,
        )
        values = _scalars(result.stages[-1])
        assert values["band_model_source_event_one_free_row_region_count"] == 0.0
        assert values["band_model_source_event_fit_region_count"] == 1.0
        detail = next(note for note in result.stages[-1].notes if "source_event_fit" in note)
        assert f"original_events={event.peak_index}~{event.end_index}" in detail
        assert "editable_rows=8~9" in detail
        assert "support_count=2" in detail
        assert "anchors=7~10" in detail
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"][:8], stress[:8]
        )
        assert result.frame.columns["stress_engineering"][10] == stress[10]
        assert np.all(np.diff(result.frame.columns["stress_engineering"][7:11]) >= 0.0)

    @pytest.mark.parametrize("method", METHODS)
    def test_crossing_one_free_row_uses_method_objective_without_fit_quality(
        self, method: str
    ) -> None:
        stress = np.asarray([10, 20, 30, 40, 50, 100, 60, 50, 80, 50, 50], dtype=np.float64)
        frame = _simple_frame(np.arange(stress.size), stress=stress)
        before = {key: value.copy() for key, value in frame.columns.items()}
        events = detect_events(stress, 0.005, 0.005, 0.05)
        event = next(item for item in events if item.peak_index == 5)
        assert event.kind == "partial_recovery"
        assert (event.peak_index, event.end_index) == (5, 8)
        assert event.end_at_observation_boundary is False

        result = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": method,
                        "source_elastic_end_index": 6,
                    },
                )
            ],
            frame,
        )

        stage = result.stages[-1]
        values = _scalars(stage)
        assert values["band_model_source_event_one_free_row_region_count"] == 1.0
        assert values["band_model_source_event_fit_region_count"] == 1.0
        x = frame.columns["strain_engineering"]
        expected = (
            stress[6] + (stress[8] - stress[6]) * (x[7] - x[6]) / (x[8] - x[6])
            if method == "linear"
            else np.clip(stress[7], stress[6], stress[8])
        )
        assert result.frame.columns["stress_engineering"][7] == pytest.approx(
            expected, rel=1e-12, abs=1e-12
        )
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"][:7], stress[:7]
        )
        assert result.frame.columns["stress_engineering"][8] == stress[8]
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"][8:], stress[8:]
        )
        detail = next(note for note in stage.notes if "source_event_fit" in note)
        assert "original_events=5~8" in detail
        assert "editable_rows=7~7" in detail
        assert "source_editable_rows=7~7" in detail
        assert "support_count=1" in detail
        assert "anchors=6~8" in detail
        assert "quality=not_reported" in detail
        assert "R²=" not in detail and "RMSE=" not in detail
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)

    def test_declining_locked_crossing_anchors_remain_an_explicit_hold(self) -> None:
        stress = np.asarray([10, 20, 100, 95, 70, 60, 70, 80, 50, 50], dtype=np.float64)
        frame = _simple_frame(np.arange(stress.size), stress=stress)
        before = {key: value.copy() for key, value in frame.columns.items()}
        event = next(
            item
            for item in detect_events(stress, 0.005, 0.005, 0.05)
            if item.kind == "partial_recovery"
        )
        assert event.peak_index <= 3 < event.end_index
        assert stress[3] > stress[event.end_index]

        with pytest.raises(ProcessingError) as raised:
            processing.apply(
                [
                    Step(
                        BAND_MODEL,
                        {
                            "policy": POLICY,
                            "method": "least_squares",
                            "source_elastic_end_index": 3,
                        },
                    )
                ],
                frame,
            )
        assert "A2 attempt=" in str(raised.value)
        assert "고정 관측 앵커 응력이 감소" in str(raised.value)
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)

    def test_targetless_and_crossing_components_merge_before_original_refit(self) -> None:
        stress = np.asarray(
            [10, 20, 100, 80, 60, 50, 55, 58, 100, 120, 50, 110, 120, 121],
            dtype=np.float64,
        )
        frame = _simple_frame(np.arange(stress.size), stress=stress)
        events = detect_events(stress, 0.005, 0.005, 0.05)
        assert [(event.peak_index, event.end_index) for event in events] == [(2, 8), (9, 12)]

        result = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": 5,
                    },
                )
            ],
            frame,
        )

        stage = result.stages[-1]
        detail = next(note for note in stage.notes if "source_event_fit" in note)
        assert "original_events=2~8,9~12" in detail
        assert "core=2~11" in detail
        assert "editable_rows=6~11" in detail
        assert "support_count=6" in detail
        assert "anchors=5~12" in detail
        expected_level = float(np.median(stress[6:12]))
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"][6:12],
            np.full(6, expected_level),
        )
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"][:6], stress[:6]
        )
        assert result.frame.columns["stress_engineering"][12] == stress[12]
        np.testing.assert_array_equal(frame.columns["stress_engineering"], stress)

    def test_protected_overlap_blocks_editable_crossing(self) -> None:
        stress = np.asarray([10, 20, 100, 80, 60, 60, 65, 70, 100, 50], dtype=np.float64)
        strain = np.arange(stress.size, dtype=np.float64)
        event = DropEvent(2, 3, 4, 5, 8, "full_recovery", False)
        component = BAND_IMPLEMENTATION._SourceEventCore(2, 8, (event,))
        with pytest.raises(BAND_IMPLEMENTATION.AutoYieldFitError, match="보호 말단 구간"):
            BAND_IMPLEMENTATION._source_event_plan(
                strain,
                stress,
                component,
                method="median_plateau",
                preserve_boundary=5,
                protected=((7, 9),),
            )

    def test_later_event_uses_noop_completion_as_fixed_anchor(self) -> None:
        stress = np.asarray(
            [10, 20, 30, 40, 50, 60, 100, 80, 100, 110, 90, 95, 110, 111],
            dtype=np.float64,
        )
        frame = _simple_frame(np.arange(stress.size), stress=stress)
        events = detect_events(stress, 0.005, 0.005, 0.05)
        assert len(events) == 2
        first, later = events
        assert first.kind == "full_recovery"
        assert first.peak_index <= 7 < first.end_index == 8
        assert stress[7] <= stress[first.end_index]
        assert later.kind == "full_recovery"
        assert later.peak_index == 9
        assert later.end_index == 12

        result = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": 7,
                    },
                )
            ],
            frame,
        )

        values = _scalars(result.stages[-1])
        assert values["band_model_source_event_crossing_noop_count"] == 1.0
        assert values["band_model_source_event_bounded_anchor_count"] == 1.0
        assert result.frame.columns["stress_engineering"][8] == stress[8]
        assert any("anchors=8~12" in note for note in result.stages[-1].notes)
        np.testing.assert_array_equal(frame.columns["stress_engineering"], stress)

    @pytest.mark.parametrize(
        ("mapping", "map_unit", "end_index"),
        [
            ((0, 1.5, 2, 3), "1", 2),
            ((0, 1, 1, 3), "1", 2),
            ((0, -1, 2, 3), "1", 2),
            ((0, 1, 2, 3), "Pa", 2),
            ((0, 1, 2, float(1 << 63)), "1", 2),
            ((0, 1, 2, 3), "1", True),
            ((0, 1, 2, 3), "1", 1.5),
            ((0, 1, 2, 3), "1", 1 << 63),
        ],
    )
    def test_invalid_source_mapping_or_E_index_is_rejected(
        self, mapping: Any, map_unit: str, end_index: Any
    ) -> None:
        frame = _simple_frame(mapping, map_unit=map_unit)
        with pytest.raises(ProcessingError):
            processing.apply(
                [
                    Step(
                        BAND_MODEL,
                        {
                            "policy": POLICY,
                            "method": "median_plateau",
                            "source_elastic_end_index": end_index,
                        },
                    )
                ],
                frame,
            )

    def test_E_prefix_before_and_after_manual_model_scope_is_explicit(self) -> None:
        frame = _simple_frame((10, 20, 30, 40))
        before = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": 5,
                    },
                )
            ],
            frame,
        )
        before_values = _scalars(before.stages[-1])
        assert before_values["band_model_source_elastic_prefix_end_index"] == -1.0
        assert "first current row as anchor" in " ".join(before.stages[-1].notes)
        np.testing.assert_array_equal(
            before.frame.columns["stress_engineering"], frame.columns["stress_engineering"]
        )

        after = processing.apply(
            [
                Step(
                    BAND_MODEL,
                    {
                        "policy": POLICY,
                        "method": "median_plateau",
                        "source_elastic_end_index": 40,
                    },
                )
            ],
            frame,
        )
        after_values = _scalars(after.stages[-1])
        assert after_values["band_model_source_elastic_prefix_end_index"] == 3.0
        assert after_values["band_model_source_event_target_count"] == 0.0
        assert "적합할 닫힌 회복 사건이 없어" in " ".join(after.stages[-1].notes)
        np.testing.assert_array_equal(
            after.frame.columns["stress_engineering"], frame.columns["stress_engineering"]
        )

    @pytest.mark.parametrize(
        "options",
        [
            {"unknown_auto_band": 0.2},
            {"source_index_column": "missing_mapping"},
            {"source_index_column": " "},
            {"source_elastic_end_index": -1},
        ],
    )
    def test_unknown_or_invalid_source_event_options_are_rejected(
        self, options: dict[str, Any]
    ) -> None:
        values: dict[str, Any] = {
            "policy": POLICY,
            "method": "median_plateau",
            "source_elastic_end_index": 2,
        }
        values.update(options)
        with pytest.raises(ProcessingError):
            processing.apply([Step(BAND_MODEL, values)], _simple_frame())
