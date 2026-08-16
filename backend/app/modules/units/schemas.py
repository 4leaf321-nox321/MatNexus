"""단위 현황의 응답 모양."""

from __future__ import annotations

from pydantic import BaseModel


class UnitOut(BaseModel):
    symbol: str
    factor: str
    """SI 로 가는 배수. **Decimal 을 문자열로 보낸다** — 0.0000166666666666667 을
    float 로 실어 보내면 자리가 잘리고, 화면이 그 잘린 값을 보여 준다."""
    offset: str
    """`SI = value * factor + offset`. 섭씨만 0 이 아니다."""
    is_si: bool


class DimensionOut(BaseModel):
    dimension: str
    si_unit: str
    """**저장 단위.** 이 차원의 값은 예외 없이 이것으로 DB 에 들어간다."""
    alias_of: str | None
    """`strain` 은 `dimensionless` 의 별칭이다 — 차원 검증에서는 같게 치지만
    화면에서는 %로 보여 준다. 단위로는 못 가르는 것을 가르는 장치다."""
    units: list[UnitOut]


class UnitsOut(BaseModel):
    dimensions: list[DimensionOut]
    total_units: int
