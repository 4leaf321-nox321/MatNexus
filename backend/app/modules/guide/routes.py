"""물성 핸드북 API.

읽기는 로그인한 누구나. 초안(리비전)도 누구나 낸다. **구조(문서·절)를 만들고,
초안을 승인하는 것은 검토자**(부서 관리자 이상)다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.guide import services
from app.modules.guide.models import GuideDocument, GuideRevision, GuideSection
from app.modules.guide.schemas import (
    AssetOut,
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    Person,
    ReviewIn,
    RevisionCreate,
    RevisionOut,
    SearchHit,
    SectionBrief,
    SectionCreate,
    SectionOut,
    SectionUpdate,
)
from app.shared import filestore
from app.shared.auth import current_user
from app.shared.errors import AppError

router = APIRouter(prefix="/guide", tags=["guide"])


# --- 보조 -----------------------------------------------------------------------


def _people(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, Person]:
    wanted = {one for one in ids if one is not None}
    if not wanted:
        return {}
    return {
        u.id: Person(id=u.id, name=u.display_name or u.email)
        for u in db.scalars(select(User).where(User.id.in_(wanted)))
    }


def _brief(section: GuideSection, pending: dict[uuid.UUID, int]) -> SectionBrief:
    return SectionBrief(
        id=section.id,
        key=section.key,
        title=section.title,
        position=section.position,
        revision_no=section.revision_no,
        pending_count=pending.get(section.id, 0),
        updated_at=section.updated_at,
    )


def _document_out(db: Session, document: GuideDocument) -> DocumentOut:
    sections = services.sections_of(db, [document.id])
    pending = services.pending_counts(db, [s.id for s in sections])
    return DocumentOut(
        id=document.id,
        key=document.key,
        title=document.title,
        kind=document.kind,
        topic=document.topic,
        summary=document.summary,
        position=document.position,
        source_filename=document.source_filename,
        updated_at=document.updated_at,
        sections=[_brief(s, pending) for s in sections],
    )


def _section_out(db: Session, section: GuideSection) -> SectionOut:
    document = db.get(GuideDocument, section.document_id)
    pending = services.pending_counts(db, [section.id])
    people = _people(db, {section.updated_by_id})
    return SectionOut(
        **_brief(section, pending).model_dump(),
        document_id=section.document_id,
        document_key=document.key if document else "?",
        document_title=document.title if document else "?",
        body=section.body,
        updated_by=people.get(section.updated_by_id) if section.updated_by_id else None,
    )


def _revision_out(db: Session, rows: list[GuideRevision]) -> list[RevisionOut]:
    if not rows:
        return []
    sections = {
        s.id: s
        for s in db.scalars(
            select(GuideSection).where(GuideSection.id.in_({r.section_id for r in rows}))
        )
    }
    documents = {
        d.id: d
        for d in db.scalars(
            select(GuideDocument).where(
                GuideDocument.id.in_({s.document_id for s in sections.values()})
            )
        )
    }
    people = _people(db, {r.author_id for r in rows} | {r.reviewed_by_id for r in rows})
    out: list[RevisionOut] = []
    for row in rows:
        section = sections.get(row.section_id)
        document = documents.get(section.document_id) if section else None
        out.append(
            RevisionOut(
                id=row.id,
                section_id=row.section_id,
                section_key=section.key if section else "?",
                section_title=section.title if section else "?",
                document_key=document.key if document else "?",
                document_title=document.title if document else "?",
                status=row.status,
                body=row.body,
                note=row.note,
                author=people.get(row.author_id) if row.author_id else None,
                created_at=row.created_at,
                reviewed_by=people.get(row.reviewed_by_id) if row.reviewed_by_id else None,
                reviewed_at=row.reviewed_at,
                review_note=row.review_note,
            )
        )
    return out


# --- 문서 -----------------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[DocumentOut]:
    """목차 전부 — 문서와 절 제목. 본문은 안 실린다(절을 열 때 읽는다)."""
    documents = services.list_documents(db)
    sections = services.sections_of(db, [d.id for d in documents])
    pending = services.pending_counts(db, [s.id for s in sections])
    by_document: dict[uuid.UUID, list[SectionBrief]] = {}
    for section in sections:
        by_document.setdefault(section.document_id, []).append(_brief(section, pending))
    return [
        DocumentOut(
            id=d.id,
            key=d.key,
            title=d.title,
            kind=d.kind,
            topic=d.topic,
            summary=d.summary,
            position=d.position,
            source_filename=d.source_filename,
            updated_at=d.updated_at,
            sections=by_document.get(d.id, []),
        )
        for d in documents
    ]


@router.post("/documents", response_model=DocumentOut, status_code=201)
def create_document(
    body: DocumentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> DocumentOut:
    services.require_reviewer(db, user)
    row = services.create_document(db, user, **body.model_dump())
    db.commit()
    return _document_out(db, row)


@router.get("/documents/{key}", response_model=DocumentOut)
def get_document(
    key: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> DocumentOut:
    return _document_out(db, services.get_document(db, key))


@router.patch("/documents/{key}", response_model=DocumentOut)
def update_document(
    key: str,
    body: DocumentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    services.require_reviewer(db, user)
    row = services.get_document(db, key)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    return _document_out(db, row)


@router.delete("/documents/{key}", status_code=204)
def delete_document(
    key: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    """소프트 삭제. 절과 리비전은 남는다 — 되살릴 수 있어야 한다."""
    services.require_reviewer(db, user)
    row = services.get_document(db, key)
    row.deleted_at = services._now()
    db.commit()
    return Response(status_code=204)


# --- 절 -------------------------------------------------------------------------


@router.post("/documents/{key}/sections", response_model=SectionOut, status_code=201)
def create_section(
    key: str,
    body: SectionCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SectionOut:
    services.require_reviewer(db, user)
    document = services.get_document(db, key)
    row = services.create_section(
        db,
        document,
        user=user,
        key=body.key,
        title=body.title,
        position=body.position,
        body=body.body,
    )
    db.commit()
    return _section_out(db, row)


@router.get("/sections/{section_id}", response_model=SectionOut)
def get_section(
    section_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> SectionOut:
    return _section_out(db, services.get_section(db, section_id))


@router.patch("/sections/{section_id}", response_model=SectionOut)
def update_section(
    section_id: uuid.UUID,
    body: SectionUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SectionOut:
    services.require_reviewer(db, user)
    row = services.get_section(db, section_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    return _section_out(db, row)


@router.delete("/sections/{section_id}", status_code=204)
def delete_section(
    section_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    services.require_reviewer(db, user)
    row = services.get_section(db, section_id)
    row.deleted_at = services._now()
    db.commit()
    return Response(status_code=204)


# --- 리비전 --------------------------------------------------------------------


@router.post("/sections/{section_id}/revisions", response_model=RevisionOut, status_code=201)
def submit_revision(
    section_id: uuid.UUID,
    body: RevisionCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RevisionOut:
    """초안을 낸다 — 누구나. 검토자는 `publish` 로 바로 승인할 수 있다."""
    section = services.get_section(db, section_id)
    row = services.submit_revision(
        db, section, user=user, body=body.body, note=body.note, publish=body.publish
    )
    db.commit()
    return _revision_out(db, [row])[0]


@router.get("/sections/{section_id}/revisions", response_model=list[RevisionOut])
def list_section_revisions(
    section_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[RevisionOut]:
    services.get_section(db, section_id)
    rows = list(
        db.scalars(
            select(GuideRevision)
            .where(GuideRevision.section_id == section_id)
            .order_by(GuideRevision.created_at.desc())
            .limit(50)
        )
    )
    return _revision_out(db, rows)


@router.get("/revisions", response_model=list[RevisionOut])
def list_revisions(
    status: str = Query(default="pending"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[RevisionOut]:
    """검토 대기열. 검토자가 본다 — 초안을 낸 사람은 자기 절에서 본다."""
    rows = list(
        db.scalars(
            select(GuideRevision)
            .where(GuideRevision.status == status)
            .order_by(GuideRevision.created_at.asc())
            .limit(200)
        )
    )
    return _revision_out(db, rows)


@router.post("/revisions/{revision_id}/approve", response_model=RevisionOut)
def approve_revision(
    revision_id: uuid.UUID,
    body: ReviewIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RevisionOut:
    row = services.get_revision(db, revision_id)
    services.approve(db, row, user=user, note=body.note)
    db.commit()
    return _revision_out(db, [row])[0]


@router.post("/revisions/{revision_id}/reject", response_model=RevisionOut)
def reject_revision(
    revision_id: uuid.UUID,
    body: ReviewIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RevisionOut:
    row = services.get_revision(db, revision_id)
    services.reject(db, row, user=user, note=body.note)
    db.commit()
    return _revision_out(db, [row])[0]


# --- 검색 -----------------------------------------------------------------------


@router.get("/search", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=1, max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SearchHit]:
    return [
        SearchHit(
            section_id=section.id,
            document_key=document.key,
            document_title=document.title,
            kind=document.kind,
            topic=document.topic,
            section_key=section.key,
            section_title=section.title,
            snippet=services.snippet(section.body_text, q),
        )
        for section, document in services.search(db, q)
    ]


# --- 그림 -----------------------------------------------------------------------


@router.post("/assets", response_model=AssetOut, status_code=201)
def upload_asset(
    file: UploadFile = File(...),
    document_key: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    """그림을 올린다 — 편집기에 붙여 넣는 순간 부른다. 본문에는 주소만 들어간다."""
    document_id = services.get_document(db, document_key).id if document_key else None
    row = services.save_asset(
        db,
        user=user,
        document_id=document_id,
        filename=file.filename or "image",
        content_type=(file.content_type or "").split(";")[0].strip().lower(),
        stream=file.file,
    )
    db.commit()
    return AssetOut(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        url=services.asset_url(row.id),
    )


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Any:
    row = services.get_asset(db, asset_id)
    path = filestore.resolve(row.path)
    if not path.is_file():
        raise AppError("MNX-GUIDE-0008", "그림 파일이 저장소에 없습니다.", status=404)
    # SVG 는 스크립트를 실을 수 있다. 첨부로 내려 `<img>` 로만 그려지게 한다 —
    # 문서로 열리면 그 안의 스크립트가 이 사이트의 권한으로 돈다.
    return FileResponse(
        path,
        media_type=row.content_type,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; script-src 'none'",
        },
    )
