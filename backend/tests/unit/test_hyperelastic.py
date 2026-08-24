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

from pathlib import Path

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


class Test실제_시험의_모양:
    """**깨끗한 합성 곡선은 실제 고무 시험처럼 생기지 않았다.**

    실제 고무 데이터가 아직 없어서(계획서 Phase 5) 지금까지는 답을 아는 매끈한
    곡선으로만 검산했다. 그런데 실제 시험에는 이런 것들이 있다 — 예비 사이클,
    토우, 하중셀 양자화, 무른/딱딱한 재료의 스케일 차이.

    **실물을 기다릴 이유가 없다.** 실제 시험이 어떻게 생겼는지만 알면 흉내낼 수
    있고, 실제로 그렇게 해서 결함 하나를 찾았다(예비 사이클, 2026-08-24).
    실물이 와도 이 시험들은 그대로 쓴다.
    """

    MU = 0.5e6
    ALPHA = 2.3

    def curve(self, strain: np.ndarray) -> np.ndarray:
        stretch = 1.0 + strain
        return (2.0 * self.MU / self.ALPHA) * (
            stretch ** (self.ALPHA - 1.0) - stretch ** (-self.ALPHA / 2.0 - 1.0)
        )

    def test_예비_사이클을_거절한다(self) -> None:
        """**정렬로 덮으면 조용히 틀린다.**

        고무는 Mullins 효과 때문에 3~5회 예비 사이클을 돌린 뒤 본시험을 잰다 —
        장비가 뱉는 파일에 올림·내림이 여러 벌 들어 있다는 뜻이다.

        막기 전에 재 봤더니 **μ 가 500 → 475 kPa 로 5% 낮게, R² 는 0.975** 로
        그럴듯하게 나왔다. 게다가 큰 RMSE 경고가 *"이 식이 이 재료의 모양과 안
        맞을 수 있습니다"* 라고 **식을 탓했다** — 문제는 데이터인데.
        """
        up = np.linspace(0.0, 1.5, 40)
        strain = np.concatenate([up, up[::-1], up])
        # 이력: 내릴 때 응력이 낮다.
        stress = np.concatenate([self.curve(up), self.curve(up[::-1]) * 0.85, self.curve(up)])
        with pytest.raises(fitting.FittingError, match="되돌아갑니다"):
            fitting.fit("ogden_1", strain, stress)

    def test_무엇을_해야_하는지_말한다(self) -> None:
        """거절만 하면 사람은 뭘 해야 할지 모른다."""
        up = np.linspace(0.0, 1.5, 40)
        strain = np.concatenate([up, up[::-1]])
        stress = np.concatenate([self.curve(up), self.curve(up[::-1])])
        with pytest.raises(fitting.FittingError) as caught:
            fitting.fit("ogden_1", strain, stress)
        message = str(caught.value)
        assert "예비 사이클" in message
        assert "쓸 구간만 잘라" in message
        # **얼마나 되돌아갔는지 숫자로 준다.** 애매한 거절은 고칠 수 없다.
        # 한 사이클이면 폭만큼 통째로 내려간 것이라 100% 다.
        assert "100%" in message

    def test_잡음은_거절하지_않는다(self) -> None:
        """**문턱을 잡음이 넘으면 쓸 수 없는 방어다.**

        실측(2026-08-24): 변형률 폭의 0.67% 짜리 잡음에서도 `gross/net` 은 1.026
        이고, 문턱은 1.25 다. 실제 장비 잡음은 표점의 0.05% 이하라 더 멀다.
        """
        strain = np.linspace(0.0, 1.5, 60)
        noisy = strain + np.random.default_rng(4).normal(0, 0.01, strain.size)
        result = fitting.fit("ogden_1", noisy, self.curve(strain))
        assert result.parameters[0].value == pytest.approx(self.MU, rel=0.1)

    def test_부분_제하도_잡는다(self) -> None:
        """한 사이클을 다 안 돌아도 잡아야 한다 — 폭의 10% 부터 걸린다."""
        up = np.linspace(0.0, 1.5, 60)
        strain = np.concatenate([up, up[::-1][:20]])  # 폭의 33% 만 되돌림
        stress = np.concatenate([self.curve(up), self.curve(up[::-1][:20])])
        with pytest.raises(fitting.FittingError, match="되돌아갑니다"):
            fitting.fit("ogden_1", strain, stress)

    @pytest.mark.parametrize(
        ("name", "mu"),
        [("무른 고무", 50e3), ("보통", 0.5e6), ("딱딱한 고무", 5e6)],
    )
    def test_스케일이_세_자릿수_달라도_경계에_안_붙는다(self, name: str, mu: float) -> None:
        """**경계에 붙은 값은 데이터가 정한 것이 아니다.**

        고무는 MPa 이고 금속은 GPa 라 경계를 절대값으로 못 적는다 — `_bounds` 가
        응력 크기에 비례해 잡는다. 그것이 실제로 100배 범위에서 도는지 본다.
        """
        strain = np.linspace(0.0, 1.5, 60)
        stretch = 1.0 + strain
        stress = (2.0 * mu / self.ALPHA) * (
            stretch ** (self.ALPHA - 1.0) - stretch ** (-self.ALPHA / 2.0 - 1.0)
        )
        result = fitting.fit("ogden_1", strain, stress)
        assert result.parameters[0].value == pytest.approx(mu, rel=0.02), name
        for item in result.parameters:
            assert item.value > item.lower * 1.001, f"{name}: {item.name} 이 하한에 붙었다"
            assert item.value < item.upper * 0.999, f"{name}: {item.name} 이 상한에 붙었다"

    def test_하중셀_양자화를_견딘다(self) -> None:
        """하중셀은 이산값을 준다. 0.1 N 단위면 10x2mm 시편에서 5 kPa 다."""
        strain = np.linspace(0.0, 1.5, 60)
        quantized = np.round(self.curve(strain) / 5e3) * 5e3
        result = fitting.fit("ogden_1", strain, quantized)
        assert result.parameters[0].value == pytest.approx(self.MU, rel=0.01)

    def test_토우는_막지_않지만_값이_틀어진다(self) -> None:
        """**이건 결함이 아니라 알고 써야 하는 것이다.**

        물림이 미끄러지면 응력이 늦게 붙는다. 실측: 토우 0.05 에서 μ 가
        500 → 442 kPa 로 **12% 낮게** 나오는데 R² 는 0.998 이다 — 숫자만 보고는
        모른다.

        고치는 길은 이미 있다. `tensile.toe_correction` 이 기본으로 공칭 축을
        쓰므로(`_pair` 의 기본값) **고무에도 그대로 돈다** — 처리 단계에서 붙이면
        된다. 여기서는 그 사실과, 안 붙였을 때 무슨 일이 나는지를 기록해 둔다.
        """
        strain = np.linspace(0.0, 1.5, 60)
        with_toe = self.curve(np.maximum(strain - 0.05, 0.0))
        result = fitting.fit("ogden_1", strain, with_toe)
        # 막지 않는다.
        assert result.r_squared > 0.99
        # 그런데 값이 10% 넘게 틀어진다.
        assert result.parameters[0].value < self.MU * 0.95


