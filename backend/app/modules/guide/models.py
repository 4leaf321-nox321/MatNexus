"""물성 핸드북 — **누구나 초안을 쓰고, 검토자가 승인한다.**

## 왜 절(section)이 단위인가

원본은 문서 하나에 절이 열 개다(「DMA 에서 Prony 카드까지」 = 11절). 문서째 두면
「ASTM E8 두께 변수」 를 찾으려고 74KB 를 스크롤한다. 절이 단위면 검색 결과가 절로
떨어지고, 편집이 절 하나로 끝나고, 앱의 자리(시험 종류·시편 규격)가 절을 가리킬
수 있다.

## 정본은 편집기 문서(JSON)

사람은 리치 텍스트 편집기로 쓰고, 편집기가 내는 문서(ProseMirror JSON)를 그대로
둔다. Markdown 이 아닌 이유: 셀 병합 표·그림 캡션이 Markdown 에 없다 — 시편 치수
매트릭스가 그 모양이다. 서식은 앱이 정한 열 개 남짓만 허용한다(편집기 쪽).

검색용으로 글자만 뽑은 `body_text` 를 한 벌 더 둔다. 보는 형태와 찾는 형태가 다르다
— 곡선(Parquet)과 요약값(행)을 따로 두는 것과 같은 이유.

## 초안 → 승인

절의 `body` 는 **승인된 것**이다. 고치려면 리비전을 만든다(누구나). 검토자(부서
관리자·시스템 관리자)가 승인하면 그 리비전이 절의 `body` 가 되고, 앞엣것은 리비전에
그대로 남는다. 검토 없이 정본이 바뀌는 길은 없다 — 나중에 AI 가 쓰게 될 때 특히
그렇다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 문서의 종류. **「무엇을 하려고 왔나」 의 입구**가 된다.
#:   specimen     시편 규격 — 어떻게 자르나
#:   method       시험 방법 — 어떻게 재나
#:   calculation  물성 계산 — 잰 것이 어떻게 물성이 되나
#:   coverage     측정 범위 — 무엇을 잴 수 있고 무엇이 가정인가
#:   instrument   장비 사용
#:   glossary     용어
KINDS = ("specimen", "method", "calculation", "coverage", "instrument", "glossary")

REVISION_STATUSES = ("pending", "approved", "rejected", "superseded")


class GuideDocument(Base):
    """문서 하나 — 절의 묶음. 「DMA 에서 Prony 카드까지」."""

    __tablename__ = "guide_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    """주소에 쓰는 이름. `dma-prony`. 바뀌지 않는다 — 앱의 자리가 이것으로 가리킨다."""
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    topic: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    """대상. **시험 종류의 key 와 같은 값**을 쓴다(`tensile`·`dma`) — 그러면 시험
    화면이 「이 종류의 가이드」 를 자동으로 끌어온다. 종류가 아닌 대상(접착·성형)은
    자유 문자열."""
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """가져온 원본 파일 이름. 대조할 때 쓴다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuideSection(Base):
    """절 하나. `body` 는 **승인된 본문**이다."""

    __tablename__ = "guide_sections"
    __table_args__ = (
        UniqueConstraint("document_id", "key", name="uq_guide_sections_doc_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guide_documents.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    body: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """편집기 문서(ProseMirror JSON). 그림은 안 들어간다 — 주소만 있다."""
    body_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    """검색용 평문. 저장할 때 `body` 에서 뽑는다. 사람이 안 쓴다."""
    revision_no: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """승인된 횟수. 화면이 「몇 번째 판인가」 를 보인다."""

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuideRevision(Base):
    """고쳐 쓴 것 하나. 승인되면 절의 본문이 되고, 여기는 그대로 남는다."""

    __tablename__ = "guide_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guide_sections.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    body_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """쓴 사람이 남긴 한 줄 — 무엇을 왜 고쳤나."""

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class GuideAsset(Base):
    """그림 파일. 본문은 주소만 든다."""

    __tablename__ = "guide_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guide_documents.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(String(500))
    """filestore 상대경로. `guide/<asset id>/<파일명>`."""
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
