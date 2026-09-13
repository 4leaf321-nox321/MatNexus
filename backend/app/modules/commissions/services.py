"""측정 의뢰 — 판정과 셈. 라우트는 얇다.

여기 있는 것: 누가 보는가 · 어느 쪽인가 · 어디로 옮길 수 있는가 · 진행률 · 항목
만들기 · 알림. 라우트가 규칙을 들고 있으면 같은 판정이 목록과 상세에서 두 벌이 된다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.commissions.models import (
    AUTHOR_MOVES,
    DELIVERABLE_CURVES,
    LAB_MOVES,
    LINKABLE,
    NOTE_REQUIRED,
    PRIORITIES,
    STATUS_LABELS,
    STATUSES,
    Commission,
    CommissionEvent,
    CommissionItem,
)
from app.modules.commissions.schemas import CommissionItemIn
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import conditions, permissions
from app.shared.errors import AppError, Forbidden, NotFound
from matcore import cards

#: 옮기는 단추에 적을 말. 상태 이름만 적으면 「접수」 가 지금 상태인지 갈 곳인지 안 갈린다.
MOVE_LABELS: dict[str, str] = {
    "draft": "작성 중으로 되돌림",
    "submitted": "의뢰",
    "accepted": "접수",
    "in_progress": "시험 시작",
    "on_hold": "보류",
    "delivered": "결과 전달",
    "closed": "확인하고 완료",
    "rejected": "반려",
}


def _now() -> datetime:
    return datetime.now(UTC)


# --- 누가 보는가 ------------------------------------------------------------------


def visible(db: Session, user: User) -> Select[tuple[Commission]]:
    """낸 부서 멤버 + 받는 부서 멤버 + 시스템 관리자. 작성 중은 낸 사람만.

    시료의 가시 범위를 따르지 않는 이유: 의뢰는 두 부서 사이의 약속이라 제3부서가
    볼 것이 아니다 — 시료가 열린 부서 것이어도 그렇다.
    """
    query = select(Commission)
    if user.is_system_admin:
        return query
    mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    return query.where(
        or_(
            Commission.requester_workspace_id.in_(mine),
            Commission.lab_workspace_id.in_(mine),
        ),
        or_(Commission.status != "draft", Commission.created_by_id == user.id),
    )


def get(db: Session, user: User, commission_id: uuid.UUID) -> Commission:
    item = db.scalar(visible(db, user).where(Commission.id == commission_id))
    if item is None:
        raise NotFound("MNX-COMMISSIONS-0001", "의뢰를 찾을 수 없습니다.")
    return item


def side_of(db: Session, item: Commission, user: User) -> str:
    """이 사람은 이 건에서 어느 쪽인가 — `requester` · `lab` · `both` · `viewer`."""
    mine = set(permissions.my_workspace_ids(db, user))
    requester = item.requester_workspace_id in mine or item.created_by_id == user.id
    lab = item.lab_workspace_id in mine
    if requester and lab:
        return "both"
    if requester:
        return "requester"
    if lab:
        return "lab"
    return "viewer"


def is_lab_side(side: str, user: User) -> bool:
    """받는 쪽으로 행동할 수 있는가. 시스템 관리자는 언제나 — 막힌 건을 푸는 사람이다."""
    return user.is_system_admin or side in ("lab", "both")


def moves(item: Commission, side: str, user: User) -> list[str]:
    """이 사람이 지금 옮길 수 있는 상태. 받는 쪽 것에 낸 사람 것을 더한다."""
    allowed: list[str] = []
    if is_lab_side(side, user):
        allowed.extend(LAB_MOVES.get(item.status, ()))
    if item.created_by_id == user.id or user.is_system_admin:
        allowed.extend(one for one in AUTHOR_MOVES.get(item.status, ()) if one not in allowed)
    return allowed


def can_edit(item: Commission, user: User) -> bool:
    """제목·목적·항목을 고칠 수 있는가 — 낸 사람이 작성 중·접수 대기일 때. 접수된 뒤에
    항목이 바뀌면 받는 쪽이 다른 일을 하고 있는 셈이다 — 그때는 말을 보탠다."""
    if item.status not in ("draft", "submitted"):
        return False
    return user.is_system_admin or item.created_by_id == user.id


def can_link(item: Commission, side: str, user: User) -> bool:
    return is_lab_side(side, user) and item.status in LINKABLE


# --- 진행률 -------------------------------------------------------------------------


def progress(
    db: Session, commission_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int, int]]:
    """건마다 (의뢰 수, 붙은 시험, 채택된 시험). **한 번에 센다** — 목록이 N+1 이 되지 않게."""
    if not commission_ids:
        return {}
    out: dict[uuid.UUID, tuple[int, int, int]] = {one: (0, 0, 0) for one in commission_ids}
    for commission_id, total in db.execute(
        select(CommissionItem.commission_id, func.coalesce(func.sum(CommissionItem.count), 0))
        .where(CommissionItem.commission_id.in_(commission_ids))
        .group_by(CommissionItem.commission_id)
    ).all():
        out[commission_id] = (int(total), 0, 0)
    for commission_id, linked, done in db.execute(
        select(
            CommissionItem.commission_id,
            func.count(TestRun.id),
            func.count(TestRun.adopted_result_id),
        )
        .join(TestRun, TestRun.commission_item_id == CommissionItem.id)
        .where(CommissionItem.commission_id.in_(commission_ids), TestRun.deleted_at.is_(None))
        .group_by(CommissionItem.commission_id)
    ).all():
        total = out[commission_id][0]
        out[commission_id] = (total, int(linked), int(done))
    return out


def linked_runs(db: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[TestRun]]:
    if not item_ids:
        return {}
    out: dict[uuid.UUID, list[TestRun]] = {one: [] for one in item_ids}
    for run in db.scalars(
        select(TestRun)
        .where(TestRun.commission_item_id.in_(item_ids), TestRun.deleted_at.is_(None))
        .order_by(TestRun.created_at)
    ):
        assert run.commission_item_id is not None
        out[run.commission_item_id].append(run)
    return out


def candidate_runs(
    db: Session, item: Commission, items: list[CommissionItem]
) -> dict[uuid.UUID, list[TestRun]]:
    """항목에 붙일 수 있는 시험 — 같은 시료, 같은 시험 종류, 아직 아무 항목에도 안 붙은 것."""
    if not items:
        return {}
    by_type: dict[uuid.UUID, list[uuid.UUID]] = {}
    for one in items:
        by_type.setdefault(one.test_type_id, []).append(one.id)
    runs = list(
        db.scalars(
            select(TestRun)
            .join(Specimen, Specimen.id == TestRun.specimen_id)
            .where(
                Specimen.sample_id == item.sample_id,
                Specimen.deleted_at.is_(None),
                TestRun.deleted_at.is_(None),
                TestRun.commission_item_id.is_(None),
                TestRun.test_type_id.in_(list(by_type)),
            )
            .order_by(TestRun.created_at.desc())
        )
    )
    out: dict[uuid.UUID, list[TestRun]] = {one.id: [] for one in items}
    for run in runs:
        for item_id in by_type.get(run.test_type_id, []):
            out[item_id].append(run)
    return out


# --- 만들기·고치기 ----------------------------------------------------------------


def lab_workspace(db: Session, slug: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None or not workspace.is_active:
        raise NotFound("MNX-COMMISSIONS-0002", f"받는 부서를 찾을 수 없습니다: {slug}")
    return workspace


def requester_workspace(db: Session, user: User) -> Workspace:
    """낸 부서 = 낸 사람의 소속 부서."""
    if user.home_workspace_id is None:
        raise AppError(
            "MNX-COMMISSIONS-0003",
            "소속 부서가 없습니다. 관리자에게 부서 지정을 요청하세요.",
            status=422,
        )
    workspace = db.get(Workspace, user.home_workspace_id)
    if workspace is None:
        raise NotFound("MNX-COMMISSIONS-0003", "소속 부서를 찾을 수 없습니다.")
    return workspace


def visible_sample(db: Session, user: User, sample_id: uuid.UUID) -> Sample:
    """볼 수 있는 시료 하나 — 재료의 가시 범위를 따른다."""
    sample = db.scalar(
        select(Sample).where(
            Sample.id == sample_id,
            Sample.deleted_at.is_(None),
            Sample.material_id.in_(permissions.visible_material_ids(db, user)),
        )
    )
    if sample is None:
        raise NotFound("MNX-COMMISSIONS-0004", "시료를 찾을 수 없습니다.")
    return sample


def check_priority(priority: str) -> str:
    if priority not in PRIORITIES:
        raise AppError("MNX-COMMISSIONS-0005", "허용되지 않는 우선순위입니다.", status=422)
    return priority


def _deliverable_keys() -> set[str]:
    cards.load_builtin()
    return {spec.key for spec in cards.list_blocks()} | {DELIVERABLE_CURVES}


def build_items(
    db: Session, user: User, commission_id: uuid.UUID, payload: list[CommissionItemIn]
) -> list[CommissionItem]:
    """항목 입력을 행으로. 조건은 시험 등록과 **같은 규칙**으로 SI 가 된다."""
    allowed_deliverables = _deliverable_keys()
    made: list[CommissionItem] = []
    for position, one in enumerate(payload):
        test_type = db.scalar(
            select(TestType).where(
                TestType.key == one.test_type_key,
                TestType.deleted_at.is_(None),
                TestType.is_active.is_(True),
                permissions.visible_owner_clause(db, user, TestType.owner_workspace_id),
            )
        )
        if test_type is None:
            raise NotFound(
                "MNX-COMMISSIONS-0006", f"시험 종류를 찾을 수 없습니다: {one.test_type_key}"
            )
        values, input_units = conditions.normalize_conditions(
            db, test_type, dict(one.conditions), dict(one.condition_units)
        )
        if one.deliverable and one.deliverable not in allowed_deliverables:
            raise AppError(
                "MNX-COMMISSIONS-0007",
                f"받을 것을 알 수 없습니다: {one.deliverable} — 카드 블록 키 또는 "
                f"'{DELIVERABLE_CURVES}'.",
                status=422,
            )
        orientations = [text.strip() for text in one.orientations if text and text.strip()]
        made.append(
            CommissionItem(
                commission_id=commission_id,
                position=position,
                test_type_id=test_type.id,
                conditions=values,
                input_units=input_units,
                orientations=orientations,
                count=one.count,
                deliverable=one.deliverable or None,
                note=(one.note or "").strip() or None,
            )
        )
    return made


def replace_items(
    db: Session, user: User, item: Commission, payload: list[CommissionItemIn]
) -> None:
    """항목 전부를 갈아 넣는다. 시험이 이미 붙은 항목은 못 지운다 — 붙은 시험의 연결이
    조용히 풀린다. 작성 중·접수 대기에서만 부르므로 실제로는 안 붙어 있다."""
    existing = list(
        db.scalars(select(CommissionItem).where(CommissionItem.commission_id == item.id))
    )
    linked = linked_runs(db, [one.id for one in existing])
    if any(linked.get(one.id) for one in existing):
        raise AppError(
            "MNX-COMMISSIONS-0008",
            "시험이 붙은 항목은 고칠 수 없습니다 — 먼저 시험 연결을 푸세요.",
            status=422,
        )
    for one in existing:
        db.delete(one)
    db.flush()
    for row in build_items(db, user, item.id, payload):
        db.add(row)
    db.flush()


# --- 상태 -----------------------------------------------------------------------------


def note_required(target: str) -> bool:
    return target in NOTE_REQUIRED


def check_target(item: Commission, target: str, allowed: list[str]) -> None:
    if target not in STATUSES:
        raise AppError("MNX-COMMISSIONS-0009", "허용되지 않는 상태입니다.", status=422)
    if target == item.status:
        raise AppError(
            "MNX-COMMISSIONS-0010",
            f"이미 '{STATUS_LABELS[target]}' 상태입니다. 말만 보태려면 상태를 비우세요.",
            status=422,
        )
    if target not in allowed:
        raise Forbidden(
            "MNX-COMMISSIONS-0011",
            f"'{STATUS_LABELS[item.status]}' 에서 '{STATUS_LABELS[target]}' 로 "
            "옮길 수 없습니다"
            + (
                " — 지금 갈 수 있는 곳: "
                + ", ".join(STATUS_LABELS[one] for one in allowed)
                + "."
                if allowed
                else "."
            ),
        )


def check_deliverable(db: Session, item: Commission) -> None:
    """「결과 전달」 은 **항목마다 채택된 결과가 하나는 있어야** 한다. 없는 항목이 있으면
    무엇을 전달했다는 것인지 없다 — 그 항목을 못 하게 됐으면 말을 남기고 보류·반려로."""
    rows = list(
        db.scalars(select(CommissionItem).where(CommissionItem.commission_id == item.id))
    )
    linked = linked_runs(db, [one.id for one in rows])
    missing = [
        one
        for one in rows
        if not any(run.adopted_result_id is not None for run in linked.get(one.id, []))
    ]
    if missing:
        raise AppError(
            "MNX-COMMISSIONS-0012",
            f"채택된 결과가 없는 항목이 {len(missing)}건 있습니다 — "
            f"{', '.join(f'{one.position + 1}번' for one in missing)}. "
            "시험을 붙이고 결과를 채택한 뒤 전달하세요.",
            status=422,
        )


def move(
    db: Session,
    item: Commission,
    *,
    actor: User,
    target: str | None,
    note: str | None,
) -> CommissionEvent:
    """상태를 옮기거나 말을 보탠다. 이벤트를 남기고 상태 열을 맞춘다. commit 은 부르는 쪽."""
    now = _now()
    event = CommissionEvent(
        commission_id=item.id,
        at=now,
        by_id=actor.id,
        from_status=item.status,
        to_status=target or item.status,
        note=note,
    )
    db.add(event)
    db.flush()
    if target is not None:
        item.status = target
        item.status_at = now
        item.status_by_id = actor.id
    return event


def auto_start(db: Session, item: Commission, *, actor: User) -> None:
    """시험이 붙으면 「접수」 는 저절로 「시험 중」 이 된다 — 그것이 시험 중이라는 뜻이다."""
    if item.status == "accepted":
        move(db, item, actor=actor, target="in_progress", note="시험이 붙어 저절로 옮김")


# --- 알림 -------------------------------------------------------------------------------


def notify_submitted(db: Session, item: Commission, actor: User) -> None:
    """받는 부서 관리자에게. 알림 모듈의 함수는 못 부르므로 큐에 직접 넣는다(`kinds`)."""
    managers = db.scalars(
        select(WorkspaceMember.user_id).where(
            WorkspaceMember.workspace_id == item.lab_workspace_id,
            WorkspaceMember.role == "manager",
        )
    )
    for user_id in managers:
        if user_id == actor.id:
            continue
        queue.enqueue(
            db,
            kind=kinds.NOTIFY_DELIVER,
            payload={
                "event_kind": "commission.submitted",
                "key": f"commission:{item.id}:submitted:{item.status_at.isoformat()}",
                "title": f"새 측정 의뢰 #{item.seq}: {item.title}",
                "body": f"{actor.display_name} 님이 냈습니다.",
                "link": f"/commissions/{item.id}",
                "to_user_id": str(user_id),
            },
        )


def notify_changed(
    db: Session,
    item: Commission,
    event: CommissionEvent,
    actor: User,
    previous_handler: uuid.UUID | None,
) -> None:
    """이 건이 움직였다고 **상대에게** 알린다 — 자기가 한 일을 자기에게 알리지 않는다.

    남이 움직이면 낸 사람에게. 낸 사람이 움직이면 담당자에게, 담당자가 없으면 마지막
    으로 다룬 사람에게. 받을 사람이 없으면 조용히 넘어간다.
    """
    if actor.id != item.created_by_id:
        to_user = item.created_by_id
    elif item.assignee_id is not None and item.assignee_id != actor.id:
        to_user = item.assignee_id
    elif previous_handler is not None and previous_handler != actor.id:
        to_user = previous_handler
    else:
        return
    if to_user is None:
        return
    moved = event.from_status != event.to_status
    what = (
        f"{STATUS_LABELS[event.from_status or event.to_status]} → "
        f"{STATUS_LABELS[event.to_status]}"
        if moved
        else "말을 보탰습니다"
    )
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "commission.changed",
            "key": f"commission:{item.id}:{event.id}",
            "title": f"측정 의뢰 #{item.seq} {what}",
            "body": f"{actor.display_name}: {event.note}"
            if event.note
            else actor.display_name,
            "link": f"/commissions/{item.id}",
            "to_user_id": str(to_user),
        },
    )


# --- 이름 -------------------------------------------------------------------------------


def names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {one for one in ids if one is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(wanted))).all()
    return {row.id: row.display_name for row in rows}


def workspaces(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Workspace]:
    if not ids:
        return {}
    return {one.id: one for one in db.scalars(select(Workspace).where(Workspace.id.in_(ids)))}


def samples(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[Sample, Material]]:
    if not ids:
        return {}
    rows = db.execute(
        select(Sample, Material)
        .join(Material, Material.id == Sample.material_id)
        .where(Sample.id.in_(ids))
    ).all()
    return {row.Sample.id: (row.Sample, row.Material) for row in rows}


def lab_members(db: Session, workspace_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    rows = db.execute(
        select(User.id, User.display_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id, User.status == "active")
        .order_by(User.display_name)
    ).all()
    return [(row.id, row.display_name) for row in rows]


def event_counts(db: Session, commission_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not commission_ids:
        return {}
    return {
        commission_id: int(count)
        for commission_id, count in db.execute(
            select(CommissionEvent.commission_id, func.count())
            .where(CommissionEvent.commission_id.in_(commission_ids))
            .group_by(CommissionEvent.commission_id)
        ).all()
    }


def specimen_names(db: Session, runs: list[TestRun]) -> dict[uuid.UUID, str]:
    ids = {run.specimen_id for run in runs}
    if not ids:
        return {}
    return {
        row.id: row.record_name
        for row in db.execute(
            select(Specimen.id, Specimen.record_name).where(Specimen.id.in_(ids))
        ).all()
    }


def scope_clause(db: Session, user: User, scope: str) -> Any:
    """목록 탭 — `mine`(내가 낸 것) · `received`(우리 부서가 받은 것) · `all`."""
    if scope == "mine":
        return Commission.created_by_id == user.id
    if scope == "received":
        mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        return and_(Commission.lab_workspace_id.in_(mine), Commission.status != "draft")
    if scope == "all":
        return None
    raise AppError("MNX-COMMISSIONS-0013", "허용되지 않는 범위입니다.", status=422)