#: Treloar (1944) 가황 천연고무 단축 인장. 출처는 픽스처 머리글에 있다.
TRELOAR = Path(__file__).resolve().parents[1] / "fixtures" / "treloar_uniaxial.csv"


def treloar() -> tuple[np.ndarray, np.ndarray]:
    """공칭 변형률(λ-1)과 공칭 응력(Pa). 우리 축 그대로다."""
    rows = [
        line.split(",")
        for line in TRELOAR.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and not line.startswith("stretch")
    ]
    stretch = np.array([float(row[0]) for row in rows])
    return stretch - 1.0, np.array([float(row[1]) for row in rows]) * 1e6


class Test문헌_벤치마크:
    """**어느 식이 져야 하는지를 아는 유일한 데이터.**

    지금까지의 검산은 전부 우리가 만든 합성 곡선이었다. Ogden 에서 만든 곡선을
    Ogden 으로 맞추면 당연히 Ogden 이 이긴다 — 그것은 계수가 되돌아오는지를
    보는 시험이지, **견주기가 가려내는지를 보는 시험이 아니다.**

    Treloar (1944) 는 초탄성 문헌의 공통 벤치마크다. 어느 식이 어디서 무너지는지가
    합의돼 있다.

        Neo-Hookean    λ≈2 위에서 무너진다 — 끝의 뻣뻣해짐(upturn)을 못 낸다
        Mooney-Rivlin  중간까지. I₂ 항이 있어 Neo-Hookean 보다 낫다
        Yeoh           I₁ 3차라 upturn 을 낸다 — 단축 전 구간에서 가장 낫다
        Ogden          문헌은 **3항**을 쓴다. 우리는 1항뿐이라 중간쯤이다

    실측(2026-08-24, λ 1.0~7.6 전 구간 상대 RMSE):

        Yeoh            4.66%
        Ogden (1항)    14.74%
        Neo-Hookean    35.67%
        Mooney-Rivlin  35.67%   ← c01 이 하한에 붙어 Neo-Hookean 과 같아졌다
    """

    def test_Yeoh_가_Neo_Hookean_을_크게_이긴다(self) -> None:
        """**upturn 을 낼 수 있느냐가 가른다.** 이것이 안 갈리면 견주기는 장식이다."""
        strain, stress = treloar()
        results = {
            item.family: item
            for item in fitting.compare(
                strain, stress, families=("neo_hookean", "mooney_rivlin", "yeoh", "ogden_1")
            )
        }
        assert results["yeoh"].relative_rmse < 0.08
        assert results["neo_hookean"].relative_rmse > 0.25
        # 최소 4배는 갈려야 "가려냈다" 고 할 수 있다.
        assert results["neo_hookean"].relative_rmse > results["yeoh"].relative_rmse * 4

    def test_1항_Ogden_의_한계가_드러난다(self) -> None:
        """**우리는 1항뿐이다.** 문헌이 Treloar 를 맞출 때 쓰는 것은 3항이고,
        1항으로는 λ=7.6 까지 못 따라간다.

        막을 일이 아니라 **아는 일**이다. 평면·등이축 데이터가 들어오면 항을
        늘리는 것이 다음 수순이고, 그때 이 숫자가 기준선이 된다.
        """
        strain, stress = treloar()
        results = {
            item.family: item
            for item in fitting.compare(strain, stress, families=("yeoh", "ogden_1"))
        }
        # Yeoh 보다는 못하고 Neo-Hookean 보다는 낫다.
        assert 0.08 < results["ogden_1"].relative_rmse < 0.25
        # 그리고 **큰 오차를 스스로 말한다.**
        assert any("안 맞을 수 있습니다" in note for note in results["ogden_1"].notes)

    def test_실무_구간에서는_넷_다_쓸_만하다(self) -> None:
        """**전 구간에서 지는 식이 쓸모없는 식은 아니다.**

        λ≤3(변형률 200%)은 실무에서 흔한 범위다. 거기서는 Neo-Hookean 도 10%
        안쪽이다 — *"Neo-Hookean 은 나쁘다"* 가 아니라 *"어디까지 쓸 것인지가
        정한다"* 가 맞는 말이다. 적합 구간 밖을 말하지 않는 태도와 같은 이유다.
        """
        strain, stress = treloar()
        keep = strain <= 2.0
        for item in fitting.compare(
            strain[keep], stress[keep], families=("neo_hookean", "mooney_rivlin", "yeoh")
        ):
            assert item.relative_rmse < 0.10, item.label

    def test_경계에_붙은_값을_짚는다(self) -> None:
        """**실제 데이터에서 방어가 도는 것을 처음 확인한 자리다.**

        Treloar 전 구간에서 Mooney-Rivlin 의 최적 c01 은 음수 쪽으로 간다. 우리는
        하한을 0 으로 두므로 거기 붙고, **그러면 Mooney-Rivlin 은 Neo-Hookean 과
        같은 식이 된다** — 실제로 상대 RMSE 가 소수점까지 같게 나온다.

        숫자만 보면 "두 식이 우연히 비슷하네" 로 읽힌다. 그것을 막는 것이 이
        메모다: 그 값은 데이터가 정한 것이 아니라 경계가 정한 것이다.
        """
        strain, stress = treloar()
        results = {
            item.family: item
            for item in fitting.compare(
                strain, stress, families=("neo_hookean", "mooney_rivlin")
            )
        }
        mooney = results["mooney_rivlin"]
        c01 = next(item for item in mooney.parameters if item.name == "c01")
        assert c01.value == pytest.approx(c01.lower, abs=1e-6)
        assert any("경계에 붙었습니다" in note for note in mooney.notes)
        # 붙은 결과: 두 식이 같아진다. 그 사실이 숫자에 그대로 나온다.
        assert mooney.relative_rmse == pytest.approx(
            results["neo_hookean"].relative_rmse, rel=1e-6
        )
