"""Original-row elastic measurement through the extension loader."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tensile_source_elastic_cases.npz"

extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(case_index: int) -> Frame:
    prefix = f"c{case_index:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as archive:
        columns = {
            name: archive[prefix + name].copy()
            for name in (
                "strain_engineering",
                "stress_engineering",
                "time",
                "source_row",
                "prepared_row",
            )
        }
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


def _run(frame: Frame, options: dict[str, object] | None = None) -> processing.PipelineResult:
    return processing.apply([Step("tensile.source_elastic_modulus", options or {})], frame)


def _scalars(result: processing.PipelineResult) -> dict[str, float]:
    return {item.key: item.value for item in result.stages[-1].scalars}


def _assert_frame_unchanged(before: Frame, after: Frame) -> None:
    assert after is before
    assert after.columns.keys() == before.columns.keys()
    assert after.units == before.units
    for name, values in before.columns.items():
        assert after.columns[name].dtype == values.dtype
        assert after.columns[name].shape == values.shape
        assert after.columns[name].tobytes() == values.tobytes()


class Test등록:
    def test_확장_로더가_기본_원행_정책과_출력값을_등록한다(self) -> None:
        plugin = registry.get("tensile.source_elastic_modulus")

        assert plugin.kind == "processing"
        assert plugin.version == "1"
        assert plugin.applies_to == ("tensile",)
        assert plugin.order > registry.get("tensile.elastic_modulus").order
        params = {item.name: item for item in plugin.params}
        assert params["policy"].default == "auto_rows_v1"
        assert params["policy"].choices == ("auto_rows_v1", "manual_rows")
        assert params["start_index"].required is True
        assert params["start_index"].when == {"policy": ("manual_rows",)}
        assert params["end_index"].when == {"policy": ("manual_rows",)}
        assert {
            "youngs_modulus",
            "elastic_window_start",
            "elastic_window_end",
            "source_elastic_start_index",
            "source_elastic_end_index",
            "source_elastic_nonincreasing_step_count",
        }.issubset({item.key for item in plugin.makes_values})

    @pytest.mark.parametrize(
        ("channel", "value"),
        [
            ("strain", None),
            ("strain", False),
            ("strain", 0),
            ("strain", ""),
            ("strain", "   "),
            ("strain", 3),
            ("stress", None),
            ("stress", False),
            ("stress", 0),
            ("stress", ""),
            ("stress", "\t "),
            ("stress", 3),
        ],
    )
    def test_명시한_잘못된_열_이름은_기본값으로_대체하지_않는다(
        self, channel: str, value: object
    ) -> None:
        with pytest.raises(ProcessingError, match="열 이름"):
            _run(_frame(24), {channel: value})


class Test실제원행:
    @pytest.mark.parametrize(
        (
            "case_index",
            "start",
            "end",
            "count",
            "nonincreasing",
            "window_low",
            "window_high",
            "youngs_modulus",
            "intercept",
            "r_squared",
        ),
        [
            (
                24,
                203,
                295,
                93,
                32,
                0.002057,
                0.009136,
                3_010_768_452.730445,
                739_835.2109369729,
                0.998259553358863,
            ),
            (
                57,
                59,
                215,
                157,
                0,
                -0.0002445,
                0.00040029999999999997,
                210_867_263_618.3178,
                97_997_770.84796642,
                0.9999963000872241,
            ),
            (
                60,
                6,
                39,
                34,
                0,
                0.0002936,
                0.001282,
                201_840_104_043.86633,
                16_544_819.473102743,
                0.9997502897472387,
            ),
            (
                117,
                155,
                256,
                102,
                16,
                0.0002946814032131637,
                0.001141816270604673,
                197_582_427_314.26544,
                -2_726_988.0354610085,
                0.9978362694798261,
            ),
        ],
    )
    def test_원행_적합과_현재입력_인덱스가_독립기대값과_일치한다(
        self,
        case_index: int,
        start: int,
        end: int,
        count: int,
        nonincreasing: int,
        window_low: float,
        window_high: float,
        youngs_modulus: float,
        intercept: float,
        r_squared: float,
    ) -> None:
        frame = _frame(case_index)
        before = {key: value.copy() for key, value in frame.columns.items()}

        result = _run(frame)
        actual = _scalars(result)
        stage = result.stages[-1]

        assert stage.plugin == "tensile.source_elastic_modulus"
        assert len(result.stages) == 1
        assert actual["source_elastic_start_index"] == float(start)
        assert actual["source_elastic_end_index"] == float(end)
        assert actual["source_elastic_nonincreasing_step_count"] == float(nonincreasing)
        assert actual["elastic_point_count"] == float(count)
        assert actual["elastic_window_start"] == pytest.approx(window_low, abs=1e-12)
        assert actual["elastic_window_end"] == pytest.approx(window_high, abs=1e-12)
        assert actual["youngs_modulus"] == pytest.approx(youngs_modulus, rel=1e-9, abs=1.0)
        assert actual["elastic_intercept"] == pytest.approx(intercept, rel=1e-9, abs=1.0)
        assert actual["elastic_r_squared"] == pytest.approx(r_squared, abs=1e-9)
        assert stage.options == {
            "policy": "auto_rows_v1",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }
        assert "현재 입력" in stage.notes[-1]
        replay = _run(frame, stage.options)
        assert _scalars(replay) == actual
        assert replay.stages[-1].notes == stage.notes
        _assert_frame_unchanged(frame, replay.frame)
        for key, values in before.items():
            assert frame.columns[key].tobytes() == values.tobytes()
        _assert_frame_unchanged(frame, result.frame)
        if case_index == 60:
            core = registry.get("tensile.elastic_modulus").fn(
                frame,
                {
                    "method": "auto",
                    "strain": "strain_engineering",
                    "stress": "stress_engineering",
                },
            )
            core_values = {item.key: item.value for item in core.scalars}
            assert result.stages[-1].notes[:-1] == core.notes
            for key, value in core_values.items():
                assert actual[key] == value

    @pytest.mark.parametrize("case_index", [17, 182])
    def test_지지부족과_품질실패는_E를_내지않고_근거를_남긴다(self, case_index: int) -> None:
        frame = _frame(case_index)
        result = _run(frame)
        actual = _scalars(result)

        assert "youngs_modulus" not in actual
        assert "elastic_intercept" not in actual
        assert "원행" in "\n".join(result.notes)
        _assert_frame_unchanged(frame, result.frame)

        if case_index == 17:
            core = registry.get("tensile.elastic_modulus").fn(
                frame,
                {
                    "method": "auto",
                    "strain": "strain_engineering",
                    "stress": "stress_engineering",
                },
            )
            core_values = {item.key: item.value for item in core.scalars}
            assert actual["elastic_point_count"] == 0.0
            assert "source_elastic_start_index" not in actual
            assert "source_elastic_end_index" not in actual
            assert result.stages[-1].notes[:-1] == core.notes
            for key, value in core_values.items():
                assert actual[key] == value
        else:
            assert actual["source_elastic_start_index"] == 5.0
            assert actual["source_elastic_end_index"] == 37.0
            assert actual["source_elastic_nonincreasing_step_count"] == 19.0
            assert actual["elastic_point_count"] == 33.0
            assert actual["elastic_window_start"] == pytest.approx(0.0001195, abs=1e-12)
            assert actual["elastic_window_end"] == pytest.approx(0.000205, abs=1e-12)
            assert actual["elastic_slope_reference"] == pytest.approx(
                894_860_295_642.5787, rel=1e-9, abs=1.0
            )
            assert actual["elastic_r_squared"] == pytest.approx(0.11013845666191235, abs=1e-9)

    def test_수동원행은_현재입력_포함경계와_JSON재생을_보존한다(self) -> None:
        frame = _frame(24)
        options = {
            "policy": "manual_rows",
            "start_index": 204,
            "end_index": 294,
        }
        replayed = json.loads(json.dumps(options))

        result = _run(frame, options)
        replay = _run(frame, replayed)
        values = _scalars(result)

        assert values["source_elastic_start_index"] == 204.0
        assert values["source_elastic_end_index"] == 294.0
        assert values["elastic_point_count"] == 91.0
        assert values["youngs_modulus"] == pytest.approx(
            3_029_067_671.4454427, rel=1e-9, abs=1.0
        )
        assert values["elastic_intercept"] == pytest.approx(
            680_780.9019999541, rel=1e-9, abs=1.0
        )
        assert _scalars(replay) == values
        assert replay.stages[-1].notes == result.stages[-1].notes
        assert replay.stages[-1].options == result.stages[-1].options
        assert result.stages[-1].options == {
            "policy": "manual_rows",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
            "start_index": 204,
            "end_index": 294,
        }
        saved_options_replay = _run(frame, result.stages[-1].options)
        assert _scalars(saved_options_replay) == values
        assert saved_options_replay.stages[-1].notes == result.stages[-1].notes
        assert saved_options_replay.stages[-1].options == result.stages[-1].options
        _assert_frame_unchanged(frame, result.frame)
        _assert_frame_unchanged(frame, replay.frame)
        _assert_frame_unchanged(frame, saved_options_replay.frame)

    @pytest.mark.parametrize(
        "options",
        [
            {"auto_stress_low": 0.2},
            {"policy": "manual_rows", "auto_stress_low": 0.2},
        ],
    )
    def test_지원하지_않는_옵션을_거절한다(self, options: dict[str, object]) -> None:
        with pytest.raises(ProcessingError, match="알 수 없는 옵션"):
            _run(_frame(24), options)

    @pytest.mark.parametrize(
        "options",
        [
            {"start_index": None},
            {"end_index": None},
            {"policy": "auto_rows_v1", "start_index": None, "end_index": None},
        ],
    )
    def test_자동정책에서_수동경계를_명시하면_거절한다(
        self, options: dict[str, object]
    ) -> None:
        with pytest.raises(ProcessingError, match="자동 원행"):
            _run(_frame(24), options)

    @pytest.mark.parametrize(
        ("start_index", "end_index"),
        [(1.5, 4), (True, 4), (0, 215), (-1, 4)],
    )
    def test_잘못된_수동경계는_명확하게_거절한다(
        self, start_index: object, end_index: object
    ) -> None:
        with pytest.raises(ProcessingError, match="수동 원행"):
            _run(
                _frame(182),
                {
                    "policy": "manual_rows",
                    "start_index": start_index,
                    "end_index": end_index,
                },
            )

    def test_선택원행에_비유한쌍이_있으면_조용히_제외하지_않는다(self) -> None:
        frame = _frame(24)
        frame.columns["strain_engineering"][220] = np.nan

        with pytest.raises(ProcessingError, match="유한하지 않은"):
            _run(frame)
