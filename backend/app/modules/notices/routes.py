"""공지 라우터.

읽기는 로그인한 모두, 쓰기는 시스템 관리자. 모듈이 작아 서비스 파일을 따로 두지
않고 여기서 끝낸다 — 나중에 로직이 붙으면 그때 나눈다(CLAUDE.md: 기존 배치가
규칙과 어긋나면 스코프 안에서 바로잡는다).

## 카드 더미에서 게시판으로 (2026-09-24)

목록이 본문까지 통째로 한 번에 나갔고, 화면은 그것을 카드로 쌓았다. 공지가 늘면
찾을 길이 없었다 — VOC 는 이미 게시판이라(번호·검색·쪽 넘기기·한 건 상세) 한 진입점
안의 두 게시판이 서로 다르게 굴었다. 이제 목록은 쪽으로 나가고(`Page`) 제목·내용으로
찾으며, 한 건은 `GET /notices/{id}` 로 연다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.notices.models import Notice, NoticeRead
from app.modules.notices.schemas import NoticeCreateRequest, NoticeOut, NoticeUpdateRequest
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import NotFound
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/notices", tags=["notices"])


def _out(notice: Notice, *, read: bool, names: dict[uuid.UUID, str]) -> NoticeOut:
    return NoticeOut(
        id=notice.id,
        title=notice.title,
        body=notice.body,
        is_published=notice.is_published,
        is_popup=notice.is_popup,
        created_at=notice.created_at,
        published_at=notice.published_at,
        is_read=read,
        created_by=names.get(notice.created_by_id) if notice.created_by_id else None,
        from_release=notice.seed_key is not None,
    )


def _names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """쓴 사람의 표시 이름 — **한 번에 묶어 읽는다**(줄마다 물으면 N+1 이다)."""
    wanted = {one for one in ids if one is not None}
    if not wanted:
        return {}
    return {
        user_id: display or email
        for user_id, display, email in db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(wanted))
        )
    }


def _read_ids(db: Session, user: User) -> set[uuid.UUID]:
    return set(
        db.scalars(select(NoticeRead.notice_id).where(NoticeRead.user_id == user.id)).all()
    )


def _visible(db: Session, notice_id: uuid.UUID, user: User) -> Notice:
    """볼 수 있는 공지 하나. **초안은 시스템 관리자만** — 목록과 같은 규칙이다. 남에게는
    없는 것과 같다(주소를 알아도 못 연다)."""
    notice = db.get(Notice, notice_id)
    if notice is None or (not notice.is_published and not user.is_system_admin):
        raise NotFound("MNX-NOTICES-0001", "공지를 찾을 수 없습니다.")
    return notice


@router.get("", response_model=Page[NoticeOut])
def list_notices(
    q: str | None = Query(default=None, max_length=200),
    unread: bool = Query(default=False),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[NoticeOut]:
    """게시판. **최근에 알린 것이 위다** — 발행 시각, 초안은 만든 시각.

    만든 시각으로만 세우면 배포가 초안으로 넣어 둔 안내(`seeds/notices`)를 며칠 뒤에
    발행했을 때 아래로 묻힌다 — 사람에게는 방금 알린 글이다.
    """
    query = select(Notice)
    if not user.is_system_admin:
        # 초안은 쓴 사람만 본다.
        query = query.where(Notice.is_published.is_(True))
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(Notice.title.ilike(needle), Notice.body.ilike(needle)))
    if unread:
        query = query.where(
            ~exists().where(NoticeRead.notice_id == Notice.id, NoticeRead.user_id == user.id)
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    rows = list(
        db.scalars(
            query.order_by(
                func.coalesce(Notice.published_at, Notice.created_at).desc(),
                Notice.created_at.desc(),
            )
            .limit(size)
            .offset(offset)
        )
    )
    read = _read_ids(db, user)
    names = _names(db, (one.created_by_id for one in rows))
    return Page(
        items=[_out(one, read=one.id in read, names=names) for one in rows],
        total=int(total),
        limit=size,
        offset=offset,
    )


@router.get("/popup", response_model=list[NoticeOut])
def popup_notices(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[NoticeOut]:
    """로그인 후 한 번 띄울 공지. 읽은 것은 빠진다."""
    read = _read_ids(db, user)
    query = (
        select(Notice)
        .where(Notice.is_published.is_(True), Notice.is_popup.is_(True))
        .order_by(Notice.published_at.desc())
    )
    rows = [n for n in db.scalars(query) if n.id not in read]
    names = _names(db, (one.created_by_id for one in rows))
    return [_out(n, read=False, names=names) for n in rows]


@router.get("/{notice_id}", response_model=NoticeOut)
def get_notice(
    notice_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> NoticeOut:
    """한 건. **읽음 표시는 따로다**(`POST …/read`) — 여는 것만으로 표시하면 목록을 미리
    불러 두는 화면이나 스크립트가 남의 읽음을 대신 찍는다."""
    notice = _visible(db, notice_id, user)
    read = notice.id in _read_ids(db, user)
    return _out(notice, read=read, names=_names(db, [notice.created_by_id]))


@router.post("", response_model=NoticeOut, status_code=201)
def create_notice(
    payload: NoticeCreateRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> NoticeOut:
    notice = Notice(
        title=payload.title,
        body=payload.body,
        is_popup=payload.is_popup,
        is_published=payload.is_published,
        published_at=datetime.now(UTC) if payload.is_published else None,
        created_by_id=admin.id,
    )
    db.add(notice)
    db.commit()
    return _out(notice, read=False, names=_names(db, [notice.created_by_id]))


@router.patch("/{notice_id}", response_model=NoticeOut)
def update_notice(
    notice_id: uuid.UUID,
    payload: NoticeUpdateRequest,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> NoticeOut:
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise NotFound("MNX-NOTICES-0001", "공지를 찾을 수 없습니다.")

    if payload.title is not None:
        notice.title = payload.title
    if payload.body is not None:
        notice.body = payload.body
    if payload.is_popup is not None:
        notice.is_popup = payload.is_popup
    if payload.is_published is not None and payload.is_published != notice.is_published:
        notice.is_published = payload.is_published
        # 발행 시각은 처음 발행할 때만 찍는다 — 수정할 때마다 갱신하면
        # "언제 알려졌는가"를 잃는다.
        if payload.is_published and notice.published_at is None:
            notice.published_at = datetime.now(UTC)

    db.commit()
    return _out(notice, read=False, names=_names(db, [notice.created_by_id]))


@router.delete("/{notice_id}", status_code=204)
def delete_notice(
    notice_id: uuid.UUID,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> None:
    """**행을 없앤다.** 읽음 기록은 FK 가 CASCADE 로 함께 지운다.

    「내리기」 와 다른 일이다 — 잘못 올린 것을 잠깐 감추려면 발행을 끄면 되고
    (`PATCH is_published`), 그때 내용과 발행 시각은 남는다. 삭제는 그 공지가
    있었다는 사실까지 없애는 것이라 화면이 먼저 묻는다.
    """
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise NotFound("MNX-NOTICES-0001", "공지를 찾을 수 없습니다.")
    db.delete(notice)
    db.commit()


@router.post("/{notice_id}/read", status_code=204)
def mark_read(
    notice_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    _visible(db, notice_id, user)
    exists_row = db.scalar(
        select(NoticeRead).where(
            NoticeRead.notice_id == notice_id, NoticeRead.user_id == user.id
        )
    )
    if exists_row is None:
        db.add(NoticeRead(notice_id=notice_id, user_id=user.id))
        db.commit()
