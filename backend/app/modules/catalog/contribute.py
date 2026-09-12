"""카탈로그에 직접 넣기 — **이관 밖의 물성 정의·재료·값.**

문헌 카탈로그는 MaterialTwin 스냅샷을 이관해 온 것이라, 저쪽에 없는 물성을 쓰려면
저쪽에 넣고 다시 이관해야 했다(2026-09-12). 여기서는 사람과 AI(MCP)가 정의·재료·값을
직접 넣는다. 그런 줄은 `mt_id` 가 비고 `created_by_id` 가 찬다 — 이관은 그 줄을 모른다.

## 규칙

- **정의의 키는 `local.<domain>.<slug>`** 다. 저쪽 키와 절대 안 겹치고, 사전을 받아
  가는 다른 시스템이 접두어만 보고 「MatNexus 가 만든 키」 를 안다. 키는 한 번 나가면
  안 바뀐다 — 스포크가 그 키로 잇기 때문이다.
- **이미 있는 물성을 또 만들지 않는다.** 이름·별칭이 같은 정의가 있으면 그 키를 알려
  주고 거절한다 — 같은 물성이 두 키로 살면 값 검색이 반씩 갈린다.
- **값은 정의의 단위로 저장한다**(원본 관문과 같은 규칙). 다른 단위로 오면 같은 차원일
  때만 환산한다. MPa 를 Pa 자리에 그대로 넣으면 1000배 틀린다.
- **출처 없는 값은 없다.** 원본이 0건으로 지켜 온 불변식이다. 제목·DOI·URL 중 하나는
  있어야 한다.
- **tier 4 는 근거 없는 값**(계산·추정·가정)이다. 방법이 computed·estimated 면 tier 4
  여야 하고, tier 4 는 `conditions.assumption` 을 단다 — 그래야 화면·MCP 의 경고가 붙는다.
- **지우기는 직접 넣은 줄만.** 이관해 온 줄은 원본이 정본이라 여기서 못 지운다.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyAlias, PropertyLink
from app.modules.catalog.schemas import (
    CatalogMaterialCreate,
    CatalogPropertyCreate,
    CatalogSourceIn,
    CatalogValueCreate,
)
from app.shared import dependents
from app.shared.errors import AppError, Forbidden, NotFound
from app.shared.text import clean, compare_key
from matcore import units

#: 직접 만든 정의의 접두어. **바꾸지 않는다** — 사전이 이미 나가 있다.
LOCAL_PREFIX = "local."

#: 원본 어휘 그대로 — 새 값을 만들지 않는다. 화면과 검색이 이 값으로 거른다.
CATEGORIES = ("metal", "polymer", "ceramic", "composite", "foam", "rubber", "molecular")
DOMAINS = (
    "mechanical",
    "thermal",
    "physical",
    "electrical",
    "magnetic",
    "optical",
    "chemical",
    "acoustic",
    "rheological",
    "surface",
    "interface",
    "structure",
)
SOURCE_KINDS = ("journal", "book", "database", "datasheet", "standard", "web", "other")
METHODS = ("measured", "handbook", "digitized", "computed", "estimated")
VALUE_TYPES = ("numeric", "categorical")

_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def is_local(row: CatalogDefinition | CatalogMaterial | CatalogSource | CatalogValue) -> bool:
    return row.mt_id is None


def origin_of(row: CatalogDefinition | CatalogMaterial | CatalogSource | CatalogValue) -> str:
    """`catalog`(이관) · `local`(여기서 직접)."""
    return "local" if is_local(row) else "catalog"


# --- 정의 ---------------------------------------------------------------------


def _same_property(db: Session, name: str) -> CatalogDefinition | None:
    """이름·별칭이 같은 정의. 같은 물성을 두 키로 만들지 않기 위해 본다."""
    needle = compare_key(name)
    found = db.scalar(
        select(CatalogDefinition).where(func.lower(CatalogDefinition.name) == name.lower())
    )
    if found is not None:
        return found
    alias = db.scalar(select(PropertyAlias).where(PropertyAlias.normalized == needle))
    if alias is None:
        return None
    return db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == alias.property_key)
    )


def create_property(
    db: Session, payload: CatalogPropertyCreate, user: User
) -> CatalogDefinition:
    """정의 하나를 만든다. 키는 `local.<domain>.<slug>`."""
    name = clean(payload.name)
    if not name:
        raise AppError("MNX-CATALOG-0036", "물성 이름이 비었습니다.", status=422)
    domain = payload.domain.strip().lower()
    if domain not in DOMAINS:
        raise AppError(
            "MNX-CATALOG-0036",
            f"도메인 '{payload.domain}' 은 카탈로그에 없습니다 — "
            f"{', '.join(DOMAINS)} 중 하나.",
            status=422,
        )
    slug = payload.slug.strip().lower()
    if not _SLUG.match(slug):
        raise AppError(
            "MNX-CATALOG-0036",
            "slug 는 영문 소문자로 시작하는 snake_case 여야 합니다 — "
            "예: flexural_modulus_wet.",
            status=422,
        )
    if payload.value_type not in VALUE_TYPES:
        raise AppError(
            "MNX-CATALOG-0036", f"value_type 은 {' · '.join(VALUE_TYPES)} 중 하나.", status=422
        )
    key = f"{LOCAL_PREFIX}{domain}.{slug}"
    if db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key)) is not None:
        raise AppError(
            "MNX-CATALOG-0037", f"이미 있는 키입니다: {key}", status=409, details={"key": key}
        )
    same = _same_property(db, name)
    if same is not None:
        raise AppError(
            "MNX-CATALOG-0037",
            f"'{name}' 은 이미 있는 물성입니다 — 키 {same.key} 를 쓰세요. "
            "같은 물성이 두 키로 살면 값 검색이 반씩 갈립니다.",
            status=409,
            details={"key": same.key},
        )

    si_unit = clean(payload.si_unit or "") or None
    if payload.value_type == "numeric":
        if si_unit is None:
            raise AppError(
                "MNX-CATALOG-0036",
                "수치 물성은 단위가 있어야 합니다 — 무차원이면 '1'.",
                status=422,
            )
        found = units.canonical(si_unit)
        if found is None:
            raise AppError(
                "MNX-CATALOG-0036",
                f"단위 '{si_unit}' 은 단위표에 없습니다. SI 정본(Pa · J/(kg.K) · 1 …)으로 "
                "적으세요 — 값을 담고 찾을 때 이 단위로 환산합니다.",
                status=422,
            )
        si_unit = found

    definition = CatalogDefinition(
        mt_id=None,
        created_by_id=user.id,
        key=key,
        domain=domain,
        name=name,
        symbol=clean(payload.symbol or "") or None,
        si_unit=si_unit,
        value_type=payload.value_type,
        description=clean(payload.description or "") or None,
        test_standard=clean(payload.test_standard or "") or None,
        condition_axes=[one for one in (payload.condition_axes or []) if one.strip()] or None,
    )
    db.add(definition)
    db.flush()
    return definition


def delete_property(db: Session, key: str) -> None:
    """직접 만든 정의만, 아무것도 안 걸려 있을 때만."""
    definition = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
    if definition is None:
        raise NotFound("MNX-CATALOG-0038", "없는 물성입니다.")
    if not is_local(definition):
        raise AppError(
            "MNX-CATALOG-0039",
            "이관해 온 물성은 여기서 못 지웁니다 — 원본(MaterialTwin)이 정본입니다.",
            status=422,
        )
    values = db.scalar(
        select(func.count()).select_from(CatalogValue).where(CatalogValue.property_key == key)
    )
    links = db.scalar(
        select(func.count()).select_from(PropertyLink).where(PropertyLink.property_key == key)
    )
    aliases = db.scalar(
        select(func.count())
        .select_from(PropertyAlias)
        .where(PropertyAlias.property_key == key)
    )
    held = [
        label
        for count, label in ((values, "값"), (links, "사내 항목 매핑"), (aliases, "별칭"))
        if count
    ]
    if held:
        raise AppError(
            "MNX-CATALOG-0040",
            f"이 물성에 {' · '.join(held)}이 걸려 있어 못 지웁니다 — 먼저 정리하세요.",
            status=409,
        )
    db.delete(definition)
    db.flush()


# --- 재료 ---------------------------------------------------------------------


def create_material(
    db: Session, payload: CatalogMaterialCreate, user: User
) -> CatalogMaterial:
    name = clean(payload.name)
    if not name:
        raise AppError("MNX-CATALOG-0041", "재료 이름이 비었습니다.", status=422)
    category = payload.category.strip().lower()
    if category not in CATEGORIES:
        raise AppError(
            "MNX-CATALOG-0041",
            f"category '{payload.category}' 는 카탈로그에 없습니다 — "
            f"{', '.join(CATEGORIES)} 중 하나.",
            status=422,
        )
    same = db.scalar(
        select(CatalogMaterial).where(func.lower(CatalogMaterial.name) == name.lower())
    )
    if same is not None:
        raise AppError(
            "MNX-CATALOG-0042",
            f"'{name}' 은 이미 카탈로그에 있습니다({same.category}) — "
            "그 재료에 값을 더하세요.",
            status=409,
            details={"catalog_material_id": str(same.id)},
        )
    material = CatalogMaterial(
        mt_id=None,
        created_by_id=user.id,
        name=name,
        material_code=clean(payload.material_code or "") or None,
        category=category,
        description=clean(payload.description or "") or None,
        manufacturer=clean(payload.manufacturer or "") or None,
        material_class=clean(payload.material_class or "") or None,
        grade=clean(payload.grade or "") or None,
        subsystem=clean(payload.subsystem or "") or None,
        attributes={"origin": "local"},
    )
    db.add(material)
    db.flush()
    return material


def delete_material(db: Session, material_id: uuid.UUID, user: User) -> None:
    material = db.get(CatalogMaterial, material_id)
    if material is None:
        raise NotFound("MNX-CATALOG-0001", "카탈로그에 없는 재료입니다.")
    if not is_local(material):
        raise AppError(
            "MNX-CATALOG-0039",
            "이관해 온 재료는 여기서 못 지웁니다 — 원본(MaterialTwin)이 정본입니다.",
            status=422,
        )
    _require_owner(material.created_by_id, user)
    refs = dependents.references_to(db, table="catalog_materials", pk=material.id)
    if refs:
        # 값(CASCADE)이든 사내 재료 연결(CASCADE)이든 — 조용히 같이 지우지 않는다.
        raise AppError(
            "MNX-CATALOG-0040",
            "이 재료에 "
            + " · ".join(f"{ref.label} {ref.count}건" for ref in refs)
            + " 이 걸려 있어 못 지웁니다 — 먼저 정리하세요.",
            status=409,
        )
    db.delete(material)
    db.flush()


# --- 값 -----------------------------------------------------------------------


def _find_or_make_source(db: Session, given: CatalogSourceIn, user: User) -> CatalogSource:
    """DOI 가 같으면 그 출처, 아니면 제목+연도가 같은 것, 없으면 새로."""
    kind = given.kind.strip().lower()
    if kind not in SOURCE_KINDS:
        raise AppError(
            "MNX-CATALOG-0043",
            f"출처 종류 '{given.kind}' 는 없습니다 — {', '.join(SOURCE_KINDS)} 중 하나.",
            status=422,
        )
    doi = clean(given.doi or "") or None
    title = clean(given.title or "") or None
    url = clean(given.url or "") or None
    if not (doi or title or url):
        raise AppError(
            "MNX-CATALOG-0043",
            "출처가 비었습니다 — 제목·DOI·URL 중 하나는 있어야 합니다. "
            "출처 없는 값은 안 받습니다.",
            status=422,
        )
    found: CatalogSource | None = None
    if doi:
        found = db.scalar(
            select(CatalogSource).where(func.lower(CatalogSource.doi) == doi.lower())
        )
    if found is None and title:
        query = select(CatalogSource).where(func.lower(CatalogSource.title) == title.lower())
        query = (
            query.where(CatalogSource.year == given.year)
            if given.year is not None
            else query.where(CatalogSource.year.is_(None))
        )
        found = db.scalar(query)
    if found is not None:
        return found
    source = CatalogSource(
        mt_id=None,
        created_by_id=user.id,
        kind=kind,
        doi=doi,
        url=url,
        title=title,
        authors=clean(given.authors or "") or None,
        year=given.year,
        publisher=clean(given.publisher or "") or None,
    )
    db.add(source)
    db.flush()
    return source


def _to_definition_unit(
    value: float, given_unit: str | None, definition: CatalogDefinition
) -> tuple[float, str | None, str | None]:
    """값을 정의의 단위로. `(값, 단위, 환산 설명 | None)`.

    정의 단위가 표에 없는 눈금(HV)이면 같은 기호만 받는다 — 환산할 수 없다.
    """
    target = definition.si_unit
    given = clean(given_unit or "") or None
    if target is None:
        return value, given, None
    target_c = units.canonical(target)
    if given is None:
        raise AppError(
            "MNX-CATALOG-0044",
            f"단위가 비었습니다 — 이 물성의 단위는 {target} 입니다. 값 옆에 단위를 적으세요.",
            status=422,
        )
    given_c = units.canonical(given)
    if target_c is None:
        if units.loose_key(given) != units.loose_key(target):
            raise AppError(
                "MNX-CATALOG-0044",
                f"이 물성은 {target} 눈금이라 환산할 수 없습니다 — {target} 로 적으세요.",
                status=422,
            )
        return value, target, None
    if given_c is None:
        raise AppError(
            "MNX-CATALOG-0044",
            f"단위 '{given}' 은 단위표에 없습니다 — 이 물성의 단위는 {target} 입니다.",
            status=422,
        )
    if given_c == target_c:
        return value, target_c, None
    if not units.same_dimension(
        units.unit_of(given_c).dimension, units.unit_of(target_c).dimension
    ):
        raise AppError(
            "MNX-CATALOG-0044",
            f"'{given}' 은 {units.unit_of(given_c).dimension} 인데 이 물성은 "
            f"{units.unit_of(target_c).dimension}({target}) 입니다 — 차원이 다릅니다.",
            status=422,
        )
    converted = units.from_si(units.to_si(value, given_c), target_c)
    return converted, target_c, f"{value} {given} → {converted:g} {target_c}"


def create_value(
    db: Session, material_id: uuid.UUID, payload: CatalogValueCreate, user: User
) -> tuple[CatalogValue, str | None]:
    """값 하나를 넣는다. `(값, 환산 설명 | None)`."""
    material = db.get(CatalogMaterial, material_id)
    if material is None:
        raise NotFound("MNX-CATALOG-0001", "카탈로그에 없는 재료입니다.")
    definition = db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == payload.property_key)
    )
    if definition is None:
        raise NotFound(
            "MNX-CATALOG-0038",
            f"없는 물성 키입니다: {payload.property_key} — "
            "resolve_property 로 키를 먼저 찾으세요.",
        )
    method = payload.method.strip().lower()
    if method not in METHODS:
        raise AppError(
            "MNX-CATALOG-0045", f"method 는 {' · '.join(METHODS)} 중 하나.", status=422
        )
    tier = payload.quality_tier
    if method in ("computed", "estimated") and tier != 4:
        raise AppError(
            "MNX-CATALOG-0045",
            f"{method} 값은 근거 없는 값이라 quality_tier 4 여야 합니다.",
            status=422,
        )

    value_num = payload.value_num
    value_text = clean(payload.value_text or "") or None
    unit: str | None = None
    note: str | None = None
    if definition.value_type == "numeric":
        if value_num is None:
            raise AppError(
                "MNX-CATALOG-0045", "수치 물성입니다 — value_num 이 필요합니다.", status=422
            )
        value_num, unit, note = _to_definition_unit(value_num, payload.unit, definition)
    elif value_text is None:
        raise AppError(
            "MNX-CATALOG-0045", "범주 물성입니다 — value_text 가 필요합니다.", status=422
        )

    conditions: dict[str, Any] = dict(payload.conditions or {})
    if tier == 4:
        conditions.setdefault("assumption", True)
    source = _find_or_make_source(db, payload.source, user)

    row = CatalogValue(
        mt_id=None,
        created_by_id=user.id,
        material_id=material.id,
        property_key=definition.key,
        value_num=value_num,
        value_text=value_text,
        unit=unit,
        uncertainty=payload.uncertainty,
        conditions=conditions or None,
        method=method,
        quality_tier=tier,
        source_id=source.id,
        source_detail=clean(payload.source_detail or "") or None,
        notes=clean(payload.notes or "") or None,
    )
    db.add(row)
    db.flush()
    return row, note


def delete_value(db: Session, value_id: uuid.UUID, user: User) -> None:
    row = db.get(CatalogValue, value_id)
    if row is None:
        raise NotFound("MNX-CATALOG-0046", "없는 값입니다.")
    if not is_local(row):
        raise AppError(
            "MNX-CATALOG-0039",
            "이관해 온 값은 여기서 못 지웁니다 — 원본(MaterialTwin)이 정본입니다.",
            status=422,
        )
    _require_owner(row.created_by_id, user)
    db.delete(row)
    db.flush()


def _require_owner(created_by_id: uuid.UUID | None, user: User) -> None:
    """넣은 사람이거나 시스템 관리자만 지운다."""
    if user.is_system_admin or created_by_id == user.id:
        return
    raise Forbidden("MNX-CATALOG-0047", "다른 사람이 넣은 것은 지울 수 없습니다.")


def creator_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
    return {user_id: name for user_id, name in rows}


__all__ = [
    "CATEGORIES",
    "DOMAINS",
    "LOCAL_PREFIX",
    "METHODS",
    "SOURCE_KINDS",
    "create_material",
    "create_property",
    "create_value",
    "creator_names",
    "delete_material",
    "delete_property",
    "delete_value",
    "is_local",
    "origin_of",
]
