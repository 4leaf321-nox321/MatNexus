"""Common tensile model-domain prefix selection."""

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
    time: object | None = None,
    units: dict[str, str] | None = None,
    extra: dict[str, object] | None = None,
) -> Frame:
    y = np.asarray(stress)
    x = np.linspace(0.0, 1.0, len(y)) if strain is None else np.asarray(strain)
    columns: dict[str, np.ndarray] = {
        "strain_engineering": x,
        "stress_engineering": y,
        "source_channel": np.arange(len(y), dtype=float),
    }
    if time is not None:
        columns["time"] = np.asarray(time)
    if extra:
        columns.update({key: np.asarray(values) for key, values in extra.items()})
    unit_map = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "source_channel": "1",
        "time": "s",
    }
    if extra:
        unit_map.update({key: "1" for key in extra})
    if units is not None:
        unit_map.update(units)
    return Frame(columns, unit_map)


def _run(frame: Frame, options: dict[str, object] | None = None) -> processing.PipelineResult:
    return processing.apply([Step("tensile.terminal_domain", options or {})], frame)


def _scalars(result: processing.PipelineResult) -> dict[str, float]:
    return {one.key: one.value for one in result.stages[-1].scalars}


def _notes(result: processing.PipelineResult) -> str:
    return "\n".join(result.stages[-1].notes)


def _oxford_pc2() -> Frame:
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    displacement_mm = np.asarray([float(row["displacement_mm"]) for row in rows])
    force_n = np.asarray([float(row["force_N"]) for row in rows])
    return Frame(
        {
            "displacement": displacement_mm * 1e-3,
            "force": force_n,
            "time": np.asarray([float(row["time_s"]) for row in rows]),
            "source_excel_row": np.asarray([int(row["source_excel_row"]) for row in rows]),
            "strain_engineering": displacement_mm / 80.0,
            "stress_engineering": force_n / 40e-6,
        },
        {
            "displacement": "m",
            "force": "N",
            "time": "s",
            "source_excel_row": "1",
            "strain_engineering": "1",
            "stress_engineering": "Pa",
        },
    )


class Test등록:
    def test_확장_로더를_거치며_말단과_모델_단계_사이에_정렬된다(self) -> None:
        plugin = registry.get("tensile.terminal_domain")

        assert plugin.kind == "processing"
        assert plugin.label == "인장 모델 말단 구간"
        assert plugin.order == 81
        assert plugin.version == "1"
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert registry.get("tensile.necking_candidate").order < plugin.order
        assert plugin.order < registry.get("tensile.model_curve").order
        assert plugin.order < registry.get("tensile.model_anchor").order
        assert all(one.property_key is None for one in plugin.makes_values)
        assert {
            "terminal_domain_end_index",
            "terminal_domain_end_strain",
            "terminal_domain_removed_points",
        }.issubset({one.key for one in plugin.makes_values})
        params = {one.name: one for one in plugin.params}
        assert params["policy"].default == "terminal_loss_auto_v1"
        assert params["end_index"].type == "int"
        assert params["end_index"].when == {"policy": ("manual_end_v1",)}
        assert params["time"].role == "column"
        assert params["time"].default is None


