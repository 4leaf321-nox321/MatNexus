"""공지 라우터.

읽기는 로그인한 모두, 쓰기는 시스템 관리자. 모듈이 작아 서비스 파일을 따로 두지
않고 여기서 끝낸다 — 나중에 로직이 붙으면 그때 나눈다(CLAUDE.md: 기존 배치가
규칙과 어긋나면 스코프 안에서 바로잡는다).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.notices.models import Notice, NoticeRead
from app.modules.notices.schemas import NoticeCreateRequest, NoticeOut, NoticeUpdateRequest
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import NotFound

router = APIRouter(prefix="/notices", tags=["notices"])


def _out(notice: Notice, *, read: bool) -> NoticeOut:
    return NoticeOut(
        id=notice.id,
        title=notice.title,
        body=notice.body,
        is_published=notice.is_published,
        is_popup=notice.is_popup,
        created_at=notice.created_at,
        published_at=notice.published_at,
        is_read=read,
    )


def _read_ids(db: Session, user: User) -> set[uuid.UUID]:
    return set(
        db.scalars(select(NoticeRead.notice_id).where(NoticeRead.user_id == user.id)).all()
    )


@router.get("", response_model=list[NoticeOut])
def list_notices(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[NoticeOut]:
    query = select(Notice).order_by(Notice.created_at.desc())
    if not user.is_system_admin:
        # 초안은 쓴 사람만 본다.
        query = query.where(Notice.is_published.is_(True))
    read = _read_ids(db, user)
    return [_out(notice, read=notice.id in read) for notice in db.scalars(query)]


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
    return [_out(n, read=False) for n in db.scalars(query) if n.id not in read]


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
    return _out(notice, read=False)


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
    return _out(notice, read=False)


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
    if db.get(Notice, notice_id) is None:
        raise NotFound("MNX-NOTICES-0001", "공지를 찾을 수 없습니다.")
    exists = db.scalar(
        select(NoticeRead).where(
            NoticeRead.notice_id == notice_id, NoticeRead.user_id == user.id
        )
    )
    if exists is None:
        db.add(NoticeRead(notice_id=notice_id, user_id=user.id))
        db.commit()
