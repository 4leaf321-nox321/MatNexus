"""나가는 숫자의 단위계 — **고르지 않으면 mm·N·tonne**(ADR 0036).

다른 시스템으로 나가는 것(카드 덱·중립 JSON · 재료 내보내기 · 문헌 내보내기 · 덱 묶음)은
전부 여기서 계를 고르고 여기서 옮긴다. 자리마다 기본을 적어 두면 한 곳만 SI 로 남고, 그
파일을 받은 쪽은 10⁶ 배 틀린 숫자를 **오류 없이** 쓴다. 실제로 재료 내보내기가 「값은 SI
그대로」 라고 적어 두고 밀도만 tonne/mm3 로 내보내고 있었다(2026-09-24, 해석 연동이 짚었다).

## 저장은 그대로 SI 다

여기는 **나가는 숫자**만 다룬다. 저장을 옮기면 처리 결과의 해시 사슬이 전부 바뀐다(ADR
0004 · 개발계획 v1.88.0). `matcore.export.systems.get(None)` 이 SI 를 주는 것도 그대로 둔다 —
라이브러리는 정책을 모른다. 「고르지 않으면 mm·N·tonne」 은 앱의 정책이라 여기 있다.

## 계가 정하지 않는 단위는 **받은 그대로 두고 말한다**

계가 정하는 것은 질량·길이·시간 셋이다. 그 셋(과 온도)으로 짜인 SI 단위는 전부 기호표에
있어 옮긴다(`matcore.export.systems.KNOWN` — 선하중·표면에너지·파괴인성까지). 저항률
(ohm.m)·준위 에너지(eV)·경도(HV)·몰당 에너지(J/mol)처럼 전류·물질량·눈금이 든 것은 계가
정하지 않는다. 지어내 옮기지 않고 SI 값과 그 단위를 그대로 두되(`Converted.converted=False`),
부르는 쪽이 파일 머리에 「이 단위들은 그대로 뒀다」 를 적는다 — 값마다 단위가 붙어 있으니
섞여도 조용히 섞이지는 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import UnitSystemDef
from app.shared.errors import AppError
from matcore import export, units
from matcore.export.systems import UnitSystem

#: 고르지 않았을 때의 계 — 판재 CAE 의 관행이고, 화면과 AI 의 답도 이 계로 말한다.
DEFAULT = "mm_n_tonne"


def custom(db: Session) -> list[UnitSystem]:
    """사용자가 만든 계. 읽을 때마다 유도한다 — 인수를 저장하지 않는다."""
    return [
        export.systems.derive(
            row.key, row.label, mass=row.mass, length=row.length, time=row.time
        )
        for row in db.scalars(select(UnitSystemDef).order_by(UnitSystemDef.key))
    ]


def available(db: Session) -> list[UnitSystem]:
    """고를 수 있는 계 — 붙박이 먼저, 그다음 사용자 계."""
    return [*export.SYSTEMS, *custom(db)]


def resolve(db: Session, key: str | None, *, code: str) -> UnitSystem:
    """key 로 계를 고른다. **비우면 `DEFAULT`.** 모르면 422 — 쓸 수 있는 것을 함께 말한다."""
    wanted = key or DEFAULT
    try:
        return export.systems.get(wanted)
    except KeyError:
        pass
    for item in custom(db):
        if item.key == wanted:
            return item
    known = ", ".join(one.key for one in available(db))
    raise AppError(
        code, f"모르는 단위계입니다: {wanted!r}. 쓸 수 있는 것: {known}", status=422
    )


def describe(system: UnitSystem) -> dict[str, Any]:
    """파일 머리에 적는 계 — **받는 쪽이 숫자를 읽기 전에 볼 자리.**"""
    return {
        "key": system.key,
        "label": system.label,
        "mass": system.mass,
        "length": system.length,
        "time": system.time,
        "stress": system.symbol("Pa"),
        "symbols": dict(system.symbols),
    }


@dataclass(frozen=True)
class Converted:
    value: float
    unit: str
    converted: bool
    """`False` 면 이 계에 기호가 없어 **받은 단위 그대로** 둔 값이다(값도 그대로)."""


def convert(system: UnitSystem, value: float, unit: str | None) -> Converted:
    """**SI 값** 하나를 그 계로. 표기는 가려 읽는다 — `W/(m*K)` 와 `W/(m.K)` 는 같은 것이다.

    옮기는 것은 **인수가 1 인 SI 단위**뿐이다. `deg` 처럼 SI 가 아닌 단위로 적힌 값은 그 값이
    이미 그 단위라서 SI 로 여겨 옮기면 틀린다 — 그대로 둔다.
    """
    if not unit:
        return Converted(value, unit or "", False)
    try:
        found = units.unit_of(unit)
    except units.UnknownUnit:
        return Converted(value, unit, False)
    symbol = found.symbol
    if found.factor != 1 or found.offset != 0:
        return Converted(value, symbol, False)
    try:
        return Converted(system.convert(value, symbol), system.symbol(symbol), True)
    except KeyError:
        # 계가 정하지 않는 물리량 — 받은 그대로 둔다(위 머리말).
        return Converted(value, symbol, False)
