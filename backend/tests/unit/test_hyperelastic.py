"""고무 초탄성 — **답을 아는 곡선으로 검산한다.**

실제 고무 데이터가 아직 없다. 그래서 65 가 한 것과 같은 방식으로 본다: 계수를
정해 곡선을 만들고, 그 곡선에서 **같은 계수가 되돌아오는지** 확인한다. 되돌아오지
않으면 식이 틀렸거나 초기값·경계가 잘못 잡힌 것이다.

여기서 지키는 것은 넷이다.

    계수가 되돌아온다            식과 적합기가 맞다
    축을 식이 선언한다           고무는 공칭, 금속은 진응력 — 섞이면 조용히 틀린다
    발산할 계수를 짚는다         적합은 됐는데 해석이 안 도는 경우가 있다
    재료군을 가른다              Voce 와 Ogden 을 RMSE 로 줄 세우면 안 된다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import fitting
from matcore.fitting import hyperelastic

fitting.load_builtin()


def curve(
    family: str, parameters: list[float], top: float = 2.0, points: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    """답을 아는 곡선. 공칭 변형률 0~top."""
    strain = np.linspace(0.0, top, points)
    stress = fitting.FAMILIES[family].evaluate(
        np.asarray(parameters, dtype=np.float64), strain
    )
    return strain, np.asarray(stress, dtype=np.float64)


class TestRoundTrip:
    """**계수가 되돌아오는가.**"""

    @pytest.mark.parametrize(
        ("family", "truth"),
        [
            ("ogden_1", [1.0e6, 3.0]),
            ("neo_hookean", [4.0e5]),
            ("mooney_rivlin", [3.0e5, 1.0e5]),
            ("yeoh", [4.0e5, -2.0e4, 5.0e3]),
        ],
    )
    def test_같은_계수가_되돌아온다(self, family: str, truth: list[float]) -> None:
        strain, stress = curve(family, truth)
        got = fitting.fit(family, strain, stress)
        for item, expected in zip(got.parameters, truth, strict=True):
            assert item.value == pytest.approx(expected, rel=1e-3, abs=1e-3 * abs(truth[0]))
        assert got.relative_rmse < 1e-6

    def test_다른_식은_다르게_틀린다(self) -> None:
        """**어느 것이 맞는지 고르지 않는다** — 나란히 주고 사람이 고른다."""
        strain, stress = curve("ogden_1", [1.0e6, 3.0])
        results = fitting.compare(strain, stress, families=("ogden_1", "neo_hookean", "yeoh"))
        assert next(item.family for item in results) == "ogden_1"
        # Neo-Hookean 은 지수가 고정이라 이 곡선을 못 따라간다.
        worst = next(item for item in results if item.family == "neo_hookean")
        assert worst.relative_rmse > 0.05

    def test_초기_전단탄성률을_함께_낸다(self) -> None:
        """식이 달라도 이 값은 비슷해야 한다 — **RMSE 하나로는 안 보이는 것**이다."""
        strain, stress = curve("ogden_1", [1.0e6, 3.0])
        got = fitting.fit("ogden_1", strain, stress)
        extras = fitting.FAMILIES["ogden_1"].extras(
            np.asarray([item.value for item in got.parameters])
        )
        assert extras["shear_modulus"] == pytest.approx(1.0e6, rel=1e-3)
        assert extras["mode"] == "단축 인장"


class TestAxes:
    """**축이 금속과 반대다.** 섞이면 덱은 돌고 재료만 딴판이 된다."""

    def test_고무는_공칭에_맞춘다(self) -> None:
        for key in ("ogden_1", "neo_hookean", "mooney_rivlin", "yeoh"):
            family = fitting.FAMILIES[key]
            assert family.x_column == "strain_engineering"
            assert family.y_column == "stress_engineering"
            assert family.x_label == "공칭 변형률"
            assert family.block == "hyperelastic"

    def test_금속은_진응력에_맞춘다(self) -> None:
        for key in ("voce", "swift", "hockett_sherby"):
            family = fitting.FAMILIES[key]
            assert family.x_column == "strain_true_plastic"
            assert family.block == "hardening"

    def test_메모가_소성변형률이라고_적지_않는다(self) -> None:
        """고무 카드에 "소성변형률 0~2 구간" 이라고 적히면 그것은 거짓말이다."""
        strain, stress = curve("ogden_1", [1.0e6, 3.0])
        got = fitting.fit("ogden_1", strain, stress)
        joined = " ".join(got.notes)
        assert "공칭 변형률" in joined
        assert "소성변형률" not in joined


class TestStability:
    def test_발산할_계수를_짚는다(self) -> None:
        """**적합은 되는데 해석이 안 돈다.** 막지 않고 말한다."""
        # 공칭 응력이 꺾여 내려가는 곡선. Yeoh 의 음수 항이 이런 모양을 낸다.
        strain = np.linspace(0.0, 3.0, 60)
        stress = fitting.FAMILIES["yeoh"].evaluate(np.asarray([3.0e5, -9.0e4, 2.0e3]), strain)
        got = fitting.fit("yeoh", strain, stress)
        assert any("감소합니다" in note for note in got.notes), got.notes

    def test_잘_생긴_곡선에는_안_짚는다(self) -> None:
        strain, stress = curve("ogden_1", [1.0e6, 3.0])
        got = fitting.fit("ogden_1", strain, stress)
        assert not any("감소합니다" in note for note in got.notes)


class TestPrepare:
    def test_식이_성립하지_않는_점을_걷는다(self) -> None:
        """**탄성 구간을 걷는 것이 아니다** — 초탄성은 그 구간도 설명한다."""
        strain = np.asarray([-1.5, -0.5, 0.0, 0.5, 1.0])
        stress = np.asarray([-1.0, -0.4, 0.0, 0.5, 1.0])
        x, _y, notes = hyperelastic.positive_stretch(strain, stress)
        assert len(x) == 4
        assert any("신축비가 0 이하" in note for note in notes)

    def test_원점에_겹친_점을_모은다(self) -> None:
        strain = np.asarray([0.0, 0.0, 0.0, 0.5, 1.0])
        stress = np.asarray([0.0, 0.0, 0.0, 0.5, 1.0])
        x, _y, notes = hyperelastic.positive_stretch(strain, stress)
        assert len(x) == 3
        assert any("한 점으로 모았습니다" in note for note in notes)


class TestApplies:
    def test_재료군을_가른다(self) -> None:
        """**Voce 와 Ogden 을 RMSE 로 줄 세우면 안 된다** — 같은 물음의 답이 아니다."""
        metal = {item.key for item in fitting.families_for("Metal")}
        rubber = {item.key for item in fitting.families_for("Rubber")}
        assert "voce" in metal and "ogden_1" not in metal
        assert "ogden_1" in rubber

    def test_재료를_모르면_전부_준다(self) -> None:
        """고를 재료가 없으면 감추지 않는다 — 감추면 왜 없는지 알 길이 없다."""
        every = {item.key for item in fitting.families_for(None)}
        assert {"voce", "ogden_1"} <= every
