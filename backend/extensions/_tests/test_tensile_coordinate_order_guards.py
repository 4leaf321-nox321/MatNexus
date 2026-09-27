"""Focused contracts for the pre-sort tensile coordinate guards."""

from __future__ import annotations

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step, apply

EXTENSIONS = __import__("pathlib").Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()


def _source_frame(strain: list[float]) -> Frame:
    count = len(strain)
    values = np.asarray(strain, dtype=np.float64)
    return Frame(
        {
            "strain_engineering": values,
            "stress_engineering": np.linspace(1.0e6, 3.0e6, count),
            "source_row": np.arange(100, 100 + count, dtype=np.float64),
        },
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_row": "1",
        },
    )


def _source_guard(frame: Frame, **overrides: object) -> processing.PipelineResult:
    options: dict[str, object] = {
        "proof_left_index": 2,
        "proof_right_index": 3,
        "proof_strain": 0.001,
        "peak_index": frame.length() - 1,
        "peak_strain": float(frame.columns["strain_engineering"][-1]),
        "order_evidence_code": 1,
        "force_peak_match_code": 1,
        **overrides,
    }
    return apply([Step("tensile.source_support_order_guard", options)], frame)


def _plastic_frame(
    x: list[float],
    source: list[float],
    *,
    source_name: str = "source_row",
    units: dict[str, str] | None = None,
) -> Frame:
    return Frame(
        {
            "strain_true_plastic": np.asarray(x, dtype=np.float64),
            "stress_true": np.linspace(100.0e6, 140.0e6, len(x)),
            source_name: np.asarray(source, dtype=np.float64),
        },
        units
        or {
            "strain_true_plastic": "1",
            "stress_true": "Pa",
            source_name: "1",
        },
    )


def _plastic_guard(
    frame: Frame, *, include_source_index: bool = True, **overrides: object
) -> processing.PipelineResult:
    options: dict[str, object] = {"x": "strain_true_plastic"}
    if include_source_index:
        options["source_index"] = "source_row"
    options.update(overrides)
    return apply([Step("tensile.plastic_coordinate_order_guard", options)], frame)


def _scalar(result: processing.PipelineResult, key: str) -> float:
    return next(item.value for item in result.scalars if item.key == key)


def test_guard_registration_and_produced_keys_are_bounded() -> None:
    source = registry.get("tensile.source_support_order_guard")
    plastic = registry.get("tensile.plastic_coordinate_order_guard")
    assert source.meta["candidate_only"] is True
    assert plastic.meta["candidate_only"] is True
    assert source.order < registry.get("curve.sort_unique").order or source.order == 73
    assert all(len(item.key) <= 50 for item in source.makes_values + plastic.makes_values)
    x_column = {item.name: item for item in plastic.params}["x"]
    assert x_column.default is None
    source_index = {item.name: item for item in plastic.params}["source_index"]
    assert source_index.type == "choice"
    assert source_index.default == "auto"
    assert source_index.choices == (
        "auto",
        "source_row",
        "prepared_row",
        "source_csv_line",
        "source_excel_row",
    )
    assert source_index.role is None


def test_source_guard_accepts_interpolated_proof_and_only_diagnoses_early_backstep() -> None:
    frame = _source_frame([0.0, 0.0009, 0.0008, 0.0012, 0.0016, 0.004])
    before = {key: value.copy() for key, value in frame.columns.items()}

    result = _source_guard(
        frame,
        proof_left_index=3,
        proof_right_index=4,
        proof_strain=0.0014,
        peak_index=5,
        peak_strain=0.004,
    )

    stage = result.stages[-1]
    assert stage.frame is frame
    assert _scalar(result, "source_support_order_code") == 1.0
    assert _scalar(result, "source_support_proof_mode_code") == 0.0
    assert _scalar(result, "source_support_points") == 2.0
    assert _scalar(result, "source_support_backstep_count") == 1.0
    assert _scalar(result, "source_support_mismatch_count") == 0.0
    for key, value in before.items():
        np.testing.assert_array_equal(frame.columns[key], value)


@pytest.mark.parametrize(
    ("proof_strain", "mode", "points"),
    [(0.001, 1.0, 2.0), (0.002, 2.0, 1.0)],
)
def test_source_guard_distinguishes_exact_proof_boundaries(
    proof_strain: float, mode: float, points: float
) -> None:
    frame = _source_frame([0.0, 0.001, 0.002, 0.003])
    result = _source_guard(
        frame,
        proof_left_index=1,
        proof_right_index=2,
        proof_strain=proof_strain,
        peak_index=3,
        peak_strain=0.003,
    )
    assert _scalar(result, "source_support_proof_mode_code") == mode
    assert _scalar(result, "source_support_points") == points


