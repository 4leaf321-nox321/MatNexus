"""Source-event closure never bridges a gap or rewrites its original arrays."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions
from matcore.processing._drop_recovery import DropEvent

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
extensions.load(EXTENSIONS)
composition_module = import_module("matnexus_ext.tensile_extras.lower_composition")


def _full(peak: int, end: int) -> DropEvent:
    return DropEvent(
        peak_index=peak,
        drop_start=peak + 1,
        trough_index=peak + 2,
        recovery_index=peak + 3,
        end_index=end,
        kind="full_recovery",
        end_at_observation_boundary=False,
    )


def _partial(peak: int, end: int, *, open_end: bool = False) -> DropEvent:
    return DropEvent(
        peak_index=peak,
        drop_start=peak + 1,
        trough_index=peak + 2,
        recovery_index=peak + 3,
        end_index=end,
        kind="partial_recovery",
        end_at_observation_boundary=open_end,
    )


def test_closed_partial_and_full_events_connect_at_one_original_row() -> None:
    events = (_partial(136, 1163), _full(1163, 1733))

    closure = composition_module.connected_lower_closure(
        events,
        ((61, 1033),),
        ((0,),),
        root_component=0,
        failed_event=1,
    )

    assert closure is not None
    assert closure.component_indices == (0,)
    assert closure.event_indices == (0, 1)


def test_model_component_cannot_bridge_disconnected_member_events() -> None:
    events = (_full(120, 180), _full(200, 250), _full(150, 170))

    closure = composition_module.connected_lower_closure(
        events,
        ((100, 300),),
        ((0, 1),),
        root_component=0,
        failed_event=2,
    )

    assert closure is None


def test_boundary_open_partial_event_cannot_connect_to_a_closed_event() -> None:
    events = (_partial(100, 200, open_end=True), _full(200, 260))

    closure = composition_module.connected_lower_closure(
        events,
        ((60, 150),),
        ((0,),),
        root_component=0,
        failed_event=1,
    )

    assert closure is None


def test_whole_component_with_a_disconnected_eligible_member_is_held() -> None:
    events = (_full(120, 180), _full(220, 260), _full(180, 200))

    closure = composition_module.connected_lower_closure(
        events,
        ((100, 300),),
        ((0, 1),),
        root_component=0,
        failed_event=2,
    )

    assert closure is None


def test_lower_suffix_minorant_preserves_outer_anchors_and_source() -> None:
    source = np.asarray([1.0, 3.0, 2.0, 5.0, 4.0, 6.0])
    before = source.copy()

    result = composition_module.lower_suffix_minorant(source, left=0, right=5)

    np.testing.assert_array_equal(result, [1.0, 2.0, 2.0, 4.0, 4.0, 6.0])
    assert result[0] == source[0]
    assert result[5] == source[5]
    assert np.all(np.diff(result) >= 0.0)
    assert np.all(result <= source)
    np.testing.assert_array_equal(source, before)


def test_lower_suffix_minorant_rejects_an_infeasible_left_anchor() -> None:
    with pytest.raises(ValueError, match="suffix minimum"):
        composition_module.lower_suffix_minorant(
            np.asarray([1.0, 5.0, 3.0, 4.0]), left=1, right=3
        )


def test_failure_diagnostic_reports_observed_boundary_and_source_row_gap() -> None:
    events = (_partial(68, 583), _full(585, 867))
    stress = np.zeros(868, dtype=np.float64)
    stress[583:586] = 51.5825
    source_rows = np.arange(1000, 1000 + 2 * stress.size, 2, dtype=np.int64)

    diagnostic = composition_module.lower_closure_failure_diagnostic(
        events,
        ((30, 517),),
        ((0,),),
        root_component=0,
        failed_event=1,
        stress=stress,
        source_rows=source_rows,
    )

    assert "closure_diagnostic_scope=observed_root_prior_event_boundary" in diagnostic
    assert "prior_event=0" in diagnostic
    assert "prior_event_interval=68~583" in diagnostic
    assert "failed_event_peak=585" in diagnostic
    assert "boundary_relation=gap" in diagnostic
    assert "observed_index_gap=1" in diagnostic
    assert "observed_boundary_tie=true" in diagnostic
    assert "observed_between_all_equal=true" in diagnostic
    assert "source_row_interval=2166~2170" in diagnostic
    assert "source_row_gap=3" in diagnostic
    assert "source_row_gap_exceeds_observed=true" in diagnostic


def test_failure_diagnostic_does_not_invent_a_tie_for_component_membership() -> None:
    events = (_full(100, 180), _full(220, 260), _full(150, 170))
    stress = np.ones(261, dtype=np.float64)

    diagnostic = composition_module.lower_closure_failure_diagnostic(
        events,
        ((80, 200),),
        ((0, 1),),
        root_component=0,
        failed_event=2,
        stress=stress,
    )

    assert "prior_event=unavailable" in diagnostic
    assert "boundary_relation=unavailable" in diagnostic
    assert "observed_boundary_tie=not_evaluated" in diagnostic
    assert "observed_between_all_equal=not_evaluated" in diagnostic
    assert "source_row_evidence=unavailable" in diagnostic
