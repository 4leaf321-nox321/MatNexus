"""Contract tests for the opt-in acquisition-prefix card boundary."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    strain: list[float],
    stress: list[float],
    *,
    units: dict[str, str] | None = None,
) -> Frame:
    return Frame(
        {
            "displacement": np.arange(len(strain), dtype=np.float64),
            "force": np.asarray(stress, dtype=np.float64),
            "strain_engineering": np.asarray(strain, dtype=np.float64),
            "stress_engineering": np.asarray(stress, dtype=np.float64),
            "source_row": np.arange(100, 100 + len(strain), dtype=np.float64),
        },
        units
        or {
            "displacement": "m",
            "force": "N",
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_row": "1",
        },
    )


def test_prepeak_prefix_keeps_earliest_peak_and_all_columns_without_sorting() -> None:
    # The pinned CD1/M09CPMMA/M12DPMMA corpus is an external 198-test artifact,
    # so repository tests use the same observed failure shape: a later
    # acquisition row returns to an earlier strain after the maximum load.
    frame = _frame([0.0, 0.01, 0.02, 0.015, 0.03], [1.0, 4.0, 8.0, 7.0, 6.0])

    result = apply([Step("tensile.prepeak_prefix", {})], frame)

    stage = result.stages[-1]
    assert stage.plugin == "tensile.prepeak_prefix"
    np.testing.assert_array_equal(stage.frame.columns["strain_engineering"], [0.0, 0.01, 0.02])
    np.testing.assert_array_equal(stage.frame.columns["stress_engineering"], [1.0, 4.0, 8.0])
    np.testing.assert_array_equal(stage.frame.columns["source_row"], [100.0, 101.0, 102.0])
    assert stage.frame.columns["displacement"].tolist() == [0.0, 1.0, 2.0]
    assert stage.frame.columns["force"].tolist() == [1.0, 4.0, 8.0]
    values = {scalar.key: scalar.value for scalar in stage.scalars}
    assert values == {
        "prepeak_prefix_input_points": 5.0,
        "prepeak_prefix_peak_input_index": 2.0,
        "prepeak_prefix_peak_input_strain": 0.02,
        "prepeak_prefix_peak_input_stress": 8.0,
        "prepeak_prefix_removed_points": 2.0,
        "prepeak_prefix_order_evidence_code": 1.0,
        "prepeak_prefix_force_peak_index": 2.0,
        "prepeak_prefix_force_peak_match_code": 1.0,
    }
    assert "네킹이나 파단을 입증" in " ".join(stage.notes)


def test_prepeak_prefix_uses_first_index_for_tied_global_peak() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 9.0])

    stage = apply([Step("tensile.prepeak_prefix", {})], frame).stages[-1]

    assert stage.frame.length() == 3
    values = {scalar.key: scalar.value for scalar in stage.scalars}
    assert values["prepeak_prefix_peak_input_index"] == 2.0
    assert values["prepeak_prefix_removed_points"] == 1.0


def test_prepeak_prefix_reports_missing_order_evidence() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    del frame.columns["source_row"]

    stage = apply([Step("tensile.prepeak_prefix", {})], frame).stages[-1]

    values = {scalar.key: scalar.value for scalar in stage.scalars}
    assert values["prepeak_prefix_order_evidence_code"] == 0.0
    assert "순서 증거 없음" in " ".join(stage.notes)


def test_prepeak_prefix_does_not_assume_missing_force_unit_is_newtons() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    del frame.units["force"]

    stage = apply([Step("tensile.prepeak_prefix", {})], frame).stages[-1]

    values = {scalar.key: scalar.value for scalar in stage.scalars}
    assert values["prepeak_prefix_force_peak_match_code"] == 0.0
    assert "최대공칭응력 후보" in " ".join(stage.notes)


def test_prepeak_prefix_rejects_nonmonotone_order_evidence() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015, 0.03], [1.0, 4.0, 8.0, 7.0, 6.0])
    frame.columns["source_row"] = np.asarray([100.0, 101.0, 103.0, 102.0, 104.0])

    with pytest.raises(ProcessingError, match="엄격히 증가하지 않아"):
        apply([Step("tensile.prepeak_prefix", {})], frame)


def test_prepeak_prefix_rejects_noninteger_order_evidence() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.03], [1.0, 4.0, 8.0, 7.0])
    frame.columns["source_row"] = np.asarray([100.0, 101.5, 102.0, 103.0])

    with pytest.raises(ProcessingError, match="정수가 아닌"):
        apply([Step("tensile.prepeak_prefix", {})], frame)


def test_prepeak_prefix_accepts_source_data_and_physical_row_pair() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    frame.columns["source_data_row"] = np.asarray([1.0, 2.0, 3.0, 4.0])
    frame.columns["source_physical_line"] = np.asarray([2.0, 3.0, 4.0, 5.0])
    frame.units["source_data_row"] = "1"
    frame.units["source_physical_line"] = "1"
    del frame.columns["source_row"]
    del frame.units["source_row"]

    stage = apply([Step("tensile.prepeak_prefix", {})], frame).stages[-1]

    np.testing.assert_array_equal(stage.frame.columns["source_data_row"], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(stage.frame.columns["source_physical_line"], [2.0, 3.0, 4.0])
    assert "source_data_row" in " ".join(stage.notes)
    assert "source_physical_line" in " ".join(stage.notes)


@pytest.mark.parametrize("column", ["source_data_row", "source_physical_line"])
def test_prepeak_prefix_rejects_single_source_row_pair_column(column: str) -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    frame.columns[column] = np.asarray([1.0, 2.0, 3.0, 4.0])
    frame.units[column] = "1"

    with pytest.raises(ProcessingError, match="두 열을 함께"):
        apply([Step("tensile.prepeak_prefix", {})], frame)


@pytest.mark.parametrize(
    ("data_unit", "physical_unit", "remove_physical", "message"),
    [
        ("?", None, True, "단위는 '1'"),
        ("?", "1", False, "단위는 '1'"),
        ("mm", "mm", False, "단위는 '1'"),
    ],
)
def test_prepeak_prefix_rejects_unusable_source_pair_units(
    data_unit: str, physical_unit: str | None, remove_physical: bool, message: str
) -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    frame.columns["source_data_row"] = np.asarray([1.0, 2.0, 3.0, 4.0])
    frame.columns["source_physical_line"] = np.asarray([2.0, 3.0, 4.0, 5.0])
    frame.units["source_data_row"] = data_unit
    frame.units["source_physical_line"] = physical_unit
    if remove_physical:
        del frame.columns["source_physical_line"]
        del frame.units["source_physical_line"]

    with pytest.raises(ProcessingError, match=message):
        apply([Step("tensile.prepeak_prefix", {})], frame)


@pytest.mark.parametrize(
    ("data_row", "physical_line", "message"),
    [
        ([1.0, 3.0, 2.0, 4.0], [2.0, 4.0, 3.0, 5.0], "엄격히 증가"),
        ([1.0, 2.0, 2.0, 4.0], [2.0, 3.0, 3.0, 5.0], "엄격히 증가"),
        ([1.0, 2.5, 3.0, 4.0], [2.0, 3.0, 4.0, 5.0], "정수가 아닌"),
        ([1.0, 2.0, 3.0, 4.0], [2.0, 3.0, 5.0, 6.0], "대응 차이"),
        ([1.0, 2.0, 4.0, 5.0], [2.0, 3.0, 5.0, 6.0], "1부터 연속"),
        ([0.0, 1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0], "1 이상"),
        ([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0], "source_physical_line.*source_data_row"),
        ([2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0], "source_physical_line.*source_data_row"),
    ],
)
def test_prepeak_prefix_rejects_invalid_source_row_pair(
    data_row: list[float], physical_line: list[float], message: str
) -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.015], [1.0, 5.0, 9.0, 8.0])
    frame.columns["source_data_row"] = np.asarray(data_row)
    frame.columns["source_physical_line"] = np.asarray(physical_line)
    frame.units["source_data_row"] = "1"
    frame.units["source_physical_line"] = "1"

    with pytest.raises(ProcessingError, match=message):
        apply([Step("tensile.prepeak_prefix", {})], frame)


def test_prepeak_prefix_rejects_force_peak_mismatch() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.03], [1.0, 4.0, 8.0, 7.0])
    frame.columns["force"] = np.asarray([1.0, 4.0, 7.0, 8.0])

    with pytest.raises(ProcessingError, match="원하중과 공칭응력의 최대 위치"):
        apply([Step("tensile.prepeak_prefix", {})], frame)


def test_prepeak_prefix_rejects_nonproportional_force_and_stress() -> None:
    frame = _frame([0.0, 0.01, 0.02, 0.03], [1.0, 4.0, 8.0, 7.0])
    frame.columns["force"] = np.asarray([1.0, 4.0, 8.0, 6.0])

    with pytest.raises(ProcessingError, match="양의 일정 비례"):
        apply([Step("tensile.prepeak_prefix", {})], frame)


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (_frame([0.0], [1.0]), "최소 2개"),
        (_frame([0.0, 0.01], [3.0, 2.0]), "첫 원행"),
        (_frame([0.0, 0.01], [-3.0, -2.0]), "양수가 아닙니다"),
        (
            _frame(
                [0.0, 0.01],
                [1.0, 2.0],
                units={"strain_engineering": "%", "stress_engineering": "Pa"},
            ),
            "단위는 '1'",
        ),
    ],
)
def test_prepeak_prefix_rejects_unsupported_inputs(frame: Frame, message: str) -> None:
    with pytest.raises(ProcessingError, match=message):
        apply([Step("tensile.prepeak_prefix", {})], frame)


def test_prepeak_prefix_rejects_mismatched_or_nonfinite_columns() -> None:
    mismatched = _frame([0.0, 0.01], [1.0, 2.0])
    mismatched.columns["source_row"] = np.asarray([1.0])
    with pytest.raises(ProcessingError, match="점 수가 맞지 않습니다"):
        apply([Step("tensile.prepeak_prefix", {})], mismatched)

    nonfinite = _frame([0.0, 0.01], [1.0, 2.0])
    nonfinite.columns["force"][1] = np.nan
    with pytest.raises(ProcessingError, match="유한하지 않은"):
        apply([Step("tensile.prepeak_prefix", {})], nonfinite)


def test_prepeak_prefix_registration_declares_opt_in_uniform_card_scope() -> None:
    plugin = registry.get("tensile.prepeak_prefix")

    assert plugin.version == "1"
    assert plugin.order == 18
    assert plugin.meta["scope"] == "uniform_true_plastic_card"
    assert plugin.meta["candidate_only"] is True
    keys = {item.key for item in plugin.makes_values}
    assert all(len(key) <= 50 for key in keys)
