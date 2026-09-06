"""질량·길이·시간 셋으로 단위계를 유도한다(2026-09-05).

두 계가 코드에 박혀 있어 다른 조합(LS-DYNA 의 mm·ms·kg)은 배포가 필요했다.
유도한 계가 붙박이 계와 **같은 기호·같은 숫자**를 내야 한다 — 다르면 어느 쪽이
틀린지 덱을 열어도 모른다.
"""

import pytest

from matcore.export import systems


def test_mm_N_tonne_을_유도하면_붙박이와_같다() -> None:
    made = systems.derive("x", "x", mass="tonne", length="mm", time="s")
    assert dict(made.symbols).items() >= dict(systems.MM_N_TONNE.symbols).items()
    assert made.declaration == systems.MM_N_TONNE.declaration
    for si_unit in systems.DECLARED:
        assert made.convert(3.5, si_unit) == pytest.approx(
            systems.MM_N_TONNE.convert(3.5, si_unit)
        ), si_unit


def test_SI_를_유도하면_붙박이와_같다() -> None:
    made = systems.derive("x", "x", mass="kg", length="m", time="s")
    for si_unit in systems.DECLARED:
        assert made.symbol(si_unit) == systems.SI.symbol(si_unit)
        assert made.convert(2.0, si_unit) == 2.0


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


def test_기본_단위가_아닌_것은_거절한다() -> None:
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="MPa", length="mm", time="s")
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="kg", length="mm", time="degC")
    with pytest.raises(ValueError):
        systems.derive("x", "x", mass="kg", length="furlong", time="s")
