"""VOC 라우터 — 게시판이고 절차다.

접수는 누구나(로그인한 사람). **목록도 누구나 본다** — 게시판이다. 같은 문제를
여럿이 따로 내고 무엇이 고쳐졌는지 낸 사람만 아는 것을 막는다(2026-09-11).
상태를 옮기는 것은 관리자와 낸 사람이 각자 갈 수 있는 곳만(`models.ADMIN_MOVES` ·
`AUTHOR_MOVES`), 말을 보태는 것은 누구나.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.voc.models import (
    ADMIN_MOVES,
    AUTHOR_MOVES,
    NOTE_REQUIRED,
    VOC_STATUS_LABELS,
    VOC_STATUSES,
    VocEvent,
    VocItem,
)
from app.modules.voc.schemas import (
    VocCreateRequest,
    VocDetailOut,
    VocEventOut,
    VocEventRequest,
    VocOut,
    VocStatusOut,
    VocUpdateRequest,
)
from app.shared.auth import current_user
from app.shared.errors import AppError, Forbidden, NotFound
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/voc", tags=["voc"])

#: 옮기는 단추에 적을 말. 상태 이름만 적으면 「해결」 이 지금 상태인지 갈 곳인지
#: 안 갈린다.
MOVE_LABELS: dict[str, str] = {
    "open": "다시 열기",
    "accepted": "접수",
    "in_progress": "처리 시작",
    "resolved": "해결로 옮김",
    "closed": "확인하고 종료",
    "rejected": "반려",
}


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """이름을 **한 번에** 읽는다. 줄마다 `db.get` 하면 목록이 N+1 이다."""
    wanted = {one for one in ids if one is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(wanted))).all()
    return {row.id: row.display_name for row in rows}


def _others_spoke(db: Session, item: VocItem) -> bool:
    """낸 사람 아닌 누군가가 이 건에 말을 남겼는가."""
    return (
        db.scalar(
            select(func.count())
            .select_from(VocEvent)
            .where(VocEvent.item_id == item.id, VocEvent.by_id != item.created_by_id)
        )
        or 0
    ) > 0


def _editable(db: Session, item: VocItem, user: User) -> bool:
    """고치거나 지울 수 있는가.

    **낸 사람은 남이 말을 남기기 전까지, 관리자는 언제나.** 남의 말이 달린 뒤에
    본문이 바뀌면 그 말이 딴 소리가 된다 — 읽는 사람은 엉뚱한 답을 한 것으로 본다.
    그때는 고치는 대신 말을 보태는 것이 맞다.
    """
    if user.is_system_admin:
        return True
    if item.created_by_id != user.id:
        return False
    return not _others_spoke(db, item)


def _moves(item: VocItem, user: User) -> list[str]:
    """이 사람이 지금 옮길 수 있는 상태. 관리자면 관리자 것에 낸 사람 것을 더한다."""
    allowed: list[str] = []
    if user.is_system_admin:
        allowed.extend(ADMIN_MOVES.get(item.status, ()))
    if item.created_by_id == user.id:
        allowed.extend(one for one in AUTHOR_MOVES.get(item.status, ()) if one not in allowed)
    return allowed


def _out(
    item: VocItem,
    *,
    viewer: User,
    names: dict[uuid.UUID, str],
    editable: bool,
    event_count: int,
) -> VocOut:
    return VocOut(
        id=item.id,
        seq=item.seq,
        title=item.title,
        status=item.status,
        status_label=VOC_STATUS_LABELS.get(item.status, item.status),
        page_path=item.page_path,
        created_at=item.created_at,
        created_by=names.get(item.created_by_id) if item.created_by_id else None,
        status_at=item.status_at,
        status_by=names.get(item.status_by_id) if item.status_by_id else None,
        is_mine=item.created_by_id == viewer.id,
        can_edit=editable,
        event_count=event_count,
    )


def _detail(db: Session, item: VocItem, viewer: User) -> VocDetailOut:
    events = list(
        db.scalars(
            select(VocEvent)
            .where(VocEvent.item_id == item.id)
            .order_by(VocEvent.at, VocEvent.id)
        )
    )
    names = _names(db, {item.created_by_id, item.status_by_id, *(one.by_id for one in events)})
    allowed = _moves(item, viewer)
    head = _out(
        item,
        viewer=viewer,
        names=names,
        editable=_editable(db, item, viewer),
        # 등록 이벤트는 빼고 센다 — 「말이 오간 건」 을 세는 수다.
        event_count=max(len(events) - 1, 0),
    )
    return VocDetailOut(
        **head.model_dump(),
        body=item.body,
        events=[
            VocEventOut(
                id=one.id,
                at=one.at,
                by=names.get(one.by_id) if one.by_id else None,
                from_status=one.from_status,
                to_status=one.to_status,
                to_status_label=VOC_STATUS_LABELS.get(one.to_status, one.to_status),
                note=one.note,
            )
            for one in events
        ],
        allowed=allowed,
        can_delete_events=bool(viewer.is_system_admin),
        allowed_labels={one: MOVE_LABELS.get(one, one) for one in allowed},
        note_required=[one for one in allowed if one in NOTE_REQUIRED],
    )


def _get(db: Session, item_id: uuid.UUID) -> VocItem:
    item = db.get(VocItem, item_id)
    if item is None:
        raise NotFound("MNX-VOC-0001", "접수 내역을 찾을 수 없습니다.")
    return item


@router.post("", response_model=VocDetailOut, status_code=201)
def create_item(
    payload: VocCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    now = datetime.now(UTC)
    item = VocItem(
        title=payload.title,
        body=payload.body,
        page_path=payload.page_path,
        created_by_id=user.id,
        status="open",
        status_at=now,
        status_by_id=user.id,
    )
    db.add(item)
    db.flush()
    # **등록도 이벤트다.** 이력의 첫 줄이 「누가 언제 냈다」 여야 절차가 처음부터 읽힌다.
    db.add(
        VocEvent(item_id=item.id, at=now, by_id=user.id, from_status=None, to_status="open")
    )
    # 관리자에게 — 알림 모듈을 직접 부르지 않고 큐에 던진다(모듈 경계).
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "voc.registered",
            "key": f"voc:{item.id}:registered",
            "title": f"새 VOC #{item.seq}: {item.title}",
            "body": f"{user.display_name} 님이 {item.page_path or '어디선가'} 에서 냈습니다.",
            "link": f"/voc/{item.id}",
            "to_user_id": None,
        },
    )
    db.commit()
    return _detail(db, item, user)


def _notify_changed(
    db: Session,
    item: VocItem,
    event: VocEvent,
    actor: User,
    previous_handler: uuid.UUID | None,
) -> None:
    """이 건이 움직였다고 **상대에게** 알린다.

    남이 움직이면 낸 사람에게, 낸 사람이 움직이면 마지막으로 다룬 관리자에게 —
    자기가 한 일을 자기에게 알리지 않는다. 받을 사람이 없으면 조용히 넘어간다.
    """
    if actor.id != item.created_by_id:
        to_user = item.created_by_id
    elif previous_handler is not None and previous_handler != item.created_by_id:
        to_user = previous_handler
    else:
        return
    moved = event.from_status != event.to_status
    what = (
        f"{VOC_STATUS_LABELS[event.from_status or event.to_status]} → "
        f"{VOC_STATUS_LABELS[event.to_status]}"
        if moved
        else "말을 보탰습니다"
    )
    queue.enqueue(
        db,
        kind=kinds.NOTIFY_DELIVER,
        payload={
            "event_kind": "voc.changed",
            "key": f"voc:{item.id}:{event.id}",
            "title": f"VOC #{item.seq} {what}",
            "body": f"{actor.display_name}: {event.note}"
            if event.note
            else actor.display_name,
            "link": f"/voc/{item.id}",
            "to_user_id": str(to_user),
        },
    )


@router.get("/statuses", response_model=list[VocStatusOut])
def list_statuses(user: User = Depends(current_user)) -> list[VocStatusOut]:
    """상태의 차례와 이름. **화면이 표를 갖지 않는다** — 거르개 칩이 이것으로 선다."""
    return [VocStatusOut(key=one, label=VOC_STATUS_LABELS[one]) for one in VOC_STATUSES]


@router.get("", response_model=Page[VocOut])
def list_items(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    mine: bool = Query(default=False),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[VocOut]:
    """게시판. **누구나 전부 본다** — 최신이 위다."""
    query = select(VocItem)
    if status:
        if status not in VOC_STATUSES:
            raise AppError("MNX-VOC-0002", "허용되지 않는 상태입니다.", status=422)
        query = query.where(VocItem.status == status)
    if mine:
        query = query.where(VocItem.created_by_id == user.id)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(VocItem.title.ilike(needle), VocItem.body.ilike(needle)))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    items = list(db.scalars(query.order_by(VocItem.seq.desc()).limit(size).offset(offset)))
    ids = [one.id for one in items]
    names = _names(
        db, {one.created_by_id for one in items} | {one.status_by_id for one in items}
    )
    # 건마다 세지 않는다 — 한 번에 묶어 센다.
    counts: dict[uuid.UUID, int] = {}
    spoken: set[uuid.UUID] = set()
    if ids:
        for item_id, count in db.execute(
            select(VocEvent.item_id, func.count())
            .where(VocEvent.item_id.in_(ids))
            .group_by(VocEvent.item_id)
        ).all():
            counts[item_id] = int(count)
        by_item = {one.id: one.created_by_id for one in items}
        for item_id, by_id in db.execute(
            select(VocEvent.item_id, VocEvent.by_id)
            .where(VocEvent.item_id.in_(ids))
            .distinct()
        ).all():
            if by_id != by_item.get(item_id):
                spoken.add(item_id)

    return Page(
        items=[
            _out(
                one,
                viewer=user,
                names=names,
                editable=user.is_system_admin
                or (one.created_by_id == user.id and one.id not in spoken),
                event_count=max(counts.get(one.id, 0) - 1, 0),
            )
            for one in items
        ],
        total=int(total),
        limit=size,
        offset=offset,
    )


@router.get("/{item_id}", response_model=VocDetailOut)
def get_item(
    item_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    return _detail(db, _get(db, item_id), user)


def _mine(db: Session, item_id: uuid.UUID, user: User) -> VocItem:
    """고치거나 지울 수 있는 것만 돌려준다. 규칙은 `_editable` 과 같다 — 화면은
    단추를 감출 뿐이고, 주소를 아는 사람은 여기서 막힌다."""
    item = _get(db, item_id)
    if user.is_system_admin:
        return item
    if item.created_by_id != user.id:
        raise Forbidden("MNX-VOC-0003", "자기가 낸 것만 고치거나 지울 수 있습니다.")
    if _others_spoke(db, item):
        raise Forbidden(
            "MNX-VOC-0004",
            "남이 말을 남긴 뒤에는 고칠 수 없습니다. 덧붙일 말이 있으면 아래에 남겨 주세요.",
        )
    return item


@router.patch("/{item_id}", response_model=VocDetailOut)
def update_item(
    item_id: uuid.UUID,
    payload: VocUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    item = _mine(db, item_id, user)
    # **안 보낸 것과 비운 것을 가른다.** 안 가르면 제목만 고치는 요청이 본문을
    # 지운다(AGENTS.md).
    if payload.title is not None:
        item.title = payload.title
    if payload.body is not None:
        item.body = payload.body
    db.commit()
    return _detail(db, item, user)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """**행을 없앤다.** 이력도 함께 간다(CASCADE) — 화면이 먼저 묻는다."""
    db.delete(_mine(db, item_id, user))
    db.commit()


@router.delete("/{item_id}/events/{event_id}", response_model=VocDetailOut)
def delete_event(
    item_id: uuid.UUID,
    event_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """이력 한 줄을 지운다 — **시스템 관리자만.**

    「해결」 로 옮겼다가 「처리 중」 으로 되돌리는 실수가 나는데, 그 줄을 지울 길이
    없었다(VOC 2026-09-13). 지우면 **상태는 남은 이력에서 다시 정한다** — 마지막으로
    상태를 옮긴 줄이 곧 지금 상태다. 등록 줄은 못 지운다: 그것이 건의 시작이다.
    """
    if not user.is_system_admin:
        raise Forbidden("MNX-VOC-0008", "이력은 시스템 관리자만 지울 수 있습니다.")
    item = _get(db, item_id)
    event = db.get(VocEvent, event_id)
    if event is None or event.item_id != item.id:
        raise NotFound("MNX-VOC-0009", "그 이력이 없습니다.")
    if event.from_status is None:
        raise AppError(
            "MNX-VOC-0010",
            "등록 줄은 지울 수 없습니다 — 건 자체를 지우려면 접수 내역을 지우세요.",
            status=422,
        )
    db.delete(event)
    db.flush()

    # 남은 이력에서 상태를 다시 정한다. 댓글(from == to)은 상태를 안 바꾼다.
    remaining = list(
        db.scalars(
            select(VocEvent)
            .where(VocEvent.item_id == item.id)
            .order_by(VocEvent.at.desc(), VocEvent.id.desc())
        )
    )
    last_move = next(
        (
            one
            for one in remaining
            if one.from_status is None or one.from_status != one.to_status
        ),
        None,
    )
    if last_move is not None:
        item.status = last_move.to_status
        item.status_at = last_move.at
        item.status_by_id = last_move.by_id
    db.commit()
    return _detail(db, item, user)


@router.post("/{item_id}/events", response_model=VocDetailOut)
def add_event(
    item_id: uuid.UUID,
    payload: VocEventRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VocDetailOut:
    """상태를 옮기거나 말을 보탠다.

    **갈 수 있는 곳만 간다.** 관리자는 `ADMIN_MOVES`, 낸 사람은 `AUTHOR_MOVES` —
    「해결됐다」 는 관리자가 말하고 「됐다」 는 낸 사람이 확인한다. 말만 보태는 것은
    보는 사람 누구나 할 수 있다.
    """
    item = _get(db, item_id)
    note = (payload.note or "").strip() or None
    target = payload.status

    if target is not None:
        if target not in VOC_STATUSES:
            raise AppError("MNX-VOC-0002", "허용되지 않는 상태입니다.", status=422)
        if target == item.status:
            raise AppError(
                "MNX-VOC-0005",
                f"이미 '{VOC_STATUS_LABELS[target]}' 상태입니다. "
                "말만 보태려면 상태를 비우세요.",
                status=422,
            )
        allowed = _moves(item, user)
        if target not in allowed:
            raise Forbidden(
                "MNX-VOC-0006",
                f"'{VOC_STATUS_LABELS[item.status]}' 에서 '{VOC_STATUS_LABELS[target]}' 로 "
                "옮길 수 없습니다"
                + (
                    " — 지금 갈 수 있는 곳: "
                    + ", ".join(VOC_STATUS_LABELS[one] for one in allowed)
                    + "."
                    if allowed
                    else "."
                ),
            )
        if target in NOTE_REQUIRED and note is None:
            raise AppError(
                "MNX-VOC-0007",
                f"'{VOC_STATUS_LABELS[target]}' 로 옮길 때는 말을 적어야 합니다 — "
                "무엇을 했는지, 왜인지 없으면 읽는 사람이 되물어야 합니다.",
                status=422,
            )

    now = datetime.now(UTC)
    previous_handler = item.status_by_id
    event = VocEvent(
        item_id=item.id,
        at=now,
        by_id=user.id,
        from_status=item.status,
        to_status=target or item.status,
        note=note,
    )
    db.add(event)
    db.flush()
    if target is not None:
        item.status = target
        item.status_at = now
        item.status_by_id = user.id
    _notify_changed(db, item, event, user, previous_handler)
    db.commit()
    return _detail(db, item, user)
