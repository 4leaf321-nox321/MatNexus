"""물성 핸드북 — 절·리비전·검색·그림.

## 검색은 trigram

`body_text` 에 `pg_trgm` GIN 을 건다. 한국어는 띄어쓰기가 단어 경계가 아니라
`tsvector` 의 `simple` 사전으로는 「치수변수」 로 「치수」 를 못 찾는다. trigram 은
세 글자씩 쪼개 색인하므로 가운데 일치가 된다 — 재료 이름 검색과 같은 선택이다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.guide.models import (
    GuideAsset,
    GuideDocument,
    GuideRevision,
    GuideSection,
)
from app.shared import audit, filestore, permissions
from app.shared.errors import AppError, Conflict, Forbidden, NotFound

logger = logging.getLogger(__name__)

#: 그림으로 받는 종류. SVG 는 스크립트를 실을 수 있어 **`<img>` 로만** 보인다(라우트).
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SNIPPET_RADIUS = 60


def _now() -> datetime:
    return datetime.now(UTC)


# --- 권한 -----------------------------------------------------------------------


def is_reviewer(db: Session, user: User) -> bool:
    """검토자 — 부서 관리자 이상. 재료·프로파일을 만드는 역할과 같다."""
    return user.is_system_admin or permissions.is_any_manager(db, user)


def require_reviewer(db: Session, user: User) -> None:
    if not is_reviewer(db, user):
        raise Forbidden("MNX-GUIDE-0005", "검토자(부서 관리자 이상)만 할 수 있습니다.")


# --- 본문 -----------------------------------------------------------------------


def plain_text(body: dict[str, Any]) -> str:
    """편집기 문서에서 글자만 뽑는다. 검색과 요약이 쓴다."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
            node_type = node.get("type")
            for child in node.get("content", []) or []:
                walk(child)
            # 문단이 끝나면 띄운다 — 안 띄우면 앞 문단 끝과 뒤 문단 첫 글자가 붙어
            # 없는 단어가 검색에 걸린다.
            if node_type in ("paragraph", "heading", "tableCell", "tableHeader", "listItem"):
                parts.append(" ")
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(body)
    return " ".join("".join(parts).split())


def outline(body: dict[str, Any]) -> list[dict[str, Any]]:
    """절 안의 제목들. 오른쪽 목차가 쓴다."""
    found: list[dict[str, Any]] = []
    for node in body.get("content", []) or []:
        if isinstance(node, dict) and node.get("type") == "heading":
            level = int((node.get("attrs") or {}).get("level", 2))
            found.append({"level": level, "text": plain_text(node)})
    return found


# --- 문서 -----------------------------------------------------------------------


def get_document(db: Session, key: str) -> GuideDocument:
    row = db.scalar(
        select(GuideDocument).where(
            GuideDocument.key == key, GuideDocument.deleted_at.is_(None)
        )
    )
    if row is None:
        raise NotFound("MNX-GUIDE-0001", f"문서가 없습니다: {key}")
    return row


def list_documents(db: Session) -> list[GuideDocument]:
    return list(
        db.scalars(
            select(GuideDocument)
            .where(GuideDocument.deleted_at.is_(None))
            .order_by(GuideDocument.kind, GuideDocument.position, GuideDocument.title)
        )
    )


def create_document(db: Session, user: User | None, **fields: Any) -> GuideDocument:
    key = str(fields["key"])
    if db.scalar(select(GuideDocument.id).where(GuideDocument.key == key)) is not None:
        raise Conflict("MNX-GUIDE-0006", f"같은 키의 문서가 이미 있습니다: {key}")
    row = GuideDocument(created_by_id=user.id if user else None, **fields)
    db.add(row)
    db.flush()
    return row


# --- 절 -------------------------------------------------------------------------


def get_section(db: Session, section_id: uuid.UUID) -> GuideSection:
    row = db.get(GuideSection, section_id)
    if row is None or row.deleted_at is not None:
        raise NotFound("MNX-GUIDE-0002", "절이 없습니다.")
    return row


def sections_of(db: Session, document_ids: list[uuid.UUID]) -> list[GuideSection]:
    if not document_ids:
        return []
    return list(
        db.scalars(
            select(GuideSection)
            .where(
                GuideSection.document_id.in_(document_ids), GuideSection.deleted_at.is_(None)
            )
            .order_by(GuideSection.position, GuideSection.title)
        )
    )