class Test자동_말단_선택:
    def test_공칭_응력에서_마지막_단일_급락점만_제외한다(self) -> None:
        stress = np.asarray([100.0] * 10 + [0.0])
        frame = _frame(stress)
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame)

        assert result.frame.length() == 10
        assert result.frame.columns["strain_engineering"][-1] == pytest.approx(0.9)
        assert _scalars(result)["terminal_domain_end_index"] == 9.0
        assert _scalars(result)["terminal_domain_removed_points"] == 1.0
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            np.testing.assert_array_equal(result.frame.columns[key], values[:10])

    def test_짧은_감소_연결의_가장_이른_후보만_쓴다(self) -> None:
        stress = np.asarray([100.0] * 29 + [89.0, 77.0, 70.0])

        result = _run(_frame(stress))

        assert result.frame.length() == 29
        assert _scalars(result)["terminal_domain_end_index"] == 28.0
        assert "chain_2" in _notes(result)
        assert "첫 제외 행 29" in _notes(result)

    def test_후보_국소하중은_초기_고립_최댓값으로_부풀지_않는다(self) -> None:
        stress = np.asarray([100.0, 100.0, 500.0] + [100.0] * 7 + [0.0])

        result = _run(_frame(stress))

        assert result.frame.length() == 10
        assert "L=100 Pa" in _notes(result)

    def test_음의_초기_응력은_그대로_남기고_오프셋하지_않는다(self) -> None:
        stress = np.asarray([-5000.0] + [100.0] * 9 + [0.0])

        result = _run(_frame(stress))

        assert result.frame.length() == 10
        assert result.frame.columns["stress_engineering"][0] == -5000.0
        assert _scalars(result)["terminal_domain_removed_points"] == 1.0

    def test_안정된_낮은_하중_꼬리는_자동_자르기를_보류한다(self) -> None:
        with pytest.raises(ProcessingError, match="ambiguous_stable_low_suffix") as error:
            _run(_frame([100.0] * 10 + [70.0]))

        assert "후보 유지 행 9" in str(error.value)

    def test_샘플링_간격이_급락_연결을_가로지르면_보류한다(self) -> None:
        time = np.asarray([row * 0.0001 for row in range(28)] + [0.9, 0.9002, 0.92, 1.0])
        stress = np.asarray([100.0] * 29 + [89.0, 70.0, 0.0])

        with pytest.raises(ProcessingError, match="ambiguous_sampling_gap") as error:
            _run(_frame(stress, time=time))

        assert "후보 유지 행 28" in str(error.value)
        assert "29→30" in str(error.value)

    def test_회복된_내부_급락은_간격_경고도_자르기도_하지_않는다(self) -> None:
        time = np.asarray([row * 0.0001 for row in range(28)] + [0.9, 0.9002, 0.92, 1.0])
        stress = np.asarray([100.0] * 29 + [89.0, 70.0, 100.0])

        result = _run(_frame(stress, time=time))

        assert result.frame.length() == len(stress)
        assert "no_abrupt_terminal_loss" in _notes(result)

    def test_완만한_마지막_감소는_남기고_미해결이라고_쓴다(self) -> None:
        stress = np.concatenate((np.full(89, 100.0), np.linspace(100.0, 88.0, 12)))

        result = _run(_frame(stress))

        assert result.frame.length() == len(stress)
        assert "gradual_tail_unresolved" in _notes(result)
        assert "물리적으로 유효하다고 판정한 것은 아닙니다" in _notes(result)

    def test_양수_응력이_없는_입력은_보존하고_진행축은_보고한다(self) -> None:
        result = _run(_frame(np.linspace(-5.0, -1.0, 5)))

        assert result.frame.length() == 5
        assert _scalars(result)["terminal_domain_progress_basis_code"] == 1.0
        assert "변형률 을 사용" in _notes(result)


class Test진행축:
    def test_유효한_시간은_비단조_변형률보다_먼저_쓴다(self) -> None:
        strain = np.asarray([0.0, 0.2, 0.15, 0.4])
        result = _run(_frame([10.0, 11.0, 12.0, 13.0], strain, time=[0, 1, 2, 3]))

        assert result.frame.length() == 4
        assert _scalars(result)["terminal_domain_progress_basis_code"] == 2.0
        assert _scalars(result)["terminal_domain_strain_strict"] == 0.0
        assert "변형률은 원래 행 순서에서 엄격히 증가하지 않습니다" in _notes(result)

    def test_잘못된_시간_단위는_변형률로_대체하고_이유를_남긴다(self) -> None:
        frame = _frame([10.0, 11.0, 12.0, 13.0], time=[0, 1, 2, 3], units={"time": "ms"})

        result = _run(frame)

        assert _scalars(result)["terminal_domain_progress_basis_code"] == 1.0
        assert "단위가 'ms' 이므로 초로 읽지 않았습니다" in _notes(result)

    def test_시간과_변형률을_쓸_수_없으면_행순서로_대체한다(self) -> None:
        frame = _frame(
            [10.0, 11.0, 12.0, 13.0],
            [0.0, 0.2, 0.2, 0.1],
            units={"time": "ms"},
        )

        result = _run(frame)

        assert _scalars(result)["terminal_domain_progress_basis_code"] == 0.0
        assert "원래 행 순서" in _notes(result)
        assert "실제 시간·변형률 간격을 증명하지 않습니다" in _notes(result)

    def test_비단조_변형률은_정렬하지_않고_행순서로_처리한다(self) -> None:
        strain = np.asarray([0.0, 0.2, 0.1, 0.3])
        result = _run(_frame([10.0, 11.0, 12.0, 13.0], strain))

        assert result.frame.columns["strain_engineering"].tolist() == strain.tolist()
        assert _scalars(result)["terminal_domain_progress_basis_code"] == 0.0
        assert _scalars(result)["terminal_domain_strain_strict"] == 0.0
        assert "변형률은 원래 행 순서에서 엄격히 증가하지 않습니다" in _notes(result)


