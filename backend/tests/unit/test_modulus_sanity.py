"""탄성률이 말이 되는 값인가(`app/shared/modulus_sanity.py`) — 막지 않고 경고한다.

2026-11-14(VOC 43): 단위 실수는 탄성률을 1000배 단위로 틀리게 하는데 처리 단계는 「0 이하」 만
거절했다. 범위 숫자는 잠정값이라, 여기서는 **자릿수가 틀린 값이 걸리고 정상 값이 안
걸리는지**만 묶는다.
"""

from __future__ import annotations

import pytest

from app.shared.modulus_sanity import (
    DECLARED_RATIO,
    family_range,
    judge,
    nearest_declared,
)


@pytest.mark.parametrize(
    ("value", "family"),
    [
        (205e9, "Metal"),  # 강판
        (70e9, "금속"),  # 알루미늄
        (2.4e9, "Polymer"),  # PC
        (5.6e3, "polymer"),  # PDMS — 1 kPa 근처도 진짜 값이다
        (50.0, "Polymer"),  # 하이드로젤
        (150e9, "Ceramic"),  # 칩
        (5e6, "Rubber"),
        (2.4e9, "처음 보는 군"),  # 모르는 군은 불가능 값만 본다
        (2.4e9, None),
    ],
)
def test_정상_값은_말하지_않는다(value: float, family: str | None) -> None:
    assert judge(value, "탄성계수", family=family) == []


@pytest.mark.parametrize(
    ("value", "family", "mark"),
    [
        (205e6, "Metal", "범위"),  # 하중 kN → N: 1/1000
        (205e12, "Metal", "없는 값"),  # 두께 1/10: 1000배
        (150e6, "Ceramic", "범위"),
        (5e9, "Rubber", "범위"),  # 고무 1000배
        (2.5e18, "Polymer", "없는 값"),  # 두께 µm: 10⁹ 배
        (0.5, None, "없는 값"),
    ],
)
def test_자릿수가_틀린_값은_말한다(value: float, family: str | None, mark: str) -> None:
    found = judge(value, "굽힘 탄성률", family=family)
    assert len(found) == 1 and mark in found[0], found
    assert "굽힘 탄성률" in found[0]


def test_고분자의_작게_틀린_값은_선언값이_잡는다() -> None:
    """PC 2.4 GPa 를 1/1000 로 낸 2.4 MPa 는 점착제 범위 안이라 재료군 범위로는 못 잡는다 —
    재료에 적어 둔 값과 견줘야 잡힌다."""
    assert judge(2.4e6, "굽힘 탄성률", family="Polymer") == []
    found = judge(2.4e6, "굽힘 탄성률", family="Polymer", declared=2.4e9)
    assert len(found) == 1 and "적어 둔 탄성률 2.4 GPa" in found[0] and "1e+03배" in found[0]


def test_선언값과_몇십_퍼센트_차이는_말하지_않는다() -> None:
    """적층재의 굽힘 등가 E 는 인장 E 와 수십 % 다르다 — 단위 실수는 10배 이상이다."""
    assert judge(20e9, "굽힘 탄성률", family="Composite", declared=28e9) == []
    just_over = 28e9 / (DECLARED_RATIO * 1.01)
    assert len(judge(just_over, "굽힘 탄성률", family="Composite", declared=28e9)) == 1


def test_재료군_항목의_칸이_기본_범위를_이긴다() -> None:
    assert family_range("Polymer", {"modulus_min": 1e8, "modulus_max": 1e10}) == (1e8, 1e10)
    # 한쪽만 적으면 다른 쪽은 기본 범위
    assert family_range("Metal", {"modulus_max": 3e11}) == (5e9, 3e11)
    assert family_range("처음 보는 군") is None
    found = judge(2.4e6, "굽힘 탄성률", family="Polymer", attributes={"modulus_min": 1e8})
    assert len(found) == 1 and "범위" in found[0]


def test_선언값은_시험_온도에_가장_가까운_점() -> None:
    """첫 점(가장 낮은 온도)과 견주면 고온 시험이 온도 탓으로 걸린다."""
    points = [
        {"temperature_k": 293.15, "value_si": 20e9},
        {"temperature_k": 423.15, "value_si": 2e9},
    ]
    assert nearest_declared(points, 293.15) == 20e9
    assert nearest_declared(points, 413.15) == 2e9
    assert nearest_declared([{"value_si": 7e10}], 500.0) == 7e10  # 온도 없는 점은 상온
    assert nearest_declared([], 293.15) is None
