"""적용 부품 — 재료가 쓰이는 부품 줄(파트명 · 제품 · 부품코드 · 사업부 · 출처, ADR 0064).

    읽기       summary(재료 여럿의 이름 목록) · page(한 재료의 줄 — 찾기 · 거르기 · 쪽)
    넣기       plan → apply. 미리보기에서 줄마다 new · exists · error, 넣는 것은 new 만
    고치기     update — 이름이 바뀌면 기준정보 값을 다시 찾고 쓰는 수를 옮긴다
    지우기     remove
    BOM       plan_bom → apply_bom. 재질 글자로 재료를 찾아 재료마다 줄을 넣는다

## 이름 셋은 기준정보를 거친다

파트명 · 제품 · 사업부는 값마다 기준정보를 찾거나 만들고(`resolve_or_create`) **쓰는 수를
옮긴다**
— 여기서 안 옮기면 피커에 「쓰이지 않는 값」 이 남고 관리 화면의 「쓰는 곳」 이 거짓말을 한다
(예전 `set_uses` 와 같은 규칙).

## 예전 칸(`applied_products` · `applied_parts`)

재료 응답의 두 목록은 이 줄들에서 뽑은 이름이다(`summary`). 그 칸으로 **저장**하면(재료 만들기
· 고치기 · 일괄 등록 · 이관 · MCP) 그 축의 **이름만 있는 줄**만 갈아 끼운다(`set_names`).
부품코드
· 제품 · 사업부가 붙은 줄은 표에서만 고친다 — 칩 편집 한 번에 BOM 에서 온 줄이 사라지면 안
된다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.materials.models import PART_SOURCES, USE_AXES, Material, MaterialPart
from app.modules.vocabulary import services as vocabulary_services
from app.modules.workbench.models import BomAlias
from app.shared import permissions
from app.shared.errors import AppError
from app.shared.text import clean, compare_key

#: 한 번에 넣는 줄의 상한 — BOM 하나가 수백 줄이다.
LINES_MAX = 2000
#: 줄의 칸 → 기준정보 축 · 모델 칸.
NAMED = (
    ("part", "part", "part_term_id", "part_name"),
    ("product", "product", "product_term_id", "product_name"),
    ("division", "division", "division_term_id", "division_name"),
)


def _key(part: str | None, product: str | None, code: str | None, division: str | None) -> str:
    """같은 줄을 가리는 열쇠 — 넷의 비교키를 잇는다. 대소문자 · 공백 차이로 두 줄이 되면 안
    된다."""
    return "|".join(compare_key(one) for one in (part, product, code, division))


def _row_key(row: MaterialPart) -> str:
    return _key(row.part_name, row.product_name, row.part_code, row.division_name)


# ── 읽기 ────────────────────────────────────────────────────────────────────


def summary(
    db: Session, material_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, list[str]]]:
    """재료들의 **이름 목록**(제품 · 파트)을 한 번에 — 예전 `uses_of` 자리.

    목록이 재료마다 물으면 N+1 이다. 같은 이름이 여러 줄에 있어도 한 번만, 적은 차례로.
    """
    if not material_ids:
        return {}
    found: dict[uuid.UUID, dict[str, list[str]]] = {
        one: {axis: [] for axis in USE_AXES} for one in material_ids
    }
    seen: dict[tuple[uuid.UUID, str], set[str]] = defaultdict(set)
    rows = db.execute(
        select(MaterialPart.material_id, MaterialPart.product_name, MaterialPart.part_name)
        .where(MaterialPart.material_id.in_(material_ids))
        .order_by(MaterialPart.position, MaterialPart.created_at)
    )
    for material_id, product, part in rows:
        for axis, name in (("product", product), ("part", part)):
            if name and name not in seen[(material_id, axis)]:
                seen[(material_id, axis)].add(name)
                found[material_id][axis].append(name)
    return found


def page(
    db: Session,
    material_id: uuid.UUID,
    *,
    q: str | None = None,
    division: str | None = None,
    product: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MaterialPart], int, dict[str, list[tuple[str, int]]]]:
    """한 재료의 줄 — 찾기(파트명 · 부품코드 · 제품) · 사업부 · 제품 거르기 · 쪽.

    거르기 고르개(`facets`)는 **거르기 전** 그 재료 전체에서 센다 — 고르면 다른 선택지가
    사라지면 사람은 되돌아갈 길을 잃는다."""
    base = select(MaterialPart).where(MaterialPart.material_id == material_id)
    facets: dict[str, list[tuple[str, int]]] = {}
    for name, column in (
        ("divisions", MaterialPart.division_name),
        ("products", MaterialPart.product_name),
    ):
        facets[name] = [
            (str(value), int(count))
            for value, count in db.execute(
                select(column, func.count())
                .where(MaterialPart.material_id == material_id, column.is_not(None))
                .group_by(column)
                .order_by(func.count().desc(), column)
            )
        ]
    query = base
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(
                MaterialPart.part_name.ilike(needle),
                MaterialPart.part_code.ilike(needle),
                MaterialPart.product_name.ilike(needle),
                MaterialPart.note.ilike(needle),
            )
        )
    if division:
        query = query.where(MaterialPart.division_name == division)
    if product:
        query = query.where(MaterialPart.product_name == product)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        db.scalars(
            query.order_by(MaterialPart.position, MaterialPart.created_at)
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total, facets


# ── 넣기 ────────────────────────────────────────────────────────────────────


@dataclass
class Line:
    """사람이 적은 줄 하나 — 다듬은 뒤."""

    part: str | None
    product: str | None
    part_code: str | None
    division: str | None
    note: str | None = None

    @property
    def key(self) -> str:
        return _key(self.part, self.product, self.part_code, self.division)


def _line(raw: dict[str, Any], *, division: str | None = None) -> Line:
    return Line(
        part=clean(raw.get("part")),
        product=clean(raw.get("product")),
        part_code=clean(raw.get("part_code")),
        division=clean(raw.get("division")) or clean(division),
        note=clean(raw.get("note")),
    )


@dataclass
class Plan:
    """무엇이 들어갈지 — 줄마다 `new` · `exists` · `error`."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for one in self.rows if one["status"] == status)

    def out(self, *, applied: bool) -> dict[str, Any]:
        return {
            "applied": applied,
            "new": self.count("new"),
            "exists": self.count("exists"),
            "errors": self.count("error"),
            "rows": self.rows,
        }


