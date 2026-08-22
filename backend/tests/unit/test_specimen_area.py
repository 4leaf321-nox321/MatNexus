"""시편 단면적 — **모양마다 식이 다르고, 틀리면 티가 안 난다.**

12.5 mm 환봉의 단면적은 122.7 mm² 인데, 평판 식(폭 곱하기 두께)으로 계산하면
그 값이 아예 안 나오거나(칸이 없어서) 엉뚱한 수가 나온다. 그리고 그 수로 나눈
응력은 **오류 없이 그럴듯한 다른 값**이다.

여기서는 답을 손으로 아는 값으로 검산한다.
"""

from __future__ import annotations

import math

import pytest

from matcore import specimen


class TestFormulas:
    def test_평판은_폭_곱하기_두께(self) -> None:
        # 12.473 mm 곱하기 0.986 mm — Zwick 실파일의 b0·a0 다.
        area = specimen.area("rectangle", {"width": 0.012473, "thickness": 0.000986})
        assert area == pytest.approx(0.012473 * 0.000986, rel=1e-12)

    def test_환봉은_원이다(self) -> None:
        area = specimen.area("circle", {"diameter": 0.0125})
        assert area == pytest.approx(math.pi * 0.00625**2, rel=1e-12)
        # 12.5 mm 환봉 = 122.7 mm². 평판 식이었다면 나올 수 없는 값이다.
        assert area == pytest.approx(122.7e-6, rel=1e-3)

    def test_관은_고리다(self) -> None:
        area = specimen.area("tube", {"outer_diameter": 0.02, "inner_diameter": 0.018})
        assert area == pytest.approx(math.pi / 4 * (0.02**2 - 0.018**2), rel=1e-12)

    def test_직접_적은_값은_그대로(self) -> None:
        assert specimen.area("manual", {"area": 1.5e-4}) == pytest.approx(1.5e-4)


class TestRefusals:
    """**어림값을 만들지 않는다.** 없으면 실패하고, 그게 맞다."""

    def test_칸이_모자라면_무엇이_없는지_말한다(self) -> None:
        with pytest.raises(specimen.SpecimenError) as caught:
            specimen.area("circle", {"width": 0.01, "thickness": 0.001})
        assert "diameter" in str(caught.value)

    def test_0_은_없는_것으로_본다(self) -> None:
        """0 을 값으로 받으면 단면적이 0 이 되고, 응력이 무한대가 된다."""
        with pytest.raises(specimen.SpecimenError):
            specimen.area("rectangle", {"width": 0.01, "thickness": 0.0})

    def test_내경이_외경보다_크면_거절한다(self) -> None:
        with pytest.raises(specimen.SpecimenError):
            specimen.area("tube", {"outer_diameter": 0.018, "inner_diameter": 0.02})

    def test_모르는_모양은_거절한다(self) -> None:
        with pytest.raises(specimen.SpecimenError):
            specimen.area("hexagon", {"width": 0.01})


class TestCatalog:
    def test_식이_요구하는_칸을_선언한다(self) -> None:
        """화면이 "직경 칸이 없어서 이 식을 못 고릅니다" 를 말하려면 필요하다."""
        assert specimen.CROSS_SECTIONS["circle"].needs == ("diameter",)
        assert set(specimen.CROSS_SECTIONS["rectangle"].needs) == {"width", "thickness"}

    def test_선언한_칸만_있으면_실제로_돈다(self) -> None:
        """**선언과 실제가 어긋나면 조용하다.** 화면은 고를 수 있다고 하는데
        계산은 다른 칸을 찾아 실패한다 — 그래서 돌려 본다."""
        for shape in specimen.CROSS_SECTIONS.values():
            values = {name: 0.01 for name in shape.needs}
            if shape.key == "tube":
                values = {"outer_diameter": 0.02, "inner_diameter": 0.01}
            assert specimen.area(shape.key, values) > 0
