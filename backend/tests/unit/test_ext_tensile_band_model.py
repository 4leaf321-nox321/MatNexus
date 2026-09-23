"""Registered stable-band modeling preserves source rows and method contracts."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pytest
from numpy.typing import NDArray

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "stable_band_model_v1_cases.npz"
R16_RECIPES = (
    Path(__file__).resolve().parents[2]
    / "extensions"
    / "tensile_extras"
    / "recipes"
    / "progressive_terminal_domain_v2_examples.json"
)
R17_RECIPES = (
    Path(__file__).resolve().parents[2]
    / "extensions"
    / "tensile_extras"
    / "recipes"
    / "stable_band_model_v1_examples.json"
)
R17_V2_RECIPES = R17_RECIPES.with_name("stable_band_model_v2_examples.json")
TERMINAL_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "tensile_terminal_v2_cases.npz"
)
METHODS = (
    "lower_envelope",
    "isotonic",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
)
LEGACY_METHODS = {
    "lower_envelope": "lower_envelope_auto_v1",
    "isotonic": "isotonic_auto_v1",
    "median_plateau": "median_plateau_auto_v1",
    "linear": "linear_auto_v1",
    "least_squares": "least_squares_auto_v1",
    "robust_linear": "robust_linear_auto_v1",
}


class _ExpectedRegion(TypedDict):
    peak: int
    band: tuple[int, int]
    left: dict[str, int]


EXPECTED_REGIONS: dict[int, _ExpectedRegion] = {
    0: {
        "peak": 74,
        "band": (90, 917),
        "left": {
            "lower_envelope": 34,
            "isotonic": 36,
            "median_plateau": 35,
            "linear": 36,
            "least_squares": 35,
            "robust_linear": 35,
        },
    },
    2: {
        "peak": 146,
        "band": (319, 1650),
        "left": {
            "lower_envelope": 68,
            "isotonic": 72,
            "median_plateau": 71,
            "linear": 72,
            "least_squares": 70,
            "robust_linear": 70,
        },
    },
    26: {
        "peak": 132,
        "band": (409, 485),
        "left": {method: 44 for method in METHODS},
    },
    27: {
        "peak": 127,
        "band": (459, 563),
        "left": {method: 40 for method in METHODS},
    },
    4: {
        "peak": 136,
        "band": (217, 1033),
        "left": {
            "lower_envelope": 61,
            "isotonic": 64,
            "median_plateau": 63,
            "linear": 64,
            "least_squares": 62,
            "robust_linear": 62,
        },
    },
}

extensions.load(EXTENSIONS)
processing.load_builtin()
band_module = import_module("matnexus_ext.tensile_extras.band_model")
compute_band_model = band_module.compute_band_model


def _frame(
    stress: Any,
    strain: Any | None = None,
    *,
    time: Any | None = None,
    units: dict[str, str] | None = None,
) -> Frame:
    y = np.asarray(stress)
    x = (
        np.arange(y.size, dtype=np.float64) / max(1, y.size - 1)
        if strain is None
        else np.asarray(strain)
    )
    t = np.arange(y.size, dtype=np.float64) * 0.01 if time is None else np.asarray(time)
    columns = {
        "strain_engineering": x.copy(),
        "stress_engineering": y.copy(),
        "time": t.copy(),
        "displacement": x.copy(),
        "force": y.copy(),
        "source_marker": np.arange(y.size, dtype=np.float64),
    }
    unit_map = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "time": "s",
        "displacement": "m",
        "force": "N",
        "source_marker": "1",
    }
    if units:
        unit_map.update(units)
    return Frame(columns, unit_map)


def _source_frame(case_index: int) -> Frame:
    prefix = f"c{case_index:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as archive:
        columns = {
            "strain_engineering": archive[f"{prefix}x"].copy(),
            "stress_engineering": archive[f"{prefix}y"].copy(),
            "time": archive[f"{prefix}time"].copy(),
            "source_row": archive[f"{prefix}row"].copy(),
            "displacement": archive[f"{prefix}displacement_m"].copy(),
            "force": archive[f"{prefix}force_N"].copy(),
            "prepared_row": archive[f"{prefix}prepared_row"].copy(),
        }
        source_keys = [
            key
            for key in archive.files
            if key.startswith(prefix + "source_") and key not in columns
        ]
        for key in source_keys:
            columns[key.removeprefix(prefix)] = archive[key].copy()
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "time": "s",
        "source_row": "1",
        "displacement": "m",
        "force": "N",
        "prepared_row": "1",
    }
    units.update({key: "1" for key in columns if key not in units})
    return Frame(columns, units)


def _bt3_frame() -> Frame:
    prefix = "c118_"
    with np.load(TERMINAL_FIXTURE, allow_pickle=False) as archive:
        columns = {
            "strain_engineering": archive[f"{prefix}x"].copy(),
            "stress_engineering": archive[f"{prefix}y"].copy(),
            "time": archive[f"{prefix}time"].copy(),
            "source_row": archive[f"{prefix}row"].copy(),
            "displacement": archive[f"{prefix}displacement_m"].copy(),
            "force": archive[f"{prefix}force_N"].copy(),
            "prepared_row": archive[f"{prefix}prepared_row"].copy(),
        }
    return Frame(
        columns,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "time": "s",
            "source_row": "1",
            "displacement": "m",
            "force": "N",
            "prepared_row": "1",
        },
    )


def _run(
    frame: Frame, method: str, options: dict[str, Any] | None = None
) -> processing.PipelineResult:
    selected: dict[str, Any] = {"policy": "band_and_events_auto_v1", "method": method}
    if options:
        selected.update(options)
    return processing.apply([Step("tensile.band_model", selected)], frame)


def _stage_scalars(result: processing.PipelineResult) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in result.stages[-1].scalars}


def _shared_anchor_curve() -> NDArray[np.float64]:
    values = np.asarray(
        [0.0, 30.0, 60.0, 40.0, 35.0, 50.0, 60.0, 85.0, 90.0, 95.0, 100.0, 85.0] + [80.0] * 20,
        dtype=np.float64,
    )
    return values


class TestRegistration:
    def test_registers_six_explicit_methods_between_source_and_model_stages(self) -> None:
        plugin = registry.get("tensile.band_model")

        assert plugin.kind == "processing"
        assert plugin.version == "2"
        assert plugin.order == 36
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert registry.get("tensile.yield_drop").order < plugin.order
        assert plugin.order < registry.get("tensile.model_curve").order
        params = {param.name: param for param in plugin.params}
        assert params["method"].required is True
        assert params["method"].default is None
        assert params["method"].choices == METHODS
        assert params["policy"].default == "band_and_events_auto_v2"
        assert params["policy"].choices == (
            "band_and_events_auto_v1",
            "band_and_events_auto_v2",
            "manual_band_v1",
        )
        assert params["band_start"].when == {"policy": ("manual_band_v1",)}
        assert params["strain"].unit == "1"
        assert params["stress"].unit == "Pa"
        assert params["time"].unit == "s"
        assert params["time"].required is False
        assert params["time"].default is None

    def test_missing_optional_time_uses_strain_progress_without_source_mutation(self) -> None:
        source = _source_frame(0)
        columns = {
            key: values.copy() for key, values in source.columns.items() if key != "time"
        }
        units = {key: unit for key, unit in source.units.items() if key != "time"}
        frame = Frame(columns, units)
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = processing.apply(
            [Step("tensile.band_model", {"method": "median_plateau"})],
            frame,
        )

        assert "time" not in frame.columns
        assert "time" not in result.frame.columns
        assert result.frame.length() == frame.length()
        assert "공학 변형률 진행축" in " ".join(result.stages[-1].notes)
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)


class Test실제원행:
    @pytest.mark.parametrize("case_index", (0, 2, 26, 27))
    @pytest.mark.parametrize("method", METHODS)
    def test_real_band_uses_method_anchor_and_changes_only_its_original_influence(
        self, case_index: int, method: str
    ) -> None:
        frame = _source_frame(case_index)
        before = {key: values.copy() for key, values in frame.columns.items()}
        expected = EXPECTED_REGIONS[case_index]
        computation = compute_band_model(
            before["strain_engineering"],
            before["stress_engineering"],
            before["time"],
            method=method,
            policy="band_and_events_auto_v1",
        )

        result = _run(frame, method)

        scalars = _stage_scalars(result)
        output = result.frame.columns["stress_engineering"]
        start, end = expected["band"]
        left = expected["left"][method]
        assert scalars["band_model_peak_index"] == expected["peak"]
        assert scalars["band_model_band_start_index"] == start
        assert scalars["band_model_band_end_index"] == end
        assert scalars["band_model_left_anchor_index"] == left
        assert result.frame.length() == frame.length()
        assert np.all(np.diff(output[left : end + 1]) >= 0.0)
        assert output[left] == before["stress_engineering"][left]
        assert output[end] == before["stress_engineering"][end]
        np.testing.assert_array_equal(output, computation.values)
        changed = np.flatnonzero(output != before["stress_engineering"])
        actual_intervals = [
            (record.left_anchor, record.right_anchor)
            for record in computation.records
            if record.proposal is not None and record.left_anchor is not None
        ]
        expected_intervals = [(left, end)]
        if case_index == 2:
            event_left = {
                "lower_envelope": 1806,
                "isotonic": 1836,
                "median_plateau": 1813,
                "linear": 1836,
                "least_squares": 1813,
                "robust_linear": 1813,
            }[method]
            expected_intervals.append((event_left, 1889))
        assert sorted(actual_intervals) == sorted(expected_intervals)
        assert all(
            any(start < row < stop for start, stop in expected_intervals) for row in changed
        )
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            if key != "stress_engineering":
                np.testing.assert_array_equal(result.frame.columns[key], values)

    @pytest.mark.parametrize("method", METHODS)
    def test_v2_completes_the_original_full_recovery_end_for_all_methods(
        self, method: str
    ) -> None:
        frame = _source_frame(2)
        strain = frame.columns["strain_engineering"][::2].copy()
        stress = frame.columns["stress_engineering"][::2].copy()
        progress = frame.columns["time"][::2].copy()

        computation = compute_band_model(
            strain,
            stress,
            progress,
            method=method,
            policy="band_and_events_auto_v2",
        )

        assert computation.selection.band_start_row is not None
        assert computation.selection.band_start_row <= 670
        assert computation.selection.band_end_row == 824
        assert computation.model_end_row == 825
        completed = [
            event
            for event in computation.events
            if event.kind == "full_recovery" and event.peak_index == 670
        ]
        assert len(completed) == 1
        assert (completed[0].recovery_index, completed[0].end_index) == (804, 825)
        band = next(record for record in computation.records if record.region_kind == "band")
        assert band.right_anchor == 825
        assert band.core_end == 824
        assert band.left_anchor is not None
        assert computation.compositions[0].newly_included_rows == (825, 825)
        assert computation.values[825] == stress[825]
        assert np.all(np.diff(computation.values[band.left_anchor : 826]) >= 0.0)

    def test_explicit_v1_keeps_the_same_decimated_completion_boundary_hold(self) -> None:
        frame = _source_frame(2)
        with pytest.raises(ProcessingError, match="recovered_event_crosses_band_influence"):
            compute_band_model(
                frame.columns["strain_engineering"][::2],
                frame.columns["stress_engineering"][::2],
                frame.columns["time"][::2],
                method="median_plateau",
                policy="band_and_events_auto_v1",
            )

    def test_omitted_policy_uses_registered_v2_default(self) -> None:
        frame = _source_frame(2)
        decimated = Frame(
            {key: value[::2].copy() for key, value in frame.columns.items()},
            dict(frame.units),
        )

        result = processing.apply(
            [Step("tensile.band_model", {"method": "median_plateau"})], decimated
        )

        assert result.stages[-1].options["policy"] == "band_and_events_auto_v2"
        scalars = _stage_scalars(result)
        assert scalars["band_model_band_end_index"] == 824
        assert scalars["band_model_model_end_index"] == 825

    @pytest.mark.parametrize("method", METHODS[1:])
    def test_pc4_closed_partial_continuation_composes_with_later_events(
        self, method: str
    ) -> None:
        frame = _source_frame(4)
        source = frame.columns["stress_engineering"].copy()
        computation = compute_band_model(
            frame.columns["strain_engineering"],
            source,
            frame.columns["time"],
            method=method,
            policy="band_and_events_auto_v1",
        )
        events = [record for record in computation.records if record.source_event]
        superseded = [
            record
            for record in events
            if record.decision == "band_supersedes_partial_continuation"
        ]
        assert len(superseded) == 1
        partial = superseded[0].source_event
        assert partial is not None
        assert partial.kind == "partial_recovery"
        assert (
            partial.peak_index,
            partial.trough_index,
            partial.recovery_index,
            partial.end_index,
            partial.end_at_observation_boundary,
        ) == (136, 179, 200, 1163, False)
        assert "continuation 1034~1163" in (superseded[0].reason or "")
        assert "별도 영향 구간은 적합 결과에 따라 변경될 수 있습니다" in (
            superseded[0].reason or ""
        )
        fitted = {
            record.source_event.peak_index: record
            for record in events
            if record.source_event is not None and record.decision == "event_fit"
        }
        # The independent Huber replay computes its fixed MAD from unconstrained
        # initial OLS residuals; 26 IRLS iterations place the final core target
        # between source rows 1858 and 1859.
        expected_lefts = {
            "isotonic": (1162, 1867),
            "median_plateau": (1042, 1858),
            "linear": (1162, 1867),
            "least_squares": (1061, 1856),
            "robust_linear": (1046, 1858),
        }[method]
        assert set(fitted) == {1163, 1869}
        assert (fitted[1163].left_anchor, fitted[1163].right_anchor) == (
            expected_lefts[0],
            1733,
        )
        assert (fitted[1869].left_anchor, fitted[1869].right_anchor) == (
            expected_lefts[1],
            1922,
        )

        result = _run(frame, method)
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"], computation.values
        )

    def test_pc4_lower_envelope_keeps_its_infeasible_later_event_hold(self) -> None:
        frame = _source_frame(4)

        with pytest.raises(
            ProcessingError,
            match=r"disjoint_recovered_event_fit_infeasible: method=lower_envelope, peak=1163",
        ):
            _run(frame, "lower_envelope")

    def test_pc4_v2_lower_pool_matches_original_suffix_minima_and_keeps_later_event_separate(
        self,
    ) -> None:
        frame = _source_frame(4)
        before = {key: value.copy() for key, value in frame.columns.items()}
        source = frame.columns["stress_engineering"].copy()
        strain = frame.columns["strain_engineering"].copy()
        progress = frame.columns["time"].copy()
        computation = compute_band_model(
            strain,
            source,
            progress,
            method="lower_envelope",
            policy="band_and_events_auto_v2",
        )

        expected = source.copy()
        for left, right in ((61, 1733), (1850, 1922)):
            suffix_minima = np.minimum.accumulate(source[left + 1 : right + 1][::-1])[::-1]
            expected[left + 1 : right] = suffix_minima[:-1]

        np.testing.assert_array_equal(computation.values, expected)
        assert (computation.selection.band_start_row, computation.selection.band_end_row) == (
            217,
            1033,
        )
        assert computation.model_end_row == 1733
        proposal_intervals = [
            (record.left_anchor, record.right_anchor)
            for record in computation.records
            if record.proposal is not None and record.left_anchor is not None
        ]
        assert sorted(proposal_intervals) == [(61, 1733), (1850, 1922)]
        composition = next(
            item
            for item in computation.compositions
            if item.kind == "lower_connected_component"
        )
        assert composition.includes_band
        assert composition.outer_left == 61
        assert composition.outer_right == 1733
        assert composition.released_internal_anchors == (1033,)
        assert composition.newly_included_rows == (1034, 1733)
        assert composition.newly_changed_points == 628
        assert (136, 1163, "partial_recovery") in composition.event_intervals
        assert (1163, 1733, "full_recovery") in composition.event_intervals
        partial_record = next(
            record
            for record in computation.records
            if record.source_event is not None and record.source_event.peak_index == 136
        )
        assert partial_record.decision == "lower_component_pool_member"
        assert "재계산되었습니다" in (partial_record.reason or "")
        assert int(np.count_nonzero(computation.values != source)) == 1323
        assert np.all(np.diff(computation.values[61 : 1733 + 1]) >= 0.0)
        assert np.all(np.diff(computation.values[1850 : 1922 + 1]) >= 0.0)
        changed_rows = np.flatnonzero(computation.values != source)
        assert all(61 < row < 1733 or 1850 < row < 1922 for row in changed_rows)

        event_fits = {
            record.source_event.peak_index: record
            for record in computation.records
            if record.source_event is not None and record.decision == "event_fit"
        }
        assert (event_fits[1869].left_anchor, event_fits[1869].right_anchor) == (
            1850,
            1922,
        )

        result = processing.apply(
            [
                Step(
                    "tensile.band_model",
                    {
                        "policy": "band_and_events_auto_v2",
                        "method": "lower_envelope",
                    },
                )
            ],
            frame,
        )
        output = result.frame.columns["stress_engineering"]
        np.testing.assert_array_equal(output, expected)
        assert _stage_scalars(result)["band_model_model_end_index"] == 1733
        assert _stage_scalars(result)["band_model_lower_composition_changed_points"] == 628
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            if key != "stress_engineering":
                np.testing.assert_array_equal(result.frame.columns[key], values)

    def test_partial_recovery_after_band_start_is_not_superseded(self) -> None:
        from matcore.processing._drop_recovery import DropEvent

        event = DropEvent(
            peak_index=136,
            drop_start=146,
            trough_index=179,
            recovery_index=230,
            end_index=1163,
            kind="partial_recovery",
            end_at_observation_boundary=False,
        )

        assert not band_module._can_supersede_closed_partial_continuation(
            event,
            influence_start=61,
            band_start=217,
            band_end=1033,
        )

    def test_no_band_recovered_metal_delegates_to_same_legacy_method(self) -> None:
        frame = _source_frame(151)
        before = {key: values.copy() for key, values in frame.columns.items()}

        from matcore.processing.tensile import yield_drop

        for method in METHODS:
            result = _run(frame, method)
            legacy = yield_drop(
                frame,
                {
                    "method": LEGACY_METHODS[method],
                    "strain": "strain_engineering",
                    "stress": "stress_engineering",
                },
            )
            np.testing.assert_array_equal(
                result.frame.columns["stress_engineering"],
                legacy.frame.columns["stress_engineering"],
            )
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)

    def test_real_nonstrict_bt3_source_is_held_without_sorting(self) -> None:
        frame = _bt3_frame()
        before = {key: values.copy() for key, values in frame.columns.items()}

        with pytest.raises(ProcessingError, match="엄격히 증가"):
            _run(frame, "median_plateau")

        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)


class Test이벤트와수동영역:
    def test_recovered_event_can_share_the_band_left_anchor_without_overlap(self) -> None:
        source = _shared_anchor_curve()
        strain = np.arange(source.size, dtype=np.float64) / 100.0
        frame = _frame(source, strain)
        options = {
            "policy": "manual_band_v1",
            "method": "median_plateau",
            "band_start": 12,
            "band_end": 31,
            "peak_row": 10,
            "left_anchor": 6,
        }

        result = _run(frame, "median_plateau", options)
        source_result = compute_band_model(
            strain,
            source,
            np.arange(source.size, dtype=np.float64),
            method="median_plateau",
            policy="manual_band_v1",
            band_start=12,
            band_end=31,
            peak_row=10,
            left_anchor=6,
        )

        event_records = [record for record in source_result.records if record.source_event]
        shared = [
            record
            for record in event_records
            if record.source_event is not None and record.source_event.end_index == 6
        ]
        assert len(shared) == 1
        assert shared[0].decision == "event_fit"
        assert shared[0].right_anchor == 6
        assert shared[0].left_anchor is not None and shared[0].left_anchor < 6
        assert source_result.records[0].left_anchor == 6
        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"], source_result.values
        )

    def test_recovered_event_crossing_band_right_edge_fails_explicitly(self) -> None:
        source = np.asarray(
            [10, 20, 30, 40, 50, 55, 60, 70, 80, 90, 100, 90]
            + [80] * 17
            + [50, 40, 60, 70, 80, 90, 101],
            dtype=np.float64,
        )
        detected = next(
            event
            for event in band_module.detect_events(source, 0.005, 0.005, 0.05)
            if event.peak_index == 10
        )
        assert detected.kind == "full_recovery"
        assert detected.end_index > 31
        frame = _frame(source)

        with pytest.raises(ProcessingError, match="recovered_event_crosses_band_influence"):
            _run(
                frame,
                "median_plateau",
                {
                    "policy": "manual_band_v1",
                    "band_start": 12,
                    "band_end": 31,
                    "peak_row": 10,
                    "left_anchor": 6,
                },
            )

    @pytest.mark.parametrize(
        "options",
        [
            {"method": "median_plateau", "band_start": 1},
            {
                "policy": "band_and_events_auto_v1",
                "method": "median_plateau",
                "band_start": 2,
                "band_end": 20,
            },
            {
                "policy": "manual_band_v1",
                "method": "median_plateau",
                "band_start": 1,
                "band_end": 2,
                "unused": 1,
            },
        ],
    )
    def test_rejects_missing_manual_bounds_wrong_policy_fields_and_unknown_options(
        self, options: dict[str, Any]
    ) -> None:
        with pytest.raises(ProcessingError):
            processing.apply([Step("tensile.band_model", options)], _frame([1, 2, 3, 4]))

    def test_manual_anchor_must_be_a_guarded_observed_crossing(self) -> None:
        with pytest.raises(ProcessingError, match="왼쪽 앵커"):
            _run(
                _frame(_shared_anchor_curve()),
                "median_plateau",
                {
                    "policy": "manual_band_v1",
                    "band_start": 12,
                    "band_end": 31,
                    "peak_row": 10,
                    "left_anchor": 5,
                },
            )


class Test재생과호환성:
    def test_no_band_delegates_bitwise_to_the_same_legacy_method(self) -> None:
        frame = _source_frame(9)
        source = frame.columns["stress_engineering"].copy()
        from matcore.processing.tensile import yield_drop

        for method in METHODS:
            result = _run(frame, method)
            legacy = yield_drop(
                frame,
                {
                    "method": LEGACY_METHODS[method],
                    "strain": "strain_engineering",
                    "stress": "stress_engineering",
                },
            )
            assert result.stages[-1].options["method"] == method
            assert result.stages[-1].frame.columns["stress_engineering"].dtype == np.float64
            np.testing.assert_array_equal(
                result.frame.columns["stress_engineering"],
                legacy.frame.columns["stress_engineering"],
            )
            np.testing.assert_array_equal(frame.columns["stress_engineering"], source)

    def test_json_round_trip_replays_the_same_curve_and_effective_defaults(self) -> None:
        frame = _source_frame(0)
        options = {
            "policy": "band_and_events_auto_v1",
            "method": "robust_linear",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
            "time": "time",
            "minimum_band_rows": 20,
            "minimum_progress_span": 0.1,
            "maximum_stress_over_peak": 0.9,
            "maximum_range_over_peak": 0.02,
            "maximum_gap_over_band_span": 0.1,
            "loading_floor_fraction": 0.4,
        }
        replay = json.loads(json.dumps(options))

        first = _run(frame, "robust_linear", options)
        second = processing.apply([Step("tensile.band_model", replay)], frame)

        assert first.stages[-1].options == second.stages[-1].options
        assert json.loads(json.dumps(first.stages[-1].options)) == first.stages[-1].options
        np.testing.assert_array_equal(
            first.frame.columns["stress_engineering"],
            second.frame.columns["stress_engineering"],
        )

    def test_rejects_wrong_si_units_and_does_not_mutate_inputs(self) -> None:
        frame = _frame([0.0, 20.0, 80.0, *([70.0] * 20)], units={"stress_engineering": "MPa"})
        before = {key: value.copy() for key, value in frame.columns.items()}

        with pytest.raises(ProcessingError, match="단위가 'Pa'"):
            _run(frame, "median_plateau")

        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)

    def test_r17_examples_replace_only_six_yield_drop_stages_and_keep_upper_exact(
        self,
    ) -> None:
        r16 = json.loads(R16_RECIPES.read_text(encoding="utf-8"))
        r17_v1 = json.loads(R17_RECIPES.read_text(encoding="utf-8"))
        r17_v2 = json.loads(R17_V2_RECIPES.read_text(encoding="utf-8"))

        assert len(r16["recipes"]) == len(r17_v1["recipes"]) == 7
        assert len(r16["recipes"]) == len(r17_v2["recipes"]) == 7
        assert r17_v1["schema"] == "matnexus.tensile.stable_band_model_v1_examples/1"
        assert r17_v2["schema"] == "matnexus.tensile.stable_band_model_v2_examples/1"
        for old, v1, v2 in zip(
            r16["recipes"], r17_v1["recipes"], r17_v2["recipes"], strict=True
        ):
            assert len(old["steps"]) == len(v1["steps"]) == len(v2["steps"])
            old_yield = [
                step for step in old["steps"] if step["plugin"] == "tensile.yield_drop"
            ]
            v1_band = [step for step in v1["steps"] if step["plugin"] == "tensile.band_model"]
            v2_band = [step for step in v2["steps"] if step["plugin"] == "tensile.band_model"]
            if old_yield:
                assert len(old_yield) == len(v1_band) == len(v2_band) == 1
                assert v1_band[0]["options"]["method"] in METHODS
                assert v1_band[0]["options"]["method"] == v2_band[0]["options"]["method"]
                assert v1_band[0]["options"]["policy"] == "band_and_events_auto_v1"
                assert v2_band[0]["options"]["policy"] == "band_and_events_auto_v2"
                old_steps = [
                    step for step in old["steps"] if step["plugin"] != "tensile.yield_drop"
                ]
                v1_steps = [
                    step for step in v1["steps"] if step["plugin"] != "tensile.band_model"
                ]
                v2_steps = [
                    step for step in v2["steps"] if step["plugin"] != "tensile.band_model"
                ]
                assert old_steps == v1_steps == v2_steps
            else:
                assert not v1_band and not v2_band
                assert old["steps"] == v1["steps"] == v2["steps"]
