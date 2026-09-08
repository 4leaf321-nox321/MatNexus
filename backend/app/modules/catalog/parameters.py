"""문헌 물성의 **변수**를 드러낸다 — 한 키에 여러 변수가 들어 있다.

전수 조사(2026-09-08): 271개 정의 중 **52개 · 값 4,453건**이 파라미터 묶음이었다.
`mechanical.anand_constant` 하나에 Anand 모델의 9개 상수가 다 들어 있다:

    a=1.72 [1] · A=2800 [1/s] · h0=150000 [MPa] · Q/R=9380 [K] · …

값의 정체는 `conditions.term` 이 들고, 한 재료의 한 벌은 `conditions.set_id` 로
묶인다. **정의는 `si_unit = "1"` 하나만 말하지만** 진짜 단위는 항마다 다르고
(`conditions.unit_of_term`), `value_num` 은 **SI 가 아니라 그 항의 원래 단위**다.

## 그래서 이 모듈이 하는 일

    is_parameterized(key)   이 키가 변수 묶음인가
    terms(key)              그 변수들이 무엇인가 — 사람에게 되물을 목록
    label(정의, term)       표시 이름 — 「Anand 점소성 상수 · A」
    sets(재료, key)         한 벌씩 묶어 준다 — 채택의 단위(ADR 0029 D3)

**정의 표를 고치지 않는다.** 이관물이라 배포마다 원본으로 덮인다(ADR 0027) —
읽는 층에서 드러내는 것이 유일하게 안 지워지는 길이다.

## 캐시를 두는 이유

「이 키가 파라미터형인가」 는 검색 한 번에 열세 번 넘게 묻는다. 카탈로그는 이관
때만 바뀌므로 프로세스 수명 동안 캐시해도 안전하다 — 이관 뒤에는 앱이 다시 뜬다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogValue

#: `conditions` 에서 변수를 가리키는 칸.
TERM = "term"
MODEL = "model"
SET_ID = "set_id"
UNIT_OF_TERM = "unit_of_term"

#: 파라미터형으로 볼 최소 변수 수. 하나뿐이면 그냥 그 물성이다.
MIN_TERMS = 2

_cache: dict[str, list[str]] | None = None


@dataclass(frozen=True)
class Term:
    """한 변수. **단위가 항마다 다르다** — 그것이 이 표의 존재 이유다."""

    name: str
    unit: str
    count: int


@dataclass(frozen=True)
class ParameterSet:
    """한 벌. **채택의 단위다** — `A` 만 떼어 가면 뜻이 없다."""

    key: str
    model: str
    set_id: str
    material_id: uuid.UUID
    material_name: str
    terms: list[dict[str, Any]] = field(default_factory=list)
    source: str | None = None
    quality_tier: int | None = None


def _load(db: Session) -> dict[str, list[str]]:
    """키별 변수 목록. **한 번만 훑는다.**"""
    global _cache
    if _cache is not None:
        return _cache
    rows = db.execute(
        text(f"""
        SELECT property_key, conditions->>'{TERM}' AS term, count(*)
        FROM catalog_values
        WHERE conditions ? '{TERM}' AND conditions->>'{TERM}' IS NOT NULL
        GROUP BY 1, 2
        """)
    ).all()
    found: dict[str, list[str]] = {}
    for key, term, _count in rows:
        found.setdefault(key, []).append(term)
    # 변수가 하나뿐인 키는 파라미터형이 아니다 — 조건을 적어 뒀을 뿐이다.
    _cache = {key: sorted(terms) for key, terms in found.items() if len(terms) >= MIN_TERMS}
    return _cache


def forget() -> None:
    """캐시를 버린다. 이관·시험이 부른다."""
    global _cache
    _cache = None


def is_parameterized(db: Session, key: str) -> bool:
    """이 키 하나에 여러 변수가 들어 있나."""
    return key in _load(db)


def parameterized_keys(db: Session) -> list[str]:
    return sorted(_load(db))


def terms(db: Session, key: str, *, limit: int = 40) -> list[Term]:
    """그 키의 변수들 — **사람에게 되물을 목록.**

    개수가 많은 것부터 준다. Prony 완화시간처럼 85종인 것도 있어서, 앞의 몇 개만
    봐도 무엇을 고르는 자리인지 알 수 있어야 한다.
    """
    if not is_parameterized(db, key):
        return []
    rows = db.execute(
        text(f"""
        SELECT conditions->>'{TERM}' AS term,
               coalesce(conditions->>'{UNIT_OF_TERM}', '') AS unit,
               count(*) AS n
        FROM catalog_values
        WHERE property_key = :key AND conditions ? '{TERM}'
        GROUP BY 1, 2 ORDER BY n DESC, term LIMIT :limit
        """),
        {"key": key, "limit": limit},
    ).all()
    return [Term(name=row[0], unit=row[1], count=int(row[2])) for row in rows]


def label(definition: CatalogDefinition, term: str | None = None) -> str:
    """표시 이름. **이름만으로는 무엇인지 모른다.**

    항복강도 (Rp0.2)             기호가 있으면 함께
    Anand 점소성 상수 · A        변수가 있으면 그것까지
    """
    name = definition.name
    if term:
        return f"{name} · {term}"
    if definition.symbol:
        return f"{name} ({definition.symbol})"
    return name


def unit_of(db: Session, key: str, term: str | None) -> str:
    """그 변수의 진짜 단위. **정의가 말하는 단위가 아니다.**

    파라미터형에서 정의는 대개 `1`(무차원)이라고 적혀 있는데, 실제로는 항마다
    `MPa`·`1/s`·`K` 로 다르다.
    """
    if term and is_parameterized(db, key):
        found = db.execute(
            text(f"""
            SELECT coalesce(conditions->>'{UNIT_OF_TERM}', '') FROM catalog_values
            WHERE property_key = :key AND conditions->>'{TERM}' = :term
              AND conditions->>'{UNIT_OF_TERM}' IS NOT NULL LIMIT 1
            """),
            {"key": key, "term": term},
        ).scalar()
        if found:
            return str(found)
    definition = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
    return (definition.si_unit or "") if definition else ""


def sets(
    db: Session,
    *,
    key: str,
    material_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[ParameterSet]:
    """한 벌씩 묶어 준다 — **채택의 단위**(ADR 0029).

    `set_id` 가 없는 값도 있다(원본이 안 준 것). 그때는 재료+모델로 묶는다 — 한
    재료에 같은 모델이 두 벌이면 섞이지만, 안 묶어서 낱개로 흩는 것보다 낫다.
    """
    query = (
        select(
            CatalogValue.material_id,
            func.coalesce(CatalogValue.conditions[MODEL].astext, ""),
            func.coalesce(CatalogValue.conditions[SET_ID].astext, ""),
        )
        .where(CatalogValue.property_key == key, CatalogValue.conditions.has_key(TERM))
        .group_by(CatalogValue.material_id, text("2"), text("3"))
        .limit(limit)
    )
    if material_id is not None:
        query = query.where(CatalogValue.material_id == material_id)

    made: list[ParameterSet] = []
    for owner, model, set_id in db.execute(query).all():
        rows = db.execute(
            text(f"""
            SELECT v.conditions->>'{TERM}', v.value_num, v.value_text,
                   coalesce(v.conditions->>'{UNIT_OF_TERM}', ''), v.quality_tier,
                   left(coalesce(v.source_detail, ''), 160), m.name
            FROM catalog_values v JOIN catalog_materials m ON m.id = v.material_id
            WHERE v.property_key = :key AND v.material_id = :owner
              AND coalesce(v.conditions->>'{MODEL}', '') = :model
              AND coalesce(v.conditions->>'{SET_ID}', '') = :set_id
            ORDER BY 1
            """),
            {"key": key, "owner": owner, "model": model, "set_id": set_id},
        ).all()
        if not rows:
            continue
        made.append(
            ParameterSet(
                key=key,
                model=model,
                set_id=set_id,
                material_id=owner,
                material_name=rows[0][6] or "",
                quality_tier=rows[0][4],
                source=rows[0][5] or None,
                terms=[
                    {
                        "term": row[0],
                        "value": row[1],
                        "text": row[2],
                        "unit": row[3],
                    }
                    for row in rows
                ],
            )
        )
    return made