def plan(db: Session, material: Material, lines: Sequence[dict[str, Any]]) -> Plan:
    """한 재료에 넣을 줄 — **쓰지 않는다.** 같은 줄 · 이미 있는 줄 · 빈 줄을 가린다."""
    if len(lines) > LINES_MAX:
        raise AppError(
            "MNX-MATERIALS-0060",
            f"한 번에 {LINES_MAX}줄까지 넣습니다(받은 줄 {len(lines)}).",
            status=422,
        )
    have = {
        _row_key(row)
        for row in db.scalars(
            select(MaterialPart).where(MaterialPart.material_id == material.id)
        )
    }
    out = Plan()
    seen: set[str] = set()
    for index, raw in enumerate(lines):
        line = _line(raw)
        row: dict[str, Any] = {
            "index": index,
            "part": line.part,
            "product": line.product,
            "part_code": line.part_code,
            "division": line.division,
            "note": line.note,
            "status": "new",
            "reason": None,
        }
        out.rows.append(row)
        out.lines.append(line)
        if not (line.part or line.product or line.part_code):
            row.update(
                status="error", reason="파트명 · 제품 · 부품코드 중 하나는 있어야 합니다."
            )
            continue
        if line.part_code and len(line.part_code) > 100:
            row.update(status="error", reason="부품코드가 100자를 넘습니다.")
            continue
        if line.key in have:
            row.update(status="exists", reason="이미 있는 줄입니다.")
            continue
        if line.key in seen:
            row.update(status="exists", reason="같은 줄이 위에 있습니다.")
            continue
        seen.add(line.key)
    return out


