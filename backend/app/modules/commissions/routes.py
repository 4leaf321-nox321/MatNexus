"""측정 의뢰 라우터 — 게시판이고 절차고, 끝이 데이터다.

낸 부서와 받는 부서만 본다. 상태를 옮기는 것은 받는 쪽과 낸 사람이 각자 갈 수 있는
곳만(`models.LAB_MOVES` · `AUTHOR_MOVES`), 말을 보태는 것은 보는 사람 누구나. 시험을
붙이는 것은 받는 쪽이 접수한 뒤(`LINKABLE`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.commissions import services
from app.modules.commissions.models import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    STATUSES,
    Commission,
    CommissionEvent,
    CommissionItem,
)
from app.modules.commissions.schemas import (
    AssignRequest,
    AttachSampleRequest,
    CommissionCreateRequest,
    CommissionDetailOut,
    CommissionEventOut,
    CommissionEventRequest,
    CommissionItemOut,
    CommissionOut,
    CommissionStatusOut,
    CommissionUpdateRequest,
    LinkedRunOut,
    LinkRunRequest,
    NamedOut,
    ProgressOut,
    ResolveItemRequest,
    SampleRefOut,
    WorkspaceRefOut,
)
from app.modules.materials.models import Specimen
from app.modules.tests.models import TestRun, TestType
from app.shared import conditions
from app.shared.auth import current_user
from app.shared.errors import AppError, Forbidden, NotFound
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/commissions", tags=["commissions"])


def _rows(
    db: Session, items: list[Commission], viewer: User, *, sides: dict[uuid.UUID, str]
) -> list[CommissionOut]:
    ids = [one.id for one in items]
    names = services.names(
        db,
        {one.created_by_id for one in items}
        | {one.status_by_id for one in items}
        | {one.assignee_id for one in items},
    )
    workspaces = services.workspaces(
        db,
        {one.requester_workspace_id for one in items}
        | {one.lab_workspace_id for one in items},
    )
    samples = services.samples(db, {one.sample_id for one in items if one.sample_id})
    progress = services.progress(db, ids)
    counts = services.event_counts(db, ids)
    spoken = services.spoken_by_others(db, items)
    item_counts: dict[uuid.UUID, int] = {}
    if ids:
        for commission_id, count in db.execute(
            select(CommissionItem.commission_id, func.count())
            .where(CommissionItem.commission_id.in_(ids))
            .group_by(CommissionItem.commission_id)
        ).all():
            item_counts[commission_id] = int(count)

    out: list[CommissionOut] = []
    for one in items:
        requester = workspaces[one.requester_workspace_id]
        lab = workspaces[one.lab_workspace_id]
        found = samples.get(one.sample_id) if one.sample_id else None
        total, linked, done = progress.get(one.id, (0, 0, 0))
        out.append(
            CommissionOut(
                id=one.id,
                seq=one.seq,
                title=one.title,
                status=one.status,
                status_label=STATUS_LABELS.get(one.status, one.status),
                priority=one.priority,
                priority_label=PRIORITY_LABELS.get(one.priority, one.priority),
                requester_workspace=WorkspaceRefOut(slug=requester.slug, name=requester.name),
                lab_workspace=WorkspaceRefOut(slug=lab.slug, name=lab.name),
                sample=(
                    SampleRefOut(
                        id=found[0].id,
                        record_name=found[0].record_name,
                        material_id=found[1].id,
                        material_name=found[1].record_name,
                    )
                    if found
                    else None
                ),
                material_hint=one.material_hint,
                due_on=one.due_on,
                created_at=one.created_at,
                created_by=names.get(one.created_by_id) if one.created_by_id else None,
                status_at=one.status_at,
                status_by=names.get(one.status_by_id) if one.status_by_id else None,
                assignee=(
                    NamedOut(id=one.assignee_id, name=names.get(one.assignee_id, "알 수 없음"))
                    if one.assignee_id
                    else None
                ),
                item_count=item_counts.get(one.id, 0),
                progress=ProgressOut(total=total, linked=linked, done=done),
                is_mine=one.created_by_id == viewer.id,
                side=sides[one.id],
                event_count=max(counts.get(one.id, 0) - 1, 0),
                can_delete=services.can_delete(one, viewer, others_spoke=one.id in spoken),
            )
        )
    return out


def _run_out(run: TestRun, specimen_names: dict[uuid.UUID, str]) -> LinkedRunOut:
    return LinkedRunOut(
        id=run.id,
        record_name=run.record_name,
        status=run.status,
        adopted=run.adopted_result_id is not None,
        specimen_name=specimen_names.get(run.specimen_id),
        tested_at=run.tested_at,
    )


def _detail(db: Session, item: Commission, viewer: User) -> CommissionDetailOut:
    side = services.side_of(db, item, viewer)
    head = _rows(db, [item], viewer, sides={item.id: side})[0]
    rows = list(
        db.scalars(
            select(CommissionItem)
            .where(CommissionItem.commission_id == item.id)
            .order_by(CommissionItem.position)
        )
    )
    type_ids = {one.test_type_id for one in rows if one.test_type_id}
    type_labels = (
        {
            row.id: (row.key, row.label)
            for row in db.execute(
                select(TestType.id, TestType.key, TestType.label).where(
                    TestType.id.in_(type_ids)
                )
            ).all()
        }
        if type_ids
        else {}
    )
    linked = services.linked_runs(db, [one.id for one in rows])
    lab_side = services.is_lab_side(side, viewer)
    candidates = services.candidate_runs(db, item, rows) if lab_side else {}
    every_run = [run for runs in linked.values() for run in runs] + [
        run for runs in candidates.values() for run in runs
    ]
    specimen_names = services.specimen_names(db, every_run)

    events = list(
        db.scalars(
            select(CommissionEvent)
            .where(CommissionEvent.commission_id == item.id)
            .order_by(CommissionEvent.at, CommissionEvent.id)
        )
    )
    names = services.names(db, {one.by_id for one in events})
    allowed = services.moves(item, side, viewer)
    can_assign = lab_side
    return CommissionDetailOut(
        **head.model_dump(),
        purpose=item.purpose,
        sample_plan=item.sample_plan,
        items=[
            CommissionItemOut(
                id=one.id,
                position=one.position,
                test_type_key=(
                    type_labels[one.test_type_id][0]
                    if one.test_type_id in type_labels
                    else None
                ),
                test_type_label=(
                    type_labels[one.test_type_id][1]
                    if one.test_type_id in type_labels
                    else None
                ),
                property_hint=one.property_hint,
                conditions=dict(one.conditions),
                input_units=dict(one.input_units),
                orientations=list(one.orientations),
                count=one.count,
                deliverable=one.deliverable,
                note=one.note,
                runs=[_run_out(run, specimen_names) for run in linked.get(one.id, [])],
                done=sum(
                    1 for run in linked.get(one.id, []) if run.adopted_result_id is not None
                ),
                candidates=[
                    _run_out(run, specimen_names) for run in candidates.get(one.id, [])
                ],
            )
            for one in rows
        ],
        events=[
            CommissionEventOut(
                id=one.id,
                at=one.at,
                by=names.get(one.by_id) if one.by_id else None,
                from_status=one.from_status,
                to_status=one.to_status,
                to_status_label=STATUS_LABELS.get(one.to_status, one.to_status),
                note=one.note,
            )
            for one in events
        ],
        allowed=allowed,
        allowed_labels={one: services.MOVE_LABELS.get(one, one) for one in allowed},
        note_required=[one for one in allowed if services.note_required(one)],
        can_edit=services.can_edit(item, viewer),
        can_link=services.can_link(item, side, viewer),
        can_assign=can_assign,
        can_resolve=services.can_resolve(item, side, viewer),
        can_comment=services.can_comment(side, viewer),
        assignees=(
            [
                NamedOut(id=user_id, name=name)
                for user_id, name in services.lab_members(db, item.lab_workspace_id)
            ]
            if can_assign
            else []
        ),
    )


@router.get("/statuses", response_model=list[CommissionStatusOut])
def list_statuses(user: User = Depends(current_user)) -> list[CommissionStatusOut]:
    """상태의 차례와 이름. 화면이 표를 갖지 않는다."""
    return [CommissionStatusOut(key=one, label=STATUS_LABELS[one]) for one in STATUSES]


@router.get("", response_model=Page[CommissionOut])
def list_commissions(
    scope: str = Query(default="all", pattern="^(ours|mine|received|all)$"),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[CommissionOut]:
    """의뢰 게시판. 최신이 위다. **누구나 본다** — 작성 중은 낸 사람만(ADR 0035)."""
    query = services.visible(db, user)
    clause = services.scope_clause(db, user, scope)
    if clause is not None:
        query = query.where(clause)
    if status:
        if status not in STATUSES:
            raise AppError("MNX-COMMISSIONS-0009", "허용되지 않는 상태입니다.", status=422)
        query = query.where(Commission.status == status)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(Commission.title.ilike(needle), Commission.purpose.ilike(needle))
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    items = list(db.scalars(query.order_by(Commission.seq.desc()).limit(size).offset(offset)))
    sides = {one.id: services.side_of(db, one, user) for one in items}
    return Page(
        items=_rows(db, items, user, sides=sides), total=int(total), limit=size, offset=offset
    )


@router.post("", response_model=CommissionDetailOut, status_code=201)
def create_commission(
    payload: CommissionCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    requester = services.requester_workspace(db, user)
    lab = services.lab_workspace(db, payload.lab_workspace_slug)
    sample = (
        services.visible_sample(db, user, payload.sample_id)
        if payload.sample_id is not None
        else None
    )
    now = services._now()
    status = "submitted" if payload.submit else "draft"
    item = Commission(
        title=payload.title.strip(),
        purpose=payload.purpose.strip(),
        status=status,
        priority=services.check_priority(payload.priority),
        requester_workspace_id=requester.id,
        lab_workspace_id=lab.id,
        sample_id=sample.id if sample is not None else None,
        material_hint=(payload.material_hint or "").strip() or None,
        sample_plan=(payload.sample_plan or "").strip() or None,
        due_on=payload.due_on,
        created_by_id=user.id,
        created_at=now,
        status_at=now,
        status_by_id=user.id,
    )
    db.add(item)
    db.flush()
    for row in services.build_items(db, user, item.id, payload.items):
        db.add(row)
    db.add(
        CommissionEvent(
            commission_id=item.id, at=now, by_id=user.id, from_status=None, to_status=status
        )
    )
    db.flush()
    if status == "submitted":
        services.notify_submitted(db, item, user)
    db.commit()
    return _detail(db, item, user)


@router.get("/{commission_id}", response_model=CommissionDetailOut)
def get_commission(
    commission_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    return _detail(db, services.get(db, user, commission_id), user)


def _editable(db: Session, commission_id: uuid.UUID, user: User) -> Commission:
    item = services.get(db, user, commission_id)
    if not services.can_edit(item, user):
        raise Forbidden(
            "MNX-COMMISSIONS-0014",
            "낸 사람이 작성 중·접수 대기일 때만 고칠 수 있습니다. "
            "접수된 뒤에는 말을 보태세요.",
        )
    return item


@router.patch("/{commission_id}", response_model=CommissionDetailOut)
def update_commission(
    commission_id: uuid.UUID,
    payload: CommissionUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """**안 보낸 것과 비운 것을 가른다.** 기한은 비울 수 있는 칸이라 `model_fields_set`
    으로 가른다."""
    item = _editable(db, commission_id, user)
    sent = payload.model_fields_set
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.purpose is not None:
        item.purpose = payload.purpose.strip()
    if payload.sample_id is not None:
        item.sample_id = services.visible_sample(db, user, payload.sample_id).id
    if "material_hint" in sent:
        item.material_hint = (payload.material_hint or "").strip() or None
    if item.sample_id is None and not item.material_hint:
        raise AppError(
            "MNX-COMMISSIONS-0027",
            "시료를 고르거나, 새 재료가 무엇인지 적어야 합니다.",
            status=422,
        )
    if payload.lab_workspace_slug is not None:
        item.lab_workspace_id = services.lab_workspace(db, payload.lab_workspace_slug).id
    if "sample_plan" in sent:
        item.sample_plan = (payload.sample_plan or "").strip() or None
    if "due_on" in sent:
        item.due_on = payload.due_on
    if payload.priority is not None:
        item.priority = services.check_priority(payload.priority)
    if payload.items is not None:
        services.replace_items(db, user, item, payload.items)
    db.commit()
    return _detail(db, item, user)


@router.delete("/{commission_id}", status_code=204)
def delete_commission(
    commission_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """**낸 사람은 받는 쪽이 손대기 전까지, 시스템 관리자는 언제나.**

    받는 쪽이 접수하거나 말을 남긴 뒤에는 절차의 기록이다 — 안 할 거면 반려·완료로
    둔다. 관리자가 지우면 이력도 함께 가고(CASCADE) 붙은 시험은 남는다 — 화면이 먼저
    묻는다.
    """
    item = services.get(db, user, commission_id)
    others = item.id in services.spoken_by_others(db, [item])
    if not services.can_delete(item, user, others_spoke=others):
        raise Forbidden(
            "MNX-COMMISSIONS-0015",
            "받는 부서가 손댄 의뢰는 낸 사람이 지울 수 없습니다 — "
            "반려나 완료로 두거나 시스템 관리자에게 요청하세요.",
        )
    db.delete(item)
    db.commit()


@router.post("/{commission_id}/assignee", response_model=CommissionDetailOut)
def assign(
    commission_id: uuid.UUID,
    payload: AssignRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """담당자 — 받는 부서 멤버 가운데. 받는 쪽만 정한다."""
    item = services.get(db, user, commission_id)
    side = services.side_of(db, item, user)
    if not services.is_lab_side(side, user):
        raise Forbidden("MNX-COMMISSIONS-0016", "담당자는 받는 부서가 정합니다.")
    if payload.assignee_id is not None:
        members = {user_id for user_id, _ in services.lab_members(db, item.lab_workspace_id)}
        if payload.assignee_id not in members:
            raise AppError(
                "MNX-COMMISSIONS-0017", "담당자는 받는 부서의 멤버여야 합니다.", status=422
            )
    item.assignee_id = payload.assignee_id
    db.commit()
    return _detail(db, item, user)


@router.post("/{commission_id}/events", response_model=CommissionDetailOut)
def add_event(
    commission_id: uuid.UUID,
    payload: CommissionEventRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """상태를 옮기거나 말을 보탠다. **갈 수 있는 곳만 간다.**

    **낸 쪽과 받는 쪽만.** 보기는 전원이지만(ADR 0035) 이 건의 흐름에 말을 얹는 것은
    약속한 두 쪽이다 — 제3부서가 끼어들면 누구에게 답해야 하는지가 흐려진다.
    """
    item = services.get(db, user, commission_id)
    side = services.side_of(db, item, user)
    if not services.can_comment(side, user):
        raise Forbidden(
            "MNX-COMMISSIONS-0033",
            "이 의뢰는 낸 부서와 받는 부서만 움직이고 말을 보탤 수 있습니다 — "
            "읽기만 됩니다. 물을 것이 있으면 낸 사람에게 직접 물어 주세요.",
        )
    note = (payload.note or "").strip() or None
    target = payload.status
    if target is not None:
        services.check_target(item, target, services.moves(item, side, user))
        if services.note_required(target) and note is None:
            raise AppError(
                "MNX-COMMISSIONS-0018",
                f"'{STATUS_LABELS[target]}' 로 옮길 때는 말을 적어야 합니다 — 언제쯤인지, "
                "왜인지, 어디서 보는지 없으면 읽는 사람이 되물어야 합니다.",
                status=422,
            )
        if target == "delivered":
            services.check_deliverable(db, item)
    previous_handler = item.status_by_id
    was_draft = item.status == "draft"
    event = services.move(db, item, actor=user, target=target, note=note)
    if target == "submitted" and (was_draft or event.from_status == "rejected"):
        services.notify_submitted(db, item, user)
    else:
        services.notify_changed(db, item, event, user, previous_handler)
    db.commit()
    return _detail(db, item, user)


def _linkable(db: Session, commission_id: uuid.UUID, user: User) -> Commission:
    item = services.get(db, user, commission_id)
    side = services.side_of(db, item, user)
    if not services.is_lab_side(side, user):
        raise Forbidden("MNX-COMMISSIONS-0019", "시험은 받는 부서가 붙입니다.")
    if not services.can_link(item, side, user):
        raise AppError(
            "MNX-COMMISSIONS-0020",
            f"'{STATUS_LABELS[item.status]}' 상태에서는 시험을 붙일 수 없습니다 — "
            "접수한 뒤에.",
            status=422,
        )
    return item


def _item_of(db: Session, item: Commission, item_id: uuid.UUID) -> CommissionItem:
    row = db.get(CommissionItem, item_id)
    if row is None or row.commission_id != item.id:
        raise NotFound("MNX-COMMISSIONS-0021", "그 항목이 없습니다.")
    return row


@router.post("/{commission_id}/items/{item_id}/runs", response_model=CommissionDetailOut)
def link_run(
    commission_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: LinkRunRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """시험을 항목에 붙인다. **같은 시료, 같은 시험 종류**여야 한다 — 다른 시료의 시험을
    붙이면 의뢰가 재지도 않은 것을 잰 것으로 적는다. 붙으면 「접수」 는 「시험 중」 이 된다."""
    item = _linkable(db, commission_id, user)
    row = _item_of(db, item, item_id)
    if item.sample_id is None:
        raise AppError(
            "MNX-COMMISSIONS-0028",
            "시료가 아직 없습니다 — 재료·시료를 등록하고 이 의뢰에 이은 뒤 시험을 붙이세요.",
            status=422,
        )
    if row.test_type_id is None:
        raise AppError(
            "MNX-COMMISSIONS-0029",
            "이 항목은 시험 종류가 미정입니다 — 종류를 먼저 정하세요.",
            status=422,
        )
    run = db.scalar(
        select(TestRun)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .where(TestRun.id == payload.run_id, TestRun.deleted_at.is_(None))
    )
    if run is None:
        raise NotFound("MNX-COMMISSIONS-0022", "시험을 찾을 수 없습니다.")
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None or specimen.sample_id != item.sample_id:
        raise AppError(
            "MNX-COMMISSIONS-0023", "이 의뢰의 시료로 한 시험만 붙일 수 있습니다.", status=422
        )
    if run.test_type_id != row.test_type_id:
        raise AppError(
            "MNX-COMMISSIONS-0024", "항목의 시험 종류와 다른 시험입니다.", status=422
        )
    if run.commission_item_id is not None and run.commission_item_id != row.id:
        raise AppError(
            "MNX-COMMISSIONS-0025",
            "이미 다른 의뢰 항목에 붙은 시험입니다 — 한 시험은 한 항목에만 답합니다.",
            status=422,
        )
    run.commission_item_id = row.id
    services.move(
        db,
        item,
        actor=user,
        target=None,
        note=f"{row.position + 1}번 항목에 시험 연결: {run.record_name}",
    )
    services.auto_start(db, item, actor=user)
    db.commit()
    return _detail(db, item, user)


@router.delete(
    "/{commission_id}/items/{item_id}/runs/{run_id}", response_model=CommissionDetailOut
)
def unlink_run(
    commission_id: uuid.UUID,
    item_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """연결을 푼다. 시험은 남는다 — 잘못 붙였을 때."""
    item = _linkable(db, commission_id, user)
    row = _item_of(db, item, item_id)
    run = db.get(TestRun, run_id)
    if run is None or run.commission_item_id != row.id:
        raise NotFound("MNX-COMMISSIONS-0026", "이 항목에 붙은 시험이 아닙니다.")
    run.commission_item_id = None
    services.move(
        db,
        item,
        actor=user,
        target=None,
        note=f"{row.position + 1}번 항목의 시험 연결 해제: {run.record_name}",
    )
    db.commit()
    return _detail(db, item, user)


def _resolvable(db: Session, commission_id: uuid.UUID, user: User) -> Commission:
    item = services.get(db, user, commission_id)
    side = services.side_of(db, item, user)
    if not services.can_resolve(item, side, user):
        raise Forbidden(
            "MNX-COMMISSIONS-0030",
            "시료를 잇거나 종류를 정하는 것은 받는 부서가 접수한 뒤에 합니다.",
        )
    return item


@router.post("/{commission_id}/sample", response_model=CommissionDetailOut)
def attach_sample(
    commission_id: uuid.UUID,
    payload: AttachSampleRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """새 재료 의뢰에 등록된 시료를 잇는다 — 받는 쪽이 재료·시료를 만든 뒤.

    시험이 이미 붙어 있으면 못 바꾼다 — 붙은 시험은 옛 시료의 것이라 「무엇을 쟀는지」 가
    어긋난다. 그때는 연결을 풀고 잇는다. `material_hint` 는 남긴다(무엇을 달라고 했는지).
    """
    item = _resolvable(db, commission_id, user)
    sample = services.visible_sample(db, user, payload.sample_id)
    rows = list(
        db.scalars(select(CommissionItem).where(CommissionItem.commission_id == item.id))
    )
    linked = services.linked_runs(db, [one.id for one in rows])
    if item.sample_id is not None and item.sample_id != sample.id and any(linked.values()):
        raise AppError(
            "MNX-COMMISSIONS-0031",
            "시험이 붙어 있어 시료를 바꿀 수 없습니다 — 먼저 시험 연결을 푸세요.",
            status=422,
        )
    item.sample_id = sample.id
    services.move(db, item, actor=user, target=None, note=f"시료 연결: {sample.record_name}")
    db.commit()
    return _detail(db, item, user)


@router.post("/{commission_id}/items/{item_id}/test-type", response_model=CommissionDetailOut)
def resolve_item(
    commission_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ResolveItemRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommissionDetailOut:
    """종류 미정 항목에 시험 종류를 정한다 — 받는 쪽. 「무엇을 재는지」 만 있던 항목이
    이것으로 시험을 붙일 수 있게 된다. 시험이 붙은 항목의 종류는 못 바꾼다."""
    item = _resolvable(db, commission_id, user)
    row = _item_of(db, item, item_id)
    if services.linked_runs(db, [row.id]).get(row.id):
        raise AppError(
            "MNX-COMMISSIONS-0032",
            "시험이 붙은 항목의 종류는 바꿀 수 없습니다 — 먼저 시험 연결을 푸세요.",
            status=422,
        )
    test_type = services.visible_test_type(db, payload.test_type_key)
    values, input_units = conditions.normalize_conditions(
        db, test_type, dict(payload.conditions), dict(payload.condition_units)
    )
    row.test_type_id = test_type.id
    row.conditions = values
    row.input_units = input_units
    services.move(
        db,
        item,
        actor=user,
        target=None,
        note=f"{row.position + 1}번 항목의 시험 종류 결정: {test_type.label}",
    )
    db.commit()
    return _detail(db, item, user)
