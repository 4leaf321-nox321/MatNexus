"""나가는 숫자 하나를 계로 옮긴다 — **DB 에 실제로 적힌 표기 그대로**(ADR 0036 D3).

문헌 값은 `J/m^2`·`Pa*m^0.5`·`kg/(m^2*s)` 처럼 적혀 있다(MaterialTwin 이관). 기호표가 아는
정본(`J/m2`)으로 읽혀야 옮겨지고, 못 읽으면 조용히 SI 로 남는다 — 그 한 줄이 파일에서 계가
다른 줄이 된다. 그래서 표기는 DB 에서 센 것을 그대로 쓴다(2026-09-24, 72가지).
"""

from __future__ import annotations

import pytest

from app.shared import unit_systems
from matcore.export.systems import MM_N_TONNE, SI


@pytest.mark.parametrize(
    ("stored", "value", "expected", "unit"),
    [
        # 박리강도 1,049건 — 가장 많다.
        ("N/m", 1049.0, 1.049, "N/mm"),
        ("J/m^2", 1.5, 0.0015, "mJ/mm2"),
        ("m^2/s", 4.0e-6, 4.0, "mm2/s"),
        # 50 MPa·√m = 50·√1000 MPa·√mm.
        ("Pa*m^0.5", 50.0e6, 1581.1388300841897, "MPa.mm0.5"),
        ("J", 27.0, 27000.0, "mJ"),
        ("kg/(m^2*s)", 1.0, 1.0e-9, "tonne/(mm2.s)"),
        ("K*m^2/W", 0.002, 2.0, "K.mm2/mW"),
        ("m/cycle", 1.0e-8, 1.0e-5, "mm/cycle"),
        ("m^3/(m^2*s)", 1.0e-3, 1.0, "mm3/(mm2.s)"),
        # 강의 음향 임피던스 45 MRayl.
        ("Pa*s/m", 4.5e7, 0.045, "N.s/mm3"),
        ("m^3/kg", 1.0e-3, 1.0e9, "mm3/tonne"),
        ("m", 0.0012, 1.2, "mm"),
    ],
)
def test_계가_정하는_물리량은_그_계로_옮긴다(
    stored: str, value: float, expected: float, unit: str
) -> None:
    got = unit_systems.convert(MM_N_TONNE, value, stored)
    assert got.converted
    assert got.unit == unit
    assert got.value == pytest.approx(expected)
    # SI 로 고르면 숫자는 그대로, 기호는 정본으로.
    same = unit_systems.convert(SI, value, stored)
    assert same.converted and same.value == pytest.approx(value)


@pytest.mark.parametrize(
    "stored", ["ohm*m", "S/m", "V", "T", "J/mol", "mol/m^3", "eV", "dB", "g/600s", "HV", "deg"]
)
def test_계가_정하지_않는_것은_그대로_둔다(stored: str) -> None:
    """전류·물질량·로그·눈금·각 — 계가 정하지 않는다. 지어내 옮기지 않는다."""
    got = unit_systems.convert(MM_N_TONNE, 3.0, stored)
    assert not got.converted
    assert got.value == 3.0