def _term(
    db: Session, slug: str, value: str | None, *, created_by_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, str | None]:
    if not value:
        return None, None
    term = vocabulary_services.resolve_or_create(
        db, vocabulary_services.get_vocabulary(db, slug), value, created_by_id=created_by_id
    )
    if term is None:
        return None, None
    vocabulary_services.bump_usage(db, term.id, 1)
    return term.id, term.value


def _next_position(db: Session, material_id: uuid.UUID) -> int:
    top = db.scalar(
        select(func.max(MaterialPart.position)).where(MaterialPart.material_id == material_id)
    )
    return int(top) + 1 if top is not None else 0


def _add(
    db: Session,
    material: Material,
    line: Line,
    *,
    position: int,
    source: str,
    source_ref: str | None,
    created_by_id: uuid.UUID | None,
) -> MaterialPart:
    part_id, part_name = _term(db, "part", line.part, created_by_id=created_by_id)
    product_id, product_name = _term(db, "product", line.product, created_by_id=created_by_id)
    division_id, division_name = _term(
        db, "division", line.division, created_by_id=created_by_id
    )
    row = MaterialPart(
        material_id=material.id,
        part_term_id=part_id,
        part_name=part_name,
        product_term_id=product_id,
        product_name=product_name,
        part_code=line.part_code,
        division_term_id=division_id,
        division_name=division_name,
        source=source,
        source_ref=source_ref,
        note=line.note,
        position=position,
        created_by_id=created_by_id,
    )
    db.add(row)
    return row


def apply(
    db: Session,
    user: User,
    material: Material,
    planned: Plan,
    *,
    source: str = "manual",
    source_ref: str | None = None,
) -> list[MaterialPart]:
    """계획의 `new` 줄을 넣는다. 커밋은 부르는 쪽."""
    if source not in PART_SOURCES:
        raise AppError("MNX-MATERIALS-0061", f"모르는 출처입니다: {source}", status=422)
    position = _next_position(db, material.id)
    have = {
        _row_key(row)
        for row in db.scalars(
            select(MaterialPart).where(MaterialPart.material_id == material.id)
        )
    }
    made: list[tuple[dict[str, Any], MaterialPart]] = []
    for row, line in zip(planned.rows, planned.lines, strict=True):
        if row["status"] != "new":
            continue
        added = _add(
            db,
            material,
            line,
            position=position,
            source=source,
            source_ref=clean(source_ref),
            created_by_id=user.id,
        )
        # 열쇠는 **기준정보가 정한 이름으로** — 별칭으로 적은 「포스코(주)」 가 「포스코」 와
        # 두 줄이
        # 되지 않게.
        if _row_key(added) in have:
            # 별칭을 풀고 나니 이미 있는 줄이었다 — 넣지 않고 쓰는 수를 되돌린다.
            _release(db, added)
            db.expunge(added)
            row.update(status="exists", reason="이미 있는 줄입니다(기준정보 이름으로 같다).")
            continue
        have.add(_row_key(added))
        position += 1
        made.append((row, added))
    db.flush()
    for row, added in made:
        row["id"] = str(added.id)
    return [added for _, added in made]


def _release(db: Session, row: MaterialPart) -> None:
    for _, _, column, _ in NAMED:
        vocabulary_services.bump_usage(db, getattr(row, column), -1)


# ── 고치기 · 지우기 ──────────────────────────────────────────────────────────