def test_source_guard_holds_preproof_coordinate_intrusion_after_stable_sort() -> None:
    # The source proof pair is rows 1->2, but row 0's x=.014 becomes the
    # sorted left bracket for proof=.015.
    frame = _source_frame([0.014, 0.01, 0.02, 0.03])
    with pytest.raises(ProcessingError, match="proof 보간쌍"):
        _source_guard(
            frame,
            proof_left_index=1,
            proof_right_index=2,
            proof_strain=0.015,
            peak_index=3,
            peak_strain=0.03,
        )


def test_source_guard_holds_exact_proof_tie_that_mean_would_merge() -> None:
    # Proof is exactly row 1, but row 0 has the same x and would be averaged
    # into the proof row by the following mean duplicate policy.
    frame = _source_frame([0.01, 0.01, 0.015, 0.03])
    with pytest.raises(ProcessingError, match="동률 병합"):
        _source_guard(
            frame,
            proof_left_index=1,
            proof_right_index=2,
            proof_strain=0.01,
            peak_index=3,
            peak_strain=0.03,
        )


@pytest.mark.parametrize(
    ("strain", "proof_left", "proof_right", "proof_strain", "message"),
    [
        ([0.0, 0.001, 0.0025, 0.0015, 0.004], 1, 2, 0.002, "좌표창"),
        ([0.0, 0.0005, 0.0015, 0.0012, 0.002], 1, 2, 0.001, "엄격히 증가하지"),
    ],
)
def test_source_guard_holds_coordinate_reentry_or_support_backstep(
    strain: list[float],
    proof_left: int,
    proof_right: int,
    proof_strain: float,
    message: str,
) -> None:
    frame = _source_frame(strain)
    with pytest.raises(ProcessingError, match=message):
        _source_guard(
            frame,
            proof_left_index=proof_left,
            proof_right_index=proof_right,
            proof_strain=proof_strain,
            peak_index=4,
            peak_strain=strain[-1],
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"order_evidence_code": 0}, "order_evidence_code=1"),
        ({"force_peak_match_code": 0}, "force_peak_match_code=1"),
        ({"peak_index": 3}, "prefix 마지막 행"),
        ({"peak_strain": 0.0041}, "정확히 일치"),
        ({"proof_strain": 0.0045}, "크지 않습니다"),
        ({"proof_left_index": 1, "proof_right_index": 3}, "인접 원행"),
    ],
)
def test_source_guard_validates_scalar_contract(
    overrides: dict[str, object], message: str
) -> None:
    frame = _source_frame([0.0, 0.001, 0.0025, 0.0035, 0.004])
    with pytest.raises(ProcessingError, match=message):
        _source_guard(frame, **overrides)


def test_plastic_guard_allows_derived_first_proof_row_and_reports_zero_duplicates() -> None:
    frame = _plastic_frame([0.0, 0.0, 0.01, 0.02], [100.5, 101.0, 102.0, 103.0])
    before = {key: value.copy() for key, value in frame.columns.items()}

    result = _plastic_guard(frame)

    assert result.stages[-1].frame is frame
    assert result.stages[-1].options["x"] == "strain_true_plastic"
    assert _scalar(result, "plastic_coord_order_code") == 1.0
    assert _scalar(result, "plastic_coord_positive_order_code") == 1.0
    assert _scalar(result, "plastic_coord_positive_points") == 2.0
    assert _scalar(result, "plastic_coord_zero_duplicate_count") == 1.0
    assert _scalar(result, "plastic_coord_derived_first_code") == 1.0
    assert "후속 first 정리" in " ".join(result.notes)
    for key, value in before.items():
        np.testing.assert_array_equal(frame.columns[key], value)


def test_plastic_guard_requires_explicit_x_column() -> None:
    frame = _plastic_frame([0.0, 0.0, 0.01, 0.02], [100.5, 101.0, 102.0, 103.0])

    with pytest.raises(ProcessingError, match=r"'x'.*명시"):
        apply(
            [
                Step(
                    "tensile.plastic_coordinate_order_guard",
                    {"source_index": "source_row"},
                )
            ],
            frame,
        )


def test_plastic_guard_auto_selects_m11_style_csv_line_evidence() -> None:
    frame = _plastic_frame(
        [0.0, 0.0, 0.01, 0.02],
        [118.5, 119.0, 120.0, 121.0],
        source_name="source_csv_line",
    )

    result = _plastic_guard(frame, include_source_index=False)

    assert result.stages[-1].options["source_index"] == "source_csv_line"
    assert "source_csv_line" in " ".join(result.notes)
    assert _scalar(result, "plastic_coord_source_rows_checked") == 3.0


def test_plastic_guard_auto_choice_value_selects_csv_line_evidence() -> None:
    frame = _plastic_frame(
        [0.0, 0.0, 0.01, 0.02],
        [118.5, 119.0, 120.0, 121.0],
        source_name="source_csv_line",
    )

    result = _plastic_guard(frame, source_index="auto")

    assert result.stages[-1].options["source_index"] == "source_csv_line"


