"""재료 합치기 — 같은 재료를 두 번 등록했을 때 하나로(2026-11-17, VOC 59 · ADR 0092).

시료 이동(ADR 0079)으로 시료는 옮길 수 있었지만, 재료에 직접 붙은 것(선언 물성 · 밀도 ·
푸아송비 · 문헌 연결 · 계수 묶음 · 적용 부품 · 카드 · 묶음 기록)은 따라오지 않아 빈 재료를
휴지통에 넣으면 그것도 함께 사라졌다. 합치기는 **보내는 재료(source)의 것을 받는 재료(target)
로** 모으고 보내는 재료를 휴지통으로 보낸다(되살릴 수 있다).

    옮기는 것(행)   시료(시편 · 시험 · 처리 결과 · 채택이 따라감) · 카드 · 묶음 기록 · 저장한
                    대표 곡선 · 계수 묶음 · 문헌 연결 · 워크벤치에 담긴 줄 · BOM 이름 매칭
    채우는 것(값)   받는 재료가 비어 있는 칸만 — 밀도 · 푸아송비(근거와 함께) · 별칭 · 메모 ·
                    받는 재료에 없는 선언 물성 항목 · 입력 단위 · 적용 부품
    받는 재료 우선  같은 칸의 값이 다르면 받는 재료의 값을 둔다(사용자 결정). 미리보기가 다른
                    값을 목록으로 보인다 — 사람이 보고 받는 재료를 고친다.

**분류가 같아야 한다**(Family · Category · Grade, 시료 이동과 같은 규칙). 다른 분류를 합치는
것은 다른 재료의 시험을 만드는 일이다 — Grade 를 잘못 적었으면 재료의 분류를 먼저 고친다. 두
재료와 보내는 재료의 시료 · 시편을 모두 고칠 수 있어야 한다(ADR 0035). 하나라도 막히면 합치지
않는다 — 반만 옮긴 재료는 휴지통에 넣을 수 없다.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.catalog.models import CatalogLink
from app.modules.fitting.models import PropertyCard, PropertyCardRemark
from app.modules.grouping.models import GroupResult
from app.modules.materials import parts, services
from app.modules.materials.models import (
    Material,
    MaterialParameterSet,
    MaterialPart,
    Sample,
    Specimen,
)
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.models import TestRun
from app.modules.vocabulary import services as vocabulary_services
from app.modules.workbench.models import BomAlias, WorkbenchItem
from app.shared import audit, permissions, semantic
from app.shared.errors import AppError

#: 받는 재료가 비었을 때만 채우는 칸 — (칸, 이름, 보일 단위, 근거 칸 이름).
FIELDS: tuple[tuple[str, str, str, str | None], ...] = (
    ("density_si", "밀도", "kg/m³", "density"),
    ("poisson_ratio", "푸아송비", "", "poisson_ratio"),
    ("alias", "별칭", "", None),
    ("note", "메모", "", None),
)


@dataclass
class MergePlan:
    source: Material
    target: Material
    samples: list[Sample]
    """옮길 시료 — 휴지통의 것도(되살리면 받는 재료로 돌아오게)."""
    specimens: int
    test_runs: int
    cards: list[PropertyCard]
    groups: list[GroupResult]
    ensembles: list[EnsembleResult]
    parameter_sets: list[MaterialParameterSet]
    catalog_link: CatalogLink | None
    workbench_items: list[WorkbenchItem]
    bom_aliases: list[BomAlias]
    parts: int
    """받는 재료에 없는 적용 부품 줄 수(복사)."""
    values: dict[str, Any] = field(default_factory=dict)
    """받는 재료에 채울 칸 → 값."""
    evidence: dict[str, Any] = field(default_factory=dict)
    declared: list[dict[str, Any]] = field(default_factory=list)
    """받는 재료에 더할 선언 물성 줄."""
    units: dict[str, str] = field(default_factory=dict)
    taken: list[str] = field(default_factory=list)
    """받는 재료에 없어 가져오는 값 — 사람이 읽는 줄."""
    kept: list[str] = field(default_factory=list)
    """값이 달라 받는 재료의 것을 둔 칸 — 두 값을 함께."""
    left: list[str] = field(default_factory=list)
    """옮기지 않고 보내는 재료에 남는 것(받는 재료에 같은 자리가 이미 있다)."""
    blocked: list[str] = field(default_factory=list)


def _number(value: float, unit: str) -> str:
    return f"{value:.6g}{f' {unit}' if unit else ''}"


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(float(a) - float(b)) <= 1e-9 * max(abs(float(a)), abs(float(b)), 1e-300)
    return bool(a == b)


def _naming(column: str, value: Any) -> str:
    """이름을 정하는 칸(두께 · Details)을 사람이 읽는 꼴로."""
    return _number(float(value) * 1e3, "mm") if column == "spec_thickness_m" else str(value)


def _shown(value: Any, unit: str) -> str:
    if isinstance(value, int | float):
        return _number(float(value), unit)
    text = str(value)
    return text if len(text) <= 40 else text[:40] + "…"


def make_plan(
    db: Session, user: User, source_id: uuid.UUID, target_id: uuid.UUID
) -> MergePlan:
    """보내는 재료를 받는 재료로 합치면 무엇이 어디로 가는지 — **쓰지 않는다.**

    막히는 것은 `blocked` 에 까닭과 함께 — 막힌 것이 하나라도 있으면 `execute` 가 거절한다.
    """
    visible = permissions.visible_materials(db, user)
    source = db.scalar(visible.where(Material.id == source_id, Material.deleted_at.is_(None)))
    if source is None:
        raise AppError("MNX-MATERIALS-0071", "합칠 재료를 찾을 수 없습니다.", status=404)
    target = db.scalar(visible.where(Material.id == target_id, Material.deleted_at.is_(None)))
    if target is None:
        raise AppError("MNX-MATERIALS-0071", "받을 재료를 찾을 수 없습니다.", status=404)

    blocked: list[str] = []
    if source.id == target.id:
        blocked.append("같은 재료끼리는 합치지 않습니다")
    same_kind = (source.family, source.category, (source.grade or "").casefold()) == (
        target.family,
        target.category,
        (target.grade or "").casefold(),
    )
    if not same_kind:
        blocked.append(
            "분류가 다른 재료는 합치지 않습니다"
            f"({source.family} · {source.category} · {source.grade} → {target.family} · "
            f"{target.category} · {target.grade}) — Grade 를 잘못 적었으면 재료의 분류를 먼저 "
            "고치세요"
        )
    editor = permissions.editor(db, user)
    for material, role in ((source, "합칠 재료"), (target, "받을 재료")):
        if not editor.allows(material):
            locked = permissions.locked(db, material, code="MNX-MATERIALS-0072")
            blocked.append(f"{role}를 고칠 수 없습니다 — {locked.message}")

    samples = list(
        db.scalars(
            select(Sample)
            .where(Sample.material_id == source.id)
            .order_by(Sample.deleted_at.is_not(None), Sample.seq_no)
        )
    )
    alive = [one for one in samples if one.deleted_at is None]
    specimens = list(
        db.scalars(
            select(Specimen).where(
                Specimen.sample_id.in_([one.id for one in alive]),
                Specimen.deleted_at.is_(None),
            )
        )
    )
    locked_rows = [one.record_name for one in alive if not editor.allows(one)] + [
        one.record_name for one in specimens if not editor.allows(one)
    ]
    if locked_rows:
        blocked.append(
            "고칠 수 없는 시료 · 시편이 있어 합칠 수 없습니다: "
            + ", ".join(locked_rows[:3])
            + (f" 외 {len(locked_rows) - 3}건" if len(locked_rows) > 3 else "")
        )
    runs = (
        list(
            db.scalars(
                select(TestRun.id).where(
                    TestRun.specimen_id.in_([one.id for one in specimens]),
                    TestRun.deleted_at.is_(None),
                )
            )
        )
        if specimens
        else []
    )

    plan = MergePlan(
        source=source,
        target=target,
        samples=samples,
        specimens=len(specimens),
        test_runs=len(runs),
        cards=list(
            db.scalars(
                select(PropertyCard)
                .where(PropertyCard.material_id == source.id)
                .order_by(PropertyCard.created_at)
            )
        ),
        groups=list(
            db.scalars(select(GroupResult).where(GroupResult.material_id == source.id))
        ),
        ensembles=list(
            db.scalars(select(EnsembleResult).where(EnsembleResult.material_id == source.id))
        ),
        parameter_sets=[],
        catalog_link=None,
        workbench_items=list(
            db.scalars(
                select(WorkbenchItem).where(
                    WorkbenchItem.kind == "material", WorkbenchItem.target_id == source.id
                )
            )
        ),
        bom_aliases=list(
            db.scalars(select(BomAlias).where(BomAlias.material_id == source.id))
        ),
        parts=0,
        blocked=blocked,
    )
    _plan_values(plan)
    _plan_rows(db, plan)
    return plan


def _plan_values(plan: MergePlan) -> None:
    """칸 · 선언 물성 · 입력 단위 — 받는 재료가 비었으면 가져오고, 다르면 받는 재료의 것."""
    source, target = plan.source, plan.target
    for column, label, unit, evidence_key in FIELDS:
        mine, theirs = getattr(source, column), getattr(target, column)
        if mine is None or mine == "":
            continue
        if theirs is None or theirs == "":
            plan.values[column] = mine
            plan.taken.append(f"{label} {_shown(mine, unit)}")
            if evidence_key and (source.column_evidence or {}).get(evidence_key):
                plan.evidence[evidence_key] = copy.deepcopy(
                    source.column_evidence[evidence_key]
                )
        elif not _same(mine, theirs):
            plan.kept.append(
                f"{label}: 받는 재료 {_shown(theirs, unit)} 유지"
                f"(합칠 재료 {_shown(mine, unit)})"
            )
    for column, label in (("spec_thickness_m", "스펙 두께"), ("details", "Details")):
        mine, theirs = getattr(source, column), getattr(target, column)
        if mine is not None and theirs is not None and not _same(mine, theirs):
            plan.kept.append(
                f"{label}: 받는 재료 {_naming(column, theirs)} 유지(합칠 재료 "
                f"{_naming(column, mine)}) — 이름을 정하는 칸이라 가져오지 않습니다"
            )

    have = {
        str(row.get("item")): row
        for row in target.declared_properties or []
        if row.get("item")
    }
    for row in source.declared_properties or []:
        item = str(row.get("item") or "")
        if not item:
            continue
        if item not in have:
            plan.declared.append(copy.deepcopy(row))
            have[item] = row
            plan.taken.append(f"선언 물성 「{item}」")
        elif have[item] != row:
            plan.kept.append(f"선언 물성 「{item}」: 값 · 출처가 달라 받는 재료의 줄 유지")
    for key, unit in (source.input_units or {}).items():
        if key not in (target.input_units or {}):
            plan.units[key] = unit


def _plan_rows(db: Session, plan: MergePlan) -> None:
    """한 재료에 하나뿐인 자리(문헌 연결 · 같은 계수 묶음)는 받는 재료에 이미 있으면 남긴다."""
    source, target = plan.source, plan.target
    mine = db.scalar(select(CatalogLink).where(CatalogLink.material_id == source.id))
    theirs = db.scalar(select(CatalogLink).where(CatalogLink.material_id == target.id))
    if mine is not None:
        if theirs is None:
            plan.catalog_link = mine
        elif theirs.catalog_material_id != mine.catalog_material_id:
            plan.left.append(
                "문헌 연결: 받는 재료의 연결 유지 — 합칠 재료의 연결은 옛 재료에 남음"
            )
    taken = {
        (one.model, one.catalog_material_id, one.source_ref)
        for one in db.scalars(
            select(MaterialParameterSet).where(MaterialParameterSet.material_id == target.id)
        )
    }
    for one in db.scalars(
        select(MaterialParameterSet).where(MaterialParameterSet.material_id == source.id)
    ):
        if (one.model, one.catalog_material_id, one.source_ref) in taken:
            plan.left.append(
                f"계수 묶음 「{one.label}」: 받는 재료에 같은 묶음이 있어 옛 재료에 남음"
            )
        else:
            plan.parameter_sets.append(one)
    have = {
        parts.row_key(row)
        for row in db.scalars(
            select(MaterialPart).where(MaterialPart.material_id == target.id)
        )
    }
    plan.parts = sum(
        1
        for row in db.scalars(
            select(MaterialPart).where(MaterialPart.material_id == source.id)
        )
        if parts.row_key(row) not in have
    )


def execute(db: Session, user: User, plan: MergePlan, *, comment: str | None) -> None:
    """합친다. **커밋은 부르는 쪽이 한다.** 막힌 것이 있으면 아무것도 쓰기 전에 거절한다."""
    if plan.blocked:
        raise AppError(
            "MNX-MATERIALS-0073",
            "합칠 수 없습니다 — " + " · ".join(plan.blocked),
            status=422,
        )
    source, target = plan.source, plan.target
    note = (comment or "").strip() or None

    # 1. 시료 — 시편 · 시험 · 처리 결과 · 채택은 시료를 따라간다. 이름은 받은 재료 기준으로.
    for sample in plan.samples:
        permissions.note_edit(db, user, sample)
        sample.material_id = target.id
        sample.seq_no = services.next_sample_seq(db, target.id)
        # 번호는 `max+1` 이라 건마다 흘려보낸다(relocation 과 같은 까닭).
        db.flush()
    services.rename_descendants(db, target)

    # 2. 카드 · 기록 — 같은 재료의 것이므로 받는 재료로. 카드에는 코멘트가 남는다.
    for card in plan.cards:
        card.material_id = target.id
        message = (
            f"재료 합치기 — 「{source.record_name}」 의 카드를 「{target.record_name}」 로 "
            "옮겼습니다."
        )
        db.add(
            PropertyCardRemark(
                card_id=card.id,
                kind="relocated",
                message=message,
                comment=note,
                payload={
                    "merged_from": source.record_name,
                    "to_materials": [target.record_name],
                },
                created_by_id=user.id,
            )
        )
        audit.record(
            db,
            action=audit.CARD_REMARKED,
            actor=user,
            target_table="property_cards",
            target_id=card.id,
            target_label=card.label,
            workspace_id=target.owner_workspace_id,
            changes={"message": message, "comment": note},
        )
    for group in plan.groups:
        group.material_id = target.id
    for ensemble in plan.ensembles:
        ensemble.material_id = target.id
    for one in plan.parameter_sets:
        one.material_id = target.id
    if plan.catalog_link is not None:
        plan.catalog_link.material_id = target.id
    for alias in plan.bom_aliases:
        alias.material_id = target.id
    for item in plan.workbench_items:
        twin = db.scalar(
            select(WorkbenchItem.id).where(
                WorkbenchItem.run_id == item.run_id,
                WorkbenchItem.kind == "material",
                WorkbenchItem.target_id == target.id,
            )
        )
        if twin is not None:
            db.delete(item)  # 같은 작업에 받는 재료가 이미 담겨 있다
        else:
            item.target_id = target.id
    db.flush()

    # 3. 값 — 받는 재료가 비어 있던 칸만.
    if plan.values or plan.declared or plan.units or plan.evidence:
        permissions.note_edit(db, user, target)
    for column, value in plan.values.items():
        setattr(target, column, value)
    if plan.evidence:
        target.column_evidence = {**(target.column_evidence or {}), **plan.evidence}
    if plan.declared:
        target.declared_properties = [*(target.declared_properties or []), *plan.declared]
    if plan.units:
        target.input_units = {**(target.input_units or {}), **plan.units}
    parts.copy_all(db, source, target, created_by_id=user.id)

    # 4. 보내는 재료는 휴지통으로 — 되살릴 수 있다(줄은 남는다). 지우기와 같은 길이다.
    source.deleted_at = datetime.now(UTC)
    vocabulary_services.release_bindings(db, source, vocabulary_services.MATERIAL_BINDINGS)
    services.release_uses(db, source)
    audit.record(
        db,
        action=audit.MATERIAL_DELETED,
        actor=user,
        target_table="materials",
        target_id=source.id,
        target_label=source.record_name,
        workspace_id=source.owner_workspace_id,
        changes={"deleted_at": {"after": source.deleted_at.isoformat()}},
        reason=f"재료 합치기 — 「{target.record_name}」 로",
    )
    audit.record(
        db,
        action=audit.MATERIALS_MERGED,
        actor=user,
        target_table="materials",
        target_id=target.id,
        target_label=target.record_name,
        workspace_id=target.owner_workspace_id,
        changes={
            "from": source.record_name,
            "samples": len(plan.samples),
            "test_runs": plan.test_runs,
            "cards": len(plan.cards),
            "taken": plan.taken,
            "kept": plan.kept,
            "left": plan.left,
            "comment": note,
        },
    )
    semantic.queue_materials(db, [target.id])
    db.flush()
