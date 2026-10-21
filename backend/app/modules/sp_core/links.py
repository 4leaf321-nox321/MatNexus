"""SP 객체 ↔ MatNexus — **대조하고, 사람이 확인한 것만 잇는다**(ADR 0063).

    대조   한 SP 타입 전체를 한 대상(기준정보 축 · 물성 · 물성군 · 분야)과 견준다. 쓰지 않는다.
    잇기   (SP 타입, key) ↔ (대상 종류, 대상) 를 기록한다. 미리보기가 기본, 오류가 한 줄이라도
           있으면 하나도 안 넣는다(물성 분류 밀어 넣기와 같은 규칙, ADR 0054).
    끊기   연결을 지운다. 연결은 사람의 확인이라 지워도 되돌릴 수 있게 감사에 남긴다.

## 대조는 정확히 맞는 것만

key 가 같거나(물성 · 물성군 · 분야는 키를 갖는다) 이름 · 별칭의 비교키(`compare_key`)가
**하나에만** 맞을 때 「후보」 다. 둘 이상에 맞으면 「애매함」 으로 따로 보인다. 비슷한 이름은
후보가 아니다 — 「항복응력」 은 유변학 물성이라 이름이 비슷한 강도에 잇으면 숫자는 그럴듯하고
아무도 모른다(ADR 0054 대안). 후보도 **저절로 잇지 않는다** — AI 가 사람에게 보이고 확인받은
뒤 잇는다.

맞은편 목록은 공용 모듈(`shared/link_targets`)이 낸다 — 모듈끼리는 `models` 말고 안 부른다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.sp_core.models import SpCoreLink, SpCoreObject
from app.shared import audit, link_targets
from app.shared.errors import AppError
from app.shared.text import compare_key

#: 대조 결과 목록 하나의 상한 — 넘으면 수만 말한다.
LIST_MAX = 500
TARGETS = link_targets.TARGETS


def target_label(db: Session, kind: str, ref: str) -> str | None:
    """대상이 있으면 그 이름 — 없으면 None."""
    return link_targets.label_of(db, kind, ref)


def match(
    db: Session, sp_type: str, kind: str, vocabulary: str | None = None
) -> dict[str, Any]:
    """한 SP 타입을 한 대상과 견준다 — 후보 · 애매함 · SP 에만 있는 것 · 이미 이은 것."""
    if kind not in TARGETS:
        raise link_targets.bad_kind(kind)
    objects = list(
        db.scalars(
            select(SpCoreObject)
            .where(SpCoreObject.type_slug == sp_type, SpCoreObject.deleted.is_(False))
            .order_by(SpCoreObject.key)
        )
    )
    pool = link_targets.pool(db, kind, vocabulary)
    by_key = {one.key: one for one in pool if one.key}
    by_name: dict[str, dict[str, tuple[link_targets.Target, str]]] = defaultdict(dict)
    for one in pool:
        for name, how in one.names:
            if name:
                by_name[name].setdefault(one.ref, (one, how))
    linked: dict[tuple[str, str], list[SpCoreLink]] = defaultdict(list)
    for link in db.scalars(
        select(SpCoreLink).where(SpCoreLink.sp_type == sp_type, SpCoreLink.target_kind == kind)
    ):
        linked[(link.sp_key, link.target_ref)].append(link)
    linked_keys = {sp_key for sp_key, _ in linked}

    matched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    sp_only: list[dict[str, Any]] = []
    for obj in objects:
        hit = by_key.get(obj.key)
        how = "key"
        if hit is None:
            found = list(by_name.get(compare_key(obj.label), {}).values())
            if len(found) > 1:
                ambiguous.append(
                    {
                        "sp_key": obj.key,
                        "sp_label": obj.label,
                        "candidates": [
                            {"target_ref": one.ref, "target_label": one.label, "by": by}
                            for one, by in found[:10]
                        ],
                    }
                )
                continue
            if found:
                hit, how = found[0]
        if hit is None:
            sp_only.append(
                {"sp_key": obj.key, "sp_label": obj.label, "linked": obj.key in linked_keys}
            )
            continue
        links = linked.get((obj.key, hit.ref), [])
        matched.append(
            {
                "sp_key": obj.key,
                "sp_label": obj.label,
                "target_ref": hit.ref,
                "target_label": hit.label,
                "by": how,
                "link_id": str(links[0].id) if links else None,
            }
        )
    hit_refs = {one["target_ref"] for one in matched}
    return {
        "sp_type": sp_type,
        "target": kind,
        "vocabulary": vocabulary,
        "sp_total": len(objects),
        "target_total": len(pool),
        "matched_total": len(matched),
        "linked_total": sum(1 for one in matched if one["link_id"]),
        "ambiguous_total": len(ambiguous),
        "sp_only_total": len(sp_only),
        "target_only_total": len([one for one in pool if one.ref not in hit_refs]),
        "matched": matched[:LIST_MAX],
        "ambiguous": ambiguous[:LIST_MAX],
        "sp_only": sp_only[:LIST_MAX],
    }


# ── 잇기 · 끊기 ──────────────────────────────────────────────────────────────


@dataclass
class Plan:
    rows: list[dict[str, Any]]

    @property
    def errors(self) -> int:
        return sum(1 for one in self.rows if one["status"] == "error")

    def out(self, *, applied: bool) -> dict[str, Any]:
        return {
            "applied": applied,
            "new": sum(1 for one in self.rows if one["status"] == "new"),
            "exists": sum(1 for one in self.rows if one["status"] == "exists"),
            "errors": self.errors,
            "rows": self.rows,
        }


def plan(db: Session, items: list[dict[str, Any]]) -> Plan:
    """무엇이 이어질지 — 쓰지 않는다. 줄마다 `new` · `exists` · `error`(이유와 함께)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        sp_type, sp_key = str(item["sp_type"]), str(item["sp_key"])
        kind, ref = str(item["target"]), str(item["target_ref"])
        row: dict[str, Any] = {
            "sp_type": sp_type,
            "sp_key": sp_key,
            "target": kind,
            "target_ref": ref,
            "sp_label": None,
            "target_label": None,
            "status": "new",
            "reason": None,
        }
        rows.append(row)
        if kind not in TARGETS:
            row.update(
                status="error", reason=f"대상 종류는 {', '.join(TARGETS)} 중 하나입니다."
            )
            continue
        obj = db.scalar(
            select(SpCoreObject).where(
                SpCoreObject.type_slug == sp_type, SpCoreObject.key == sp_key
            )
        )
        if obj is None:
            row.update(
                status="error", reason="받은 SP 객체에 없습니다 — 타입 · key 를 보세요."
            )
            continue
        row["sp_label"] = obj.label
        if obj.deleted:
            merged = f" — {obj.merged_into} 에 합쳐졌습니다" if obj.merged_into else ""
            row.update(status="error", reason=f"SP 에서 사라진 객체입니다{merged}.")
            continue
        label = target_label(db, kind, ref)
        if label is None:
            row.update(status="error", reason=f"그런 {TARGETS[kind]}이(가) 없습니다: {ref}")
            continue
        row["target_label"] = label
        pair = (sp_type, sp_key, kind, ref)
        if pair in seen:
            row.update(status="exists", reason="같은 줄이 위에 있습니다.")
            continue
        seen.add(pair)
        existing = db.scalar(
            select(SpCoreLink).where(
                SpCoreLink.sp_type == sp_type,
                SpCoreLink.sp_key == sp_key,
                SpCoreLink.target_kind == kind,
                SpCoreLink.target_ref == ref,
            )
        )
        if existing is not None:
            row.update(
                status="exists", reason="이미 이어져 있습니다.", link_id=str(existing.id)
            )
    return Plan(rows=rows)


