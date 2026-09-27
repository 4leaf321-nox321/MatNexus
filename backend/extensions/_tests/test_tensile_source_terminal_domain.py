"""Standalone contracts for the atomic source-terminal domain processor."""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing
from matcore.processing import Frame, ProcessingError

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()
source_terminal_domain = importlib.import_module(
    "matnexus_ext.tensile_extras.source_terminal_domain"
)
terminal_domain = importlib.import_module("matnexus_ext.tensile_extras.terminal_domain")


def _frame(
    stress: object,
    *,
    time: object | None = None,
    force_name: str = "force",
    strain_name: str = "strain_engineering",
    stress_name: str = "stress_engineering",
) -> Frame:
    values = np.asarray(stress, dtype=np.float64)
    count = len(values)
    columns: dict[str, np.ndarray] = {
        "displacement": np.arange(count, dtype=np.float64),
        force_name: values / 2.0,
        strain_name: np.linspace(0.0, 1.0, count),
        stress_name: values,
        "source_row": np.arange(100, 100 + count, dtype=np.float64),
    }
    units = {
        "displacement": "m",
        force_name: "N",
        strain_name: "1",
        stress_name: "Pa",
        "source_row": "1",
    }
    if time is not None:
        columns["time"] = np.asarray(time, dtype=np.float64)
        units["time"] = "s"
    return Frame(columns, units)


def _scalar_values(result: object) -> dict[str, float]:
    return {item.key: item.value for item in result.scalars}  # type: ignore[attr-defined]


def _terminal_options(policy: str = terminal_domain.AUTO_POLICY) -> dict[str, object]:
    return {"policy": policy}


def test_public_options_have_no_spoofable_peak_or_terminal_result_fields() -> None:
    for key in (
        "peak_index",
        "peak_stress",
        "terminal_end_index",
        "terminal_decision_code",
    ):
        with pytest.raises(ProcessingError, match=key):
            source_terminal_domain.prepare_options({key: 1})

    prepared = source_terminal_domain.prepare_options({})
    assert prepared["policy"] == terminal_domain.AUTO_POLICY
    assert prepared["strain"] == terminal_domain.DEFAULT_STRAIN
    assert prepared["stress"] == terminal_domain.DEFAULT_STRESS
    assert prepared["time"] == terminal_domain.DEFAULT_TIME


def test_negative_preload_is_recomputed_from_the_full_source_frame() -> None:
    frame = _frame([-5.0, -2.0, 0.0, 4.0, 10.0, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5])
    before = {key: values.copy() for key, values in frame.columns.items()}

    result = source_terminal_domain.source_terminal_domain(frame, {})
    values = _scalar_values(result)

    assert result.frame is frame
    assert values["source_terminal_guard_code"] == 1.0
    assert values["source_terminal_guard_peak_index"] == 4.0
    assert values["terminal_domain_decision_code"] == 0.0
    for key, expected in before.items():
        np.testing.assert_array_equal(frame.columns[key], expected)


def test_custom_force_column_is_replayed_as_a_public_column_option() -> None:
    frame = _frame(
        [-5.0, -2.0, 0.0, 4.0, 10.0, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5],
        force_name="load_n",
    )

    result = source_terminal_domain.source_terminal_domain(frame, {"force": "load_n"})

    assert result.frame is frame
    assert result.effective_options is not None
    assert result.effective_options["force"] == "load_n"
    replay = source_terminal_domain.source_terminal_domain(
        frame, dict(result.effective_options)
    )
    assert replay.effective_options == result.effective_options


def test_manual_end_before_raw_peak_is_held_without_mutating_input() -> None:
    frame = _frame([-5.0, -2.0, 0.0, 10.0, 9.0, 8.0])
    before = {key: values.copy() for key, values in frame.columns.items()}
    before_units = dict(frame.units)

    with pytest.raises(ProcessingError, match="source peak를 보존하지 않았습니다"):
        source_terminal_domain.source_terminal_domain(
            frame,
            {"policy": terminal_domain.MANUAL_POLICY, "end_index": 2},
        )

    assert frame.units == before_units
    for key, expected in before.items():
        np.testing.assert_array_equal(frame.columns[key], expected)


def test_custom_force_stress_and_strain_columns_replay_with_terminal_scalars() -> None:
    stress = np.asarray([-5.0, -2.0, 0.0, *([10.0] * 7), 0.0])
    frame = _frame(
        stress,
        force_name="load_n",
        stress_name="sigma_pa",
        strain_name="epsilon_eng",
    )
    options = {
        "policy": terminal_domain.AUTO_POLICY,
        "force": "load_n",
        "stress": "sigma_pa",
        "strain": "epsilon_eng",
    }

    direct = terminal_domain.terminal_domain(
        frame,
        {
            "policy": terminal_domain.AUTO_POLICY,
            "stress": "sigma_pa",
            "strain": "epsilon_eng",
        },
    )
    result = source_terminal_domain.source_terminal_domain(frame, options)
    direct_values = {
        item.key: item.value
        for item in direct.scalars
        if item.key.startswith("terminal_domain_")
    }
    result_values = _scalar_values(result)

    assert {key: result_values[key] for key in direct_values} == direct_values
    assert result.effective_options is not None
    assert result.effective_options["force"] == "load_n"
    assert result.effective_options["stress"] == "sigma_pa"
    assert result.effective_options["strain"] == "epsilon_eng"

    replay = source_terminal_domain.source_terminal_domain(
        frame, dict(result.effective_options)
    )
    assert replay.effective_options == result.effective_options
    assert _scalar_values(replay) == result_values


