"""Common tensile model-domain prefix selection."""

from __future__ import annotations

import base64
import csv
import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "oxford_pc_fig5_50mm_min_test2.csv"
)
R16_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "tensile_terminal_v2_cases.npz"
)
R15_RECIPES = (
    Path(__file__).resolve().parents[2]
    / "extensions"
    / "tensile_extras"
    / "recipes"
    / "adaptive_plastic_domain_v1_examples.json"
)
R16_RECIPES = (
    Path(__file__).resolve().parents[2]
    / "extensions"
    / "tensile_extras"
    / "recipes"
    / "progressive_terminal_domain_v2_examples.json"
)
V2_OPTIONS: dict[str, object] = {
    "policy": "terminal_loss_auto_v2",
    "strain": "strain_engineering",
    "stress": "stress_engineering",
    "time": "time",
}
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


def _r16_source_frame(case_index: int) -> Frame:
    prefix = f"c{case_index:03d}_"
    with np.load(R16_FIXTURE, allow_pickle=False) as archive:
        columns = {
            "strain_engineering": archive[f"{prefix}x"].copy(),
            "stress_engineering": archive[f"{prefix}y"].copy(),
            "time": archive[f"{prefix}time"].copy(),
            "source_row": archive[f"{prefix}row"].copy(),
            "displacement": archive[f"{prefix}displacement_m"].copy(),
            "force": archive[f"{prefix}force_N"].copy(),
            "prepared_row": archive[f"{prefix}prepared_row"].copy(),
        }
        source_excel_row = f"{prefix}source_excel_row"
        if source_excel_row in archive:
            columns["source_excel_row"] = archive[source_excel_row].copy()
    return Frame(
        columns,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "time": "s",
            "source_row": "1",
            "displacement": "m",
            "force": "N",
            "prepared_row": "1",
            **({"source_excel_row": "1"} if "source_excel_row" in columns else {}),
        },
    )


class Test등록:
    def test_확장_로더를_거치며_말단과_모델_단계_사이에_정렬된다(self) -> None:
        plugin = registry.get("tensile.terminal_domain")

        assert plugin.kind == "processing"
        assert plugin.label == "인장 시험 종료 구간"
        assert plugin.order == 20
        assert plugin.version == "2"
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert registry.get("tensile.engineering").order < plugin.order
        assert plugin.order < registry.get("tensile.elastic_modulus").order
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
        assert "terminal_loss_auto_v2" in params["policy"].choices
        assert params["end_index"].type == "int"
        assert params["end_index"].when == {"policy": ("manual_end_v1",)}
        assert params["time"].role == "column"
        assert params["time"].default is None
        assert "초 단위" in (params["time"].help or "")
        assert "마지막 10%" in params["policy"].choice_help["terminal_loss_auto_v1"]
        assert "현재 입력 프레임" in params["policy"].choice_help["manual_end_v1"]
        assert "현재 입력 프레임" in (params["end_index"].help or "")
        assert "근사" in (params["policy"].choice_help["terminal_loss_auto_v2"] or "")
        assert "terminal_domain_v2_near_optimal_knot_span" in {
            one.key for one in plugin.makes_values
        }


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