def apply(db: Session, user: User, planned: Plan, *, note: str | None = None) -> None:
    """계획대로 잇는다 — **오류가 한 줄이라도 있으면 하나도 안 넣는다.** 커밋은 부르는 쪽."""
    if planned.errors:
        raise AppError(
            "MNX-SPCORE-0004",
            f"잇지 못하는 줄이 {planned.errors}개 있어 아무것도 잇지 않았습니다 — 미리보기의 "
            "이유를 보고 고쳐 주세요.",
            status=422,
            details={"rows": [one for one in planned.rows if one["status"] == "error"]},
        )
    for row in planned.rows:
        if row["status"] != "new":
            continue
        link = SpCoreLink(
            sp_type=row["sp_type"],
            sp_key=row["sp_key"],
            target_kind=row["target"],
            target_ref=row["target_ref"],
            note=note,
            created_by_id=user.id,
        )
        db.add(link)
        db.flush()
        row["link_id"] = str(link.id)
        # **사람이 해도 남긴다** — 분류와 같이 바깥과 AI 가 읽는 전사 자산의 연결이다.
        audit.record(
            db,
            action=audit.SP_CORE_LINKED,
            actor=user,
            target_table="sp_core_links",
            target_id=link.id,
            target_label=f"{row['sp_type']}:{row['sp_key']} → {row['target_label']}",
            changes={
                "sp_type": row["sp_type"],
                "sp_key": row["sp_key"],
                "target": row["target"],
                "target_ref": row["target_ref"],
            },
        )


def remove(db: Session, user: User, ids: list[uuid.UUID], *, dry_run: bool) -> dict[str, Any]:
    """연결을 끊는다. 없는 id 는 이유와 함께 말하고, 있는 것만 끊는다."""
    found = {
        one.id: one for one in db.scalars(select(SpCoreLink).where(SpCoreLink.id.in_(ids)))
    }
    rows: list[dict[str, Any]] = []
    for link_id in dict.fromkeys(ids):
        link = found.get(link_id)
        if link is None:
            rows.append(
                {"id": str(link_id), "status": "missing", "reason": "그런 연결이 없습니다."}
            )
            continue
        rows.append(
            {
                "id": str(link.id),
                "status": "removed" if not dry_run else "will_remove",
                "sp_type": link.sp_type,
                "sp_key": link.sp_key,
                "target": link.target_kind,
                "target_ref": link.target_ref,
            }
        )
        if dry_run:
            continue
        audit.record(
            db,
            action=audit.SP_CORE_UNLINKED,
            actor=user,
            target_table="sp_core_links",
            target_id=link.id,
            target_label=(
                f"{link.sp_type}:{link.sp_key} → {link.target_kind}:{link.target_ref}"
            ),
            changes={
                "sp_type": link.sp_type,
                "sp_key": link.sp_key,
                "target": link.target_kind,
                "target_ref": link.target_ref,
            },
        )
        db.delete(link)
    return {"applied": not dry_run, "rows": rows}
