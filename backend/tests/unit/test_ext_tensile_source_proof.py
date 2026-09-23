"""Source-row Rp from adjacent original acquisition rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tensile_source_proof_cases.npz"
PROOF = "tensile.source_proof_stress"
ELASTIC = "tensile.source_elastic_modulus"

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
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "time": "s",
        "source_row": "1",
        "prepared_row": "1",
    }
    return Frame(columns, units)


def _direct(frame: Frame, options: dict[str, Any]) -> processing.PipelineResult:
    return processing.apply([Step(PROOF, options)], frame)


def _chain(frame: Frame) -> processing.PipelineResult:
    return processing.apply([Step(ELASTIC), Step(PROOF)], frame)


def _scalars(result: processing.PipelineResult) -> dict[str, float]:
    return {item.key: item.value for item in result.scalars}


def _assert_unchanged(before: Frame, after: Frame) -> None:
    assert after is before
    assert after.units == before.units
    assert after.columns.keys() == before.columns.keys()
    for key, values in before.columns.items():
        assert after.columns[key].dtype == values.dtype
        assert after.columns[key].shape == values.shape
        assert after.columns[key].tobytes() == values.tobytes()


def _frame_snapshot(
    frame: Frame,
) -> tuple[dict[str, str], dict[str, tuple[int, str, tuple[int, ...], bytes]]]:
    return (
        dict(frame.units),
        {
            key: (id(values), str(values.dtype), values.shape, values.tobytes())
            for key, values in frame.columns.items()
        },
    )


def _assert_snapshot_unchanged(
    frame: Frame,
    snapshot: tuple[dict[str, str], dict[str, tuple[int, str, tuple[int, ...], bytes]]],
) -> None:
    units, columns = snapshot
    assert dict(frame.units) == units
    assert frame.columns.keys() == columns.keys()
    for key, values in frame.columns.items():
        object_id, dtype, shape, raw_bytes = columns[key]
        assert id(values) == object_id
        assert str(values.dtype) == dtype
        assert values.shape == shape
        assert values.tobytes() == raw_bytes


class Test등록:
    def test_확장_등록과_기본_참조를_확인한다(self) -> None:
        plugin = registry.get(PROOF)
        assert plugin.kind == "processing"
        assert plugin.version == "1"
        assert plugin.prepare_options is not None
        params = {param.name: param for param in plugin.params}
        assert params["policy"].default == "first_positive_forward_v1"
        assert params["youngs_modulus"].default == "@youngs_modulus"
        assert params["start_index"].default == "@source_elastic_end_index"
        assert params["search_start"].default == "@elastic_window_end"
        prepared = plugin.prepare_options({})
        assert prepared == {
            "policy": "first_positive_forward_v1",
            "youngs_modulus": "@youngs_modulus",
            "start_index": "@source_elastic_end_index",
            "search_start": "@elastic_window_end",
        }


class Test실제원자료:
    @pytest.mark.parametrize(
        (
            "case_index",
            "left",
            "right",
            "proof_strain",
            "proof_stress",
            "e_end",
            "w_end",
            "max_strain",
        ),
        [
            (24, 323, 324, 0.016596898333534588, 43_947_881.01031954, 295, 0.009136, 0.1293),
            (
                57,
                541,
                542,
                0.0039063467180888165,
                401_986_115.95114946,
                215,
                0.00040029999999999997,
                0.039034900000000004,
            ),
            (60, 83, 84, 0.005205250314315098, 646_948_056.9279947, 39, 0.001282, 0.163),
            (
                117,
                560,
                561,
                0.0037813684623946202,
                351_967_104.7410098,
                256,
                0.001141816270604673,
                0.12145408646805458,
            ),
        ],
    )
    def test_원행_E에서_첫_양수_전진교점을_원래_행으로_재생한다(
        self,
        case_index: int,
        left: int,
        right: int,
        proof_strain: float,
        proof_stress: float,
        e_end: int,
        w_end: float,
        max_strain: float,
    ) -> None:
        frame = _frame(case_index)
        result = _chain(frame)
        values = _scalars(result)
        proof_stage = result.stages[-1]

        assert len(result.stages) == 2
        assert proof_stage.plugin == PROOF
        assert values["source_proof_left_index"] == float(left)
        assert values["source_proof_right_index"] == float(right)
        assert values["proof_strain"] == pytest.approx(proof_strain, abs=1e-12)
        assert values["proof_stress"] == pytest.approx(proof_stress, rel=1e-9, abs=1.0)
        assert values["proof_offset"] == 0.002
        assert values["source_proof_search_start_index"] == float(e_end)
        assert values["source_proof_search_end_index"] == float(
            len(frame.columns["strain_engineering"]) - 1
        )
        assert values["source_proof_search_start_strain"] == pytest.approx(w_end, abs=1e-12)
        assert values["source_proof_search_end_strain"] == pytest.approx(max_strain, abs=1e-12)
        assert values["source_proof_positive_crossing_candidate_count"] == 1.0
        assert values["source_proof_nonpositive_crossing_candidate_count"] == 0.0
        assert values["source_proof_backward_crossing_candidate_count"] == 0.0
        assert values["source_proof_equal_strain_crossing_candidate_count"] == 0.0
        assert values["source_proof_coincident_forward_residual_segment_count"] == 0.0
        assert proof_stage.options == {
            "policy": "first_positive_forward_v1",
            "youngs_modulus": proof_stage.options["youngs_modulus"],
            "offset_strain": 0.002,
            "start_index": e_end,
            "end_index": len(frame.columns["strain_engineering"]) - 1,
            "search_start": w_end,
            "search_end": max_strain,
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }
        replay_options = json.loads(json.dumps(proof_stage.options))
        replay = processing.apply(
            [Step(ELASTIC, result.stages[0].options), Step(PROOF, replay_options)], frame
        )
        assert _scalars(replay) == values
        assert replay.stages[-1].notes == proof_stage.notes
        _assert_unchanged(frame, result.frame)
        _assert_unchanged(frame, replay.frame)

    @pytest.mark.parametrize("case_index", [5, 23, 30])
    def test_실제_보류군은_내력없이_단계를_중단한다(self, case_index: int) -> None:
        frame = _frame(case_index)
        with pytest.raises(ProcessingError, match="교점") as raised:
            _chain(frame)

        done = raised.value.done
        assert done is not None
        assert len(done.stages) == 1
        assert done.stages[0].plugin == ELASTIC
        assert "전진 적격 인접 쌍" in str(raised.value)
        assert "외삽하지 않았습니다" in str(raised.value)
        _assert_unchanged(frame, done.frame)

    def test_원행_E가_없는_17번은_Rp단계에_도달하지_않는다(self) -> None:
        frame = _frame(17)
        with pytest.raises(ProcessingError, match="@youngs_modulus") as raised:
            _chain(frame)
        done = raised.value.done
        assert done is not None
        assert len(done.stages) == 1
        assert done.stages[0].plugin == ELASTIC
        _assert_unchanged(frame, done.frame)

    def test_직접_E와_수동_검색경계의_JSON재생을_지원한다(self) -> None:
        frame = _frame(57)
        options = {
            "youngs_modulus": 210_867_263_618.3178,
            "offset_strain": 0.002,
            "start_index": 215,
            "end_index": 600,
            "search_start": 0.00040029999999999997,
            "search_end": 0.01,
        }
        result = _direct(frame, options)
        stage = result.stages[-1]
        values = _scalars(result)
        assert values["source_proof_left_index"] == 541.0
        assert values["source_proof_right_index"] == 542.0
        assert values["proof_stress"] == pytest.approx(401_986_115.95114946, rel=1e-9, abs=1.0)
        assert set(stage.options) == {
            "policy",
            "youngs_modulus",
            "offset_strain",
            "start_index",
            "end_index",
            "search_start",
            "search_end",
            "strain",
            "stress",
        }
        replay = _direct(frame, json.loads(json.dumps(stage.options)))
        assert _scalars(replay) == values
        assert replay.stages[-1].notes == stage.notes
        _assert_unchanged(frame, result.frame)
        _assert_unchanged(frame, replay.frame)

    @pytest.mark.parametrize(
        ("channel", "value"),
        [("strain", None), ("strain", "  "), ("stress", False), ("stress", 0)],
    )
    def test_명시한_잘못된_채널은_기본값으로_대체하지_않는다(
        self, channel: str, value: Any
    ) -> None:
        frame = _frame(57)
        options = {
            "youngs_modulus": 210_867_263_618.3178,
            "start_index": 215,
            "end_index": 600,
            "search_start": 0.00040029999999999997,
            "search_end": 0.01,
            channel: value,
        }
        with pytest.raises(ProcessingError, match="열 이름"):
            _direct(frame, options)


class Test경계:
    @staticmethod
    def _synthetic(strain: list[float], stress: list[float]) -> Frame:
        return Frame(
            {
                "strain_engineering": np.asarray(strain, dtype=np.float64),
                "stress_engineering": np.asarray(stress, dtype=np.float64),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

    @staticmethod
    def _options(size: int) -> dict[str, Any]:
        return {
            "youngs_modulus": 1000.0,
            "offset_strain": 0.001,
            "start_index": 0,
            "end_index": size - 1,
            "search_start": -1.0,
            "search_end": 1.0,
        }

    def test_하강응력의_전진교점은_허용한다(self) -> None:
        frame = self._synthetic([0.001, 0.002, 0.003], [1.0, 3.0, 0.0])
        result = _direct(frame, self._options(3))
        values = _scalars(result)
        assert values["source_proof_left_index"] == 1.0
        assert values["source_proof_right_index"] == 2.0
        assert values["proof_strain"] == pytest.approx(0.0025)
        assert values["proof_stress"] == pytest.approx(1.5)
        _assert_unchanged(frame, result.frame)

    def test_역행원행교점을_선택하지않고_그사이를_건너뛰지않는다(self) -> None:
        frame = self._synthetic([0.0, 0.002, 0.003, 0.0025], [0.0, 2.0, 3.0, 0.5])
        snapshot = _frame_snapshot(frame)
        with pytest.raises(ProcessingError, match="역행 잔차 교점 후보 1개") as raised:
            _direct(frame, self._options(4))
        done = raised.value.done
        assert done is not None
        assert not done.stages
        assert "양수 전진 후보 0개" in str(raised.value)
        _assert_snapshot_unchanged(frame, snapshot)

    def test_일치잔차선분은_왼쪽관측점을_선택한다(self) -> None:
        frame = self._synthetic([0.002, 0.003, 0.004], [1.0, 2.0, 3.0])
        result = _direct(frame, self._options(3))
        values = _scalars(result)
        assert values["proof_strain"] == pytest.approx(0.002)
        assert values["proof_stress"] == pytest.approx(1.0)
        assert values["source_proof_left_index"] == 0.0
        assert values["source_proof_right_index"] == 1.0
        assert values["source_proof_coincident_forward_residual_segment_count"] == 2.0
        assert values["source_proof_positive_crossing_candidate_count"] == 2.0
        assert "t=0" in result.notes[0]

    def test_비양수_전진교점만_있으면_Rp를_내지_않는다(self) -> None:
        frame = self._synthetic([0.0, 0.001], [-1.0, -1.0])
        snapshot = _frame_snapshot(frame)
        with pytest.raises(ProcessingError, match="비양수 전진 후보 1개") as raised:
            _direct(frame, self._options(2))
        done = raised.value.done
        assert done is not None
        assert not done.stages
        assert "양수 전진 후보 0개" in str(raised.value)
        _assert_snapshot_unchanged(frame, snapshot)

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("policy", "another_policy"),
            ("auto_stress_low", 0.2),
            ("youngs_modulus", 0.0),
            ("youngs_modulus", float("inf")),
            ("offset_strain", -0.001),
            ("offset_strain", float("nan")),
            ("start_index", 1.5),
            ("end_index", True),
            ("search_start", float("nan")),
            ("search_end", float("inf")),
        ],
    )
    def test_지원하지않거나_유효하지않은_입력은_명확히거절한다(
        self, key: str, value: Any
    ) -> None:
        frame = self._synthetic([0.0, 0.001, 0.002], [0.0, 1.0, 2.0])
        with pytest.raises(ProcessingError):
            _direct(frame, {**self._options(3), key: value})
