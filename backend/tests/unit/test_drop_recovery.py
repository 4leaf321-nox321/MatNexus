"""yield_drop 의 사건·범위 계약을 DB 없이 검증한다."""

from __future__ import annotations

import json

import numpy as np
import pytest

from matcore import processing
from matcore.processing import Frame, ProcessingError, Step
from matcore.processing._drop_recovery import DropEvent, detect_events
from matcore.processing.tensile import (
    AUTO_LOWER_ENVELOPE_METHOD,
    _expand_event_intervals,
    _fit_linear,
)


@pytest.fixture(autouse=True)
def _plugins() -> None:
    processing.load_builtin()


def _frame(stress: list[float], strain: list[float] | None = None) -> Frame:
    y = np.asarray(stress, dtype=np.float64)
    x = (
        np.arange(y.size, dtype=np.float64)
        if strain is None
        else np.asarray(strain, dtype=float)
    )
    return Frame(
        {
            "strain_engineering": x,
            "stress_engineering": y,
            "time": np.arange(y.size, dtype=np.float64),
            "source_row": np.arange(100, 100 + y.size, dtype=np.float64),
        },
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "time": "s",
            "source_row": "1",
        },
    )


def _run(frame: Frame, **options: object) -> processing.PipelineResult:
    return processing.apply([Step("tensile.yield_drop", options)], frame)


def _scalar(result: processing.PipelineResult, key: str) -> float:
    for scalar in result.scalars:
        if scalar.key == key:
            return scalar.value
    raise AssertionError(f"missing scalar {key}")


def test_detect_events_classifies_full_partial_and_terminal() -> None:
    full = detect_events(np.asarray([0, 10, 20, 10, 15, 20], dtype=float), 0.2, 0.2)
    partial = detect_events(np.asarray([0, 10, 20, 10, 13, 14], dtype=float), 0.2, 0.1)
    terminal = detect_events(np.asarray([0, 10, 20, 10, 11], dtype=float), 0.2, 0.2)

    assert full == [DropEvent(2, 3, 3, 4, 5, "full_recovery", False)]
    assert partial == [DropEvent(2, 3, 3, 4, 5, "partial_recovery", True)]
    assert terminal == [DropEvent(2, 3, 3, None, 4, "terminal_unrecovered", True)]


def test_detect_events_finds_repeated_events_and_uses_last_plateau_peak() -> None:
    events = detect_events(np.asarray([0, 100, 100, 50, 95, 100, 60, 100], dtype=float), 0.2)

    assert len(events) == 2
    assert events[0].peak_index == 2
    assert events[0].kind == "full_recovery"
    assert events[1].peak_index == 5
    assert events[1].kind == "full_recovery"


def test_full_outer_event_absorbs_internal_falls_and_keeps_first_trough() -> None:
    events = detect_events(
        np.asarray([0, 100, 20, 30, 25, 20, 100], dtype=float),
        0.005,
    )

    assert events == [DropEvent(1, 2, 2, 3, 6, "full_recovery", False)]


def test_partial_rebound_small_redrop_is_not_split_without_full_return() -> None:
    events = detect_events(
        np.asarray([0, 100, 50, 70, 65, 72, 68], dtype=float),
        0.2,
        recovery_threshold=0.1,
    )

    assert events == [DropEvent(1, 2, 2, 3, 5, "partial_recovery", True)]


def test_outer_full_event_recovery_starts_after_later_trough() -> None:
    events = detect_events(
        np.asarray([0, 100, 50, 70, 40, 90, 100], dtype=float),
        0.2,
        recovery_threshold=0.1,
    )

    assert events == [DropEvent(1, 2, 4, 5, 6, "full_recovery", False)]


def test_events_keep_diagnoses_reversed_and_duplicate_strain() -> None:
    frame = _frame([0, 100, 50, 80, 90], [0, 1, 1, 0.5, 0.4])
    result = _run(frame, scope="events", method="keep", threshold=0.2)

    np.testing.assert_array_equal(
        result.frame.columns["stress_engineering"], frame.columns["stress_engineering"]
    )
    assert any("역전" in note and "중복" in note for note in result.notes)


def test_events_with_nonzero_domain_offset_report_absolute_rows() -> None:
    frame = _frame([0, 10, 20, 100, 50, 90, 100, 80])
    result = _run(
        frame,
        scope="events",
        range_start=2,
        range_end=6,
        method="keep",
        threshold=0.2,
    )

    assert any("peak index 3" in note and "end index 6" in note for note in result.notes)


