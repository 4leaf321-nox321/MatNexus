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


class AliasOut(BaseModel):
    """같은 단위의 다른 표기. **장비마다 다르게 적는다.**

    실측: 마이크로를 마이크로 기호(U+00B5)로 적는 장비와 그리스 뮤(U+03BC)로
    적는 장비가 섞여 있다 — 눈으로는 같아 보이는데 코드포인트가 다르다.
    """

    written: str
    """파일·폼에 적혀 오는 글자."""
    means: str
    """우리 표의 어느 심볼로 읽는가."""


class DimensionOut(BaseModel):
    dimension: str
    si_unit: str
    """**저장 단위.** 이 차원의 값은 예외 없이 이것으로 DB 에 들어간다."""
    alias_of: str | None
    """`strain` 은 `dimensionless` 의 별칭이다 — 차원 검증에서는 같게 치지만
    화면에서는 %로 보여 준다. 단위로는 못 가르는 것을 가르는 장치다."""
    units: list[UnitOut]
    aliases: list[AliasOut]
    """이 차원의 단위를 가리키는 다른 표기들."""


class UnitsOut(BaseModel):
    dimensions: list[DimensionOut]
    total_units: int
