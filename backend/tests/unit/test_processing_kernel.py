"""처리 파이프라인 — **답을 아는 곡선으로 검산한다.**

수치 코드는 "돌아간다" 로는 아무것도 증명되지 않는다. 틀린 탄성계수도 실수로
나오고, 틀린 항복강도도 MPa 단위로 그럴듯하게 나온다. 그래서 여기서는 **답을
미리 아는 곡선**을 만들어 그 값이 나오는지 본다.

합성 곡선: E=200 GPa 의 탄성 구간 + 항복 400 MPa 뒤 선형 경화. 이 곡선의
0.2% 오프셋 항복강도와 탄성계수는 손으로 계산할 수 있다.

그리고 **실제 Zwick 파일**로 한 번 더 돌린다. 합성 데이터만 쓰면 "장비가 실제로
주는 모양" 에서 깨지는 것을 못 잡는다 — 실제로 그 종류의 결함을 여러 번 냈다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import parsers, processing
from matcore.parsers import zwick_tra
from matcore.processing import Frame, ProcessingError, Step

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 합성 곡선의 정답.
E_TRUE = 200e9
YIELD_TRUE = 400e6
HARDENING = 2e9


@pytest.fixture(autouse=True)
def _plugins() -> None:
    processing.load_builtin()


def synthetic() -> Frame:
    """E=200 GPa, 항복 400 MPa, 그 뒤 기울기 2 GPa 인 이상적 곡선."""
    yield_strain = YIELD_TRUE / E_TRUE  # 0.002
    elastic = np.linspace(0.0, yield_strain, 40)
    plastic = np.linspace(yield_strain, 0.10, 200)[1:]
    strain = np.concatenate([elastic, plastic])
    stress = np.where(
        strain <= yield_strain,
        E_TRUE * strain,
        YIELD_TRUE + HARDENING * (strain - yield_strain),
    )
    return Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


def scalar(result: processing.PipelineResult, key: str) -> float:
    for item in result.scalars:
        if item.key == key:
            return item.value
    raise AssertionError(f"{key} 가 결과에 없습니다: {[s.key for s in result.scalars]}")


class Test탄성계수:
    def test_아는_답이_나온다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {
                        "method": "linear_regression",
                        "minimum_strain": 0.0002,
                        "maximum_strain": 0.0015,
                    },
                )
            ],
            synthetic(),
        )
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=1e-6)
        assert scalar(result, "elastic_r_squared") == pytest.approx(1.0, abs=1e-9)

    def test_방법마다_값이_다르고_그_사실이_남는다(self) -> None:
        # 이상적 탄성 구간에서는 세 방법이 같아야 한다. 달라지면 구현이 틀린 것이다.
        frame = synthetic()
        values = {}
        for method in ("linear_regression", "chord", "secant"):
            result = processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"method": method, "minimum_strain": 0.0, "maximum_strain": 0.0015},
                    )
                ],
                frame,
            )
            values[method] = scalar(result, "youngs_modulus")
            # **무엇으로 쟀는지가 값과 함께 남아야** 나중에 비교가 성립한다.
            assert method in result.notes[0]
        for value in values.values():
            assert value == pytest.approx(E_TRUE, rel=1e-6)

    def test_항복_뒤까지_잡으면_R제곱이_떨어진다(self) -> None:
        # 값 자체는 나온다 — 그게 위험한 점이다. 그 사실은 R² 에만 보인다.
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0, "maximum_strain": 0.05},
                )
            ],
            synthetic(),
        )
        assert scalar(result, "elastic_r_squared") < 0.99
        assert any("R²" in note for note in result.notes)

    def test_점이_적으면_R제곱을_믿지_말라고_말한다(self) -> None:
        """**실측으로 걸린 것이다.**

        18점짜리 곡선에 좁은 구간을 잡으면 2점만 걸리고, 2점을 지나는 직선은
        언제나 R²=1 이다. 화면에 1.00000 이 찍히면 사람은 "완벽하게 맞았다" 로
        읽는데 실제로는 "정보가 없다" 다. 실제 `.tra` 로 돌렸을 때 그렇게
        6.9 GPa 가 R²=1 과 함께 나왔다 — 강판이면 200 GPa 여야 한다.
        """
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                )
            ],
            sparse,
        )
        assert scalar(result, "elastic_r_squared") == pytest.approx(1.0)
        assert any("믿을 수 없습니다" in note for note in result.notes)

    def test_구간에_점이_없으면_실제_범위를_알려_준다(self) -> None:
        with pytest.raises(ProcessingError, match="관측 범위는"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 5.0, "maximum_strain": 6.0},
                    )
                ],
                synthetic(),
            )


class Test항복강도:
    def test_0_2퍼센트_오프셋이_아는_답을_준다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0, "maximum_strain": 0.0015},
                ),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic(),
        )
        # 오프셋 선 stress = E*(e-0.002) 와 경화선 stress = 400M + 2G*(e-0.002)
        # 의 교점. 정리하면 (e-0.002) = 400e6 / (200e9-2e9) 이고, 그 지점의
        # 응력은 E * 그 값이다.
        expected = E_TRUE * (YIELD_TRUE / (E_TRUE - HARDENING))
        assert scalar(result, "proof_stress") == pytest.approx(expected, rel=2e-3)

    def test_앞_단계_값을_참조한다(self) -> None:
        # **사람이 E 를 두 번 적지 않아야 한다.** 손으로 옮기면 방법을 바꿔 다시
        # 쟀을 때 항복강도만 옛 값으로 남고, 그 결과는 그럴듯해 보인다.
        result = processing.apply(
            [
                Step("tensile.elastic_modulus", {"method": "manual", "manual_modulus": 150e9}),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic(),
        )
        assert result.stages[1].options["youngs_modulus"] == pytest.approx(150e9)

    def test_참조할_값이_없으면_어느_단계가_필요한지_말한다(self) -> None:
        with pytest.raises(ProcessingError, match="앞 단계가 내지 않았습니다"):
            processing.apply(
                [Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"})],
                synthetic(),
            )

    def test_만나지_않으면_외삽하지_않고_실패한다(self) -> None:
        """**이 테스트가 이 모듈의 태도 전부다.**

        탄성 구간만 측정된 곡선에 0.2% 오프셋을 걸면 교점이 없다. 외삽하면
        그럴듯한 항복강도가 나오고 아무도 의심하지 않는다.
        """
        strain = np.linspace(0.0, 0.001, 50)
        elastic_only = Frame(
            {"strain_engineering": strain, "stress_engineering": E_TRUE * strain},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="외삽해서 값을 만들지 않습니다"):
            processing.apply(
                [Step("tensile.proof_stress", {"youngs_modulus": E_TRUE})], elastic_only
            )


class Test진응력:
    def test_변환식이_맞다(self) -> None:
        result = processing.apply(
            [Step("tensile.true_plastic", {"youngs_modulus": E_TRUE})], synthetic()
        )
        frame = result.frame
        eng_strain = frame.columns["strain_engineering"]
        eng_stress = frame.columns["stress_engineering"]
        assert frame.columns["strain_true"] == pytest.approx(np.log1p(eng_strain))
        assert frame.columns["stress_true"] == pytest.approx(eng_stress * (1 + eng_strain))
        assert frame.units["stress_true"] == "Pa"

    def test_자르지_않으면_네킹_경고가_남는다(self) -> None:
        # 조용히 넘어가면 그 곡선으로 적합한 경화식이 네킹 후 구간까지 맞추려 든다.
        result = processing.apply(
            [Step("tensile.true_plastic", {"youngs_modulus": E_TRUE})], synthetic()
        )
        assert any("네킹 뒤 구간이 섞여" in note for note in result.notes)

    def test_음의_소성변형률을_어떻게_다뤘는지_남는다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.true_plastic",
                    {"youngs_modulus": E_TRUE, "negative_policy": "clip_zero"},
                )
            ],
            synthetic(),
        )
        assert np.all(result.frame.columns["strain_true_plastic"] >= 0)
        assert any("0 으로 잘랐습니다" in note for note in result.notes)


class Test네킹:
    def test_후보만_내고_아무것도_자르지_않는다(self) -> None:
        frame = synthetic()
        before = frame.length()
        result = processing.apply([Step("tensile.necking_candidate", {})], frame)
        assert result.frame.length() == before
        assert any("아무것도 자르지 않았습니다" in note for note in result.notes)


class Test정렬:
    def test_정렬되지_않은_입력을_계산이_거절한다(self) -> None:
        # **np.interp 는 정렬을 검사하지 않는다.** 오류 없이 엉뚱한 값을 낸다.
        shuffled = synthetic()
        order = np.arange(shuffled.length())[::-1]
        reversed_frame = shuffled.select(order)
        with pytest.raises(ProcessingError, match="sort_unique"):
            processing.apply([Step("tensile.elastic_modulus", {})], reversed_frame)

    def test_정렬_단계가_중복을_정리한다(self) -> None:
        frame = Frame(
            {"x": np.array([2.0, 1.0, 1.0, 3.0]), "y": np.array([20.0, 10.0, 12.0, 30.0])},
            {"x": "1", "y": "Pa"},
        )
        result = processing.apply(
            [Step("curve.sort_unique", {"x": "x", "duplicate_policy": "mean"})], frame
        )
        assert result.frame.columns["x"] == pytest.approx([1.0, 2.0, 3.0])
        assert result.frame.columns["y"] == pytest.approx([11.0, 20.0, 30.0])
        assert "중복 1점" in result.notes[0]

    def test_거절_정책은_거절한다(self) -> None:
        frame = Frame({"x": np.array([1.0, 1.0])}, {"x": "1"})
        with pytest.raises(ProcessingError, match="같은 값이 1개"):
            processing.apply(
                [Step("curve.sort_unique", {"x": "x", "duplicate_policy": "reject"})], frame
            )


class Test재샘플:
    def test_관측_밖은_만들어_내지_않는다(self) -> None:
        with pytest.raises(ProcessingError, match="측정하지 않은 구간"):
            processing.apply(
                [Step("curve.resample", {"x": "strain_engineering", "end": 99.0})],
                synthetic(),
            )

    def test_격자_위로_보간한다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "curve.resample",
                    {"x": "strain_engineering", "count": 51, "start": 0.0, "end": 0.05},
                )
            ],
            synthetic(),
        )
        assert result.frame.length() == 51
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(0.0)


class Test단위:
    def test_변형률이_퍼센트면_거절한다(self) -> None:
        # 저장 단위는 고를 수 있는 것이 아니다. 여기서 안 막으면 100배 어긋난다.
        frame = Frame(
            {
                "strain_engineering": np.linspace(0, 5, 10),
                "stress_engineering": np.linspace(0, 4e8, 10),
            },
            {"strain_engineering": "%", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="무차원 변형률"):
            processing.apply([Step("tensile.elastic_modulus", {})], frame)

    def test_응력이_MPa면_거절한다(self) -> None:
        frame = Frame(
            {
                "strain_engineering": np.linspace(0, 0.05, 10),
                "stress_engineering": np.linspace(0, 400, 10),
            },
            {"strain_engineering": "1", "stress_engineering": "MPa"},
        )
        with pytest.raises(ProcessingError, match="Pa 여야"):
            processing.apply([Step("tensile.elastic_modulus", {})], frame)


class Test실제장비파일:
    """**합성 데이터만으로는 장비가 주는 모양에서 깨지는 것을 못 잡는다.**"""

    def frame(self) -> Frame:
        parsers.load_builtin()
        parsed = zwick_tra.parse(TRA.read_bytes())
        curve = parsed.all_curves[0]
        columns = {
            channel.key: np.asarray(
                [np.nan if v is None else v for v in channel.values], dtype=np.float64
            )
            for channel in curve.channels
        }
        units = {channel.key: channel.si_unit for channel in curve.channels}
        return Frame(columns, units)

    def test_변위_하중에서_물성까지_이어진다(self) -> None:
        frame = self.frame()
        assert "displacement" in frame.columns, sorted(frame.columns)
        assert "force" in frame.columns

        # 시편 치수는 곡선에 없다 — 시편 기록에서 온다. 여기서는 실측 폭을 쓴다.
        width = float(np.nanmedian(frame.columns["specimen_width"]))
        thickness = 1.0e-3
        result = processing.apply(
            [
                Step("tensile.engineering", {"gauge_length": 0.05, "area": width * thickness}),
                Step(
                    "curve.sort_unique",
                    {"x": "strain_engineering", "duplicate_policy": "mean"},
                ),
                Step("tensile.strength", {}),
                Step("tensile.necking_candidate", {}),
            ],
            frame,
        )
        uts = scalar(result, "tensile_strength")
        # 강판이면 100 MPa ~ 2 GPa 사이다. 자릿수가 틀리면 면적·단위가 어긋난 것이다.
        assert 1e8 < uts < 2e9, f"인장강도가 {uts / 1e6:.4g} MPa 로 물리적이지 않습니다"
        assert result.frame.units["stress_engineering"] == "Pa"

    def test_실패한_단계에서_멈추고_어디서인지_말한다(self) -> None:
        with pytest.raises(ProcessingError, match="2단계"):
            processing.apply(
                [
                    Step("tensile.engineering", {"gauge_length": 0.05, "area": 1e-5}),
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 9.0, "maximum_strain": 10.0},
                    ),
                    Step("tensile.strength", {}),
                ],
                self.frame(),
            )


def test_등록되지_않은_단계는_코드라고_말한다() -> None:
    # 프로파일(데이터)과 처리(코드)의 경계를 화면이 분명히 보여 줘야 한다.
    with pytest.raises(ProcessingError, match="정의만으로는 만들 수 없습니다"):
        processing.apply([Step("tensile.made_up", {})], synthetic())
