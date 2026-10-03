"""물성 분류의 일 — 씨앗 · 트리 · 고치기 · 밀어 넣기 · 바깥으로 내는 목록 (ADR 0054).

라우트(`taxonomy_routes.py`)는 판정과 커밋만 하고 여기를 부른다. **여기서는 커밋하지 않는다** —
씨앗 · 이관과 같은 규율이다(미리 보기가 같은 길을 커밋 없이 탄다).

## 밀어 넣기는 이름을 맞추지 않는다 — 정확히 맞는 것만

분류는 바깥(SP)에 이미 있다. 그것을 표로 붙여 넣으면 줄마다 분야 > 물성군 > 물성을 찾고,
없는 분야 · 군은 만든다. **물성은 만들지 않는다** — 키 · 이름 · 별칭이 정확히 하나에 맞아야
하고, 아니면 그 줄이 오류다. 비슷한 것을 골라 주면 「항복응력」 이 유변학 물성으로 조용히
들어간다(`shared/property_names` 머리말의 실측).

**오류가 하나라도 있으면 아무것도 안 넣는다.** 분류가 반만 들어가면 어디까지 들어갔는지를
사람이 다시 맞춰 봐야 한다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.catalog.contribute import DOMAINS, LOCAL_PREFIX
from app.modules.catalog.models import CatalogDefinition, CatalogValue
from app.modules.catalog.ontology_models import PropertyAlias
from app.modules.catalog.taxonomy_models import (
    PropertyField,
    PropertyGroup,
    PropertyGroupMember,
)
from app.modules.catalog.taxonomy_schemas import (
    FeedFieldOut,
    FeedFieldPage,
    FeedGroupOut,
    FeedGroupPage,
    FeedPropertyOut,
    FeedPropertyPage,
    ImportErrorOut,
    ImportFieldOut,
    ImportGroupOut,
    ImportMemberOut,
    PropertyFieldCreate,
    PropertyFieldOut,
    PropertyFieldUpdate,
    PropertyGroupCreate,
    PropertyGroupOut,
    PropertyGroupUpdate,
    TaxonomyAssignOut,
    TaxonomyImportOut,
    TaxonomyImportRow,
    TaxonomyOut,
    TaxonomyPropertyOut,
)
from app.shared import audit
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.text import clean, compare_key

#: 씨앗 분야 — 키 앞머리와 그 한글 이름(화면의 `DOMAIN_LABELS` 와 같은 말), 물성이 많은
#: 차례. **씨앗일 뿐이다** — 심은 뒤에는 자료 관리자가 고친 이름이 이긴다(`ensure_*` 는 없는
#: 것만 만든다).
SEED_FIELDS: dict[str, str] = {
    "mechanical": "기계",
    "thermal": "열",
    "physical": "물리",
    "chemical": "화학",
    "optical": "광학",
    "electrical": "전기",
    "interface": "계면",
    "structure": "구조",
    "rheological": "유변",
    "magnetic": "자성",
    "surface": "표면",
    "acoustic": "음향",
}
assert set(SEED_FIELDS) == set(DOMAINS), "키 앞머리가 늘면 씨앗 분야에도 이름을 준다"

#: 분야 · 물성군 키. 빈칸과 주소에 걸리는 글자만 막는다 — SP 의 키를 그대로 받을 수 있게
#: 넓게 둔다.
KEY_PATTERN = re.compile(r"^[^\s/?#%\\]{1,100}$")
FIELD_KEY_PREFIX = "pf-"
GROUP_KEY_PREFIX = "pg-"

#: 트리 한 번에 싣는 물성 상한. 지금 271종 — 넘으면 `truncated` 로 말한다(조용히 자르지
#: 않는다).
MAX_TREE_PROPERTIES = 5000

#: 바깥이 한 쪽에 받을 수 있는 행. **넘게 달라면 깎지 않고 거절한다** — SP 는 「받은 행이
#: page_size 보다 적으면 끝」 으로 읽어서(연동 지침 §3.3), 2000 을 달라는데 1000 을 주면 거기서
#: 멈추고 나머지를 영영 안 받는다.
FEED_PAGE_MAX = 1000

#: SP 가 여러 값을 가르는 글자(`objects/bulk.MULTI_SEP`).
MULTI_SEP = ";"


def _now() -> datetime:
    return datetime.now(UTC)


def _pairs(rows: Any) -> dict[Any, Any]:
    """두 칸짜리 줄 → 사전. `dict(rows)` 로 쓰면 타입 검사가 `Row` 를 짝으로 못 읽는다."""
    return {row[0]: row[1] for row in rows}


# ── 씨앗 ────────────────────────────────────────────────────────────────────


def ensure_builtin_property_fields(db: Session) -> list[str]:
    """씨앗 분야 중 **없는 것만** 만든다. 있으면(폐기했어도) 건드리지 않는다 — 고친 이름이
    이긴다."""
    have = set(db.scalars(select(PropertyField.key)))
    made: list[str] = []
    for order, (key, name) in enumerate(SEED_FIELDS.items(), start=1):
        if key in have:
            continue
        db.add(PropertyField(key=key, name=name, sort_order=order * 10))
        made.append(key)
    db.flush()
    return made


# ── 키 · 이름 ───────────────────────────────────────────────────────────────


def _key(raw: str | None) -> str | None:
    """적은 키를 다듬고 검사한다. 비었으면 `None`(만들 때 지어 준다)."""
    key = clean(raw)
    if key is None:
        return None
    if not KEY_PATTERN.match(key):
        raise AppError(
            "MNX-CATALOG-0056",
            f"키 「{key}」 는 쓸 수 없습니다 — 빈칸과 / ? # % \\ 없이 100자까지입니다.",
            status=422,
        )
    return key


def _numbered(keys: Any, prefix: str) -> int:
    best = 0
    for key in keys:
        tail = key[len(prefix) :] if key.startswith(prefix) else ""
        if tail.isdigit():
            best = max(best, int(tail))
    return best


class _KeyMaker:
    """`pf-0001` · `pg-0001` 의 다음 번호. 한 번에 여럿을 만들어도, 사람이 준 키와도 안
    겹친다."""

    def __init__(self, db: Session) -> None:
        self.taken = set(db.scalars(select(PropertyField.key))) | set(
            db.scalars(select(PropertyGroup.key))
        )
        self._next = {
            FIELD_KEY_PREFIX: _numbered(self.taken, FIELD_KEY_PREFIX) + 1,
            GROUP_KEY_PREFIX: _numbered(self.taken, GROUP_KEY_PREFIX) + 1,
        }

    def make(self, prefix: str) -> str:
        while True:
            key = f"{prefix}{self._next[prefix]:04d}"
            self._next[prefix] += 1
            if key not in self.taken:
                self.taken.add(key)
                return key


def _name(raw: str, *, limit: int) -> str:
    name = clean(raw)
    if not name:
        raise AppError("MNX-CATALOG-0056", "이름이 비었습니다.", status=422)
    return name[:limit]


def _field_or_404(db: Session, key: str) -> PropertyField:
    row = db.scalar(select(PropertyField).where(PropertyField.key == key))
    if row is None:
        raise NotFound("MNX-CATALOG-0059", f"없는 분야입니다: {key}")
    return row


def _group_or_404(db: Session, key: str) -> PropertyGroup:
    row = db.scalar(select(PropertyGroup).where(PropertyGroup.key == key))
    if row is None:
        raise NotFound("MNX-CATALOG-0060", f"없는 물성군입니다: {key}")
    return row


def _field_name_taken(db: Session, name: str, *, besides: PropertyField | None = None) -> None:
    """분야 이름은 **폐기한 것까지** 하나뿐이다 — 같은 이름이 둘이면 밀어 넣기가 어느 쪽인지
    모른다."""
    wanted = compare_key(name)
    for one in db.scalars(select(PropertyField)):
        if one is not besides and compare_key(one.name) == wanted:
            hint = " (폐기된 분야 — 되살리세요)" if one.retired_at else ""
            raise Conflict(
                "MNX-CATALOG-0058", f"이름이 같은 분야가 있습니다: {one.name}{hint}"
            )


def _group_name_taken(
    db: Session, field_row: PropertyField, name: str, *, besides: PropertyGroup | None = None
) -> None:
    """물성군 이름은 **한 분야 안에서** 하나뿐이다(폐기한 것까지). 분야가 다르면 같아도
    된다."""
    wanted = compare_key(name)
    for one in db.scalars(select(PropertyGroup).where(PropertyGroup.field_id == field_row.id)):
        if one is not besides and compare_key(one.name) == wanted:
            hint = " (폐기된 물성군 — 되살리세요)" if one.retired_at else ""
            raise Conflict(
                "MNX-CATALOG-0058",
                f"「{field_row.name}」 에 이름이 같은 물성군이 있습니다: {one.name}{hint}",
            )


def _record(
    db: Session,
    user: User,
    *,
    target: PropertyField | PropertyGroup,
    label: str,
    changes: dict[str, Any],
) -> None:
    """분야 · 물성군을 고친 일 — **사람이 해도 남긴다.** 바깥(SP)과 AI 가 읽는 전사 분류다
    (정의문과 같은 판단). 넣기 · 빼기와 밀어 넣기는 제 자리에서 따로 남긴다."""
    audit.record(
        db,
        action=audit.PROPERTY_TAXONOMY_CHANGED,
        actor=user,
        target_table=target.__tablename__,
        target_id=target.id,
        target_label=label,
        changes=changes,
    )


# ── 트리 ────────────────────────────────────────────────────────────────────


def tree(db: Session) -> TaxonomyOut:
    """분야 · 물성군 · 물성 전부 — 화면이 트리로 엮는다. 물성은 문헌 + 사내(`local.`) 다."""
    fields = list(
        db.scalars(select(PropertyField).order_by(PropertyField.sort_order, PropertyField.key))
    )
    groups = list(
        db.scalars(
            select(PropertyGroup).order_by(PropertyGroup.sort_order, PropertyGroup.name)
        )
    )
    members: dict[str, Any] = _pairs(
        db.execute(
            select(PropertyGroupMember.property_key, PropertyGroupMember.group_id)
        ).all()
    )
    counts: dict[str, int] = _pairs(
        db.execute(
            select(CatalogValue.property_key, func.count()).group_by(CatalogValue.property_key)
        ).all()
    )
    rows = list(
        db.scalars(
            select(CatalogDefinition)
            .order_by(CatalogDefinition.key)
            .limit(MAX_TREE_PROPERTIES + 1)
        )
    )
    truncated = len(rows) > MAX_TREE_PROPERTIES
    rows = rows[:MAX_TREE_PROPERTIES]

    group_key: dict[Any, str] = {one.id: one.key for one in groups}
    field_key = {one.id: one.key for one in fields}
    in_group: dict[Any, int] = defaultdict(int)
    for group_id in members.values():
        in_group[group_id] += 1
    groups_in_field: dict[Any, int] = defaultdict(int)
    properties_in_field: dict[Any, int] = defaultdict(int)
    for one in groups:
        if one.retired_at is None:
            groups_in_field[one.field_id] += 1
        properties_in_field[one.field_id] += in_group[one.id]

    return TaxonomyOut(
        fields=[
            PropertyFieldOut(
                key=one.key,
                name=one.name,
                description=one.description,
                sort_order=one.sort_order,
                retired=one.retired_at is not None,
                group_count=groups_in_field[one.id],
                property_count=properties_in_field[one.id],
            )
            for one in fields
        ],
        groups=[
            PropertyGroupOut(
                key=one.key,
                field_key=field_key[one.field_id],
                name=one.name,
                description=one.description,
                sort_order=one.sort_order,
                retired=one.retired_at is not None,
                property_count=in_group[one.id],
            )
            for one in groups
        ],
        properties=[
            TaxonomyPropertyOut(
                key=one.key,
                name=one.name,
                symbol=one.symbol,
                si_unit=one.si_unit,
                domain=one.domain,
                local=one.key.startswith(LOCAL_PREFIX),
                deprecated=one.deprecated,
                group_key=group_key.get(members.get(one.key)),
                value_count=counts.get(one.key, 0),
            )
            for one in rows
        ],
        truncated=truncated,
    )


# ── 분야 · 물성군 고치기 ─────────────────────────────────────────────────────


def create_field(db: Session, user: User, payload: PropertyFieldCreate) -> PropertyField:
    name = _name(payload.name, limit=100)
    key = _key(payload.key) or _KeyMaker(db).make(FIELD_KEY_PREFIX)
    if db.scalar(select(PropertyField.id).where(PropertyField.key == key)) is not None:
        raise Conflict("MNX-CATALOG-0057", f"이미 있는 분야 키입니다: {key}")
    _field_name_taken(db, name)
    last = db.scalar(select(func.max(PropertyField.sort_order))) or 0
    row = PropertyField(
        key=key,
        name=name,
        description=clean(payload.description),
        sort_order=last + 10,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    _record(
        db,
        user,
        target=row,
        label=f"분야 {name} ({key})",
        changes={"created": {"before": None, "after": {"key": key, "name": name}}},
    )
    return row


def update_field(
    db: Session, user: User, key: str, payload: PropertyFieldUpdate
) -> PropertyField:
    row = _field_or_404(db, key)
    data = payload.model_dump(exclude_unset=True)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if data.get("name") is not None:
        name = _name(data["name"], limit=100)
        if name != row.name:
            _field_name_taken(db, name, besides=row)
            before["name"], after["name"] = row.name, name
            row.name = name
    if "description" in data:
        description = clean(data["description"])
        if description != row.description:
            before["description"], after["description"] = row.description, description
            row.description = description
    if data.get("sort_order") is not None and data["sort_order"] != row.sort_order:
        before["sort_order"], after["sort_order"] = row.sort_order, data["sort_order"]
        row.sort_order = data["sort_order"]
    if data.get("retired") is not None and data["retired"] != (row.retired_at is not None):
        if data["retired"]:
            active = db.scalar(
                select(func.count())
                .select_from(PropertyGroup)
                .where(PropertyGroup.field_id == row.id, PropertyGroup.retired_at.is_(None))
            )
            if active:
                raise Conflict(
                    "MNX-CATALOG-0062",
                    f"쓰는 중인 물성군이 {active}개 있어 폐기할 수 없습니다 — "
                    "먼저 옮기거나 폐기하세요.",
                )
            row.retired_at = _now()
        else:
            row.retired_at = None
        before["retired"], after["retired"] = not data["retired"], data["retired"]

    if after:
        db.flush()
        _record(
            db,
            user,
            target=row,
            label=f"분야 {row.name} ({row.key})",
            changes={name: {"before": before[name], "after": after[name]} for name in after},
        )
    return row


def create_group(db: Session, user: User, payload: PropertyGroupCreate) -> PropertyGroup:
    field_row = _field_or_404(db, payload.field_key)
    if field_row.retired_at is not None:
        raise Conflict(
            "MNX-CATALOG-0061", f"폐기된 분야에는 물성군을 만들 수 없습니다: {field_row.name}"
        )
    name = _name(payload.name, limit=200)
    key = _key(payload.key) or _KeyMaker(db).make(GROUP_KEY_PREFIX)
    if db.scalar(select(PropertyGroup.id).where(PropertyGroup.key == key)) is not None:
        raise Conflict("MNX-CATALOG-0057", f"이미 있는 물성군 키입니다: {key}")
    _group_name_taken(db, field_row, name)
    last = (
        db.scalar(
            select(func.max(PropertyGroup.sort_order)).where(
                PropertyGroup.field_id == field_row.id
            )
        )
        or 0
    )
    row = PropertyGroup(
        key=key,
        field_id=field_row.id,
        name=name,
        description=clean(payload.description),
        sort_order=last + 10,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    _record(
        db,
        user,
        target=row,
        label=f"물성군 {name} ({key})",
        changes={
            "created": {
                "before": None,
                "after": {"key": key, "name": name, "field": field_row.key},
            }
        },
    )
    return row


def update_group(
    db: Session, user: User, key: str, payload: PropertyGroupUpdate
) -> PropertyGroup:
    row = _group_or_404(db, key)
    data = payload.model_dump(exclude_unset=True)
    field_row = db.get(PropertyField, row.field_id)
    assert field_row is not None
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if data.get("field_key") is not None and data["field_key"] != field_row.key:
        target = _field_or_404(db, data["field_key"])
        if target.retired_at is not None:
            raise Conflict(
                "MNX-CATALOG-0061", f"폐기된 분야로는 옮길 수 없습니다: {target.name}"
            )
        _group_name_taken(db, target, data.get("name") or row.name, besides=row)
        before["field"], after["field"] = field_row.key, target.key
        row.field_id = target.id
        field_row = target
    if data.get("name") is not None:
        name = _name(data["name"], limit=200)
        if name != row.name:
            _group_name_taken(db, field_row, name, besides=row)
            before["name"], after["name"] = row.name, name
            row.name = name
    if "description" in data:
        description = clean(data["description"])
        if description != row.description:
            before["description"], after["description"] = row.description, description
            row.description = description
    if data.get("sort_order") is not None and data["sort_order"] != row.sort_order:
        before["sort_order"], after["sort_order"] = row.sort_order, data["sort_order"]
        row.sort_order = data["sort_order"]
    if data.get("retired") is not None and data["retired"] != (row.retired_at is not None):
        if data["retired"]:
            inside = db.scalar(
                select(func.count())
                .select_from(PropertyGroupMember)
                .where(PropertyGroupMember.group_id == row.id)
            )
            if inside:
                raise Conflict(
                    "MNX-CATALOG-0062",
                    f"물성이 {inside}개 들어 있어 폐기할 수 없습니다 — "
                    "먼저 다른 군으로 옮기세요.",
                )
            row.retired_at = _now()
        else:
            if field_row.retired_at is not None:
                raise Conflict(
                    "MNX-CATALOG-0061",
                    f"분야 「{field_row.name}」 가 폐기돼 있습니다 — 분야를 먼저 되살리세요.",
                )
            row.retired_at = None
        before["retired"], after["retired"] = not data["retired"], data["retired"]

    if after:
        db.flush()
        _record(
            db,
            user,
            target=row,
            label=f"물성군 {row.name} ({row.key})",
            changes={name: {"before": before[name], "after": after[name]} for name in after},
        )
    return row


def _touch(db: Session, keys: list[str]) -> None:
    """소속이 바뀐 물성의 `updated_at` — 바깥이 읽는 물성 행에 물성군이 실린다."""
    if keys:
        db.execute(
            update(CatalogDefinition)
            .where(CatalogDefinition.key.in_(keys))
            .values(updated_at=func.now())
        )


def assign(
    db: Session, user: User, group_key: str | None, property_keys: list[str]
) -> TaxonomyAssignOut:
    """물성 여럿을 한 물성군에 — `group_key` 가 없으면 군에서 뺀다. 이미 거기 있으면
    그대로다."""
    wanted = list(dict.fromkeys(key.strip() for key in property_keys if key.strip()))
    known = set(
        db.scalars(select(CatalogDefinition.key).where(CatalogDefinition.key.in_(wanted)))
    )
    unknown = [key for key in wanted if key not in known]
    if unknown:
        raise NotFound("MNX-CATALOG-0063", f"없는 물성입니다: {', '.join(unknown[:10])}")

    group: PropertyGroup | None = None
    if group_key is not None:
        group = _group_or_404(db, group_key)
        if group.retired_at is not None:
            raise Conflict(
                "MNX-CATALOG-0061", f"폐기된 물성군에는 넣을 수 없습니다: {group.name}"
            )
        field_row = db.get(PropertyField, group.field_id)
        if field_row is not None and field_row.retired_at is not None:
            raise Conflict("MNX-CATALOG-0061", f"폐기된 분야의 물성군입니다: {field_row.name}")

    current = {
        one.property_key: one
        for one in db.scalars(
            select(PropertyGroupMember).where(PropertyGroupMember.property_key.in_(wanted))
        )
    }
    group_keys = _pairs(db.execute(select(PropertyGroup.id, PropertyGroup.key)))
    changed: list[str] = []
    unchanged: list[str] = []
    before: dict[str, str | None] = {}
    for key in wanted:
        member = current.get(key)
        if group is None:
            if member is None:
                unchanged.append(key)
                continue
            before[key] = group_keys.get(member.group_id)
            db.delete(member)
        elif member is None:
            before[key] = None
            db.add(
                PropertyGroupMember(property_key=key, group_id=group.id, created_by_id=user.id)
            )
        elif member.group_id != group.id:
            before[key] = group_keys.get(member.group_id)
            member.group_id = group.id
            member.created_by_id = user.id
        else:
            unchanged.append(key)
            continue
        changed.append(key)

    if changed:
        db.flush()
        _touch(db, changed)
        audit.record(
            db,
            action=audit.PROPERTY_TAXONOMY_ASSIGNED,
            actor=user,
            target_table="property_group_members",
            target_id=group.id if group else None,
            target_label=f"물성군 {group.name} ({group.key})" if group else "물성군에서 빼기",
            changes={
                "properties": {
                    "before": before,
                    "after": {key: group.key if group else None for key in changed},
                }
            },
        )
    return TaxonomyAssignOut(group_key=group_key, changed=changed, unchanged=unchanged)


# ── 밀어 넣기 ───────────────────────────────────────────────────────────────


class _RowError(Exception):
    """이 줄은 넣을 수 없다 — 메시지가 그대로 화면에 간다."""


@dataclass(eq=False)
class _FieldDraft:
    key: str
    name: str
    description: str | None
    existing: PropertyField | None
    row: PropertyField | None = None
    """넣은 뒤의 행(있던 것이면 그것)."""

    @property
    def action(self) -> str:
        if self.existing is None:
            return "create"
        if self.existing.retired_at is not None:
            return "restore"
        if self.name != self.existing.name or (
            self.description is not None and self.description != self.existing.description
        ):
            return "update"
        return "unchanged"


@dataclass(eq=False)
class _GroupDraft:
    key: str
    name: str
    field: _FieldDraft
    description: str | None
    existing: PropertyGroup | None
    before_field_key: str | None = None
    row: PropertyGroup | None = None

    @property
    def action(self) -> str:
        if self.existing is None:
            return "create"
        if self.before_field_key is not None and self.before_field_key != self.field.key:
            return "move"
        if self.existing.retired_at is not None:
            return "restore"
        if self.name != self.existing.name or (
            self.description is not None and self.description != self.existing.description
        ):
            return "update"
        return "unchanged"


@dataclass(eq=False)
class _MemberDraft:
    property_key: str
    property_name: str
    group: _GroupDraft
    before_group_key: str | None
    line: int
    domain: str = ""

    @property
    def cross_domain(self) -> bool:
        """씨앗 분야(키 = 키 앞머리)로 가는데 앞머리가 다르다 — 스키마의 `cross_domain`."""
        target = self.group.field.key
        return target in SEED_FIELDS and target != self.domain

    @property
    def action(self) -> str:
        if self.before_group_key is None:
            return "assign"
        if self.before_group_key != self.group.key:
            return "move"
        return "unchanged"


@dataclass
class ImportPlan:
    fields: list[_FieldDraft] = field(default_factory=list)
    groups: list[_GroupDraft] = field(default_factory=list)
    members: list[_MemberDraft] = field(default_factory=list)
    errors: list[ImportErrorOut] = field(default_factory=list)

    def out(self, *, applied: bool) -> TaxonomyImportOut:
        return TaxonomyImportOut(
            applied=applied,
            fields=[
                ImportFieldOut(
                    key=one.key,
                    name=one.name,
                    action=one.action,  # type: ignore[arg-type]
                    before_name=(
                        one.existing.name
                        if one.existing is not None and one.existing.name != one.name
                        else None
                    ),
                )
                for one in self.fields
            ],
            groups=[
                ImportGroupOut(
                    key=one.key,
                    name=one.name,
                    field_key=one.field.key,
                    action=one.action,  # type: ignore[arg-type]
                    before_name=(
                        one.existing.name
                        if one.existing is not None and one.existing.name != one.name
                        else None
                    ),
                    before_field_key=(
                        one.before_field_key if one.before_field_key != one.field.key else None
                    ),
                )
                for one in self.groups
            ],
            members=[
                ImportMemberOut(
                    property_key=one.property_key,
                    property_name=one.property_name,
                    group_key=one.group.key,
                    action=one.action,  # type: ignore[arg-type]
                    before_group_key=one.before_group_key,
                    domain=one.domain,
                    cross_domain=one.cross_domain,
                )
                for one in self.members
            ],
            errors=self.errors,
        )


class _Planner:
    """줄을 차례로 읽으며 분야 · 군 · 소속의 초안을 쌓는다. **DB 는 읽기만 한다.**"""

    def __init__(self, db: Session) -> None:
        self.keys = _KeyMaker(db)
        fields = list(db.scalars(select(PropertyField)))
        groups = list(db.scalars(select(PropertyGroup)))
        self.field_by_key = {one.key: one for one in fields}
        self.field_by_name = {compare_key(one.name): one for one in fields}
        self.field_key_of = {one.id: one.key for one in fields}
        self.group_by_key = {one.key: one for one in groups}
        self.group_by_name = {(one.field_id, compare_key(one.name)): one for one in groups}
        self.group_key_of: dict[Any, str] = {one.id: one.key for one in groups}

        self.definitions: dict[str, str] = _pairs(
            db.execute(select(CatalogDefinition.key, CatalogDefinition.name)).all()
        )
        self.domains: dict[str, str] = _pairs(
            db.execute(select(CatalogDefinition.key, CatalogDefinition.domain)).all()
        )
        self.by_name: dict[str, set[str]] = defaultdict(set)
        for key, name in self.definitions.items():
            self.by_name[compare_key(name)].add(key)
        self.by_alias: dict[str, set[str]] = defaultdict(set)
        for key, normalized in db.execute(
            select(PropertyAlias.property_key, PropertyAlias.normalized)
        ):
            if key in self.definitions:
                self.by_alias[normalized].add(key)
        self.membership: dict[str, Any] = _pairs(
            db.execute(
                select(PropertyGroupMember.property_key, PropertyGroupMember.group_id)
            ).all()
        )

        self.plan = ImportPlan()
        self._fields: dict[str, _FieldDraft] = {}
        self._fields_by_name: dict[str, _FieldDraft] = {}
        self._groups: dict[str, _GroupDraft] = {}
        self._groups_by_name: dict[tuple[str, str], _GroupDraft] = {}
        self._members: dict[str, _MemberDraft] = {}

    # 분야 ------------------------------------------------------------------

    def _add_field(self, draft: _FieldDraft) -> _FieldDraft:
        # 사람이 준 키도 맡아 둔다 — 뒤 줄에서 지어 주는 `pf-0003` 이 앞 줄의 `pf-0003` 과
        # 겹치지 않게.
        self.keys.taken.add(draft.key)
        self._fields[draft.key] = draft
        self._fields_by_name[compare_key(draft.name)] = draft
        self.plan.fields.append(draft)
        return draft

    def _same_text(
        self, kind: str, label: str, draft: Any, attr: str, value: str | None
    ) -> None:
        """같은 것이 여러 줄에 나오면 말이 같아야 한다 — 다르면 어느 쪽이 맞는지 모른다."""
        if value is None:
            return
        current = getattr(draft, attr)
        if current is None:
            setattr(draft, attr, value)
        elif current != value:
            raise _RowError(f"{kind} 「{label}」 의 설명이 줄마다 다릅니다.")

    def field_of(self, row: TaxonomyImportRow) -> _FieldDraft:
        name = clean(row.field)
        key = _row_key(row.field_key)
        description = clean(row.field_description)
        if not name and not key:
            raise _RowError("분야가 비었습니다.")

        if key:
            draft = self._fields.get(key)
            if draft is not None:
                if name and compare_key(name) != compare_key(draft.name):
                    raise _RowError(
                        f"분야 「{key}」 의 이름이 줄마다 다릅니다 — "
                        f"「{draft.name}」 · 「{name}」."
                    )
                self._same_text("분야", draft.name, draft, "description", description)
                return draft
            existing = self.field_by_key.get(key)
            if existing is None and not name:
                raise _RowError(f"새 분야 「{key}」 에는 이름이 필요합니다.")
            final = name or (existing.name if existing else "")
            self._field_name_free(final, key)
            return self._add_field(
                _FieldDraft(key=key, name=final, description=description, existing=existing)
            )

        assert name is not None
        wanted = compare_key(name)
        draft = self._fields_by_name.get(wanted)
        if draft is not None:
            self._same_text("분야", draft.name, draft, "description", description)
            return draft
        # 분야 칸에 키를 적어도 된다(`mechanical`).
        existing = self.field_by_name.get(wanted) or self.field_by_key.get(name)
        if existing is not None:
            draft = self._fields.get(existing.key)
            if draft is not None:
                self._same_text("분야", draft.name, draft, "description", description)
                return draft
            return self._add_field(
                _FieldDraft(
                    key=existing.key,
                    name=existing.name,
                    description=description,
                    existing=existing,
                )
            )
        return self._add_field(
            _FieldDraft(
                key=self.keys.make(FIELD_KEY_PREFIX),
                name=name[:100],
                description=description,
                existing=None,
            )
        )

    def _field_name_free(self, name: str, key: str) -> None:
        wanted = compare_key(name)
        other = self._fields_by_name.get(wanted)
        if other is not None and other.key != key:
            raise _RowError(f"이름 「{name}」 은 분야 「{other.key}」 가 이미 씁니다.")
        existing = self.field_by_name.get(wanted)
        if existing is not None and existing.key != key:
            raise _RowError(f"이름 「{name}」 은 분야 「{existing.key}」 가 이미 씁니다.")

    # 물성군 ----------------------------------------------------------------

    def _add_group(self, draft: _GroupDraft) -> _GroupDraft:
        self.keys.taken.add(draft.key)
        self._groups[draft.key] = draft
        self._groups_by_name[(draft.field.key, compare_key(draft.name))] = draft
        self.plan.groups.append(draft)
        return draft

    def group_of(self, row: TaxonomyImportRow, field_draft: _FieldDraft) -> _GroupDraft | None:
        name = clean(row.group)
        key = _row_key(row.group_key)
        description = clean(row.group_description)
        if not name and not key:
            if clean(row.property):
                raise _RowError("물성군이 비었습니다 — 물성은 물성군에 듭니다.")
            return None

        if key:
            draft = self._groups.get(key)
            if draft is not None:
                if draft.field is not field_draft:
                    raise _RowError(
                        f"물성군 「{draft.name}」 이 줄마다 다른 분야에 있습니다 — "
                        f"「{draft.field.name}」 · 「{field_draft.name}」."
                    )
                if name and compare_key(name) != compare_key(draft.name):
                    raise _RowError(
                        f"물성군 「{key}」 의 이름이 줄마다 다릅니다 — "
                        f"「{draft.name}」 · 「{name}」."
                    )
                self._same_text("물성군", draft.name, draft, "description", description)
                return draft
            existing = self.group_by_key.get(key)
            if existing is None and not name:
                raise _RowError(f"새 물성군 「{key}」 에는 이름이 필요합니다.")
            final = name or (existing.name if existing else "")
            self._group_name_free(final, key, field_draft)
            return self._add_group(
                _GroupDraft(
                    key=key,
                    name=final[:200],
                    field=field_draft,
                    description=description,
                    existing=existing,
                    before_field_key=self.field_key_of.get(existing.field_id)
                    if existing
                    else None,
                )
            )

        assert name is not None
        wanted = compare_key(name)
        draft = self._groups_by_name.get((field_draft.key, wanted))
        if draft is not None:
            self._same_text("물성군", draft.name, draft, "description", description)
            return draft
        existing = None
        if field_draft.existing is not None:
            existing = self.group_by_name.get((field_draft.existing.id, wanted))
            if existing is None:
                # 물성군 칸에 키를 적어도 된다 — 같은 분야의 것이면.
                by_key = self.group_by_key.get(name)
                if by_key is not None and by_key.field_id == field_draft.existing.id:
                    existing = by_key
        if existing is not None:
            draft = self._groups.get(existing.key)
            if draft is not None:
                if draft.field is not field_draft:
                    raise _RowError(
                        f"물성군 「{draft.name}」 이 줄마다 다른 분야에 있습니다 — "
                        f"「{draft.field.name}」 · 「{field_draft.name}」."
                    )
                self._same_text("물성군", draft.name, draft, "description", description)
                return draft
            return self._add_group(
                _GroupDraft(
                    key=existing.key,
                    name=existing.name,
                    field=field_draft,
                    description=description,
                    existing=existing,
                    before_field_key=self.field_key_of.get(existing.field_id),
                )
            )
        return self._add_group(
            _GroupDraft(
                key=self.keys.make(GROUP_KEY_PREFIX),
                name=name[:200],
                field=field_draft,
                description=description,
                existing=None,
            )
        )

    def _group_name_free(self, name: str, key: str, field_draft: _FieldDraft) -> None:
        wanted = compare_key(name)
        other = self._groups_by_name.get((field_draft.key, wanted))
        if other is not None and other.key != key:
            raise _RowError(
                f"「{field_draft.name}」 에 이름이 같은 물성군이 있습니다: "
                f"{other.name} ({other.key})"
            )
        if field_draft.existing is not None:
            existing = self.group_by_name.get((field_draft.existing.id, wanted))
            if existing is not None and existing.key != key:
                raise _RowError(
                    f"「{field_draft.name}」 에 이름이 같은 물성군이 있습니다: "
                    f"{existing.name} ({existing.key})"
                )

    # 물성 ------------------------------------------------------------------

    def resolve(self, text: str) -> str:
        """키 → 이름 → 별칭 차례로, **정확히 하나**에 맞아야 한다."""
        if text in self.definitions:
            return text
        wanted = compare_key(text)
        hits = self.by_name.get(wanted) or self.by_alias.get(wanted) or set()
        if not hits:
            raise _RowError(
                f"물성 「{text}」 을 찾을 수 없습니다 — "
                "키 · 이름 · 별칭이 정확히 맞아야 합니다."
            )
        if len(hits) > 1:
            listed = ", ".join(sorted(hits)[:5])
            raise _RowError(
                f"「{text}」 에 맞는 물성이 {len(hits)}개입니다({listed}) — 키로 적으세요."
            )
        return next(iter(hits))

    def member(self, row: TaxonomyImportRow, group: _GroupDraft, line: int) -> None:
        text = clean(row.property)
        if not text:
            return
        key = self.resolve(text)
        name = self.definitions[key]
        seen = self._members.get(key)
        if seen is not None:
            if seen.group is not group:
                raise _RowError(
                    f"물성 「{name}」({key}) 이 두 물성군에 있습니다 — "
                    f"「{seen.group.name}」({seen.line}번 줄) · 「{group.name}」. "
                    "물성은 한 군에만 듭니다."
                )
            return
        draft = _MemberDraft(
            property_key=key,
            property_name=name,
            group=group,
            before_group_key=self.group_key_of.get(self.membership.get(key)),
            line=line,
            domain=self.domains.get(key, ""),
        )
        self._members[key] = draft
        self.plan.members.append(draft)


def _row_key(raw: str | None) -> str | None:
    try:
        return _key(raw)
    except AppError as exc:
        raise _RowError(exc.message) from None


def plan_import(db: Session, rows: list[TaxonomyImportRow]) -> ImportPlan:
    """붙여넣은 줄로 무엇이 생기고 바뀌는지 — **DB 를 안 바꾼다.**"""
    planner = _Planner(db)
    for line, row in enumerate(rows, start=1):
        cells = (
            row.field,
            row.field_key,
            row.group,
            row.group_key,
            row.property,
            row.field_description,
            row.group_description,
        )
        if not any(clean(one) for one in cells):
            continue
        try:
            field_draft = planner.field_of(row)
            group_draft = planner.group_of(row, field_draft)
            if group_draft is not None:
                planner.member(row, group_draft, line)
        except _RowError as exc:
            planner.plan.errors.append(ImportErrorOut(row=line, message=str(exc)))
    return planner.plan


def apply_import(db: Session, user: User, plan: ImportPlan) -> None:
    """계획을 그대로 넣는다. **오류가 있으면 하나도 안 넣는다.**"""
    if plan.errors:
        raise AppError(
            "MNX-CATALOG-0064",
            f"넣을 수 없는 줄이 {len(plan.errors)}개 있어 아무것도 넣지 않았습니다 — "
            "미리 보기에서 고친 뒤 다시 넣으세요.",
            status=422,
        )
    now = _now()
    last_field = db.scalar(select(func.max(PropertyField.sort_order))) or 0
    for draft in plan.fields:
        if draft.existing is None:
            last_field += 10
            draft.row = PropertyField(
                key=draft.key,
                name=draft.name,
                description=draft.description,
                sort_order=last_field,
                created_by_id=user.id,
            )
            db.add(draft.row)
            continue
        draft.row = draft.existing
        if draft.row.name != draft.name:
            draft.row.name = draft.name
        if draft.description is not None and draft.row.description != draft.description:
            draft.row.description = draft.description
        if draft.row.retired_at is not None:
            draft.row.retired_at = None
    db.flush()

    last_group: dict[Any, int] = _pairs(
        db.execute(
            select(PropertyGroup.field_id, func.max(PropertyGroup.sort_order)).group_by(
                PropertyGroup.field_id
            )
        ).all()
    )
    for group in plan.groups:
        field_row = group.field.row
        assert field_row is not None
        if group.existing is None:
            last_group[field_row.id] = (last_group.get(field_row.id) or 0) + 10
            group.row = PropertyGroup(
                key=group.key,
                field_id=field_row.id,
                name=group.name,
                description=group.description,
                sort_order=last_group[field_row.id],
                created_by_id=user.id,
            )
            db.add(group.row)
            continue
        group.row = group.existing
        if group.row.field_id != field_row.id:
            group.row.field_id = field_row.id
        if group.row.name != group.name:
            group.row.name = group.name
        if group.description is not None and group.row.description != group.description:
            group.row.description = group.description
        if group.row.retired_at is not None:
            group.row.retired_at = None
    db.flush()

    moved: list[str] = []
    current = {
        one.property_key: one
        for one in db.scalars(
            select(PropertyGroupMember).where(
                PropertyGroupMember.property_key.in_([m.property_key for m in plan.members])
            )
        )
    }
    for member in plan.members:
        if member.action == "unchanged":
            continue
        group_row = member.group.row
        assert group_row is not None
        row = current.get(member.property_key)
        if row is None:
            db.add(
                PropertyGroupMember(
                    property_key=member.property_key,
                    group_id=group_row.id,
                    created_by_id=user.id,
                )
            )
        else:
            row.group_id = group_row.id
            row.created_by_id = user.id
        moved.append(member.property_key)
    db.flush()
    _touch(db, moved)

    def count(items: list[Any], action: str) -> int:
        return sum(1 for one in items if one.action == action)

    audit.record(
        db,
        action=audit.PROPERTY_TAXONOMY_IMPORTED,
        actor=user,
        target_table="property_groups",
        target_id=None,
        target_label="물성 분류 밀어 넣기",
        changes={
            "fields": {
                "before": None,
                "after": {
                    "create": [one.key for one in plan.fields if one.action == "create"],
                    "update": count(plan.fields, "update"),
                    "restore": count(plan.fields, "restore"),
                },
            },
            "groups": {
                "before": None,
                "after": {
                    "create": count(plan.groups, "create"),
                    "update": count(plan.groups, "update"),
                    "move": count(plan.groups, "move"),
                    "restore": count(plan.groups, "restore"),
                },
            },
            "members": {
                "before": None,
                "after": {
                    "assign": count(plan.members, "assign"),
                    "move": count(plan.members, "move"),
                },
            },
            "at": {"before": None, "after": now.isoformat()},
        },
    )


# ── 바깥(SP)이 읽는 목록 ──────────────────────────────────────────────────────


def _page_size(page_size: int) -> int:
    if page_size > FEED_PAGE_MAX:
        raise AppError(
            "MNX-CATALOG-0065",
            f"page_size 는 {FEED_PAGE_MAX} 이하입니다 — "
            "깎아서 주면 받는 쪽이 끝으로 읽습니다.",
            status=422,
        )
    return page_size


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _joined(values: Any) -> str | None:
    """여럿을 `;` 로 — 값 안의 `;` 는 `,` 로 바꾼다(받는 쪽이 둘로 가르지 않게)."""
    items = [str(one).replace(MULTI_SEP, ",").strip() for one in values or []]
    items = [one for one in items if one]
    return MULTI_SEP.join(items) if items else None


def feed_fields(db: Session, page: int, page_size: int) -> FeedFieldPage:
    size = _page_size(page_size)
    total = db.scalar(select(func.count()).select_from(PropertyField)) or 0
    rows = list(
        db.scalars(
            select(PropertyField)
            .order_by(PropertyField.key)
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    ids = [one.id for one in rows]
    groups: dict[Any, int] = _pairs(
        db.execute(
            select(PropertyGroup.field_id, func.count())
            .where(PropertyGroup.field_id.in_(ids), PropertyGroup.retired_at.is_(None))
            .group_by(PropertyGroup.field_id)
        ).all()
    )
    properties: dict[Any, int] = _pairs(
        db.execute(
            select(PropertyGroup.field_id, func.count())
            .join(PropertyGroupMember, PropertyGroupMember.group_id == PropertyGroup.id)
            .where(PropertyGroup.field_id.in_(ids))
            .group_by(PropertyGroup.field_id)
        ).all()
    )
    return FeedFieldPage(
        items=[
            FeedFieldOut(
                key=one.key,
                name=one.name,
                description=one.description,
                sort_order=one.sort_order,
                group_count=groups.get(one.id, 0),
                property_count=properties.get(one.id, 0),
                status="active" if one.retired_at is None else "deprecated",
                is_active=one.retired_at is None,
                deleted=one.retired_at is not None,
                updated_at=_utc(one.updated_at),
            )
            for one in rows
        ],
        total=total,
        page=page,
        page_size=size,
    )


def feed_groups(db: Session, page: int, page_size: int) -> FeedGroupPage:
    size = _page_size(page_size)
    total = db.scalar(select(func.count()).select_from(PropertyGroup)) or 0
    rows = db.execute(
        select(PropertyGroup, PropertyField)
        .join(PropertyField, PropertyField.id == PropertyGroup.field_id)
        .order_by(PropertyGroup.key)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    ids = [group.id for group, _ in rows]
    counts: dict[Any, int] = _pairs(
        db.execute(
            select(PropertyGroupMember.group_id, func.count())
            .where(PropertyGroupMember.group_id.in_(ids))
            .group_by(PropertyGroupMember.group_id)
        ).all()
    )
    return FeedGroupPage(
        items=[
            FeedGroupOut(
                key=group.key,
                name=group.name,
                description=group.description,
                field_key=field_row.key,
                field_name=field_row.name,
                sort_order=group.sort_order,
                property_count=counts.get(group.id, 0),
                # 분야가 폐기됐으면 그 안의 군도 쓰지 않는 것이다.
                status=(
                    "active"
                    if group.retired_at is None and field_row.retired_at is None
                    else "deprecated"
                ),
                is_active=group.retired_at is None and field_row.retired_at is None,
                deleted=group.retired_at is not None or field_row.retired_at is not None,
                updated_at=_utc(max(group.updated_at, field_row.updated_at)),
            )
            for group, field_row in rows
        ],
        total=total,
        page=page,
        page_size=size,
    )


def feed_properties(db: Session, page: int, page_size: int) -> FeedPropertyPage:
    """허브 키 전부 — 문헌 + 사내(`local.`), 폐기한 것까지. 행마다 물성군 · 분야가 실린다."""
    size = _page_size(page_size)
    total = db.scalar(select(func.count()).select_from(CatalogDefinition)) or 0
    rows = list(
        db.scalars(
            select(CatalogDefinition)
            .order_by(CatalogDefinition.key)
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    keys = [one.key for one in rows]
    placed = {
        key: (group, field_row)
        for key, group, field_row in db.execute(
            select(PropertyGroupMember.property_key, PropertyGroup, PropertyField)
            .join(PropertyGroup, PropertyGroup.id == PropertyGroupMember.group_id)
            .join(PropertyField, PropertyField.id == PropertyGroup.field_id)
            .where(PropertyGroupMember.property_key.in_(keys))
        ).all()
    }
    aliases: dict[str, list[str]] = defaultdict(list)
    alias_at: dict[str, datetime] = {}
    for key, alias, created_at in db.execute(
        select(PropertyAlias.property_key, PropertyAlias.alias, PropertyAlias.created_at)
        .where(PropertyAlias.property_key.in_(keys))
        .order_by(PropertyAlias.property_key, PropertyAlias.alias)
    ):
        aliases[key].append(alias)
        if key not in alias_at or created_at > alias_at[key]:
            alias_at[key] = created_at

    items: list[FeedPropertyOut] = []
    for one in rows:
        group, field_row = placed.get(one.key, (None, None))
        stamps = [one.updated_at]
        if group is not None and field_row is not None:
            stamps += [group.updated_at, field_row.updated_at]
        if one.key in alias_at:
            stamps.append(alias_at[one.key])
        items.append(
            FeedPropertyOut(
                key=one.key,
                name=one.name,
                symbol=one.symbol,
                unit=one.si_unit,
                value_type=one.value_type,
                description=one.description,
                test_standard=one.test_standard,
                condition_axes=_joined(one.condition_axes),
                origin="local" if one.key.startswith(LOCAL_PREFIX) else "literature",
                domain=one.domain,
                group_key=group.key if group else None,
                group_name=group.name if group else None,
                field_key=field_row.key if field_row else None,
                field_name=field_row.name if field_row else None,
                aliases=_joined(dict.fromkeys(aliases.get(one.key, []))),
                status="deprecated" if one.deprecated else "active",
                superseded_by=one.superseded_by,
                deprecation_note=one.deprecation_note,
                is_active=not one.deprecated,
                deleted=one.deprecated,
                updated_at=_utc(max(_utc(stamp) for stamp in stamps)),
            )
        )
    return FeedPropertyPage(items=items, total=total, page=page, page_size=size)


def field_out(db: Session, row: PropertyField) -> PropertyFieldOut:
    """분야 하나 — 고친 뒤 돌려줄 모양(트리의 한 줄과 같다)."""
    groups = list(db.scalars(select(PropertyGroup).where(PropertyGroup.field_id == row.id)))
    inside = (
        db.scalar(
            select(func.count())
            .select_from(PropertyGroupMember)
            .where(PropertyGroupMember.group_id.in_([one.id for one in groups]))
        )
        if groups
        else 0
    )
    return PropertyFieldOut(
        key=row.key,
        name=row.name,
        description=row.description,
        sort_order=row.sort_order,
        retired=row.retired_at is not None,
        group_count=sum(1 for one in groups if one.retired_at is None),
        property_count=inside or 0,
    )


def group_out(db: Session, row: PropertyGroup) -> PropertyGroupOut:
    field_row = db.get(PropertyField, row.field_id)
    assert field_row is not None
    inside = db.scalar(
        select(func.count())
        .select_from(PropertyGroupMember)
        .where(PropertyGroupMember.group_id == row.id)
    )
    return PropertyGroupOut(
        key=row.key,
        field_key=field_row.key,
        name=row.name,
        description=row.description,
        sort_order=row.sort_order,
        retired=row.retired_at is not None,
        property_count=inside or 0,
    )


__all__ = [
    "FEED_PAGE_MAX",
    "MAX_TREE_PROPERTIES",
    "SEED_FIELDS",
    "ImportPlan",
    "apply_import",
    "assign",
    "create_field",
    "create_group",
    "ensure_builtin_property_fields",
    "feed_fields",
    "feed_groups",
    "feed_properties",
    "field_out",
    "group_out",
    "plan_import",
    "tree",
    "update_field",
    "update_group",
]