def test_monotone_event_expansion_merges_overlapping_intervals() -> None:
    intervals, notes = _expand_event_intervals(
        [(1, 2), (3, 4)],
        domain_start=0,
        domain_end=5,
        strain=np.arange(6, dtype=float),
        original=np.asarray([0, 10, 1, 2, 3, 4], dtype=float),
        method="envelope",
        min_slope=5,
        slope_constraint="none",
    )

    assert intervals == [(1, 5)]
    assert any("최소 확장" in note for note in notes)


def test_protected_terminal_fall_is_allowed_only_when_both_boundary_values_are_unchanged() -> (
    None
):
    strain = np.arange(6, dtype=float)
    original = np.asarray([0, 100, 50, 75, 90, 60], dtype=float)
    intervals, notes = _expand_event_intervals(
        [(1, 4)],
        domain_start=0,
        domain_end=5,
        strain=strain,
        original=original,
        method="lower_envelope",
        min_slope=0,
        slope_constraint="none",
        protected_intervals=[(4, 5)],
    )

    assert intervals == [(1, 4)]
    assert any("기존 하강" in note and "index 4~5" in note for note in notes)

    with pytest.raises(ProcessingError, match="보호 행"):
        _expand_event_intervals(
            [(1, 4)],
            domain_start=0,
            domain_end=5,
            strain=strain,
            original=original,
            method="envelope",
            min_slope=0,
            slope_constraint="none",
            protected_intervals=[(4, 5)],
        )


def test_auto_lower_envelope_uses_fixed_rules_and_records_effective_options() -> None:
    base = _frame([0, 100, 50, 75, 90, 60])
    frame = Frame(
        {
            "eps": base.columns["strain_engineering"].copy(),
            "sig": base.columns["stress_engineering"].copy(),
            "time": base.columns["time"].copy(),
            "source_row": base.columns["source_row"].copy(),
        },
        {"eps": "1", "sig": "Pa", "time": "s", "source_row": "1"},
    )
    original_columns = {key: values.copy() for key, values in frame.columns.items()}
    requested = {
        "method": AUTO_LOWER_ENVELOPE_METHOD,
        "scope": "full",
        "threshold": -1.0,
        "recovery_threshold": 2.0,
        "min_reference_fraction": -2.0,
        "min_slope": -3.0,
        "terminal_action": "hold",
        "range_start": -2.0,
        "range_end": -1.0,
        "plateau_start": 0.03,
        "plateau_end": 0.01,
        "plateau_stress": 0.0,
        "slope_constraint": "nondecreasing",
        "strain": "eps",
        "stress": "sig",
    }
    saved_recipe = json.dumps(
        {"plugin": "tensile.yield_drop", "options": requested}, sort_keys=True
    )
    first_request = json.loads(saved_recipe)["options"]
    automatic = _run(frame, **first_request)
    repeated = _run(frame, **json.loads(saved_recipe)["options"])
    explicit = _run(
        frame,
        scope="events",
        method="lower_envelope",
        threshold=0.005,
        recovery_threshold=0.005,
        min_reference_fraction=0.05,
        min_slope=0.0,
        terminal_action="keep",
        strain="eps",
        stress="sig",
    )

    effective = {
        "scope": "events",
        "method": AUTO_LOWER_ENVELOPE_METHOD,
        "threshold": 0.005,
        "recovery_threshold": 0.005,
        "min_reference_fraction": 0.05,
        "min_slope": 0.0,
        "terminal_action": "keep",
        "strain": "eps",
        "stress": "sig",
    }
    assert automatic.stages[0].options == effective
    assert repeated.stages[0].options == effective
    assert automatic.stages[0].notes == repeated.stages[0].notes
    assert automatic.stages[0].scalars == repeated.stages[0].scalars
    np.testing.assert_array_equal(
        automatic.frame.columns["sig"], repeated.frame.columns["sig"]
    )
    np.testing.assert_array_equal(
        automatic.frame.columns["sig"], explicit.frame.columns["sig"]
    )
    for key in ("eps", "time", "source_row"):
        np.testing.assert_array_equal(automatic.frame.columns[key], original_columns[key])
        np.testing.assert_array_equal(frame.columns[key], original_columns[key])
    np.testing.assert_array_equal(frame.columns["sig"], original_columns["sig"])
    for key in (
        "event_count",
        "recovered_count",
        "partial_count",
        "open_partial_count",
        "unrecovered_count",
        "yield_drop_points",
        "remaining_drop_count",
        "fit_r_squared",
        "fit_rmse",
    ):
        assert _scalar(automatic, key) == pytest.approx(_scalar(explicit, key))
    assert _scalar(automatic, "auto_edit_applied") == 1
    assert _scalar(automatic, "auto_review_required") == 1
    assert _scalar(automatic, "auto_terminal_only") == 0
    assert any(
        "scope, threshold" in note and "range_start" in note for note in automatic.notes
    )
    assert any("미회복 말단 구간" in note for note in automatic.notes)
    assert not {
        "range_start",
        "range_end",
        "plateau_start",
        "plateau_end",
        "plateau_stress",
    } & set(automatic.stages[0].options)