def update(
    db: Session, user: User, row: MaterialPart, changes: dict[str, Any]
) -> MaterialPart:
    """**보낸 칸만** 고친다 — 안 보낸 것과 비운 것을 가른다(AGENTS · API)."""
    line = Line(
        part=clean(changes["part"]) if "part" in changes else row.part_name,
        product=clean(changes["product"]) if "product" in changes else row.product_name,
        part_code=clean(changes["part_code"]) if "part_code" in changes else row.part_code,
        division=clean(changes["division"]) if "division" in changes else row.division_name,
        note=clean(changes["note"]) if "note" in changes else row.note,
    )
    if not (line.part or line.product or line.part_code):
        raise AppError(
            "MNX-MATERIALS-0062",
            "파트명 · 제품 · 부품코드 중 하나는 있어야 합니다.",
            status=422,
        )
    for name, slug, column, text_column in NAMED:
        if name not in changes:
            continue
        vocabulary_services.bump_usage(db, getattr(row, column), -1)
        term_id, value = _term(db, slug, getattr(line, name), created_by_id=user.id)
        setattr(row, column, term_id)
        setattr(row, text_column, value)
    row.part_code = line.part_code
    row.note = line.note
    key = _row_key(row)
    others = db.scalars(
        select(MaterialPart).where(
            MaterialPart.material_id == row.material_id, MaterialPart.id != row.id
        )
    )
    if any(_row_key(one) == key for one in others):
        raise AppError(
            "MNX-MATERIALS-0063",
            "같은 줄이 이미 있습니다 — 그 줄을 고치거나 지우세요.",
            status=409,
        )
    db.flush()
    return row


def remove(db: Session, material: Material, ids: Sequence[uuid.UUID]) -> int:
    rows = list(
        db.scalars(
            select(MaterialPart).where(
                MaterialPart.material_id == material.id, MaterialPart.id.in_(list(ids))
            )
        )
    )
    for row in rows:
        _release(db, row)
        db.delete(row)
    db.flush()
    return len(rows)


def release_all(db: Session, material: Material) -> None:
    """재료가 사라질 때 쓰는 수를 되돌린다. **줄은 남긴다** — 재료가 되살아날 수 있다."""
    for row in db.scalars(select(MaterialPart).where(MaterialPart.material_id == material.id)):
        _release(db, row)


def copy_all(
    db: Session, source: Material, target: Material, *, created_by_id: uuid.UUID | None
) -> None:
    """다른 두께로 옮겨 새로 만든 재료에 줄을 그대로 — 출처까지(`relocation`)."""
    position = _next_position(db, target.id)
    have = {
        _row_key(row)
        for row in db.scalars(
            select(MaterialPart).where(MaterialPart.material_id == target.id)
        )
    }
    for row in db.scalars(
        select(MaterialPart)
        .where(MaterialPart.material_id == source.id)
        .order_by(MaterialPart.position)
    ):
        if _row_key(row) in have:
            continue
        copy = MaterialPart(
            material_id=target.id,
            part_term_id=row.part_term_id,
            part_name=row.part_name,
            product_term_id=row.product_term_id,
            product_name=row.product_name,
            part_code=row.part_code,
            division_term_id=row.division_term_id,
            division_name=row.division_name,
            source=row.source,
            source_ref=row.source_ref,
            note=row.note,
            position=position,
            created_by_id=created_by_id,
        )
        db.add(copy)
        for _, _, column, _ in NAMED:
            vocabulary_services.bump_usage(db, getattr(row, column), 1)
        have.add(_row_key(row))
        position += 1
    db.flush()


# ── 예전 칸 ─────────────────────────────────────────────────────────────────


