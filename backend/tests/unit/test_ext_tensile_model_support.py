"""Guarded source-row projection for downstream tensile-model inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tensile_model_support_cases.npz"
RECIPES = Path(__file__).resolve().parents[2] / "extensions" / "tensile_extras" / "recipes"
R17_RECIPE = RECIPES / "stable_band_model_v2_examples.json"
R18_RECIPE = RECIPES / "source_measurement_model_v1_examples.json"
SOURCE_E = "tensile.source_elastic_modulus"
SOURCE_RP = "tensile.source_proof_stress"
SUPPORT = "tensile.model_support"

extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(case_index: int) -> Frame:
    prefix = f"c{case_index:03d}_"
    names = (
        "strain_engineering",
        "stress_engineering",
        "time",
        "source_row",
        "prepared_row",
    )
    with np.load(FIXTURE, allow_pickle=False) as archive:
        columns = {name: archive[prefix + name].copy() for name in names}
    return Frame(
        columns,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "time": "s",
            "source_row": "1",
            "prepared_row": "1",
        },
    )


def _snapshot(frame: Frame) -> tuple[dict[str, str], dict[str, tuple[int, bytes]]]:
    return (
        dict(frame.units),
        {key: (id(values), values.tobytes()) for key, values in frame.columns.items()},
    )


def _assert_snapshot(
    frame: Frame, before: tuple[dict[str, str], dict[str, tuple[int, bytes]]]
) -> None:
    units, columns = before
    assert dict(frame.units) == units
    assert frame.columns.keys() == columns.keys()
    for key, values in frame.columns.items():
        object_id, data = columns[key]
        assert id(values) == object_id
        assert values.tobytes() == data


def _run(
    frame: Frame,
    *,
    support_options: dict[str, Any] | None = None,
    elastic_options: dict[str, Any] | None = None,
) -> processing.PipelineResult:
    return processing.apply(
        [
            Step(SOURCE_E, elastic_options or {}),
            Step(SOURCE_RP, {"offset_strain": 0.002}),
            Step(SUPPORT, support_options or {}),
        ],
        frame,
    )


def _record_high_indices(strain: np.ndarray, start: int, end: int) -> np.ndarray:
    kept = [start]
    for row in range(start + 1, end + 1):
        if strain[row] > strain[kept[-1]]:
            kept.append(row)
    return np.asarray(kept, dtype=np.int64)


def _support_options(
    frame: Frame, *, start: int = 0, end: int | None = None
) -> dict[str, Any]:
    return {
        "policy": "record_high_guarded_v1",
        "start_index": start,
        "end_index": frame.length() - 1 if end is None else end,
        "youngs_modulus": 1000.0,
        "elastic_intercept": 0.0,
        "source_elastic_start_index": 0,
        "source_elastic_end_index": 2,
        "source_proof_left_index": 0,
        "source_proof_right_index": 1,
    }


def _synthetic(strain: list[float], stress: list[float]) -> Frame:
    count = len(strain)
    return Frame(
        {
            "strain_engineering": np.asarray(strain, dtype=np.float64),
            "stress_engineering": np.asarray(stress, dtype=np.float64),
            "time": np.arange(count, dtype=np.float64),
        },
        {"strain_engineering": "1", "stress_engineering": "Pa", "time": "s"},
    )


class Test등록과레시피:
    def test_등록순서는원행측정뒤모델입력과두대안을둔다(self) -> None:
        assert registry.get("tensile.strength").order == 70
        assert registry.get(SOURCE_E).order == 71
        assert registry.get(SOURCE_RP).order == 72
        assert registry.get("tensile.necking_candidate").order == 80
        assert registry.get(SUPPORT).order == 81
        assert registry.get("tensile.band_model").order == 82
        assert registry.get("tensile.model_curve").order == 82
        plugin = registry.get(SUPPORT)
        assert plugin.version == "1"
        assert plugin.prepare_options is not None
        assert plugin.prepare_options({}) == {
            "policy": "record_high_guarded_v1",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
            "youngs_modulus": "@youngs_modulus",
            "elastic_intercept": "@elastic_intercept",
            "source_elastic_start_index": "@source_elastic_start_index",
            "source_elastic_end_index": "@source_elastic_end_index",
            "source_proof_left_index": "@source_proof_left_index",
            "source_proof_right_index": "@source_proof_right_index",
        }

    def test_새일곱레시피는기존R17의다른단계를보존한다(self) -> None:
        old = json.loads(R17_RECIPE.read_text(encoding="utf-8"))
        new = json.loads(R18_RECIPE.read_text(encoding="utf-8"))
        assert new["schema"] == "matnexus.tensile.source_measurement_model_v1_examples/1"
        assert len(old["recipes"]) == len(new["recipes"]) == 7
        for old_recipe, new_recipe in zip(old["recipes"], new["recipes"], strict=True):
            expected = []
            for step in old_recipe["steps"]:
                if step["plugin"] == "tensile.elastic_modulus":
                    expected.append({"plugin": SOURCE_E, "options": {}})
                elif step["plugin"] == "tensile.proof_stress":
                    expected.append({"plugin": SOURCE_RP, "options": {"offset_strain": 0.002}})
                else:
                    expected.append(step)
                if step["plugin"] == "tensile.necking_candidate":
                    expected.append({"plugin": SUPPORT, "options": {}})
            assert new_recipe["steps"] == expected
            assert new_recipe["key"].startswith("r18_source_measurement_model_v1_")


class Test원행모델입력:
    @pytest.mark.parametrize("case_index", [11, 24, 57, 117])
    def test_가드통과후기록최고원행만같은인덱스로남긴다(self, case_index: int) -> None:
        frame = _frame(case_index)
        before = _snapshot(frame)
        strain = frame.columns["strain_engineering"]
        stress = frame.columns["stress_engineering"]
        result = _run(frame)
        stage = result.stages[-1]
        selected = _record_high_indices(strain, 0, frame.length() - 1)
        assert stage.plugin == SUPPORT
        assert np.array_equal(stage.frame.columns["model_input_index"], selected)
        assert np.all(np.diff(stage.frame.columns["strain_engineering"]) > 0.0)
        assert _scalars(stage)["model_support_guard_flagged_row_count"] == 0.0
        for key, values in frame.columns.items():
            assert np.array_equal(stage.frame.columns[key], values[selected])
        _assert_snapshot(frame, before)
        if case_index == 11:
            assert np.any((strain[1:] > strain[:-1]) & (stress[1:] < stress[:-1]))

    def test_엄격한대조는모든원행과값을보존하고대응열만추가한다(self) -> None:
        frame = _frame(60)
        before = _snapshot(frame)
        result = _run(frame)
        output = result.stages[-1].frame
        assert output.length() == frame.length() == 210
        assert np.array_equal(output.columns["model_input_index"], np.arange(frame.length()))
        for key, values in frame.columns.items():
            assert output.columns[key].dtype == values.dtype
            assert np.array_equal(output.columns[key], values)
        _assert_snapshot(frame, before)

    @pytest.mark.parametrize(
        ("case_index", "anchor", "first_flag", "flag_count"),
        [
            (14, 348, 349, 9),
            (102, 1301, 1302, 17),
            (141, 492, 493, 21),
            (149, 476, 477, 7),
            (152, 56, 58, 2),
            (178, 47, 48, 10),
        ],
    )
    def test_독립적으로고정된여섯원행경계에서출력단계를보류한다(
        self, case_index: int, anchor: int, first_flag: int, flag_count: int
    ) -> None:
        frame = _frame(case_index)
        before = _snapshot(frame)
        with pytest.raises(ProcessingError) as raised:
            _run(frame)
        error = raised.value
        assert f"원행 {anchor}→{first_flag}" in str(error)
        assert "자동으로 자르지 않았습니다" in str(error)
        assert error.done is not None
        assert [stage.plugin for stage in error.done.stages] == [SOURCE_E, SOURCE_RP]
        assert "youngs_modulus" in {scalar.key for scalar in error.done.scalars}
        assert "proof_stress" in {scalar.key for scalar in error.done.scalars}
        assert str(flag_count) in str(error)
        _assert_snapshot(frame, before)

    def test_수동범위가전체원행의표시경계를끊으면그사실을남긴다(self) -> None:
        frame = _frame(14)
        result = _run(frame, support_options={"start_index": 0, "end_index": 348})
        stage = result.stages[-1]
        scalars = _scalars(stage)
        assert scalars["model_support_full_guard_flagged_row_count"] == 9.0
        assert scalars["model_support_excluded_flagged_boundary_count"] == 9.0
        assert scalars["model_support_full_peak_inside"] == 1.0
        assert "전체 입력 표시 행 9개" in " ".join(stage.notes)
        assert "수동 범위" in " ".join(stage.notes)

    def test_수동시작이0이아니어도현재입력행대응과JSON재실행이정확하다(self) -> None:
        frame = _frame(57)
        options = {"start_index": 100, "end_index": 200}
        first = _run(frame, support_options=options)
        stage = first.stages[-1]
        expected = _record_high_indices(frame.columns["strain_engineering"], 100, 200)
        assert np.array_equal(stage.frame.columns["model_input_index"], expected)
        assert expected[0] == 100 and expected[-1] == 200
        saved = json.loads(json.dumps(stage.options))
        replay = processing.apply(
            [
                Step(first.stages[0].plugin, first.stages[0].options),
                Step(first.stages[1].plugin, first.stages[1].options),
                Step(SUPPORT, saved),
            ],
            frame,
        )
        replay_stage = replay.stages[-1]
        assert replay_stage.options == stage.options
        assert np.array_equal(
            replay_stage.frame.columns["model_input_index"],
            stage.frame.columns["model_input_index"],
        )
        assert _scalars(replay_stage) == _scalars(stage)

    def test_원행교점한쪽이기록최고선택에서빠지면범위포함과구분한다(self) -> None:
        frame = _synthetic(
            [0.0, 0.00025, 0.0005, 0.00075, 0.001, 0.002, 0.0019, 0.0025],
            [0.0, 0.25, 0.5, 0.75, 1.0, 2.0, 1.9, 0.2],
        )
        result = processing.apply(
            [
                Step(SOURCE_E, {"policy": "manual_rows", "start_index": 0, "end_index": 4}),
                Step(SOURCE_RP, {"offset_strain": 0.002}),
                Step(SUPPORT),
            ],
            frame,
        )
        stage = result.stages[-1]
        scalars = _scalars(stage)
        assert scalars["model_support_proof_pair_inside"] == 1.0
        assert scalars["model_support_proof_rows_retained_count"] == 1.0
        assert scalars["model_support_proof_pair_retained"] == 0.0
        note = " ".join(stage.notes)
        assert "범위에 포함" in note and "1/2행이 남았습니다" in note
        assert np.array_equal(
            stage.frame.columns["model_input_index"], np.asarray([0, 1, 2, 3, 4, 5, 7])
        )

    def test_선택에서첫최대응력행을잃으면뒤의동률최대값으로대체하지않는다(self) -> None:
        frame = _synthetic([0.0, 2.0, 1.0, 3.0, 4.0], [1.0, 5.0, 10.0, 6.0, 10.0])
        with pytest.raises(ProcessingError, match="첫 최대응력 원행 2"):
            processing.apply(
                [Step(SUPPORT, _support_options(frame, start=0, end=4))],
                frame,
            )

    @pytest.mark.parametrize(
        "options",
        [
            {"unknown_gap_cutoff": 0.2},
            {"start_index": None},
            {"end_index": 1.5},
            {"policy": "sorted_smooth_v1"},
        ],
    )
    def test_알수없거나무효한모델입력옵션을거절한다(self, options: dict[str, Any]) -> None:
        frame = _synthetic([0.0, 0.1, 0.2], [0.0, 10.0, 20.0])
        values = _support_options(frame, start=0, end=2)
        values.update(options)
        with pytest.raises(ProcessingError):
            processing.apply([Step(SUPPORT, values)], frame)

    def test_모델입력인덱스열충돌을덮어쓰지않는다(self) -> None:
        frame = _synthetic([0.0, 0.1, 0.2], [0.0, 10.0, 20.0])
        frame = frame.with_columns(
            {"model_input_index": np.arange(3)}, {"model_input_index": "1"}
        )
        with pytest.raises(ProcessingError, match="덮어쓰지 않습니다"):
            processing.apply(
                [Step(SUPPORT, _support_options(frame, start=0, end=2))],
                frame,
            )


def _scalars(stage: processing.Stage) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in stage.scalars}
