"""단위 현황 — **무엇을 받아 무엇으로 저장하는가.**

40개 단위와 15개 차원이 `matcore/units.py` 에만 있어서, "우리 시스템이 kgf 를
받나" 를 답하려면 코드를 열어야 했다.

**읽기 전용이다.** 환산 계수와 저장 단위는 화면에서 못 고친다 — 이유는
`UnitsPage` 의 머리글에 적혀 있고, 요약하면: 이미 저장된 숫자의 뜻이 그 표에
달려 있다. `mm` 을 0.01 로 잘못 고치면 **어제 저장한 값과 오늘 저장한 값이 다른
뜻**이 되고, 둘을 구분할 방법이 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.accounts.models import User
from app.modules.units.schemas import DimensionOut, UnitOut, UnitsOut
from app.shared.auth import current_user
from matcore import units

router = APIRouter(prefix="/units", tags=["units"])


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
    return UnitsOut(
        dimensions=[
            DimensionOut(
                dimension=dimension,
                si_unit=units.SI_UNITS.get(dimension, "?"),
                alias_of=reverse_alias.get(dimension),
                units=items,
            )
            for dimension, items in sorted(grouped.items())
        ],
        total_units=len(units.UNITS),
    )