def set_names(
    db: Session,
    material: Material,
    axis: str,
    values: Sequence[str],
    *,
    created_by_id: uuid.UUID | None = None,
) -> None:
    """예전 칸(`applied_products` · `applied_parts`)으로 저장 — **이름만 있는 줄**만 바꾼다.

    이름만 있는 줄 = 그 축의 이름 하나뿐이고 다른 칸(나머지 이름 · 부품코드 · 사업부 · 비고)이
    빈 줄. 그 밖의 줄은 손대지 않는다 — 그 줄의 이름이 목록에 있으면 새 줄을 만들지 않고,
    목록에서 빠져도 지우지 않는다(표에서 고친다).

    **목록에 남은 이름의 줄은 그대로 둔다** — 지우고 다시 만들면 출처(BOM · 예전 입력) ·
    등록자가 이 저장의 것으로 바뀐다. 차례만 목록을 따른다.
    """
    if axis not in USE_AXES:
        raise AppError("MNX-MATERIALS-0014", f"모르는 용도 축입니다: {axis}", status=422)
    column = "product_term_id" if axis == "product" else "part_term_id"
    other = "part_term_id" if axis == "product" else "product_term_id"
    rows = list(
        db.scalars(select(MaterialPart).where(MaterialPart.material_id == material.id))
    )
    simple: dict[uuid.UUID, MaterialPart] = {}
    extra: list[MaterialPart] = []
    rich: list[MaterialPart] = []
    for row in rows:
        term_id = getattr(row, column)
        if (
            term_id is None
            or getattr(row, other) is not None
            or row.part_code is not None
            or row.division_term_id is not None
            or row.note
        ):
            rich.append(row)
        elif term_id in simple:
            extra.append(row)  # 같은 이름의 이름만 있는 줄이 둘 — 하나만 남긴다
        else:
            simple[term_id] = row
    kept = {getattr(row, column) for row in rich}
    base = max((row.position for row in rich), default=-1) + 1
    vocabulary = vocabulary_services.get_vocabulary(db, axis)
    seen: set[uuid.UUID] = set()
    for offset, raw in enumerate(values):
        term = vocabulary_services.resolve_or_create(
            db, vocabulary, raw, created_by_id=created_by_id
        )
        if term is None or term.id in seen or term.id in kept:
            # 빈 값 · 같은 값 두 번 · 이미 표의 줄에 있는 이름은 넘긴다.
            continue
        seen.add(term.id)
        if term.id in simple:
            simple.pop(term.id).position = base + offset
            continue
        row = MaterialPart(
            material_id=material.id,
            source="manual",
            position=base + offset,
            created_by_id=created_by_id,
        )
        setattr(row, column, term.id)
        setattr(row, "product_name" if axis == "product" else "part_name", term.value)
        db.add(row)
        vocabulary_services.bump_usage(db, term.id, 1)
    # 목록에서 빠진 이름의 줄.
    for row in [*simple.values(), *extra]:
        _release(db, row)
        db.delete(row)
    db.flush()


# ── BOM ─────────────────────────────────────────────────────────────────────

#: 재질 하나에 후보를 몇 개까지 보이나.
CANDIDATES_MAX = 5


def _resolve_material(
    db: Session, user: User, text: str, cache: dict[str, tuple[str, Any]]
) -> tuple[str, Any]:
    """재질 글자 → (`ok`, 재료) · (`ambiguous`, [후보]) · (`missing`, None).

    차례: BOM 덱이 기억한 짝(`bom_aliases`) → 재료 이름 → 별칭 → Grade(하나에만 맞을 때).
    **보이는 재료만** 본다. 이름이 비슷하다고 고르지 않는다 — 고르는 것은 사람이다.
    """
    key = compare_key(text)
    if key in cache:
        return cache[key]
    visible = permissions.visible_materials(db, user).where(Material.deleted_at.is_(None))
    found: tuple[str, Any] = ("missing", None)
    remembered = db.scalar(select(BomAlias.material_id).where(BomAlias.normalized == key))
    if remembered is not None:
        hit = db.scalar(visible.where(Material.id == remembered))
        if hit is not None:
            found = ("ok", hit)
    if found[0] == "missing":
        for column in (Material.record_name, Material.alias, Material.grade):
            hits = list(
                db.scalars(
                    visible.where(func.lower(func.trim(column)) == key).limit(
                        CANDIDATES_MAX + 1
                    )
                )
            )
            if len(hits) == 1:
                found = ("ok", hits[0])
                break
            if hits:
                found = ("ambiguous", hits[:CANDIDATES_MAX])
                break
    cache[key] = found
    return found


