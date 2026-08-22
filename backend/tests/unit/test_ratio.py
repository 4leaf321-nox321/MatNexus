"""시편 비율 조건 — **규격이 치수를 안 주고 비만 주는 일이 흔하다.**

DMA 시편 규격표에서 숫자를 실제로 주는 파트는 ISO 6721-2·-3·-10 셋뿐이고 나머지는
전부 비율이거나 장비 위임이다. 그 비를 담지 못하면 그런 규격은 빈 껍데기가 된다.

여기서 지키는 것은 둘이다.

    못 잰 것과 어긴 것은 다르다   값이 없으면 판정하지 않는다
    어겨도 막지 않는다            판정하고, 실제 값을 함께 낸다
"""

from __future__ import annotations

import pytest

from matcore import ratio


class TestJudging:
    def test_최소를_밑돌면_어긴_것이다(self) -> None:
        """ISO 6721-3: L/h >= 50. 저장탄성률 ±5 % 정확도가 여기 달려 있다."""
        check = ratio.Check("length", "thickness", minimum=50)
        (found,) = ratio.violations([check], {"length": 0.15, "thickness": 0.005})
        assert found.actual == pytest.approx(30)

    def test_최대를_넘으면_어긴_것이다(self) -> None:
        """ISO 6721-12: h/D 는 1~2. 넘으면 프리로드에서 좌굴한다."""
        check = ratio.Check("height", "diameter", minimum=1, maximum=2)
        (found,) = ratio.violations([check], {"height": 0.03, "diameter": 0.01})
        assert found.actual == pytest.approx(3)

    def test_안에_들면_조용하다(self) -> None:
        check = ratio.Check("height", "diameter", minimum=1, maximum=2)
        assert ratio.violations([check], {"height": 0.015, "diameter": 0.01}) == []


class TestSilence:
    """**못 잰 것과 어긴 것은 다르다.**

    없는 값을 0 으로 치면 모든 조건이 어긴 것으로 보이고, 그러면 경고가 소음이
    된다 — 소음이 된 경고는 아무도 안 읽는다.
    """

    def test_값이_없으면_판정하지_않는다(self) -> None:
        check = ratio.Check("length", "thickness", minimum=50)
        assert ratio.violations([check], {"length": 0.15}) == []

    def test_분모가_0_이면_판정하지_않는다(self) -> None:
        check = ratio.Check("length", "thickness", minimum=50)
        assert ratio.violations([check], {"length": 0.15, "thickness": 0.0}) == []


class TestWording:
    def test_사람이_읽는_조건을_만든다(self) -> None:
        """**키를 그대로 띄우면 못 읽는다.** `free_length` 는 우리 내부 이름이다."""
        check = ratio.Check("free_length", "thickness", minimum=50)
        assert check.label({"free_length": "자유 길이", "thickness": "두께"}) == (
            "자유 길이 / 두께 >= 50"
        )

    def test_위아래가_다_있으면_범위로_읽는다(self) -> None:
        check = ratio.Check("height", "diameter", minimum=1, maximum=2)
        assert check.label({"height": "높이", "diameter": "직경"}) == "높이 / 직경 = 1 ~ 2"