def test_auto_lower_envelope_distinguishes_no_event_from_terminal_only() -> None:
    no_event_frame = _frame([10, 11, 12, 13])
    no_event = _run(no_event_frame, method=AUTO_LOWER_ENVELOPE_METHOD)
    np.testing.assert_array_equal(
        no_event.frame.columns["stress_engineering"],
        no_event_frame.columns["stress_engineering"],
    )
    assert _scalar(no_event, "auto_edit_applied") == 0
    assert _scalar(no_event, "auto_review_required") == 0
    assert _scalar(no_event, "auto_terminal_only") == 0
    assert any("v1 기준의 편집 대상 사건이 없어" in note for note in no_event.notes)

    terminal_frame = _frame([0, 100, 90, 80])
    terminal_only = _run(terminal_frame, method=AUTO_LOWER_ENVELOPE_METHOD)
    np.testing.assert_array_equal(
        terminal_only.frame.columns["stress_engineering"],
        terminal_frame.columns["stress_engineering"],
    )
    assert _scalar(terminal_only, "auto_edit_applied") == 0
    assert _scalar(terminal_only, "auto_review_required") == 1
    assert _scalar(terminal_only, "auto_terminal_only") == 1
    assert any("사람의 검토" in note and "하항복 곡선" in note for note in terminal_only.notes)


def test_auto_lower_envelope_flags_open_partial_at_observation_end_for_review() -> None:
    frame = _frame([0, 100, 50, 60, 70])
    original_channels = {key: values.copy() for key, values in frame.columns.items()}
    result = _run(frame, method=AUTO_LOWER_ENVELOPE_METHOD)

    assert _scalar(result, "auto_edit_applied") == 1
    assert _scalar(result, "auto_review_required") == 1
    assert _scalar(result, "auto_terminal_only") == 0
    assert _scalar(result, "open_partial_count") == 1
    assert any("관측 종료까지 열려" in note and "사람의 검토" in note for note in result.notes)
    for key in ("strain_engineering", "time", "source_row"):
        np.testing.assert_array_equal(result.frame.columns[key], original_channels[key])
        np.testing.assert_array_equal(frame.columns[key], original_channels[key])
    np.testing.assert_array_equal(
        frame.columns["stress_engineering"], original_channels["stress_engineering"]
    )


def test_auto_lower_envelope_rejects_non_increasing_strain_without_sorting() -> None:
    frame = _frame([0, 100, 50, 80], [0, 1, 1, 2])
    original_x = frame.columns["strain_engineering"].copy()
    original_y = frame.columns["stress_engineering"].copy()

    with pytest.raises(ProcessingError, match="원래 측정 순서를 확인"):
        _run(frame, method=AUTO_LOWER_ENVELOPE_METHOD)

    np.testing.assert_array_equal(frame.columns["strain_engineering"], original_x)
    np.testing.assert_array_equal(frame.columns["stress_engineering"], original_y)


def test_scoped_edit_holds_when_selected_strain_is_not_strict() -> None:
    frame = _frame([0, 100, 50, 80], [0, 1, 1, 2])

    with pytest.raises(ProcessingError, match="단조 증가"):
        _run(frame, scope="events", method="envelope", threshold=0.2)


def test_range_changes_only_selected_rows_and_keeps_all_other_channels_bitwise() -> None:
    frame = _frame([0, 100, 50, 80, 70, 90, 100, 80], strain=list(range(8)))
    result = _run(
        frame,
        scope="range",
        range_start=1,
        range_end=5,
        method="median_plateau",
    )
    fixed = result.frame.columns["stress_engineering"]
    original = frame.columns["stress_engineering"]
    np.testing.assert_array_equal(fixed[[0, 6, 7]], original[[0, 6, 7]])
    for key in ("strain_engineering", "time", "source_row"):
        np.testing.assert_array_equal(result.frame.columns[key], frame.columns[key])
    assert any("index 1~5" in note and "변형률 1~5" in note for note in result.notes)


