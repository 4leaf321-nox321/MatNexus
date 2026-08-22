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

    def test_링은_두_가닥이다(self) -> None:
        """**평판 식으로 내면 강도가 두 배로 나온다** — 오류 없이.

        D412 Type 1·2 링과 D2290 스플릿디스크는 링을 두 핀에 걸어 당기므로
        하중이 걸리는 단면이 둘이다.
        """
        values = {"width": 0.006, "thickness": 0.002}
        assert specimen.area("ring", values) == pytest.approx(2 * 0.006 * 0.002)
        assert specimen.area("ring", values) == 2 * specimen.area("rectangle", values)

    def test_직접_적은_값은_그대로(self) -> None:
        assert specimen.area("manual", {"area": 1.5e-4}) == pytest.approx(1.5e-4)


class TestRefusals:
    """**어림값을 만들지 않는다.** 없으면 실패하고, 그게 맞다."""

    def test_칸이_모자라면_무엇이_없는지_말한다(self) -> None:
        with pytest.raises(specimen.SpecimenError) as caught:
            specimen.area("circle", {"width": 0.01, "thickness": 0.001})
        # **사람이 읽는 말이어야 한다.** `diameter` 는 우리 내부 이름이다.
        assert "직경" in str(caught.value)

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
        assert specimen.CROSS_SECTIONS["circle"].need_keys == ("diameter",)
        assert set(specimen.CROSS_SECTIONS["rectangle"].need_keys) == {"width", "thickness"}

    def test_요구하는_칸이_어떤_칸인지도_말한다(self) -> None:
        """**키만 주면 화면이 그 칸을 대신 만들어 줄 수 없다.**

        그리고 차원이 틀리면 조용하다 — 단면적 칸을 길이로 만들면 화면이 mm 로
        환산해 10의 6제곱 배 어긋난 값이 저장된다.
        """
        (need,) = specimen.CROSS_SECTIONS["manual"].needs
        assert (need.label, need.dimension, need.si_unit) == ("단면적", "area", "m2")

    def test_선언한_칸만_있으면_실제로_돈다(self) -> None:
        """**선언과 실제가 어긋나면 조용하다.** 화면은 고를 수 있다고 하는데
        계산은 다른 칸을 찾아 실패한다 — 그래서 돌려 본다."""
        for shape in specimen.CROSS_SECTIONS.values():
            values = {name: 0.01 for name in shape.need_keys}
            if shape.key == "tube":
                values = {"outer_diameter": 0.02, "inner_diameter": 0.01}
            assert specimen.area(shape.key, values) > 0