class Test점진적_말단_가속_시작_v2:
    def test_일곱_R16_레시피는_R15의_말단정책만_바꾼다(self) -> None:
        r15 = json.loads(R15_RECIPES.read_text(encoding="utf-8"))
        r16 = json.loads(R16_RECIPES.read_text(encoding="utf-8"))

        assert len(r15["recipes"]) == len(r16["recipes"]) == 7
        for old_recipe, new_recipe in zip(r15["recipes"], r16["recipes"], strict=True):
            assert len(old_recipe["steps"]) == len(new_recipe["steps"])
            for old_step, new_step in zip(
                old_recipe["steps"], new_recipe["steps"], strict=True
            ):
                if old_step["plugin"] == "tensile.terminal_domain":
                    assert new_step["plugin"] == old_step["plugin"]
                    assert old_step["options"]["policy"] == "terminal_loss_auto_v1"
                    assert new_step["options"]["policy"] == "terminal_loss_auto_v2"
                    assert {
                        key: value
                        for key, value in old_step["options"].items()
                        if key != "policy"
                    } == {
                        key: value
                        for key, value in new_step["options"].items()
                        if key != "policy"
                    }
                else:
                    assert new_step == old_step
            assert any(
                step["plugin"] == "tensile.plastic_domain" for step in new_recipe["steps"]
            )
            assert any(
                step.get("options", {}).get("duplicate_policy") == "first"
                for step in new_recipe["steps"]
            )

    def test_구성한_상승_선행부와_말단_가속을_자르고_JSON_옵션으로_재생한다(self) -> None:
        progress = np.linspace(0.0, 1.0, 501)
        stress = np.where(
            progress <= 0.84,
            100.0 + 2.0 * progress,
            100.0 + 2.0 * 0.84 - 100.0 * (progress - 0.84),
        )
        frame = _frame(stress, time=progress)
        before = {key: values.copy() for key, values in frame.columns.items()}

        legacy_default = _run(frame)
        legacy_explicit = _run(frame, {"policy": "terminal_loss_auto_v1"})
        assert legacy_default.frame is frame
        assert legacy_explicit.frame is frame
        assert legacy_default.stages[-1].notes == legacy_explicit.stages[-1].notes
        assert legacy_default.stages[-1].options == legacy_explicit.stages[-1].options

        result = _run(frame, V2_OPTIONS)
        values = _scalars(result)
        assert values["terminal_domain_decision_code"] == 3.0
        assert values["terminal_domain_v2_onset_status_code"] == 1.0
        assert (
            values["terminal_domain_end_index"] == values["terminal_domain_v2_candidate_index"]
        )
        assert values["terminal_domain_end_index"] < len(stress) - 1
        assert values["terminal_domain_v2_pre_slope_per_progress"] > 0.0
        assert "progressive_terminal_loss_onset" in _notes(result)
        assert "파단 판정은 아닙니다" in _notes(result)
        assert all(np.isfinite(value) for value in values.values())

        effective = result.stages[-1].options
        replay_options = json.loads(json.dumps(effective))
        replay = _run(frame, replay_options)
        assert replay.stages[-1].options == effective
        assert replay.stages[-1].notes == result.stages[-1].notes
        assert _scalars(replay) == values
        assert effective["sensitivity_start_progress"] == [0.70, 0.75, 0.80]
        effective["sensitivity_start_progress"].append(0.85)
        fresh = _run(frame, V2_OPTIONS)
        assert fresh.stages[-1].options["sensitivity_start_progress"] == [
            0.70,
            0.75,
            0.80,
        ]
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)
            np.testing.assert_array_equal(
                result.frame.columns[key],
                original[: int(values["terminal_domain_end_index"]) + 1],
            )

    def test_고정된_v2_상수는_바꿀_수_없고_v1은_v2_옵션을_받지_않는다(self) -> None:
        frame = _frame([100.0] * 20, time=np.linspace(0.0, 1.0, 20))
        changed = {**V2_OPTIONS, "score_grid_points": 252}
        with pytest.raises(ProcessingError, match="고정되어 있습니다"):
            _run(frame, changed)
        with pytest.raises(ProcessingError, match="지원하지 않는 말단 구간 옵션"):
            _run(
                frame,
                {"policy": "terminal_loss_auto_v1", "minimum_late_progress": 0.80},
            )

    def test_점수_시작을_가로지르는_큰_간격은_v2_앞당김을_보류한다(self) -> None:
        # Constructed lower-window-boundary regression; it is not a real-data case.
        before_gap = np.linspace(0.0, 0.70, 901)
        after_gap = np.linspace(0.78, 1.0, 151)[1:]
        progress = np.concatenate((before_gap, after_gap))
        stress = np.where(
            progress <= 0.84,
            100.0,
            100.0 - 100.0 * (progress - 0.84),
        )
        result = _run(_frame(stress, time=progress), V2_OPTIONS)

        assert result.frame.length() == len(progress)
        assert "significant_intersecting_progress_gap" in _notes(result)
        values = _scalars(result)
        assert values["terminal_domain_v2_intersecting_gap_count"] >= 1.0
        assert values["terminal_domain_v2_candidate_index"] < len(progress)

    def test_점수_격자만_충분하고_원래행이_성기면_잘라내지_않는다(self) -> None:
        # Constructed sparse-support regression; it does not add a source-corpus count.
        progress = np.concatenate(
            (np.linspace(0.0, 0.72, 100), [0.76, 0.78, 0.80], np.linspace(0.82, 1.0, 25))
        )
        stress = np.where(
            progress <= 0.82,
            100.0,
            100.0 - 100.0 * (progress - 0.82),
        )
        result = _run(_frame(stress, time=progress), V2_OPTIONS)

        assert result.frame.length() == len(progress)
        assert "insufficient_original_row_support" in _notes(result)
        assert _scalars(result)["terminal_domain_v2_onset_status_code"] == 0.0

    @pytest.mark.parametrize(
        ("case_index", "old_end", "expected_end"),
        [
            (85, 588, 555),  # DP980 gradual decline
            (96, 527, 503),  # DP1180 gradual decline
            (107, 4982, 4782),  # jagged 304L persistent tail loss
            (130, 655, 600),  # original 304 pre-abrupt shoulder
            (151, 330, 308),  # rising-pre 2024 shoulder
            (118, 2586, 2586),  # BT3 internal dip and recovery control
            (60, 209, 209),  # smooth 1018 decline without a distinct onset
        ],
    )
    def test_R16_실제_대표자료의_검토된_끝행과_모든_열을_보존한다(
        self, case_index: int, old_end: int, expected_end: int
    ) -> None:
        frame = _r16_source_frame(case_index)
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame, V2_OPTIONS)

        values = _scalars(result)
        assert values["terminal_domain_v2_old_end_index"] == float(old_end)
        assert values["terminal_domain_end_index"] == float(expected_end)
        assert result.frame.length() == expected_end + 1
        expected_decision_code = (
            3.0 if expected_end < old_end else 0.0 if old_end == frame.length() - 1 else 1.0
        )
        assert values["terminal_domain_decision_code"] == expected_decision_code
        assert np.all(np.diff(result.frame.columns["time"]) > 0.0)
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)
            np.testing.assert_array_equal(
                result.frame.columns[key], original[: expected_end + 1]
            )
        if case_index == 151:
            assert values["terminal_domain_v2_pre_slope_per_progress"] > 0.0
            assert values["terminal_domain_decision_code"] == 3.0
        if case_index == 118:
            assert "post_half_loss_recovery" in _notes(result)
        if case_index == 60:
            assert "substantial_preterminal_loss_no_distinct_onset" in _notes(result)

    def test_PC2_긴_저하중_평탄부는_v1_끝행에_남긴다(self) -> None:
        frame = _oxford_pc2()
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(frame, V2_OPTIONS)

        assert _scalars(result)["terminal_domain_v2_old_end_index"] == 1035.0
        assert _scalars(result)["terminal_domain_end_index"] == 1035.0
        assert "stable_loaded_final_suffix" in _notes(result)
        for key, original in before.items():
            np.testing.assert_array_equal(result.frame.columns[key], original[:1036])


