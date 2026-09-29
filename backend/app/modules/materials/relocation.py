"""시편을 **다른 두께의 같은 재료**로 옮긴다(2026-09-29).

두께가 다른 재료에 잘못 넣은 시편이 있다 — `SECC_MDOI_1.0` 아래에 실측 1.2 mm 시편이 섞였다.
재료 수정으로 두께를 바꾸면 **제대로 들어간 시료까지** 이름이 바뀌어 함께 옮겨진다. 그래서
고른 시편만 「같은 재료, 기준 두께만 다른 것」 으로 옮기는 길을 따로 둔다.

## 무엇이 어디로

    옮겨 갈 재료   원 재료의 Grade·Details 에 새 두께 → 이름(`{grade}_{details}_{두께}`).
                  같은 부서에 그 이름이 있으면 그 재료로 합치고, 없으면 원 재료를 복사해
                  만든다(분류·용도·밀도·푸아송비·선언 물성·모델 파라미터 벌·메모) — 두께만
                  다르다
    시료          고른 시편이 그 시료의 전부면 **시료째** 옮긴다(로트 정보가 함께 간다).
                  일부면 옮겨 갈 재료에 같은 로트 정보로 시료를 새로 만들어 붙인다
    이름          시료·시편·시험 이름은 옮겨 간 재료 기준으로 다시 계산한다(ADR 0004)

## 카드 — 옮기는 것은 막지 않는다(2026-09-29 요청)

옮기는 시험으로 만든 카드(확정 포함)가 원 재료에 남는다. 막으면 잘못 넣은 자료를 영영 못
고친다. 대신 **걸린 카드에는 반드시 코멘트가 붙고**, 카드마다 정리(사용 중지)를 고를 수 있다.

    note         코멘트만 — 「근거 시험 2건이 SECC_MDOI_1.2 로 옮겨졌습니다」 + 사람의 말
    deprecate    사용 중지 + 코멘트. 확정 카드는 자료 관리자만(ADR 0035), 초안은 고칠 사람

카드의 값·근거는 불변이라 코멘트는 카드와 **따로** 둔다(`PropertyCardRemark`).

## 묶음·대표 곡선 기록 — 원 재료에 그때의 기록으로 남는다

옮기는 시험을 쓴 묶음(글로벌 피팅)과 저장한 대표 곡선도 원 재료에 남는다. 계산해 둔 기록이라
고치지 않고, 계획에 알린다. **옮겨진 시험이 든 묶음으로 카드를 새로 만드는 것은 막는다** —
묶음은 재료에 붙고 카드는 그 재료로 가므로, 두께가 다른 근거가 조용히 섞인다
(`fitting.routes._refuse_moved_members`).

## 한 건이 막혀도 나머지는 간다

권한 밖이거나 이미 그 두께인 시편은 이유와 함께 돌려주고, 나머지는 옮긴다 — 시편 일괄 수정과
같은 규칙이다. **카드 처리는 먼저 전부 판정한다** — 사용 중지를 못 하는 카드가 섞여 있으면
아무것도 옮기기 전에 멈춘다(옮기다 만 상태가 남지 않게).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard, PropertyCardRemark
from app.modules.grouping.models import GroupResult
from app.modules.materials import services
from app.modules.materials.models import (
    Material,
    MaterialParameterSet,
    Sample,
    Specimen,
)
from app.modules.materials.schemas import SI_DENSITY, MaterialCreateRequest
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.models import TestRun
from app.modules.vocabulary import services as vocabulary_services
from app.modules.workspaces.models import Workspace
from app.shared import audit, permissions, semantic
from app.shared.errors import AppError, Forbidden
from matcore import naming, registry, units

#: 걸린 카드를 어떻게 — 코멘트만 · 사용 중지(+코멘트).
CARD_ACTIONS = ("note", "deprecate")


@dataclass
class Move:
    specimen: Specimen
    sample: Sample
    source: Material


@dataclass
class Target:
    """원 재료 하나가 옮겨 갈 곳."""

    source: Material
    name: str
    existing: Material | None
    moves: list[Move] = field(default_factory=list)


@dataclass
class AffectedCard:
    card: PropertyCard
    material: Material
    run_ids: list[uuid.UUID]
    """이 카드가 근거로 쓴 시험 가운데 옮기는 것."""
    can_deprecate: bool
    reason: str | None
    """사용 중지를 못 하면 그 까닭."""


@dataclass
class Plan:
    thickness_m: float
    unit: str
    targets: dict[uuid.UUID, Target]
    blocked: list[str]
    whole: dict[uuid.UUID, bool]
    """시료 id → 통째로 가나(고른 시편이 그 시료의 전부이고 시료를 고칠 수 있다)."""
    runs: dict[uuid.UUID, list[TestRun]]
    """시편 id → 살아 있는 시험."""
    cards: list[AffectedCard]
    records: list[str] = field(default_factory=list)
    """옮기는 시험을 쓴 묶음·대표 곡선 기록 — 원 재료에 남는다(고치지 않고 알린다)."""

    @property
    def moves(self) -> list[Move]:
        return [move for target in self.targets.values() for move in target.moves]


@dataclass
class Result:
    moved: int = 0
    test_runs: int = 0
    created: list[str] = field(default_factory=list)
    joined: list[str] = field(default_factory=list)
    split_samples: int = 0
    cards_noted: int = 0
    cards_deprecated: int = 0


def make_plan(
    db: Session,
    user: User,
    specimen_ids: list[uuid.UUID],
    *,
    thickness: float,
    unit: str,
) -> Plan:
    """무엇이 어디로 가는지 — **아무것도 쓰지 않는다.** 실행도 같은 판정을 지난다."""
    thickness_m = services.to_si(thickness, unit, field="두께", dimension="length")
    assert thickness_m is not None  # 값을 줬다
    editor = permissions.editor(db, user)

    targets: dict[uuid.UUID, Target] = {}
    blocked: list[str] = []
    seen: set[uuid.UUID] = set()
    for specimen_id in specimen_ids:
        if specimen_id in seen:
            continue
        seen.add(specimen_id)
        specimen = db.scalar(
            select(Specimen).where(Specimen.id == specimen_id, Specimen.deleted_at.is_(None))
        )
        if specimen is None:
            # **이름을 모르면 id 라도 준다.** 조용히 세지 않는 것이 요점이다.
            blocked.append(f"{specimen_id} — 시편을 찾을 수 없습니다")
            continue
        if not editor.allows(specimen):
            locked = permissions.locked(db, specimen, code="MNX-MATERIALS-0040")
            blocked.append(f"{specimen.record_name} — {locked.message}")
            continue
        sample = db.get(Sample, specimen.sample_id)
        source = db.get(Material, sample.material_id) if sample is not None else None
        if sample is None or source is None or source.deleted_at is not None:
            blocked.append(f"{specimen.record_name} — 시료·재료를 찾을 수 없습니다")
            continue
        target = targets.get(source.id)
        if target is None:
            name = services.material_record_name(
                grade=source.grade, details=source.details, spec_thickness_m=thickness_m
            )
            target = Target(
                source=source,
                name=name,
                existing=services.find_by_name(
                    db, owner_workspace_id=source.owner_workspace_id, record_name=name
                ),
            )
            targets[source.id] = target
        if target.name == source.record_name:
            shown = units.from_si(thickness_m, "mm")
            blocked.append(
                f"{specimen.record_name} — 이미 {shown:g} mm 재료"
                f"({source.record_name})에 있습니다"
            )
            continue
        target.moves.append(Move(specimen=specimen, sample=sample, source=source))
    # 옮길 것이 없는 원 재료는 뺀다 — 전부 막혔거나 이미 그 두께다.
    targets = {key: one for key, one in targets.items() if one.moves}

    moves = [move for one in targets.values() for move in one.moves]
    moved_ids = {move.specimen.id for move in moves}
    whole: dict[uuid.UUID, bool] = {}
    for move in moves:
        sample = move.sample
        if sample.id in whole:
            continue
        alive = set(
            db.scalars(
                select(Specimen.id).where(
                    Specimen.sample_id == sample.id, Specimen.deleted_at.is_(None)
                )
            )
        )
        # **시료째 옮기려면 그 시료도 고칠 수 있어야 한다** — 못 고치면 로트 정보를 복사한 새
        # 시료로 옮긴다(그 새 시료는 옮긴 사람이 등록자다).
        whole[sample.id] = alive <= moved_ids and editor.allows(sample)

    runs: dict[uuid.UUID, list[TestRun]] = {}
    if moved_ids:
        for run in db.scalars(
            select(TestRun).where(
                TestRun.specimen_id.in_(moved_ids), TestRun.deleted_at.is_(None)
            )
        ):
            runs.setdefault(run.specimen_id, []).append(run)
    run_ids = {run.id for listed in runs.values() for run in listed}

    return Plan(
        thickness_m=thickness_m,
        unit=unit,
        targets=targets,
        blocked=blocked,
        whole=whole,
        runs=runs,
        cards=_affected_cards(db, user, editor, targets, run_ids),
        records=_affected_records(db, targets, run_ids),
    )


def _affected_cards(
    db: Session,
    user: User,
    editor: permissions.Editor,
    targets: dict[uuid.UUID, Target],
    run_ids: set[uuid.UUID],
) -> list[AffectedCard]:
    """옮기는 시험을 **근거로 쓴** 카드. 카드는 `source.test_run_ids` 에 근거를 적는다."""
    if not run_ids or not targets:
        return []
    wanted = {str(one) for one in run_ids}
    found: list[AffectedCard] = []
    for card in db.scalars(
        select(PropertyCard)
        .where(PropertyCard.material_id.in_(list(targets)))
        .order_by(PropertyCard.created_at)
    ):
        used = [str(one) for one in (card.source or {}).get("test_run_ids") or []]
        hit = [uuid.UUID(one) for one in used if one in wanted]
        if not hit:
            continue
        reason: str | None
        if card.status == "deprecated":
            can, reason = False, "이미 사용 중지된 카드입니다 — 코멘트만 붙습니다"
        elif card.status == "published":
            can = permissions.is_data_steward(user)
            reason = None if can else "확정 카드의 사용 중지는 자료 관리자만 할 수 있습니다"
        else:
            can = editor.allows(card)
            reason = None if can else "이 초안을 고칠 권한이 없습니다"
        found.append(
            AffectedCard(
                card=card,
                material=targets[card.material_id].source,
                run_ids=hit,
                can_deprecate=can,
                reason=reason,
            )
        )
    return found


def _affected_records(
    db: Session, targets: dict[uuid.UUID, Target], run_ids: set[uuid.UUID]
) -> list[str]:
    """옮기는 시험을 쓴 **묶음·저장한 대표 곡선.** 둘 다 재료에 붙고 시험을 JSON 에 적는다.

    카드와 달리 고치지 않는다 — 계획에 알리기만 한다.
    """
    if not run_ids or not targets:
        return []
    wanted = {str(one) for one in run_ids}
    materials = list(targets)
    found: list[str] = []
    for group in db.scalars(
        select(GroupResult)
        .where(GroupResult.material_id.in_(materials))
        .order_by(GroupResult.created_at)
    ):
        hit = [one for one in group.members if str(one.get("test_run_id")) in wanted]
        if not hit:
            continue
        try:
            label = registry.get(group.plugin_id).label
        except KeyError:
            label = group.plugin_id
        found.append(
            f"묶음 「{label}」 — 구성원 {len(hit)}/{len(group.members)}개가 옮겨집니다."
            " 이 묶음으로는 새 카드를 만들 수 없습니다(옮긴 뒤 다시 묶기)"
        )
    for ensemble in db.scalars(
        select(EnsembleResult)
        .where(EnsembleResult.material_id.in_(materials))
        .order_by(EnsembleResult.created_at)
    ):
        used = [one for one in ensemble.test_run_ids if str(one) in wanted]
        if not used:
            continue
        found.append(
            f"저장한 대표 곡선({ensemble.orientation}) — 시험 {len(used)}/"
            f"{len(ensemble.test_run_ids)}건이 옮겨집니다. 그때 계산한 기록으로 남습니다"
        )
    return found


def execute(
    db: Session,
    user: User,
    plan: Plan,
    *,
    card_actions: dict[uuid.UUID, str],
    comment: str | None,
) -> Result:
    """옮긴다. **커밋은 부르는 쪽이 한다.**"""
    affected = {one.card.id: one for one in plan.cards}
    unknown = [str(key) for key in card_actions if key not in affected]
    if unknown:
        raise AppError(
            "MNX-MATERIALS-0041",
            "이번에 옮기는 시험과 상관없는 카드입니다: " + ", ".join(unknown),
            status=422,
        )
    for key, action in card_actions.items():
        if action not in CARD_ACTIONS:
            raise AppError(
                "MNX-MATERIALS-0041",
                f"카드 처리는 {' · '.join(CARD_ACTIONS)} 중 하나입니다: {action}",
                status=422,
            )
        one = affected[key]
        if action == "deprecate" and not one.can_deprecate:
            # **옮기기 전에 멈춘다** — 절반만 옮긴 뒤에 막히면 되돌릴 자리가 애매하다.
            raise Forbidden(
                "MNX-MATERIALS-0042",
                f"'{one.card.label}' 을 사용 중지할 수 없습니다 — {one.reason}. 코멘트만 "
                "남기도록 고르면 옮길 수 있습니다.",
            )

    result = Result()
    moved_to: dict[uuid.UUID, Material] = {}
    for target in plan.targets.values():
        destination = target.existing or _copy_material(db, user, target, plan)
        if target.existing is None:
            result.created.append(destination.record_name)
        else:
            result.joined.append(destination.record_name)
        moved_to[target.source.id] = destination

        # 시료마다 — 통째로 가거나, 로트 정보를 복사한 새 시료로 시편만 간다.
        by_sample: dict[uuid.UUID, list[Move]] = {}
        for move in target.moves:
            by_sample.setdefault(move.sample.id, []).append(move)
        for sample_moves in by_sample.values():
            sample = sample_moves[0].sample
            if plan.whole.get(sample.id):
                permissions.note_edit(db, user, sample)
                sample.material_id = destination.id
                sample.seq_no = services.next_sample_seq(db, destination.id)
                db.flush()
            else:
                fresh = _split_sample(db, user, sample, destination)
                result.split_samples += 1
                for move in sample_moves:
                    permissions.note_edit(db, user, move.specimen)
                    move.specimen.sample_id = fresh.id
                    move.specimen.seq_no = services.next_specimen_seq(
                        db, fresh.id, move.specimen.orientation
                    )
                    # **건마다 흘려보낸다** — 번호는 `max+1` 로 받아서, 앞 건이 DB 에 안 갔으면
                    # 셋이 같은 번호를 받는다(시편 일괄 수정이 실측으로 걸린 자리).
                    db.flush()
            result.moved += len(sample_moves)
            result.test_runs += sum(
                len(plan.runs.get(move.specimen.id, [])) for move in sample_moves
            )
        # 이름은 옮겨 간 재료 기준으로 — 시료·시편·시험까지 내려간다(ADR 0004).
        services.rename_descendants(db, destination)
        db.flush()
        audit.record(
            db,
            action=audit.SPECIMENS_RELOCATED,
            actor=user,
            target_table="materials",
            target_id=destination.id,
            target_label=destination.record_name,
            workspace_id=destination.owner_workspace_id,
            changes={
                "from": target.source.record_name,
                "to": destination.record_name,
                "created": target.existing is None,
                "specimens": [move.specimen.record_name for move in target.moves],
            },
        )

    for one in plan.cards:
        action = card_actions.get(one.card.id, "note")
        destinations = sorted({moved_to[one.material.id].record_name})
        names = [
            run.record_name
            for listed in plan.runs.values()
            for run in listed
            if run.id in set(one.run_ids)
        ]
        message = (
            f"근거 시험 {len(one.run_ids)}건이 다른 두께의 재료 {', '.join(destinations)} 로 "
            f"옮겨졌습니다 — 이 카드의 값은 그 시험을 포함해 계산된 것입니다."
        )
        db.add(
            PropertyCardRemark(
                card_id=one.card.id,
                kind="relocated",
                message=message,
                comment=(comment or "").strip() or None,
                payload={
                    "test_run_ids": [str(run_id) for run_id in one.run_ids],
                    "test_run_names": names,
                    "to_materials": destinations,
                    "action": action,
                },
                created_by_id=user.id,
            )
        )
        audit.record(
            db,
            action=audit.CARD_REMARKED,
            actor=user,
            target_table="property_cards",
            target_id=one.card.id,
            target_label=one.card.label,
            workspace_id=one.material.owner_workspace_id,
            changes={"message": message, "comment": comment, "action": action},
        )
        result.cards_noted += 1
        if action == "deprecate" and one.card.status != "deprecated":
            before = one.card.status
            one.card.status = "deprecated"
            audit.record(
                db,
                action=audit.CARD_DEPRECATED,
                actor=user,
                target_table="property_cards",
                target_id=one.card.id,
                target_label=one.card.label,
                workspace_id=one.material.owner_workspace_id,
                changes={"status": {"before": before, "after": "deprecated"}},
                reason="근거 시험이 다른 두께의 재료로 옮겨졌습니다",
            )
            result.cards_deprecated += 1

    # 새로 만든 재료는 **뜻으로도 곧바로 걸리게** — 밤의 전체 색인까지 기다리지 않는다.
    semantic.queue_materials(
        db, [moved_to[key].id for key, one in plan.targets.items() if one.existing is None]
    )
    return result


def _copy_material(db: Session, user: User, target: Target, plan: Plan) -> Material:
    """원 재료를 복사해 **두께만 다른** 재료를 만든다 — 등록과 같은 길(`make_material`)로."""
    source = target.source
    uses = services.uses_of(db, [source.id]).get(source.id) or {}
    workspace = (
        db.get(Workspace, source.owner_workspace_id) if source.owner_workspace_id else None
    )
    if workspace is None:
        raise AppError(
            "MNX-MATERIALS-0041",
            f"'{source.record_name}' 의 등록 부서를 찾을 수 없어 두께가 다른 재료를 만들 수 "
            "없습니다.",
            status=422,
        )
    payload = MaterialCreateRequest(
        family=source.family,
        category=source.category,
        grade=source.grade,
        details=source.details,
        spec_thickness=units.from_si(plan.thickness_m, plan.unit),
        spec_thickness_unit=plan.unit,
        applied_products=list(uses.get("product", [])),
        applied_parts=list(uses.get("part", [])),
        density=source.density_si,
        density_unit=SI_DENSITY,
        poisson_ratio=source.poisson_ratio,
        alias=source.alias,
        note=source.note,
    )
    made = services.make_material(db, user, payload, workspace=workspace)
    # 등록 폼에 없는 것 — 선언 물성·넣은 단위·편집을 받은 부서·모델 파라미터 벌.
    made.declared_properties = copy.deepcopy(source.declared_properties or [])
    made.input_units = {**(source.input_units or {}), "spec_thickness": plan.unit}
    made.edit_workspace_id = source.edit_workspace_id
    for one in db.scalars(
        select(MaterialParameterSet).where(MaterialParameterSet.material_id == source.id)
    ):
        db.add(
            MaterialParameterSet(
                material_id=made.id,
                model=one.model,
                label=one.label,
                property_key=one.property_key,
                origin=one.origin,
                source_ref=one.source_ref,
                source_detail=one.source_detail,
                quality_tier=one.quality_tier,
                terms=copy.deepcopy(one.terms),
                notes=one.notes,
                created_by_id=user.id,
            )
        )
    db.flush()
    return made


def _split_sample(db: Session, user: User, sample: Sample, destination: Material) -> Sample:
    """옮겨 갈 재료에 **같은 로트 정보로** 시료를 새로 만든다 — 시편 일부만 옮길 때."""
    seq_no = services.next_sample_seq(db, destination.id)
    fresh = Sample(
        workspace_id=sample.workspace_id,
        material_id=destination.id,
        seq_no=seq_no,
        record_name=naming.sample_name(material=destination.record_name, seq_no=seq_no),
        alias=sample.alias,
        lot_no=sample.lot_no,
        production_date=sample.production_date,
        density_si=sample.density_si,
        declared_properties=copy.deepcopy(sample.declared_properties or []),
        input_units=dict(sample.input_units or {}),
        note=sample.note,
        registered_by_id=user.id,
        edit_workspace_id=sample.edit_workspace_id,
    )
    # 회사 칸은 기준정보를 거친다(ADR 0010) — 쓰는 곳 수도 여기서 옮겨진다.
    vocabulary_services.apply_bindings(
        db,
        fresh,
        vocabulary_services.SAMPLE_BINDINGS,
        {
            "manufacturer": sample.manufacturer,
            "distributor": sample.distributor,
            "primary_vendor": sample.primary_vendor,
            "sales_type": sample.sales_type,
        },
        created_by_id=user.id,
    )
    db.add(fresh)
    db.flush()
    return fresh
