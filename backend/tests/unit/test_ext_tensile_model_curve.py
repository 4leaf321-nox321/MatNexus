"""Upper-envelope model curves retain every measured engineering-curve row."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "oxford_pc_fig5_50mm_min_test2.csv"
)
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    stress: object,
    strain: object | None = None,
    *,
    units: dict[str, str] | None = None,
) -> Frame:
    y = np.asarray(stress)
    x = np.arange(len(y), dtype=float) if strain is None else np.asarray(strain)
    return Frame(
        {
            "strain_engineering": x,
            "stress_engineering": y,
            "source_channel": np.arange(len(y), dtype=float),
        },
        units
        if units is not None
        else {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_channel": "1",
        },
    )


def _run(frame: Frame, options: dict[str, object] | None = None) -> processing.PipelineResult:
    return processing.apply([Step("tensile.model_curve", options or {})], frame)


def _scalar_map(result: processing.PipelineResult) -> dict[str, float]:
    return {one.key: one.value for one in result.stages[-1].scalars}


def _oxford_pc2() -> Frame:
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    displacement_mm = np.asarray([float(row["displacement_mm"]) for row in rows])
    force_n = np.asarray([float(row["force_N"]) for row in rows])
    columns = {
        "displacement": displacement_mm * 1e-3,
        "force": force_n,
        "time": np.asarray([float(row["time_s"]) for row in rows]),
        "source_excel_row": np.asarray([int(row["source_excel_row"]) for row in rows]),
        "strain_engineering": displacement_mm / 80.0,
        "stress_engineering": force_n / 40e-6,
    }
    units = {
        "displacement": "m",
        "force": "N",
        "time": "s",
        "source_excel_row": "1",
        "strain_engineering": "1",
        "stress_engineering": "Pa",
    }
    return Frame(columns, units)


class Test모델_공칭곡선_등록:
    def test_확장_로더를_통해_등록되고_Rp_매핑은_없다(self) -> None:
        plugin = registry.get("tensile.model_curve")
        assert plugin.kind == "processing"
        assert plugin.label == "소성 모델 공칭곡선"
        assert plugin.order == 82
        assert plugin.version == "1"
        assert registry.get("tensile.necking_candidate").order < plugin.order
        assert registry.get("tensile.terminal_domain").order < plugin.order
        assert plugin.order < registry.get("tensile.model_anchor").order
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert all(one.property_key is None for one in plugin.makes_values)
        assert {one.key for one in plugin.makes_values} == {
            "model_curve_changed_points",
            "model_curve_peak_stress",
            "model_curve_peak_strain",
            "model_curve_peak_index",
            "model_curve_max_raise",
            "model_curve_end_raise",
        }
        params = {one.name: one for one in plugin.params}
        assert params["method"].type == "choice"
        assert params["method"].default == "upper_envelope_auto_v1"
        assert params["method"].choice_labels == {
            "upper_envelope_auto_v1": "상측 포락선(자동)"
        }
        assert params["strain"].default == "strain_engineering"
        assert params["stress"].default == "stress_engineering"
        assert plugin.makes_values[2].key == "model_curve_peak_strain"
        assert plugin.makes_values[3].help is not None
        assert "0부터 세는 행 위치" in plugin.makes_values[3].help


class Test상측_포락선:
    @pytest.mark.parametrize(
        ("stress", "expected"),
        [
            # A 0.4% dip is raised without a detector threshold.
            ([100.0, 99.6, 100.1, 100.0], [100.0, 100.0, 100.1, 100.1]),
            # Later recovery and a higher peak do not rejoin the measured tail.
            ([5.0, 8.0, 4.0, 7.0, 9.0, 3.0, 10.0, 8.0], [5, 8, 8, 8, 9, 9, 10, 10]),
            # A single high spike propagates through every following input row.
            ([1.0, 2.0, 50.0, 2.0, 3.0], [1, 2, 50, 50, 50]),
            # The first negative measurement is the running maximum until it rises.
            ([-5000.0, 100.0, 80.0], [-5000, 100, 100]),
        ],
    )
    def test_누적_최댓값을_모든_입력_행에_적용한다(
        self, stress: list[float], expected: list[float]
    ) -> None:
        frame = _frame(stress)
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame)

        np.testing.assert_array_equal(
            result.frame.columns["stress_engineering"], np.asarray(expected, dtype=float)
        )
        assert result.frame.length() == len(stress)
        assert (
            result.frame.columns["stress_engineering"]
            is not frame.columns["stress_engineering"]
        )
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            if key != "stress_engineering":
                np.testing.assert_array_equal(result.frame.columns[key], values)

    def test_비감소_응력은_프레임과_선택_열을_그대로_쓴다(self) -> None:
        frame = _frame([1.0, 2.0, 2.0, 5.0])

        result = _run(frame)

        assert result.frame is frame
        assert (
            result.frame.columns["stress_engineering"] is frame.columns["stress_engineering"]
        )
        assert _scalar_map(result)["model_curve_changed_points"] == 0.0

    def test_진단값은_원응력_최댓값과_올림_폭을_기록한다(self) -> None:
        result = _run(_frame([1.0, 2.0, 50.0, 4.0, 5.0]))
        values = _scalar_map(result)

        assert values["model_curve_changed_points"] == 2.0
        assert values["model_curve_peak_stress"] == 50.0
        assert values["model_curve_peak_strain"] == 2.0
        assert values["model_curve_peak_index"] == 2.0
        assert values["model_curve_max_raise"] == 46.0
        assert values["model_curve_end_raise"] == 45.0
        assert all(np.isfinite(value) for value in values.values())
        peak_strain = next(
            one for one in result.stages[-1].scalars if one.key == "model_curve_peak_strain"
        )
        assert peak_strain.dimension == "strain"
        assert {one.key for one in result.stages[-1].scalars}.isdisjoint(
            {"youngs_modulus", "proof_stress", "proof_strain", "proof_offset"}
        )

    def test_유효_옵션은_기본값을_포함해_기록되고_그대로_재생된다(self) -> None:
        frame = _frame([1.0, 3.0, 2.0, 4.0])
        result = _run(frame)
        effective = result.stages[-1].options

        assert effective == {
            "method": "upper_envelope_auto_v1",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
            "domain": "all_input_rows",
            "tail_policy": "hold_running_max",
            "profile_version": "1",
        }
        replay = _run(frame, effective)
        np.testing.assert_array_equal(
            replay.frame.columns["stress_engineering"],
            result.frame.columns["stress_engineering"],
        )

    @pytest.mark.parametrize(
        ("option", "value", "message"),
        [
            ("domain", "cropped_rows", "'domain' 정책은"),
            ("tail_policy", "rejoin_peak", "'tail_policy' 정책은"),
            ("profile_version", "2", "'profile_version' 정책은"),
            ("terminal_action", "keep", "지원하지 않는"),
            ("threshold", 0.005, "지원하지 않는"),
            ("min_slope", 0.0, "지원하지 않는"),
            ("method", "upper_envelope_v2", "'method' 는"),
        ],
    )
    def test_지원하지_않는_옵션과_정책_변경은_거절한다(
        self, option: str, value: object, message: str
    ) -> None:
        with pytest.raises(ProcessingError) as error:
            _run(_frame([1.0, 2.0, 1.0]), {option: value})

        assert message in str(error.value)

    def test_사용자_열_이름과_SI_단위를_검사한다(self) -> None:
        frame = Frame(
            {
                "epsilon": np.asarray([0.0, 0.1, 0.2]),
                "sigma": np.asarray([10.0, 9.0, 11.0]),
                "source": np.asarray([7.0, 8.0, 9.0]),
            },
            {"epsilon": "1", "sigma": "Pa", "source": "1"},
        )

        result = _run(frame, {"strain": "epsilon", "stress": "sigma"})

        assert result.frame.columns["sigma"].tolist() == [10.0, 10.0, 11.0]
        assert result.frame.columns["source"] is frame.columns["source"]
        assert result.stages[-1].options["strain"] == "epsilon"
        assert result.stages[-1].options["stress"] == "sigma"


class Test입력_검증:
    @pytest.mark.parametrize(
        ("strain", "stress", "units", "message"),
        [
            ([0.0, 0.1, 0.2], [1.0, 2.0, 3.0], {"stress_engineering": "Pa"}, "단위"),
            (
                [0.0, 0.1, 0.2],
                [1.0, 2.0, 3.0],
                {"strain_engineering": "%", "stress_engineering": "Pa"},
                "현재 단위",
            ),
            (
                [0.0, 0.1, 0.2],
                [1.0, 2.0, 3.0],
                {"strain_engineering": "1", "stress_engineering": "MPa"},
                "현재 단위",
            ),
        ],
    )
    def test_단위가_누락되거나_다르면_단위_변환_없이_실패한다(
        self,
        strain: list[float],
        stress: list[float],
        units: dict[str, str],
        message: str,
    ) -> None:
        frame = _frame(stress, strain, units=units)

        with pytest.raises(ProcessingError, match=message):
            _run(frame)

    @pytest.mark.parametrize(
        ("strain", "stress", "message"),
        [
            ([0.0, 0.2, 0.1], [1.0, 2.0, 3.0], "원래 측정 행 순서를 검토"),
            ([0.0, 0.1, 0.1], [1.0, 2.0, 3.0], "자동 정렬하지 않습니다"),
            ([0.0], [1.0], "2점 이상"),
            ([0.0, 0.1, 0.2], [1.0, 2.0], "점 수가 다릅니다"),
            ([0.0, np.nan, 0.2], [1.0, 2.0, 3.0], "유한하지 않은 값"),
            ([0.0, 0.1, 0.2], [1.0, np.inf, 3.0], "유한하지 않은 값"),
            ([0.0, 0.1, 0.2], [-5.0, 0.0, -1.0], "양수인 값이 없습니다"),
        ],
    )
    def test_행_순서_길이_유한성_양수_응력을_검증한다(
        self, strain: list[float], stress: list[float], message: str
    ) -> None:
        with pytest.raises(ProcessingError, match=message):
            _run(_frame(stress, strain))

    def test_비숫자와_다차원_열은_거절한다(self) -> None:
        bad_stress = _frame(np.asarray([1.0, "bad", 3.0], dtype=object))
        with pytest.raises(ProcessingError, match="실수형 숫자"):
            _run(bad_stress)

        bad_strain = _frame([1.0, 2.0, 3.0], [[0.0, 0.1], [0.2, 0.3], [0.4, 0.5]])
        with pytest.raises(ProcessingError, match="1차원"):
            _run(bad_strain)

    def test_진단_차가_부동소수점_범위를_넘으면_유한하지_않은_값을_내지_않는다(self) -> None:
        with pytest.raises(ProcessingError, match="숫자 범위"):
            _run(_frame([1e308, -1e308, 1.0]))


class Test옥스퍼드_PC2_꼬리:
    def test_피크_뒤_모든_기록을_보존하며_공칭응력_상측값을_끝까지_유지한다(self) -> None:
        frame = _oxford_pc2()
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame)

        assert frame.length() == 1038
        assert result.frame.length() == 1038
        assert result.frame.columns["strain_engineering"][-1] == pytest.approx(1.0786575)
        assert frame.columns["stress_engineering"][0] == -5000.0
        assert result.frame.columns["stress_engineering"][0] == -5000.0
        assert frame.columns["stress_engineering"][-1] == 4_660_000.0
        assert result.frame.columns["stress_engineering"][-1] == 72_297_500.0
        assert (
            result.frame.columns["stress_engineering"]
            is not frame.columns["stress_engineering"]
        )
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            if key != "stress_engineering":
                np.testing.assert_array_equal(result.frame.columns[key], values)
        diagnostics = _scalar_map(result)
        assert diagnostics["model_curve_peak_stress"] == 72_297_500.0
        assert diagnostics["model_curve_peak_strain"] == pytest.approx(0.07437125)
        assert diagnostics["model_curve_peak_index"] == 72.0
        assert all(key.startswith("model_curve_") for key in diagnostics)
        assert all(np.isfinite(value) for value in diagnostics.values())
        assert "0~1.07866" in result.stages[-1].notes[0]
        assert "파단점으로 추정하지 않으며" in result.stages[-1].notes[1]
        assert "실제 완전소성으로 판정하지 않습니다" in result.stages[-1].notes[1]