def test_plastic_guard_auto_falls_back_to_next_valid_evidence_column() -> None:
    frame = Frame(
        {
            "strain_true_plastic": np.asarray([0.0, 0.0, 0.01, 0.02]),
            "stress_true": np.linspace(100.0e6, 140.0e6, 4),
            "source_row": np.asarray([100.5, 103.0, 102.0, 104.0]),
            "source_csv_line": np.asarray([200.5, 201.0, 202.0, 203.0]),
        },
        {
            "strain_true_plastic": "1",
            "stress_true": "Pa",
            "source_row": "1",
            "source_csv_line": "1",
        },
    )

    result = _plastic_guard(frame, include_source_index=False)

    assert result.stages[-1].options["source_index"] == "source_csv_line"


def test_plastic_guard_auto_requires_order_evidence_column() -> None:
    frame = Frame(
        {
            "strain_true_plastic": np.asarray([0.0, 0.0, 0.01, 0.02]),
            "stress_true": np.linspace(100.0e6, 140.0e6, 4),
        },
        {"strain_true_plastic": "1", "stress_true": "Pa"},
    )

    with pytest.raises(ProcessingError, match="자동 source_index"):
        _plastic_guard(frame, include_source_index=False)


def test_plastic_guard_auto_reports_nonmonotone_selected_evidence() -> None:
    frame = _plastic_frame(
        [0.0, 0.0, 0.01, 0.02],
        [118.5, 120.0, 119.0, 121.0],
        source_name="source_csv_line",
    )

    with pytest.raises(ProcessingError, match=r"source_csv_line.*엄격히 증가"):
        _plastic_guard(frame, include_source_index=False)


def test_plastic_guard_explicit_source_row_does_not_fallback_to_csv_line() -> None:
    frame = _plastic_frame(
        [0.0, 0.0, 0.01, 0.02],
        [118.5, 119.0, 120.0, 121.0],
        source_name="source_csv_line",
    )

    with pytest.raises(ProcessingError, match=r"source_row.*없습니다"):
        _plastic_guard(frame)


@pytest.mark.parametrize(
    ("x", "source", "message"),
    [
        ([0.0, 0.02, 0.01, 0.03], [100.5, 101.0, 102.0, 103.0], "양의 εp"),
        ([0.0, 0.01, 0.01, 0.03], [100.5, 101.0, 102.0, 103.0], "양의 εp"),
        ([0.0, 0.01, 0.02, 0.03], [100.5, 103.0, 102.0, 104.0], "원행 순서"),
        ([0.0, 0.01, 0.02, 0.03], [100.5, 101.0, 101.0, 103.0], "원행 순서"),
    ],
)
def test_plastic_guard_holds_first_problem_pair(
    x: list[float], source: list[float], message: str
) -> None:
    with pytest.raises(ProcessingError, match=message):
        _plastic_guard(_plastic_frame(x, source))


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (_plastic_frame([0.001, 0.01, 0.02], [100.5, 101.0, 102.0]), "첫 좌표"),
        (
            _plastic_frame(
                [0.0, 0.01, 0.02],
                [100.5, 101.0, 102.0],
                units={
                    "strain_true_plastic": "%",
                    "stress_true": "Pa",
                    "source_row": "1",
                },
            ),
            "단위는 '1'",
        ),
        (
            _plastic_frame([0.0, 0.01, np.nan], [100.5, 101.0, 102.0]),
            "유한하지 않은",
        ),
        (_plastic_frame([0.0, 0.01, 0.02], [100.5, 101.0, 102.0]), "알 수 없는"),
    ],
)
def test_plastic_guard_validates_units_finite_values_and_options(
    frame: Frame, message: str
) -> None:
    overrides = {"unexpected": 1} if message == "알 수 없는" else {}
    with pytest.raises(ProcessingError, match=message):
        _plastic_guard(frame, **overrides)


def test_plastic_guard_requires_two_positive_support_points() -> None:
    with pytest.raises(ProcessingError, match="2개 미만"):
        _plastic_guard(_plastic_frame([0.0, 0.0, 0.01], [100.5, 101.0, 102.0]))


@pytest.mark.parametrize(
    ("x", "source", "message"),
    [
        ([0.0, 0.0, 0.01, 0.0, 0.02], [100.5, 101.0, 102.0, 103.0, 104.0], "양의 εp 뒤"),
        ([0.0, 0.0, -0.01, 0.02], [100.5, 101.0, 102.0, 103.0], "음수 εp"),
        ([0.0, 0.0, 0.01, 0.02], [100.5, 101.5, 102.0, 103.0], "정수가 아닌 파생"),
    ],
)
def test_plastic_guard_holds_reappearing_zero_negative_or_derived_rows(
    x: list[float], source: list[float], message: str
) -> None:
    with pytest.raises(ProcessingError, match=message):
        _plastic_guard(_plastic_frame(x, source))