# Genuine R14 corpus rows embedded to keep provenance regressions hermetic.
# Source manifest SHA-256:
# 5632db582dcaa89520de62933160a6b26ebca56fb2c494a64e313829d642d1df.
# Corpus SHA-256:
# 5e36230067d396bf8b41d53e26803e180f313e5d80e495c153b34384f15a97fc.
# M04DPMMA is manifest case 23; M12DPMMA is case 49.
_R14_FIXTURE_BASE64 = {
    "M04DPMMA": (
        "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"
    ),
    "M12DPMMA": (
        "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"
    ),
}


def _r14_source_frame(case_key: str) -> Frame:
    """Load exact acquired channels and prepared engineering columns for an R14 case."""
    with np.load(
        BytesIO(base64.b64decode(_R14_FIXTURE_BASE64[case_key])), allow_pickle=False
    ) as archive:
        columns = {
            "strain_engineering": archive["x"].copy(),
            "stress_engineering": archive["y"].copy(),
            "time": archive["time"].copy(),
            "source_row": archive["source_row"].copy(),
            "displacement": archive["displacement"].copy(),
            "force": archive["force"].copy(),
            "prepared_row": archive["prepared_row"].copy(),
        }
    return Frame(
        columns,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "time": "s",
            "source_row": "1",
            "displacement": "m",
            "force": "N",
            "prepared_row": "1",
        },
    )