def plan_bom(
    db: Session,
    user: User,
    rows: Sequence[dict[str, Any]],
    *,
    division: str | None = None,
    choices: dict[str, uuid.UUID] | None = None,
) -> tuple[
    list[dict[str, Any]], dict[uuid.UUID, tuple[Material, list[tuple[dict[str, Any], Line]]]]
]:
    """BOM 줄 → 재료마다 넣을 줄 — **쓰지 않는다.**

    줄마다 `status`:

    - `new` · `exists`(그 재료에 이미 있음) · `error`(빈 줄)
    - `unmatched` — 재질을 재료로 못 찾음
    - `ambiguous` — 재질이 재료 여럿에 맞음. 후보를 보이고 사람이 고른다
    - `blocked` — 그 재료를 고칠 권한 없음

    사람이 고른 짝은 `choices`({재질: 재료 id})로 다시 보낸다."""
    if len(rows) > LINES_MAX:
        raise AppError(
            "MNX-MATERIALS-0060",
            f"한 번에 {LINES_MAX}줄까지 넣습니다(받은 줄 {len(rows)}).",
            status=422,
        )
    picked = {compare_key(text): material_id for text, material_id in (choices or {}).items()}
    editor = permissions.editor(db, user)
    cache: dict[str, tuple[str, Any]] = {}
    out: list[dict[str, Any]] = []
    groups: dict[uuid.UUID, tuple[Material, list[tuple[dict[str, Any], Line]]]] = {}
    have: dict[uuid.UUID, set[str]] = {}
    for index, raw in enumerate(rows):
        line = _line(raw, division=division)
        material_text = clean(raw.get("material")) or ""
        row: dict[str, Any] = {
            "index": index,
            "material": material_text,
            "part": line.part,
            "product": line.product,
            "part_code": line.part_code,
            "division": line.division,
            "status": "new",
            "reason": None,
            "material_id": None,
            "material_name": None,
            "candidates": [],
        }
        out.append(row)
        if not (line.part or line.product or line.part_code):
            row.update(
                status="error", reason="파트명 · 제품 · 부품코드 중 하나는 있어야 합니다."
            )
            continue
        if not material_text:
            row.update(status="unmatched", reason="재질 칸이 비었습니다.")
            continue
        chosen = picked.get(compare_key(material_text))
        if chosen is not None:
            hit = db.scalar(
                permissions.visible_materials(db, user).where(
                    Material.id == chosen, Material.deleted_at.is_(None)
                )
            )
            state: tuple[str, Any] = ("ok", hit) if hit is not None else ("missing", None)
        else:
            state = _resolve_material(db, user, material_text, cache)
        kind, found = state
        if kind == "ambiguous":
            row.update(
                status="ambiguous",
                reason="재질이 재료 여럿에 맞습니다 — 하나를 고르세요.",
                candidates=[{"id": str(one.id), "name": one.record_name} for one in found],
            )
            continue
        if kind == "missing":
            row.update(
                status="unmatched",
                reason="재질을 재료로 못 찾았습니다 — 재료를 골라 주세요.",
            )
            continue
        material: Material = found
        row.update(material_id=str(material.id), material_name=material.record_name)
        if not editor.allows(material):
            row.update(
                status="blocked",
                reason=permissions.locked(db, material, code="MNX-MATERIALS-0034").message,
            )
            continue
        keys = have.setdefault(
            material.id,
            {
                _row_key(one)
                for one in db.scalars(
                    select(MaterialPart).where(MaterialPart.material_id == material.id)
                )
            },
        )
        if line.key in keys:
            row.update(status="exists", reason="그 재료에 이미 있는 줄입니다.")
            continue
        keys.add(line.key)
        groups.setdefault(material.id, (material, []))[1].append((row, line))
    return out, groups


def apply_bom(
    db: Session,
    user: User,
    groups: dict[uuid.UUID, tuple[Material, list[tuple[dict[str, Any], Line]]]],
    *,
    source_ref: str | None,
) -> int:
    """재료마다 `new` 줄을 넣는다. **하나가 막혀도 나머지는 넣는다**.

    300줄 BOM 의 재질 하나 때문에 전부를 다시 고르게 하지 않는다(못 넣은 줄은 이유와 함께
    돌아간다). 커밋은 부르는 쪽."""
    made = 0
    for material, items in groups.values():
        permissions.note_edit(db, user, material)
        planned = Plan(rows=[row for row, _ in items], lines=[line for _, line in items])
        made += len(apply(db, user, material, planned, source="bom", source_ref=source_ref))
    return made