class Test수동_끝행과_옵션:
    def test_수동_끝행은_모든_열에_같은_포함_접두구간을_적용하고_재생된다(self) -> None:
        frame = _frame(
            np.linspace(10.0, 20.0, 8),
            time=np.arange(8, dtype=float),
            extra={"source_index": np.arange(20, 28)},
        )
        before = {key: values.copy() for key, values in frame.columns.items()}
        options = {"policy": "manual_end_v1", "end_index": 5}

        result = _run(frame, options)
        effective = result.stages[-1].options
        replay = _run(frame, effective)

        assert result.frame.length() == 6
        assert effective["policy"] == "manual_end_v1"
        assert effective["end_index"] == 5
        assert "support_window_rows" in effective
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            np.testing.assert_array_equal(result.frame.columns[key], values[:6])
            np.testing.assert_array_equal(replay.frame.columns[key], values[:6])
        assert _scalars(result)["terminal_domain_removed_points"] == 2.0

    def test_수동_전체끝은_프레임을_그대로_두고_끝행도_유효하다(self) -> None:
        frame = _frame([10.0, 11.0, 12.0])

        result = _run(frame, {"policy": "manual_end_v1", "end_index": 2})

        assert result.frame is frame
        assert "행 0~2 를 모두 유지했습니다" in _notes(result)

    @pytest.mark.parametrize(
        ("options", "message"),
        [
            ({"policy": "manual_end_v1"}, "end_index"),
            ({"policy": "manual_end_v1", "end_index": True}, "bool 이 아닌 정수"),
            ({"policy": "manual_end_v1", "end_index": 0}, "1~2 사이"),
            ({"policy": "manual_end_v1", "end_index": 3}, "1~2 사이"),
            ({"end_index": 1}, "자동 정책은"),
            ({"terminal_action": "keep"}, "지원하지 않는 말단 구간 옵션"),
            ({"stable_suffix_range_fraction": 0.2}, "고정되어 있습니다"),
        ],
    )
    def test_알_수_없는_또는_다른_정책_옵션은_거절한다(
        self, options: dict[str, object], message: str
    ) -> None:
        with pytest.raises(ProcessingError, match=message):
            _run(_frame([1.0, 2.0, 3.0]), options)


class Test입력_검증:
    @pytest.mark.parametrize(
        ("units", "message"),
        [
            ({"strain_engineering": "%", "stress_engineering": "Pa"}, "현재 단위"),
            ({"strain_engineering": "1", "stress_engineering": "MPa"}, "현재 단위"),
        ],
    )
    def test_변형률과_응력은_지정_단위만_받는다(
        self, units: dict[str, str], message: str
    ) -> None:
        with pytest.raises(ProcessingError, match=message):
            _run(_frame([1.0, 2.0, 3.0], units=units))

    def test_변형률_단위가_없으면_명시적으로_실패한다(self) -> None:
        frame = Frame(
            {
                "strain_engineering": np.asarray([0.0, 0.1, 0.2]),
                "stress_engineering": np.asarray([1.0, 2.0, 3.0]),
            },
            {"stress_engineering": "Pa"},
        )

        with pytest.raises(ProcessingError, match="단위는 '1' 이어야"):
            _run(frame)

    def test_단위_목록에만_있는_응력열은_명시적_입력오류다(self) -> None:
        frame = Frame(
            {"strain_engineering": np.asarray([0.0, 0.1, 0.2])},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        with pytest.raises(ProcessingError, match=r"응력.*stress_engineering"):
            _run(frame)

    @pytest.mark.parametrize(
        ("strain", "stress", "message"),
        [
            ([0.0], [1.0], "2점 이상"),
            ([0.0, 0.1, 0.2], [1.0, 2.0], "점 수가 맞지 않습니다"),
            ([0.0, np.nan, 0.2], [1.0, 2.0, 3.0], "유한하지 않은 값"),
            ([0.0, 0.1, 0.2], [1.0, np.inf, 3.0], "유한하지 않은 값"),
        ],
    )
    def test_순서_길이_수치_범위를_검증한다(
        self, strain: list[float], stress: list[float], message: str
    ) -> None:
        with pytest.raises(ProcessingError, match=message):
            _run(_frame(stress, strain))

    def test_응력은_실수형이어야_하고_모든열은_1차원_같은길이다(self) -> None:
        with pytest.raises(ProcessingError, match="실수형 숫자"):
            _run(_frame(np.asarray([1.0, "bad", 3.0], dtype=object)))
        with pytest.raises(ProcessingError, match="1차원"):
            _run(_frame([1.0, 2.0, 3.0], extra={"matrix": [[1, 2], [3, 4], [5, 6]]}))
        with pytest.raises(ProcessingError, match="점 수가 맞지 않습니다"):
            _run(_frame([1.0, 2.0, 3.0], extra={"short": [1.0, 2.0]}))


class Test옥스퍼드_PC2:
    def test_공통_말단_선택은_행1038을_남기고_나머지_두행만_제외한다(self) -> None:
        frame = _oxford_pc2()
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame)

        assert frame.length() == 1038
        assert result.frame.length() == 1036
        assert result.frame.columns["source_excel_row"][-1] == 1038
        assert _scalars(result)["terminal_domain_end_index"] == 1035.0
        assert _scalars(result)["terminal_domain_removed_points"] == 2.0
        assert _scalars(result)["terminal_domain_end_strain"] == pytest.approx(
            frame.columns["strain_engineering"][1035]
        )
        end_strain = next(
            one for one in result.stages[-1].scalars if one.key == "terminal_domain_end_strain"
        )
        assert end_strain.dimension == "strain"
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
            np.testing.assert_array_equal(result.frame.columns[key], values[:1036])
        assert _notes(result).find("첫 제외 행 1036") >= 0
        assert all(key.startswith("terminal_domain_") for key in _scalars(result))
        assert all(np.isfinite(value) for value in _scalars(result).values())