def pending_counts(db: Session, section_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not section_ids:
        return {}
    rows = db.execute(
        select(GuideRevision.section_id, func.count())
        .where(GuideRevision.section_id.in_(section_ids), GuideRevision.status == "pending")
        .group_by(GuideRevision.section_id)
    )
    return {section_id: int(count) for section_id, count in rows}


def create_section(
    db: Session,
    document: GuideDocument,
    *,
    user: User | None,
    key: str,
    title: str,
    position: int,
    body: dict[str, Any] | None,
) -> GuideSection:
    taken = db.scalar(
        select(GuideSection.id).where(
            GuideSection.document_id == document.id, GuideSection.key == key
        )
    )
    if taken is not None:
        raise Conflict("MNX-GUIDE-0006", f"이 문서에 같은 키의 절이 이미 있습니다: {key}")
    content = body or {"type": "doc", "content": []}
    row = GuideSection(
        document_id=document.id,
        key=key,
        title=title,
        position=position,
        body=content,
        body_text=plain_text(content),
        revision_no=1 if body else 0,
        updated_by_id=user.id if user else None,
    )
    db.add(row)
    db.flush()
    if body:
        # 처음 본문도 리비전으로 남긴다 — 「누가 언제 무엇을」 이 첫 판부터 있어야 한다.
        db.add(
            GuideRevision(
                section_id=row.id,
                status="approved",
                body=content,
                body_text=row.body_text,
                note="처음",
                author_id=user.id if user else None,
                reviewed_by_id=user.id if user else None,
                reviewed_at=_now(),
            )
        )
    return row


# --- 리비전 --------------------------------------------------------------------


def get_revision(db: Session, revision_id: uuid.UUID) -> GuideRevision:
    row = db.get(GuideRevision, revision_id)
    if row is None:
        raise NotFound("MNX-GUIDE-0003", "리비전이 없습니다.")
    return row


def submit_revision(
    db: Session,
    section: GuideSection,
    *,
    user: User,
    body: dict[str, Any],
    note: str | None,
    publish: bool,
) -> GuideRevision:
    """초안을 낸다. **누구나.** `publish` 는 검토자만 — 자기 것을 바로 승인한다."""
    if publish:
        require_reviewer(db, user)
    row = GuideRevision(
        section_id=section.id,
        status="pending",
        body=body,
        body_text=plain_text(body),
        note=note,
        author_id=user.id,
    )
    db.add(row)
    db.flush()
    if publish:
        approve(db, row, user=user, note=None)
    return row


def approve(db: Session, revision: GuideRevision, *, user: User, note: str | None) -> None:
    """승인 — 이 리비전이 절의 본문이 된다. 같은 절의 다른 대기 초안은 그대로 둔다
    — 남의 초안을 말없이 버리지 않는다. 검토자가 보고 거절한다."""
    require_reviewer(db, user)
    if revision.status != "pending":
        raise AppError(
            "MNX-GUIDE-0004", f"이미 {revision.status} 된 리비전입니다.", status=409
        )
    section = get_section(db, revision.section_id)
    section.body = revision.body
    section.body_text = revision.body_text
    section.revision_no += 1
    section.updated_by_id = revision.author_id
    revision.status = "approved"
    revision.reviewed_by_id = user.id
    revision.reviewed_at = _now()
    revision.review_note = note
    audit.record(
        db,
        action="guide.revision.approve",
        actor=user,
        target_table="guide_sections",
        target_id=section.id,
        target_label=section.title,
        changes={"revision_id": str(revision.id), "revision_no": section.revision_no},
        reason=note,
    )


def reject(db: Session, revision: GuideRevision, *, user: User, note: str | None) -> None:
    require_reviewer(db, user)
    if revision.status != "pending":
        raise AppError(
            "MNX-GUIDE-0004", f"이미 {revision.status} 된 리비전입니다.", status=409
        )
    revision.status = "rejected"
    revision.reviewed_by_id = user.id
    revision.reviewed_at = _now()
    revision.review_note = note


# --- 검색 -----------------------------------------------------------------------


def snippet(text: str, needle: str) -> str:
    """맞은 자리 앞뒤 한 줄."""
    lower = text.lower()
    at = lower.find(needle.lower())
    if at < 0:
        return text[: SNIPPET_RADIUS * 2] + ("…" if len(text) > SNIPPET_RADIUS * 2 else "")
    start = max(0, at - SNIPPET_RADIUS)
    end = min(len(text), at + len(needle) + SNIPPET_RADIUS)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


def search(
    db: Session, query: str, *, limit: int = 30
) -> list[tuple[GuideSection, GuideDocument]]:
    needle = query.strip()
    if len(needle) < 2:
        return []
    pattern = f"%{needle}%"
    rows = db.execute(
        select(GuideSection, GuideDocument)
        .join(GuideDocument, GuideDocument.id == GuideSection.document_id)
        .where(
            GuideSection.deleted_at.is_(None),
            GuideDocument.deleted_at.is_(None),
            or_(GuideSection.title.ilike(pattern), GuideSection.body_text.ilike(pattern)),
        )
        # 제목에 맞은 것이 먼저 — 그것이 대개 찾던 절이다.
        .order_by(
            GuideSection.title.ilike(pattern).desc(),
            GuideDocument.position,
            GuideSection.position,
        )
        .limit(limit)
    )
    return [(section, document) for section, document in rows]


# --- 그림 -----------------------------------------------------------------------


def save_asset(
    db: Session,
    *,
    user: User | None,
    document_id: uuid.UUID | None,
    filename: str,
    content_type: str,
    stream: Any,
) -> GuideAsset:
    if content_type not in IMAGE_TYPES:
        raise AppError(
            "MNX-GUIDE-0009",
            f"그림 파일만 올릴 수 있습니다 ({', '.join(sorted(IMAGE_TYPES))}).",
            status=415,
        )
    asset_id = uuid.uuid4()
    safe = filestore.sanitize_filename(filename) or f"image{IMAGE_TYPES[content_type]}"
    stored = filestore.save_stream(
        stream, relative_dir=f"guide/{asset_id}", filename=safe, max_bytes=MAX_IMAGE_BYTES
    )
    row = GuideAsset(
        id=asset_id,
        document_id=document_id,
        filename=safe,
        content_type=content_type,
        size=stored.size,
        sha256=stored.sha256,
        path=stored.relative_path,
        created_by_id=user.id if user else None,
    )
    db.add(row)
    db.flush()
    return row


def get_asset(db: Session, asset_id: uuid.UUID) -> GuideAsset:
    row = db.get(GuideAsset, asset_id)
    if row is None:
        raise NotFound("MNX-GUIDE-0008", "그림이 없습니다.")
    return row


def asset_url(asset_id: uuid.UUID) -> str:
    return f"/api/guide/assets/{asset_id}"
