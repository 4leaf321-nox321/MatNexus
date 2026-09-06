"""속도별 곡선 묶기 — **속도로 가르고, 가른 것끼리 평균하고, 민감도를 식으로 요약한다.**

정답을 아는 곡선으로 검산한다. Cowper-Symonds 로 만든 곡선을 넣으면 D·p 가
돌아와야 하고, 같은 속도의 시편은 한 묶음이어야 하며, 속도가 없는 시편은 막아야
한다 — "돌아간다" 로는 아무것도 증명되지 않는다.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import groups
from matcore.groups import rate as rate_group  # noqa: F401  (등록시킨다)
from matcore.groups.rate import RATE
from matcore.processing.tensile import PLASTIC_STRAIN, TRUE_STRESS

D, P = 1000.0, 5.0
PLUGIN = "tensile.rate_family"


def sigma0(strain: np.ndarray) -> np.ndarray:
    """기준 속도의 진응력. Voce 비슷하게."""
    return 250e6 + 150e6 * (1.0 - np.exp(-strain / 0.05))


def member(
    label: str, rate: float, *, stop: float = 0.2, points: int = 90, scale: float = 1.0
) -> groups.Member:
    """Cowper-Symonds 로 부풀린 시편 하나. 격자를 시편마다 다르게 둔다."""
    strain = np.linspace(0.0, stop, points)
    factor = 1.0 + (rate / D) ** (1.0 / P)
    return groups.Member(
        label=label,
        columns={PLASTIC_STRAIN: strain, TRUE_STRESS: sigma0(strain) * factor * scale},
        values={RATE: rate},
    )


def run(members: list[groups.Member], **options: object) -> groups.GroupOutcome:
    return groups.run_group(PLUGIN, members, options)


class Test속도로_가른다:
    def test_가까운_속도는_한_묶음이다(self) -> None:
        out = run(
            [member("a", 0.001), member("b", 0.0012), member("c", 0.1), member("d", 10.0)]
        )
        assert out.values["rate_count"] == 3
        bins = out.detail["rates"]
        assert bins[0]["members"] == ["a", "b"]
        # 묶음의 속도는 기하평균이다.
        assert bins[0]["rate"] == pytest.approx((0.001 * 0.0012) ** 0.5)
        assert [one["rate"] for one in bins[1:]] == pytest.approx([0.1, 10.0])

    def test_폭을_0으로_두면_시편마다_따로_선다(self) -> None:
        out = run([member("a", 0.001), member("b", 0.0012)], bin_ratio=0)
        assert out.values["rate_count"] == 2

    def test_기준은_가장_느린_묶음이고_그_곡선이_열로_나간다(self) -> None:
        out = run([member("fast", 10.0), member("slow", 0.001)])
        assert out.values["reference_rate"] == pytest.approx(0.001)
        assert out.detail["rates"][0]["members"] == ["slow"]
        # GroupOutcome.columns 는 기준 곡선 — 카드의 `table` 이 이것을 받는다.
        assert np.allclose(
            out.columns[TRUE_STRESS],
            sigma0(out.columns[PLASTIC_STRAIN]) * (1 + (0.001 / D) ** (1 / P)),
            rtol=1e-3,
        )


class Test묶음_안에서_평균한다:
    def test_격자가_달라도_공통_구간에_보간해_평균한다(self) -> None:
        # 같은 속도, 한쪽은 짧고 성기게. 평균은 둘의 가운데여야 한다.
        low = member("low", 0.01, stop=0.2, points=90, scale=0.9)
        high = member("high", 0.01, stop=0.12, points=25, scale=1.1)
        out = run([low, high, member("ref", 0.0001)])
        bin_ = out.detail["rates"][1]
        assert bin_["count"] == 2
        x = np.asarray(bin_["curve"][PLASTIC_STRAIN])
        y = np.asarray(bin_["curve"][TRUE_STRESS])
        assert x[-1] == pytest.approx(0.12)  # 짧은 쪽까지만
        expected = sigma0(x) * (1 + (0.01 / D) ** (1 / P)) * 1.0  # (0.9+1.1)/2
        assert np.allclose(y, expected, rtol=1e-3)
        assert any("보간" in said for said in out.warnings)

    def test_시편_하나뿐인_묶음은_평균이_아니라고_말한다(self) -> None:
        out = run([member("a", 0.001), member("b", 1.0)])
        assert any("시편 하나뿐" in said for said in out.warnings)


class Test민감도_식:
    def test_Cowper_Symonds_로_만든_곡선에서_D와_p가_돌아온다(self) -> None:
        # **기준은 가장 느린 시험 속도이지 준정적(ε̇→0)이 아니다.** 식은 준정적 대비
        # 비율로 정의되므로, 기준 속도가 빠르면 그만큼 D·p 가 밀린다 — 0.001 1/s 를
        # 기준으로 두면 p 가 5 대신 4 로 나온다(실측). 그것은 식의 정의이지 버그가
        # 아니라서, 여기서는 준정적에 가까운 기준(1e-8: 부풀림 0.6%)으로 검산한다.
        out = run(
            [member("r0", 1e-8), member("r1", 0.1), member("r2", 10.0), member("r3", 1000.0)],
            model="cowper_symonds",
        )
        assert out.values["cs_p"] == pytest.approx(P, rel=0.05)
        assert out.values["cs_d"] == pytest.approx(D, rel=0.2)
        assert out.values["model_r_squared"] > 0.99

    def test_기준_속도가_빠르면_그만큼_밀린다는_것을_안다(self) -> None:
        # 위 주석의 근거. 기준 0.001 이면 p 가 5 에서 눈에 띄게 벗어난다 — 사용자가
        # 「왜 문헌값과 다르지」 를 물을 때 답이 되는 시험이다.
        out = run(
            [member("r0", 0.001), member("r1", 0.1), member("r2", 10.0), member("r3", 1000.0)],
            model="cowper_symonds",
        )
        assert out.values["cs_p"] < P * 0.9

    def test_묶음이_둘이면_Cowper_Symonds_는_안_맞추고_이유를_남긴다(self) -> None:
        out = run([member("a", 0.001), member("b", 10.0)], model="cowper_symonds")
        assert "cs_d" not in out.values
        assert any("둘 이상" in said for said in out.warnings)

    def test_Johnson_Cook_은_묶음_둘로도_C_가_나온다(self) -> None:
        out = run([member("a", 0.001), member("b", 10.0)], model="johnson_cook")
        assert "jc_c" in out.values and out.values["jc_c"] > 0
        assert any("점 하나" in said for said in out.warnings)

    def test_식_없이도_응력비는_남는다(self) -> None:
        out = run([member("a", 0.001), member("b", 10.0)], levels="0.02, 0.1")
        fast = out.detail["rates"][1]
        assert fast["ratios"] == pytest.approx(
            [(1 + (10.0 / D) ** (1 / P)) / (1 + (0.001 / D) ** (1 / P))] * 2, rel=1e-3
        )
        assert "cs_d" not in out.values and "jc_c" not in out.values


class Test막는_것:
    def test_속도가_없는_시편은_막는다(self) -> None:
        bad = groups.Member(label="x", columns=member("x", 1.0).columns, values={})
        with pytest.raises(groups.GroupError, match="변형률 속도"):
            run([member("a", 0.001), bad])

    def test_진응력이_없는_결과는_막는다(self) -> None:
        bad = groups.Member(
            label="x", columns={PLASTIC_STRAIN: np.linspace(0, 0.1, 10)}, values={RATE: 1.0}
        )
        with pytest.raises(groups.GroupError, match="진소성변형률·진응력"):
            run([member("a", 0.001), bad])

    def test_변형률_수준을_숫자로_못_읽으면_막는다(self) -> None:
        with pytest.raises(groups.GroupError, match="숫자"):
            run([member("a", 0.001), member("b", 1.0)], levels="0.02, abc")

    def test_곡선이_안_닿는_수준은_빼고_말한다(self) -> None:
        out = run(
            [member("a", 0.001, stop=0.2), member("b", 10.0, stop=0.05)], levels="0.02, 0.1"
        )
        fast = out.detail["rates"][1]
        assert fast["ratios"][1] is None
        assert any("0.1" in said and "응력비를 뺐습니다" in said for said in out.warnings)
