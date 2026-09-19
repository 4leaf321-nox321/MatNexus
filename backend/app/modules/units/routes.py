"""단위 현황 — **무엇을 받아 무엇으로 저장하는가.**

40개 단위와 15개 차원이 `matcore/units.py` 에만 있어서, "우리 시스템이 kgf 를
받나" 를 답하려면 코드를 열어야 했다.

**읽기 전용이다.** 환산 계수와 저장 단위는 화면에서 못 고친다 — 이유는
`UnitsPage` 의 머리글에 적혀 있고, 요약하면: 이미 저장된 숫자의 뜻이 그 표에
달려 있다. `mm` 을 0.01 로 잘못 고치면 **어제 저장한 값과 오늘 저장한 값이 다른
뜻**이 되고, 둘을 구분할 방법이 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.modules.accounts.models import User
from app.modules.units.schemas import (
    AliasOut,
    DimensionOut,
    UnitConversionOut,
    UnitOut,
    UnitsOut,
)
from app.shared.auth import current_user
from app.shared.errors import AppError
from matcore import units

router = APIRouter(prefix="/units", tags=["units"])


@router.get("/convert", response_model=UnitConversionOut)
def convert(
    value: float = Query(),
    from_unit: str = Query(alias="from", min_length=1, max_length=40),
    to_unit: str | None = Query(default=None, alias="to", min_length=1, max_length=40),
    user: User = Depends(current_user),
) -> UnitConversionOut:
    """환산 — **표가 아는 만큼만, 서버가.**

    `to` 를 비우면 그 차원의 저장 단위(SI)로. 차원이 다르면 거절한다 — 「항복강도를
    °C 로」 는 숫자는 나와도 뜻이 없다. 모르는 단위는 표의 까닭(`UnknownUnit.hint`)
    을 그대로 옮긴다: 「모르는 단위」 와 「대소문자로 갈리는 단위」 는 다음에 할 일이
    다르다.
    """
    try:
        source = units.unit_of(from_unit)
    except units.UnknownUnit as exc:
        raise AppError("MNX-UNITS-0001", str(exc), status=422) from None
    si_value = units.to_si(value, from_unit)
    # 표의 모든 차원에 저장 단위가 있다(`tests/unit/test_units.py` 가 지킨다).
    si_unit = units.SI_UNITS[source.dimension]
    if to_unit is None:
        target = units.unit_of(si_unit)
    else:
        try:
            target = units.unit_of(to_unit)
        except units.UnknownUnit as exc:
            raise AppError("MNX-UNITS-0001", str(exc), status=422) from None
    if not units.same_dimension(source.dimension, target.dimension):
        raise AppError(
            "MNX-UNITS-0002",
            f"차원이 다릅니다: {source.symbol}({source.dimension}) → "
            f"{target.symbol}({target.dimension}). 같은 차원끼리만 환산합니다.",
            status=422,
        )
    return UnitConversionOut(
        value=value,
        from_unit=source.symbol,
        to_unit=target.symbol,
        result=units.from_si(si_value, target.symbol),
        dimension=source.dimension,
        si_value=si_value,
        si_unit=si_unit,
    )


@router.get("", response_model=UnitsOut)
def list_units(user: User = Depends(current_user)) -> UnitsOut:
    """차원별로 묶은 단위 전부."""
    grouped: dict[str, list[UnitOut]] = {}
    for symbol, unit in units.UNITS.items():
        grouped.setdefault(unit.dimension, []).append(
            UnitOut(
                symbol=symbol,
                factor=str(unit.factor),
                offset=str(unit.offset),
                is_si=units.SI_UNITS.get(unit.dimension) == symbol,
            )
        )
    # 저장 단위를 맨 앞에 둔다 — 표를 훑을 때 기준이 먼저 보여야 한다.
    for items in grouped.values():
        items.sort(key=lambda item: (not item.is_si, item.symbol))

    reverse_alias = {target: source for source, target in units.DIMENSION_ALIASES.items()}

    # 별칭도 차원별로 묶는다. **이게 없으면 화면이 정본만 보여 주고**, "우리
    # 장비는 N/mm2 로 적는데 되나" 를 여전히 코드로 확인해야 한다.
    aliases: dict[str, list[AliasOut]] = {}
    for written, means in units.NOTATION_ALIASES.items():
        target = units.UNITS.get(means)
        if target is None:
            continue
        aliases.setdefault(target.dimension, []).append(AliasOut(written=written, means=means))
    for alias_items in aliases.values():
        alias_items.sort(key=lambda item: item.written)

    return UnitsOut(
        dimensions=[
            DimensionOut(
                dimension=dimension,
                si_unit=units.SI_UNITS.get(dimension, "?"),
                alias_of=reverse_alias.get(dimension),
                units=items,
                aliases=aliases.get(dimension, []),
            )
            for dimension, items in sorted(grouped.items())
        ],
        total_units=len(units.UNITS),
    )
