"""등록자와 편집 부서를 넘긴다 — 자료 하나, 또는 그 아래까지(ADR 0035 D4).

## 왜 따로 있나

등록자는 「누가 고치나」 의 첫째 자리다. 그런데 계정 삭제 때의 승계(`transfer_ownership`)
말고는 바꿀 길이 없었다 — 이관 계정 하나로 올라간 자료를 실제 담당자에게 넘길 수
없었고, 그러면 그 자료는 관리자만 고치는 자료로 굳는다.

## 무엇을 넘기나

    등록자        그 자료를 고치는 사람. 넘기면 앞 사람은 이제 못 고친다
    편집 부서     등록자 말고 함께 고치는 부서. 비우면 등록자와 관리자만

**넘길 수 있는 사람은 등록자와 관리자뿐이다**(`Editor.can_hand_over`). 편집을 받은
부서 사람이 넘기게 두면 받은 권한으로 등록자의 권한을 걷는 길이 된다.

## 아래까지

재료를 넘기면서 그 아래(시료·시편·시험·카드·묶음)를 함께 넘길 수 있다. 층마다 제
등록자가 있으므로 **남이 붙인 것은 건너뛰고 이름을 말한다** — 재료의 등록자라고 남의
시험까지 가져가면, 가져간 사실을 그 사람이 모른다.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.equipment.models import EquipmentUnit
from app.modules.fitting.models import ExportProfile, PropertyCard
from app.modules.grouping.models import GroupResult
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.ownership.schemas import OwnedKind, OwnershipSkippedOut, PersonOut
from app.modules.processing.models import ProcessingRecipe
from app.modules.tests.models import FormatProfile, TestRun, TestType
from app.modules.workspaces.models import Workspace
from app.shared import audit, permissions
from app.shared.errors import NotFound

MODELS: dict[str, type[permissions.Owned]] = {
    "material": Material,
    "sample": Sample,
    "specimen": Specimen,
    "test_run": TestRun,
    "property_card": PropertyCard,
    "group_result": GroupResult,
    # 정의와 장비(ADR 0035 3단계) — 재료 아래에 매달리지 않는다. 보기는 전원이다.
    "test_type": TestType,
    "format_profile": FormatProfile,
    "recipe": ProcessingRecipe,
    "export_profile": ExportProfile,
    "equipment": EquipmentUnit,
}
LABELS: dict[str, str] = {
    "material": "재료",
    "sample": "시료",
    "specimen": "시편",
    "test_run": "시험",
    "property_card": "카드",
    "group_result": "묶음",
    "test_type": "시험 정의",
    "format_profile": "장비 파일 정의",
    "recipe": "레시피",
    "export_profile": "해석용 물성 정의",
    "equipment": "장비",
}
_KIND_OF: dict[type, OwnedKind] = {
    Material: "material",
    Sample: "sample",
    Specimen: "specimen",
    TestRun: "test_run",
    PropertyCard: "property_card",
    GroupResult: "group_result",
    TestType: "test_type",
    FormatProfile: "format_profile",
    ProcessingRecipe: "recipe",
    ExportProfile: "export_profile",
    EquipmentUnit: "equipment",
}

#: 재료 아래에 매달리지 않는 것 — 아래로 딸린 것도 없다.
_STANDALONE = (TestType, FormatProfile, ProcessingRecipe, ExportProfile, EquipmentUnit)


def kind_of(row: permissions.Owned) -> OwnedKind:
    return _KIND_OF[type(row)]


def name_of(row: permissions.Owned) -> str:
    if isinstance(
        row, PropertyCard | TestType | FormatProfile | ProcessingRecipe | ExportProfile
    ):
        return row.label
    if isinstance(row, GroupResult):
        return f"{row.plugin_id} · {len(row.members)}건"
    if isinstance(row, EquipmentUnit):
        return row.name
    if isinstance(row, Material | Sample | Specimen | TestRun):
        return row.record_name
    return str(row.id)


def _material_id(db: Session, row: permissions.Owned) -> uuid.UUID | None:
    """이 자료가 어느 재료 아래에 있나 — 보기는 재료를 따라간다."""
    if isinstance(row, Material):
        return row.id
    if isinstance(row, Sample | PropertyCard | GroupResult):
        return row.material_id
    if isinstance(row, Specimen):
        return db.scalar(select(Sample.material_id).where(Sample.id == row.sample_id))
    if isinstance(row, TestRun):
        return db.scalar(
            select(Sample.material_id)
            .join(Specimen, Specimen.sample_id == Sample.id)
            .where(Specimen.id == row.specimen_id)
        )
    return None


def load(db: Session, user: User, kind: OwnedKind, row_id: uuid.UUID) -> permissions.Owned:
    """볼 수 있는 자료 하나. **지운 것은 없는 것이다.**"""
    # `db.get` 은 모델 여섯의 합을 모른다(`Base` 로 돌려준다) — 고르는 표가 곧 그 합이다.
    row = cast(permissions.Owned | None, db.get(MODELS[kind], row_id))
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise NotFound("MNX-OWNERSHIP-0001", f"{LABELS[kind]}을 찾을 수 없습니다.")
    if isinstance(row, _STANDALONE):
        # 정의·장비는 전원이 본다 — 재료를 따라갈 것이 없다.
        return row
    material_id = _material_id(db, row)
    visible = db.scalar(
        permissions.visible_material_ids(db, user).where(Material.id == material_id)
    )
    if visible is None:
        raise NotFound("MNX-OWNERSHIP-0001", f"{LABELS[kind]}을 찾을 수 없습니다.")
    return row


def children(
    db: Session, row: permissions.Owned
) -> list[tuple[OwnedKind, list[permissions.Owned]]]:
    """아래에 딸린 **살아 있는** 것들 — 재료 → 시료 → 시편 → 시험, 재료의 카드·묶음."""
    out: list[tuple[OwnedKind, list[permissions.Owned]]] = []
    samples: list[Sample] = []
    specimens: list[Specimen] = []
    if isinstance(row, Material):
        samples = list(
            db.scalars(
                select(Sample).where(Sample.material_id == row.id, Sample.deleted_at.is_(None))
            )
        )
        out.append(("sample", list(samples)))
    if isinstance(row, Material | Sample):
        parents = [one.id for one in samples] if isinstance(row, Material) else [row.id]
        specimens = (
            list(
                db.scalars(
                    select(Specimen).where(
                        Specimen.sample_id.in_(parents), Specimen.deleted_at.is_(None)
                    )
                )
            )
            if parents
            else []
        )
        out.append(("specimen", list(specimens)))
    if isinstance(row, Material | Sample | Specimen):
        holders = [row.id] if isinstance(row, Specimen) else [one.id for one in specimens]
        runs = (
            list(
                db.scalars(
                    select(TestRun).where(
                        TestRun.specimen_id.in_(holders), TestRun.deleted_at.is_(None)
                    )
                )
            )
            if holders
            else []
        )
        out.append(("test_run", list(runs)))
    if isinstance(row, Material):
        out.append(
            (
                "property_card",
                list(
                    db.scalars(select(PropertyCard).where(PropertyCard.material_id == row.id))
                ),
            )
        )
        out.append(
            (
                "group_result",
                list(db.scalars(select(GroupResult).where(GroupResult.material_id == row.id))),
            )
        )
    return out


def people(db: Session, q: str, *, limit: int) -> list[PersonOut]:
    """이름(또는 아이디)으로 찾은 **활성** 계정 — 이름·대표 소속만 낸다."""
    query = (
        select(User, Workspace.name)
        .outerjoin(Workspace, Workspace.id == User.home_workspace_id)
        .where(User.status == "active", User.deleted_at.is_(None))
        .order_by(User.display_name)
        .limit(limit)
    )
    text = q.strip()
    if text:
        like = f"%{text}%"
        query = query.where(or_(User.display_name.ilike(like), User.email.ilike(like)))
    return [
        PersonOut(id=found.id, display_name=found.display_name, workspace=space)
        for found, space in db.execute(query).all()
    ]


def stewards(db: Session) -> list[PersonOut]:
    """자료 관리자 — **물어볼 사람.** 없으면 시스템 관리자를 댄다(빈 목록은 답이 아니다).

    `permissions.data_steward_names` 와 같은 규칙이다 — 403 이 `details.data_managers` 로
    주는 이름과 여기의 이름이 달라지면, 사람은 둘 중 누구에게 가야 할지 모른다.
    """
    active = (User.status == "active", User.deleted_at.is_(None))
    for flag in (User.is_data_manager, User.is_system_admin):
        rows = db.execute(
            select(User, Workspace.name)
            .outerjoin(Workspace, Workspace.id == User.home_workspace_id)
            .where(flag.is_(True), *active)
            .order_by(User.display_name)
        ).all()
        if rows:
            return [
                PersonOut(id=found.id, display_name=found.display_name, workspace=space)
                for found, space in rows
            ]
    return []


def active_user(db: Session, user_id: uuid.UUID) -> User:
    """넘겨받을 사람 — **지금 로그인할 수 있는 계정만.** 정지된 사람에게 넘기면 그 자료는
    아무도 못 고치는 자료가 되고, 그 사실은 누가 고치려 할 때에야 드러난다."""
    found = db.get(User, user_id)
    if found is None or not found.can_sign_in:
        raise NotFound(
            "MNX-OWNERSHIP-0002", "넘겨받을 사람을 찾을 수 없습니다 — 활성 계정이어야 합니다."
        )
    return found


def active_workspace(db: Session, slug: str) -> Workspace:
    """편집을 받을 부서 — 보관한 부서에는 안 준다(새 활동을 막은 부서다)."""
    found = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if found is None or not found.is_active:
        raise NotFound("MNX-OWNERSHIP-0003", f"부서를 찾을 수 없습니다: {slug}")
    return found


def change(
    db: Session,
    user: User,
    row: permissions.Owned,
    *,
    registrant: User | None,
    set_registrant: bool,
    workspace: Workspace | None,
    set_workspace: bool,
    include_children: bool,
) -> tuple[int, list[OwnershipSkippedOut]]:
    """넘긴다. (바꾼 수, 건너뛴 것). **커밋은 부르는 쪽이 한다.**

    맨 위 자료는 부르는 쪽이 먼저 권한을 본다(`require_hand_over`). 여기서는 아래에
    딸린 것을 한 건씩 보고, 못 넘기는 것은 이름과 까닭을 모아 돌려준다.
    """
    editor = permissions.editor(db, user)
    targets: list[permissions.Owned] = [row]
    if include_children:
        for _kind, rows in children(db, row):
            targets.extend(rows)

    people: dict[uuid.UUID, str] = {}

    def person(user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in people:
            found = db.get(User, user_id)
            people[user_id] = found.display_name if found else "?"
        return people[user_id]

    spaces: dict[uuid.UUID, str] = {}

    def space(workspace_id: uuid.UUID | None) -> str | None:
        if workspace_id is None:
            return None
        if workspace_id not in spaces:
            found = db.get(Workspace, workspace_id)
            spaces[workspace_id] = found.name if found else "?"
        return spaces[workspace_id]

    changed = 0
    skipped: list[OwnershipSkippedOut] = []
    for one in targets:
        if not editor.can_hand_over(one):
            registrant_id, _ = permissions.owner_of(one)
            name = person(registrant_id)
            skipped.append(
                OwnershipSkippedOut(
                    kind=kind_of(one),
                    name=name_of(one),
                    reason=(f"등록자 {name}" if name else "등록자 없음")
                    + " — 등록자와 자료 관리자만 넘길 수 있습니다.",
                )
            )
            continue
        before_registrant, before_workspace = permissions.owner_of(one)
        changes: dict[str, dict[str, str | None]] = {}
        if set_registrant and registrant is not None and before_registrant != registrant.id:
            permissions.set_registrant(one, registrant.id)
            changes["registrant"] = {
                "before": person(before_registrant),
                "after": registrant.display_name,
            }
        after_workspace = workspace.id if workspace is not None else None
        if set_workspace and before_workspace != after_workspace:
            permissions.set_edit_workspace(one, after_workspace)
            changes["edit_workspace"] = {
                "before": space(before_workspace),
                "after": workspace.name if workspace is not None else None,
            }
        if not changes:
            continue
        audit.record(
            db,
            action=audit.OWNERSHIP_CHANGED,
            actor=user,
            target_table=type(one).__tablename__,
            target_id=one.id,
            target_label=name_of(one),
            workspace_id=after_workspace or before_workspace,
            changes=changes,
            # **누구의 일인가** — 넘기기 전의 등록자다(지금 표에는 새 사람이 적혀 있다). 제
            # 것을 제가 넘겼거나 등록자가 없던 것이면 받은 사람의 일이다.
            subject_id=(
                before_registrant
                if before_registrant is not None and before_registrant != user.id
                else (registrant.id if registrant is not None else None)
            ),
        )
        changed += 1
    return changed, skipped