@pytest.mark.parametrize(
    "method", ("lower_envelope", "linear", "least_squares", "robust_linear")
)
def test_scoped_methods_are_deterministic_and_finite(method: str) -> None:
    frame = _frame([0, 100, 50, 90, 80, 110, 100, 120])
    options: dict[str, object] = {
        "scope": "range",
        "range_start": 1,
        "range_end": 6,
        "method": method,
        "slope_constraint": "none",
    }
    first = _run(frame, **options)
    second = _run(frame, **options)
    np.testing.assert_array_equal(
        first.frame.columns["stress_engineering"], second.frame.columns["stress_engineering"]
    )
    assert np.all(np.isfinite(first.frame.columns["stress_engineering"]))
    assert np.isfinite(_scalar(first, "fit_r_squared"))
    assert np.isfinite(_scalar(first, "fit_rmse"))


def test_envelope_and_lower_envelope_preserve_their_bounds_and_min_slope() -> None:
    frame = _frame([0, 100, 50, 90, 80, 110, 100])
    for method in ("envelope", "lower_envelope"):
        result = _run(
            frame,
            scope="range",
            range_start=1,
            range_end=5,
            method=method,
            min_slope=5,
        )
        fixed = result.frame.columns["stress_engineering"][1:6]
        original = frame.columns["stress_engineering"][1:6]
        if method == "envelope":
            assert np.all(fixed >= original)
        else:
            assert np.all(fixed <= original)
        assert np.all(np.diff(fixed) >= 5)


def test_non_decreasing_regression_constraint_has_direct_slope_floor() -> None:
    frame = _frame([100, 90, 80, 70])
    for method in ("least_squares", "robust_linear"):
        result = _run(
            frame,
            scope="range",
            range_start=0,
            range_end=3,
            method=method,
            slope_constraint="nondecreasing",
            min_slope=2,
        )
        assert np.all(np.diff(result.frame.columns["stress_engineering"]) >= 2)


def test_endpoint_line_rejects_impossible_slope_constraint() -> None:
    with pytest.raises(ProcessingError, match="양끝 직선"):
        _run(
            _frame([100, 90, 80]),
            scope="range",
            range_start=0,
            range_end=2,
            method="linear",
            slope_constraint="nondecreasing",
        )


def test_events_terminal_hold_or_keep() -> None:
    frame = _frame([0, 100, 50, 55, 52, 50])
    with pytest.raises(ProcessingError, match="terminal_unrecovered"):
        _run(frame, scope="events", method="median_plateau", threshold=0.2)

    result = _run(
        frame,
        scope="events",
        method="median_plateau",
        threshold=0.2,
        terminal_action="keep",
    )
    # The terminal fall remains bit-identical under terminal_action=keep.
    np.testing.assert_array_equal(
        result.frame.columns["stress_engineering"][4:], frame.columns["stress_engineering"][4:]
    )
    assert _scalar(result, "unrecovered_count") == 1


def test_terminal_keep_holds_when_recovered_and_terminal_events_share_peak() -> None:
    frame = _frame([0, 100, 70, 60, 80, 0])
    with pytest.raises(ProcessingError, match="보호 영역"):
        _run(
            frame,
            scope="events",
            method="median_plateau",
            threshold=0.2,
            recovery_threshold=0.05,
            terminal_action="keep",
        )


def test_range_cut_uses_first_selected_event_peak_and_cuts_every_channel() -> None:
    frame = _frame([0, 10, 20, 100, 50, 90, 100, 80])
    result = _run(
        frame,
        scope="range",
        range_start=3,
        range_end=7,
        method="cut",
        threshold=0.2,
    )
    assert result.frame.length() == 4
    for key, values in frame.columns.items():
        np.testing.assert_array_equal(result.frame.columns[key], values[:4])


def test_range_disconnected_domain_is_held_and_new_methods_reject_full_scope() -> None:
    frame = _frame([0, 100, 50, 80, 70], [0, 1, 4, 2, 5])
    with pytest.raises(ProcessingError, match="disconnected-domain"):
        _run(frame, scope="range", range_start=0.5, range_end=2.0, method="keep")
    with pytest.raises(ProcessingError, match="scope='full'"):
        _run(_frame([0, 100, 50]), method="linear")


def test_nonfinite_and_degenerate_regression_inputs_are_rejected() -> None:
    with pytest.raises(ProcessingError, match="유한하지"):
        _run(_frame([0, float("nan"), 1]), method="keep")
    with pytest.raises(ProcessingError, match="퇴화"):
        _fit_linear(
            np.asarray([1.0, 1.0]),
            np.asarray([1.0, 2.0]),
            slope_constraint="none",
        )