def test_long_lower_stable_plateau_is_allowed_when_gradual_check_is_false() -> None:
    stress = np.asarray([-5.0, -2.0, 0.0, 10.0, *([6.0] * 97)])
    frame = _frame(stress)

    result = source_terminal_domain.source_terminal_domain(frame, {})
    values = _scalar_values(result)

    assert result.frame is frame
    assert values["terminal_domain_decision_code"] == 0.0
    assert values["source_terminal_guard_gradual_unresolved"] == 0.0


def test_code_zero_with_true_gradual_tail_is_held_explicitly() -> None:
    stress = np.concatenate(
        (np.asarray([-5.0, -2.0, 0.0]), np.full(86, 10.0), np.linspace(10.0, 8.0, 12))
    )
    frame = _frame(stress)

    with pytest.raises(ProcessingError, match="gradual_tail_unresolved"):
        source_terminal_domain.source_terminal_domain(frame, {})


def test_selected_prefix_matches_terminal_domain_on_every_column() -> None:
    stress = np.asarray([-5.0, -2.0, 0.0, *([10.0] * 7), 0.0])
    frame = _frame(stress, time=np.arange(len(stress), dtype=np.float64))
    before = {key: values.copy() for key, values in frame.columns.items()}

    result = source_terminal_domain.source_terminal_domain(frame, {})
    values = _scalar_values(result)
    end = int(values["terminal_domain_end_index"])

    assert values["terminal_domain_decision_code"] == 1.0
    assert result.frame is not frame
    assert result.frame.length() == end + 1
    for key, expected in before.items():
        np.testing.assert_array_equal(frame.columns[key], expected)
        np.testing.assert_array_equal(result.frame.columns[key], expected[: end + 1])


@pytest.mark.parametrize(
    ("options", "expected_code", "stress", "time"),
    [
        (
            {"policy": terminal_domain.AUTO_POLICY},
            1.0,
            np.asarray([-5.0, -2.0, 0.0, *([10.0] * 7), 0.0]),
            None,
        ),
        (
            {"policy": terminal_domain.PROGRESSIVE_POLICY},
            3.0,
            np.where(
                np.linspace(0.0, 1.0, 501) <= 0.84,
                100.0 + 2.0 * np.linspace(0.0, 1.0, 501),
                100.0 + 2.0 * 0.84 - 100.0 * (np.linspace(0.0, 1.0, 501) - 0.84),
            ),
            np.linspace(0.0, 1.0, 501),
        ),
        (
            {"policy": terminal_domain.MANUAL_POLICY, "end_index": 5},
            2.0,
            np.asarray([-5.0, -2.0, 0.0, 10.0, 9.0, 8.0, 7.0, 6.0]),
            None,
        ),
    ],
)
def test_atomic_result_matches_direct_terminal_domain_for_each_selection_code(
    options: dict[str, object],
    expected_code: float,
    stress: np.ndarray,
    time: np.ndarray | None,
) -> None:
    frame = _frame(stress, time=time)
    direct = terminal_domain.terminal_domain(frame, options)
    atomic = source_terminal_domain.source_terminal_domain(frame, options)

    direct_values = {
        item.key: item.value
        for item in direct.scalars
        if item.key.startswith("terminal_domain_")
    }
    atomic_values = _scalar_values(atomic)
    assert atomic_values["terminal_domain_decision_code"] == expected_code
    assert {key: atomic_values[key] for key in direct_values} == direct_values
    expected_effective = dict(direct.effective_options or {})
    expected_effective["force"] = "force"
    assert atomic.effective_options == expected_effective
    assert atomic.frame.length() == direct.frame.length()
    for key in frame.columns:
        np.testing.assert_array_equal(atomic.frame.columns[key], direct.frame.columns[key])

    replay = source_terminal_domain.source_terminal_domain(
        frame, dict(atomic.effective_options or {})
    )
    assert replay.effective_options == atomic.effective_options
    assert _scalar_values(replay) == atomic_values


def test_guard_scalars_are_added_without_dropping_terminal_domain_scalars() -> None:
    frame = _frame(np.asarray([-5.0, -2.0, 0.0, 10.0, 9.0, 8.0, 7.0, 6.0]))

    result = source_terminal_domain.source_terminal_domain(
        frame, {"policy": terminal_domain.MANUAL_POLICY, "end_index": 5}
    )
    keys = set(_scalar_values(result))

    assert {
        "terminal_domain_end_index",
        "terminal_domain_decision_code",
        "terminal_domain_input_points",
        "source_terminal_guard_code",
        "source_terminal_guard_peak_index",
        "source_terminal_guard_end_index",
        "source_terminal_guard_decision_code",
        "source_terminal_guard_gradual_unresolved",
    } <= keys
