"""값으로 재료 찾기 — **「항복응력이 200MPa 근처인 재료」.**

1단계(`property_names`)가 이름을 풀고, 여기가 값을 건다. 둘은 형제다 — 그래프는
연결을 따라가는 데 강하지 **숫자 범위로 거르는 데는 표가 훨씬 낫다.**

## 단위를 안 주면 거절한다

    Pa   990건   8.0 ~ 2,753,909,000
    1    158건   0.007 ~ 0.96

값이 SI 로 저장돼 있으므로 200MPa 는 `200,000,000` 이다. 사람은 「200」이라고
치는데 그대로 넣으면 **8 Pa 짜리가 나온다.** 그래서 단위를 필수로 받고, 없으면
답하지 않는다 — 짐작해서 답하면 조용히 틀린다.

이 저장소는 단위로 여러 번 데었다. 알루미늄 밀도를 `density_kg_m3` 라 이름 붙였다가
`2.68e-09 kg/m3` 로 내보낸 일이 MCP 안내서에 적혀 있다.

## 문헌과 사내를 함께 본다

문헌만 찾으면 반쪽이다 — 사내 재료의 선언 물성도 같은 물성이고, 값이 이미 SI 로
저장돼 있어(`points[].value_si`) 같은 범위가 그대로 걸린다.

**권한은 여기서 안 건다.** 사내 재료 조회는 부르는 쪽이 `visible_materials` 를
거친다 — 이 모듈은 값만 안다(그래프 모듈과 같은 분리).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.materials.models import Material
from app.shared.errors import AppError
from matcore import units

#: 「근처」 를 물었을 때의 기본 폭. ±10% — 물성 문헌값이 그 정도로 흩어진다.
NEAR_RATIO = 0.10

#: 한 번에 돌려주는 최대. 서버가 상한을 강제한다(AGENTS.md).
MAX_ROWS = 200


@dataclass(frozen=True)
class Hit:
    """값 하나와 그것을 든 재료."""

    world: str
    """`catalog`(문헌) 또는 `internal`(사내)."""
    material_id: uuid.UUID
    material_name: str
    value_si: float
    """**SI 다.** 보여 줄 때는 물어본 단위로 되돌린다."""
    value_shown: float
    unit_shown: str
    quality_tier: int | None = None
    source_detail: str | None = None
    category: str | None = None


def bounds(
    *,
    unit: str,
    si_unit: str,
    minimum: float | None,
    maximum: float | None,
    near: float | None,
) -> tuple[float, float]:
    """사람이 준 범위를 SI 로. **단위가 안 맞으면 거절한다.**

    `near` 를 주면 ±10% 로 편다 — 「200MPa 근처」 가 실제로 사람이 묻는 방식이다.
    """
    if near is None and minimum is None and maximum is None:
        raise AppError(
            "MNX-CATALOG-0030",
            "범위를 주세요 — `near`(근처) 또는 `min`/`max` 중 하나가 있어야 합니다.",
            status=422,
        )
    canonical = units.canonical(unit)
    if canonical is None:
        raise AppError(
            "MNX-CATALOG-0031",
            f"'{unit}' 는 아는 단위가 아닙니다.",
            status=422,
        )
    # **차원이 다르면 답하지 않는다.** 「항복강도를 °C 로」 물으면 숫자는 나오지만
    # 그 답은 뜻이 없다 — 조용히 틀리는 쪽이다.
    known = units.unit_of(canonical)
    if si_unit and not units.same_dimension(known.dimension, _dimension_of(si_unit)):
        raise AppError(
            "MNX-CATALOG-0032",
            f"이 물성의 단위는 '{si_unit}' 인데 '{unit}' 로 물었습니다 — 차원이 다릅니다.",
            status=422,
        )

    if near is not None:
        middle = units.to_si(near, canonical)
        return middle * (1 - NEAR_RATIO), middle * (1 + NEAR_RATIO)
    low = units.to_si(minimum, canonical) if minimum is not None else float("-inf")
    high = units.to_si(maximum, canonical) if maximum is not None else float("inf")
    if low > high:
        raise AppError("MNX-CATALOG-0033", "최솟값이 최댓값보다 큽니다.", status=422)
    return low, high


def _dimension_of(si_unit: str) -> str:
    """SI 기호에서 차원을 되찾는다. 정의가 든 것은 기호뿐이다."""
    for dimension, symbol in units.SI_UNITS.items():
        if symbol == si_unit:
            return dimension
    # 모르는 단위(HV·ShoreA 등 원본 taxonomy 것)는 차원 검사를 건너뛴다 —
    # 억지로 꿰면 값이 상한다(ADR 0027).
    return ""


def catalog_hits(
    db: Session,
    *,
    property_key: str,
    low: float,
    high: float,
    unit: str,
    limit: int,
) -> list[Hit]:
    """문헌 값에서 찾는다."""
    query: Select[Any] = (
        select(CatalogValue, CatalogMaterial)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogValue.material_id)
        .where(
            CatalogValue.property_key == property_key,
            CatalogValue.value_num.is_not(None),
            CatalogValue.value_num >= low,
            CatalogValue.value_num <= high,
        )
        .order_by(CatalogValue.value_num)
        .limit(limit)
    )
    made: list[Hit] = []
    for value, material in db.execute(query).all():
        made.append(
            Hit(
                world="catalog",
                material_id=material.id,
                material_name=material.name,
                value_si=float(value.value_num),
                value_shown=units.from_si(value.value_num, unit),
                unit_shown=unit,
                quality_tier=value.quality_tier,
                source_detail=value.source_detail,
                category=material.category,
            )
        )
    return made


def internal_hits(
    db: Session,
    *,
    item: str,
    low: float,
    high: float,
    unit: str,
    limit: int,
    visible: Select[Any] | None = None,
) -> list[Hit]:
    """사내 재료의 선언 물성에서 찾는다.

    선언 물성은 JSONB 라 SQL 로 파고든다 — `declared_properties` 의 각 항목이
    `{"item": "항복강도", "points": [{"value_si": …}]}` 모양이다.

    **권한은 부르는 쪽이 준다**(`visible`). 이 모듈은 값만 안다.
    """
    query = select(Material.id, Material.record_name, Material.declared_properties).where(
        Material.deleted_at.is_(None),
        # **JSONB 를 통째로 훑기 전에 그 항목을 든 재료로 좁힌다.** `@>` 는
        # GIN 색인을 탄다 — 없으면 재료 전부의 JSON 을 파이썬으로 연다.
        Material.declared_properties.op("@>")(cast([{"item": item}], JSONB)),
    )
    if visible is not None:
        query = query.where(Material.id.in_(visible))
    rows = db.execute(query.limit(MAX_ROWS)).all()

    made: list[Hit] = []
    for material_id, name, declared in rows:
        for entry in declared or []:
            if entry.get("item") != item:
                continue
            for point in entry.get("points") or []:
                value = point.get("value_si")
                if not isinstance(value, int | float):
                    continue
                if low <= value <= high:
                    made.append(
                        Hit(
                            world="internal",
                            material_id=material_id,
                            material_name=name,
                            value_si=float(value),
                            value_shown=units.from_si(value, unit),
                            unit_shown=unit,
                            source_detail=entry.get("reference"),
                        )
                    )
                    break
    made.sort(key=lambda one: one.value_si)
    return made[:limit]


def si_unit_of(db: Session, property_key: str) -> str:
    definition = db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == property_key)
    )
    return (definition.si_unit or "") if definition else ""