def _r14_source_steps() -> list[Step]:
    return [
        Step(
            "tensile.terminal_domain",
            {
                "policy": "terminal_loss_auto_v1",
                "strain": "strain_engineering",
                "stress": "stress_engineering",
                "time": "time",
            },
        ),
        Step("tensile.strength", {}),
        Step("tensile.elastic_modulus", {"method": "auto"}),
        Step(
            "tensile.proof_stress",
            {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
        ),
    ]


class Test실제_보존원자료_물성:
    def test_M04_끝급락을_자른뒤_교점없는_Rp를_만들지_않는다(self) -> None:
        frame = _r14_source_frame("M04DPMMA")
        before = {key: values.copy() for key, values in frame.columns.items()}
        steps = [
            *_r14_source_steps(),
            Step("tensile.model_curve", {"method": "upper_envelope_auto_v1"}),
        ]

        with pytest.raises(ProcessingError) as error:
            processing.apply(steps, frame)

        done = error.value.done
        assert done is not None
        assert [stage.plugin for stage in done.stages] == [
            "tensile.terminal_domain",
            "tensile.strength",
            "tensile.elastic_modulus",
        ]
        assert "4단계" in str(error.value)
        assert done.frame.length() == 130

        values = {one.key: one.value for one in done.scalars}
        assert values["terminal_domain_end_index"] == 129.0
        assert values["terminal_domain_removed_points"] == 1.0
        assert values["terminal_domain_progress_basis_code"] == 2.0
        assert values["youngs_modulus"] == pytest.approx(
            2_939_721_764.132856, rel=1e-9, abs=1.0
        )
        assert values["tensile_strength"] == pytest.approx(
            73_611_718.76632309, rel=1e-9, abs=1.0
        )
        assert "proof_stress" not in values
        assert done.frame.columns["time"][-1] == 64.5
        assert frame.columns["time"][-1] == 64.85

        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)
            np.testing.assert_array_equal(done.frame.columns[key], original[:130])

    def test_M12_실제_신규엄격접두구간에서_보존원자료_E와_Rp를_계산한다(self) -> None:
        frame = _r14_source_frame("M12DPMMA")
        before = {key: values.copy() for key, values in frame.columns.items()}
        assert not np.all(np.diff(frame.columns["strain_engineering"]) > 0.0)

        with pytest.raises(ProcessingError) as old_error:
            processing.apply(
                [
                    Step("tensile.strength", {}),
                    Step("tensile.elastic_modulus", {"method": "auto"}),
                    Step(
                        "tensile.proof_stress",
                        {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
                    ),
                ],
                frame,
            )

        assert old_error.value.done is not None
        assert [stage.plugin for stage in old_error.value.done.stages] == ["tensile.strength"]
        assert "2단계" in str(old_error.value)

        steps = [
            *_r14_source_steps(),
            Step("tensile.necking_candidate", {}),
            Step("tensile.model_curve", {"method": "upper_envelope_auto_v1"}),
            Step(
                "tensile.model_anchor",
                {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
            ),
        ]

        result = processing.apply(steps, frame)

        assert [stage.plugin for stage in result.stages] == [
            "tensile.terminal_domain",
            "tensile.strength",
            "tensile.elastic_modulus",
            "tensile.proof_stress",
            "tensile.necking_candidate",
            "tensile.model_curve",
            "tensile.model_anchor",
        ]
        terminal = result.stages[0]
        assert frame.length() == 84
        assert terminal.frame.length() == 83
        terminal_values = {one.key: one.value for one in terminal.scalars}
        assert terminal_values["terminal_domain_end_index"] == 82.0
        assert terminal_values["terminal_domain_progress_basis_code"] == 2.0
        assert terminal.frame.columns["time"][-1] == 41.0
        assert frame.columns["time"][-1] == 41.21
        assert np.all(np.diff(terminal.frame.columns["strain_engineering"]) > 0.0)

        values = {one.key: one.value for one in result.scalars}
        assert values["youngs_modulus"] == pytest.approx(
            3_135_051_065.9258866, rel=1e-9, abs=1.0
        )
        assert values["proof_stress"] == pytest.approx(49_800_689.18077854, rel=1e-9, abs=1.0)
        assert values["proof_strain"] == pytest.approx(
            0.017885128546086607, rel=1e-9, abs=1e-12
        )
        assert values["tensile_strength"] == pytest.approx(
            67_760_217.02137445, rel=1e-9, abs=1.0
        )

        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)
            np.testing.assert_array_equal(terminal.frame.columns[key], original[:83])
        assert frame.units == terminal.frame.units
