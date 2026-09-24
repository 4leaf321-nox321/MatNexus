"""질량·길이·시간 셋으로 단위계를 유도한다(2026-09-05).

두 계가 코드에 박혀 있어 다른 조합(LS-DYNA 의 mm·ms·kg)은 배포가 필요했다.
유도한 계가 붙박이 계와 **같은 기호·같은 숫자**를 내야 한다 — 다르면 어느 쪽이
틀린지 덱을 열어도 모른다.
"""

from decimal import Decimal

import pytest

from matcore import units
from matcore.export import systems


def test_mm_N_tonne_을_유도하면_붙박이와_같다() -> None:
    """**인수를 두 벌 적은 것이 서로를 지킨다.** 붙박이 계는 기호로 단위표의 인수를 읽고,
    유도한 계는 차원식(`EXPONENTS`)으로 곱한다. 나가는 파일의 물리량(`EXCHANGED`)까지 —
    tonne·cycle 이 든 기호는 접두어 조합으로 검산이 안 돼서 이 대조가 유일한 검산이다."""
    made = systems.derive("x", "x", mass="tonne", length="mm", time="s")
    assert dict(made.symbols).items() >= dict(systems.MM_N_TONNE.symbols).items()
    assert made.declaration == systems.MM_N_TONNE.declaration
    for si_unit in systems.KNOWN:
        assert made.convert(3.5, si_unit) == pytest.approx(
            systems.MM_N_TONNE.convert(3.5, si_unit)
        ), si_unit


def test_SI_를_유도하면_붙박이와_같다() -> None:
    made = systems.derive("x", "x", mass="kg", length="m", time="s")
    for si_unit in systems.KNOWN:
        assert made.symbol(si_unit) == systems.SI.symbol(si_unit)
        assert made.convert(2.0, si_unit) == 2.0


#: 밑기호의 (질량, 길이, 시간). 온도(K)는 계가 안 바꾼다.
_BASE = {
    "g": (1, 0, 0),
    "m": (0, 1, 0),
    "s": (0, 0, 1),
    "N": (1, 1, -2),
    "Pa": (1, -1, -2),
    "J": (1, 2, -2),
    "W": (1, 2, -3),
    "Hz": (0, 0, -1),
    "K": (0, 0, 0),
}


def test_차원식은_기호를_다시_세어도_같다() -> None:
    """`EXPONENTS` 는 손으로 적는다. 기호를 밑기호로 풀어(`N/m` → N¹·m⁻¹) 다시 센다.

    mm·N·tonne 은 시간이 s 라 **시간 지수가 틀려도 숫자가 같게 나온다** — 위 대조로는 안
    잡히고 ms 계에서만 드러난다. 그래서 여기서 따로 센다. 밑기호가 아닌 글자(`rad`·`cycle`)가
    든 셋은 읽히지 않는데, 그 셋은 차원이 한눈에 보인다(rad · rad/s · m/cycle).
    """
    assert set(systems.EXPONENTS) == set(systems.KNOWN)
    unread = []
    for si_unit, written in systems.EXPONENTS.items():
        parsed = units._factors(si_unit)
        if parsed is None:
            unread.append(si_unit)
            continue
        total = [Decimal(0), Decimal(0), Decimal(0)]
        for base, power in parsed[0]:
            for axis, exponent in enumerate(_BASE[base]):
                total[axis] += power * exponent
        assert tuple(float(one) for one in total) == written, si_unit
    assert sorted(unread) == ["m/cycle", "rad", "rad/s"]


def test_mm_ms_kg_는_GPa_이고_없는_기호는_기본_단위로_짓는다() -> None:
    """LS-DYNA 의 흔한 계. 응력은 표에 GPa 가 있어 그것을 쓰고, 밀도 kg/mm3 는
    표에 없으니 기본 단위로 짓는다 — 손으로 표에 더 적을 것이 없다."""
    made = systems.derive("mm_ms_kg", "x", mass="kg", length="mm", time="ms")
    assert made.symbol("Pa") == "GPa"
    assert made.convert(2.1e11, "Pa") == pytest.approx(210.0)
    assert made.symbol("kg/m3") == "kg/mm3"
    assert made.convert(7850.0, "kg/m3") == pytest.approx(7.85e-6)
    # mm²/ms² = m²/s² — 비열은 SI 와 값이 같고, 기호는 표의 것을 쓴다.
    assert made.symbol("J/(kg.K)") == "J/(kg.K)"
    assert made.convert(460.0, "J/(kg.K)") == pytest.approx(460.0)
    assert made.symbol("W/(m.K)") == "kg.mm/(ms3.K)"
    assert made.convert(50.0, "W/(m.K)") == pytest.approx(5e-5)
    assert made.symbol("s") == "ms"
    assert made.symbol("1/s") == "1/ms"
    assert made.symbol("Hz") == "kHz"
    # 무차원·온도는 어느 계나 같다 — mm 계라고 `mm/mm` 를 집으면 안 된다.
    assert made.symbol("1") == "1" and made.symbol("K") == "K"
    assert made.declaration == "kg, mm, ms, GPa"
    assert made.builtin is False


def test_기호에는_그_계의_기본_단위만_든다() -> None:
    """kg·mm·ms 계의 질량 플럭스는 인수가 `tonne/(mm2.s)` 와 같다(1e9). 인수만 보고 그
    기호를 집으면 받는 사람이 「이 파일은 tonne·s 계인가」 를 묻는다 — 기본 단위로 짓는다.
    점도도 같다(`N.s/mm2` 의 s). 표에 없는 차원은 붙는 글자(K·rad·cycle)를 잃지 않는다."""
    made = systems.derive("mm_ms_kg", "x", mass="kg", length="mm", time="ms")
    assert made.symbol("kg/(m2.s)") == "kg/(mm2.ms)"
    assert made.convert(1.0e9, "kg/(m2.s)") == pytest.approx(1.0)
    assert made.symbol("Pa.s") == "kg/(mm.ms)"
    assert made.symbol("N") == "kN"
    assert made.symbol("m") == "mm" and made.symbol("kg") == "kg"
    assert made.symbol("K.m2/W") == "K.ms3/kg"
    assert made.symbol("rad/s") == "rad/ms"
    assert made.symbol("m/cycle") == "mm/cycle"
    assert made.symbol("Pa.m0.5") == "kg/(mm0.5.ms2)"


def test_기본_단위가_아닌_것은_거절한다() -> None:
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="MPa", length="mm", time="s")
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="kg", length="mm", time="degC")
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="kg", length="furlong", time="s")
