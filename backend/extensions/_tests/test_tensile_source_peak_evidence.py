"""Contracts for the retained-tail source peak and full support guard."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Scalar, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    strain: list[float],
    stress: list[float],
    *,
    evidence: str = "source_row",
) -> Frame:
    stress_values = np.asarray(stress, dtype=np.float64)
    count = len(stress)
    columns: dict[str, np.ndarray] = {
        "displacement": np.arange(count, dtype=np.float64),
        "force": stress_values / 2.0,
        "strain_engineering": np.asarray(strain, dtype=np.float64),
        "stress_engineering": stress_values,
        "time": np.arange(count, dtype=np.float64),
    }
    units = {
        "displacement": "m",
        "force": "N",
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "time": "s",
    }
    if evidence == "source_row":
        columns[evidence] = np.arange(100, 100 + count, dtype=np.float64)
        units[evidence] = "1"
    else:
        columns["source_data_row"] = np.arange(1, count + 1, dtype=np.float64)
        columns["source_physical_line"] = np.arange(2, count + 2, dtype=np.float64)
        units["source_data_row"] = "1"
        units["source_physical_line"] = "1"
    return Frame(columns, units)


def _values(frame: Frame) -> dict[str, np.ndarray]:
    return {key: value.copy() for key, value in frame.columns.items()}


def _scalar_values(result: processing.PipelineResult) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in result.scalars}


def test_source_peak_evidence_keeps_peak_before_tail_bit_exact() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015, 0.03], [1.0, 4.0, 8.0, 7.0, 6.0])
    before = _values(frame)

    result = apply([Step("tensile.source_peak_evidence_v1", {})], frame)
    stage = result.stages[-1]

    assert stage.frame is frame
    for key, expected in before.items():
        np.testing.assert_array_equal(stage.frame.columns[key], expected)
    assert _scalar_values(result) == {
        "source_peak_index": 2.0,
        "source_peak_strain": 0.02,
        "source_peak_stress": 8.0,
        "source_peak_order_evidence_code": 1.0,
        "source_peak_force_peak_match_code": 1.0,
    }


def test_source_peak_evidence_accepts_source_data_and_physical_line_pair() -> None:
    frame = _frame(
        [0.0, 0.01, 0.02, 0.015, 0.03],
        [1.0, 4.0, 8.0, 7.0, 6.0],
        evidence="source_data_row",
    )

    stage = apply([Step("tensile.source_peak_evidence_v1", {})], frame).stages[-1]

    assert stage.frame is frame
    assert "source_data_row" in " ".join(stage.notes)
    assert "source_physical_line" in " ".join(stage.notes)


def test_source_peak_evidence_allows_matched_negative_preload_rows() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.03], [-1.0, 4.0, 8.0, 7.0])

    stage = apply([Step("tensile.source_peak_evidence_v1", {})], frame).stages[-1]

    assert stage.frame is frame
    assert {item.key: item.value for item in stage.scalars}["source_peak_index"] == 2.0


def test_source_peak_evidence_fails_closed_without_row_evidence() -> None:
    frame = _frame([0.0, 0.01, 0.02], [1.0, 4.0, 8.0])
    del frame.columns["source_row"]
    del frame.units["source_row"]

    with pytest.raises(ProcessingError, match="취득 순서 증거"):
        apply([Step("tensile.source_peak_evidence_v1", {})], frame)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        ("evidence", "엄격히 증가"),
        ("force_peak", r"첫 최대 위치|양의 일정 비례"),
        ("ratio", "양의 일정 비례"),
    ],
)
def test_source_peak_evidence_rejects_bad_evidence_or_peak_mismatch(
    mutate: str, message: str
) -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.03], [1.0, 4.0, 8.0, 7.0])
    if mutate == "evidence":
        frame.columns["source_row"] = np.asarray([100.0, 101.0, 103.0, 102.0])
    elif mutate == "force_peak":
        frame.columns["force"] = np.asarray([0.5, 2.0, 3.5, 4.0])
    else:
        frame.columns["force"] = np.asarray([0.5, 2.0, 4.0, 3.0])

    with pytest.raises(ProcessingError, match=message):
        apply([Step("tensile.source_peak_evidence_v1", {})], frame)


def test_source_support_order_full_uses_prefix_for_order_but_returns_full_frame() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03, 0.035], [1.0, 4.0, 8.0, 9.0, 7.0, 6.0])
    before = _values(frame)
    steps = [
        Step("tensile.source_peak_evidence_v1", {}),
        Step(
            "tensile.source_support_order_full_v1",
            {
                "proof_left_index": 1,
                "proof_right_index": 2,
                "proof_strain": 0.015,
            },
        ),
    ]

    result = apply(steps, frame)
    stage = result.stages[-1]

    assert stage.frame is frame
    for key, expected in before.items():
        np.testing.assert_array_equal(stage.frame.columns[key], expected)
    values = _scalar_values(result)
    assert values["source_support_order_code"] == 1.0
    assert values["source_support_peak_index"] == 3.0


def test_source_support_order_full_detects_proof_to_peak_backstep() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.014, 0.025, 0.03], [1.0, 4.0, 8.0, 7.0, 9.0, 8.0])
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
    }

    with pytest.raises(ProcessingError, match=r"좌표창|엄격히 증가"):
        apply([Step("tensile.source_support_order_full_v1", options)], frame)


@pytest.mark.parametrize(
    "spoofed_key",
    ["peak_index", "peak_strain", "order_evidence_code", "force_peak_match_code"],
)
def test_source_support_order_full_rejects_spoofed_peak_or_status_options(
    spoofed_key: str,
) -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03], [1.0, 4.0, 8.0, 9.0, 7.0])
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
        spoofed_key: 2,
    }

    with pytest.raises(ProcessingError, match="알 수 없는 옵션"):
        apply([Step("tensile.source_support_order_full_v1", options)], frame)


def test_source_support_order_full_validates_evidence_in_tail() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03], [1.0, 4.0, 8.0, 9.0, 7.0])
    frame.columns["source_row"][-1] = 99.0
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
    }

    with pytest.raises(ProcessingError, match="엄격히 증가"):
        apply([Step("tensile.source_support_order_full_v1", options)], frame)


def test_source_support_order_full_defaults_to_source_peak_references() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03], [1.0, 4.0, 8.0, 9.0, 7.0])
    given = (
        Scalar("source_proof_left_index", "proof left", 1.0, "1"),
        Scalar("source_proof_right_index", "proof right", 2.0, "1"),
        Scalar("proof_strain", "proof strain", 0.015, "1", "strain"),
    )
    result = apply(
        [
            Step("tensile.source_peak_evidence_v1", {}),
            Step("tensile.source_support_order_full_v1", {}),
        ],
        frame,
        given=given,
    )

    assert result.stages[-1].frame is frame
    assert _scalar_values(result)["source_support_order_code"] == 1.0


def test_source_support_order_full_recomputes_altered_force_evidence() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03], [1.0, 4.0, 8.0, 9.0, 7.0])
    frame.columns["force"] = np.asarray([0.5, 2.0, 4.5, 4.0, 3.5])
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
    }

    with pytest.raises(ProcessingError, match=r"양의 일정 비례|첫 최대 위치"):
        apply([Step("tensile.source_support_order_full_v1", options)], frame)


def test_source_support_order_full_accepts_custom_source_columns() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.025, 0.03], [1.0, 4.0, 8.0, 9.0, 7.0])
    frame.columns["load_custom"] = frame.columns.pop("force")
    frame.units["load_custom"] = frame.units.pop("force")
    frame.columns["eps_custom"] = frame.columns.pop("strain_engineering")
    frame.units["eps_custom"] = frame.units.pop("strain_engineering")
    frame.columns["sigma_custom"] = frame.columns.pop("stress_engineering")
    frame.units["sigma_custom"] = frame.units.pop("stress_engineering")
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
        "force": "load_custom",
        "strain": "eps_custom",
        "stress": "sigma_custom",
    }

    result = apply([Step("tensile.source_support_order_full_v1", options)], frame)

    assert result.stages[-1].frame is frame
    assert _scalar_values(result)["source_support_order_code"] == 1.0


def test_source_support_order_full_uses_first_tied_peak_and_negative_preload() -> None:
    frame = _frame(
        [0.0, 0.01, 0.02, 0.025, 0.03],
        [-1.0, 4.0, 9.0, 9.0, 7.0],
    )
    options = {
        "proof_left_index": 1,
        "proof_right_index": 2,
        "proof_strain": 0.015,
    }

    result = apply([Step("tensile.source_support_order_full_v1", options)], frame)

    values = _scalar_values(result)
    assert values["source_support_order_code"] == 1.0
    assert values["source_support_peak_index"] == 2.0


def test_source_peak_and_full_guard_registrations_are_versioned() -> None:
    peak = registry.get("tensile.source_peak_evidence_v1")
    guard = registry.get("tensile.source_support_order_full_v1")

    assert peak.version == "1"
    assert guard.version == "1"
    assert peak.meta["candidate_only"] is True
    assert guard.meta["candidate_only"] is True
    assert {item.key for item in peak.makes_values} == {
        "source_peak_index",
        "source_peak_strain",
        "source_peak_stress",
        "source_peak_order_evidence_code",
        "source_peak_force_peak_match_code",
    }
