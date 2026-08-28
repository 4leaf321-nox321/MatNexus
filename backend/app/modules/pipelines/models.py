"""장비 커넥터와 수집함 — **장비 PC 가 보낸 파일이 시험이 되기 전까지 사는 자리.**

## 왜 시험을 바로 안 만드나

장비 PC 의 수집 에이전트(MatPylon)는 파일이 어느 시편의 것인지 **확신하지
못한다.** 파일 이름에서 뽑은 힌트가 전부다. 그것으로 시편을 만들면 오타 하나가
유령 시편이 된다 — 그래서 에이전트는 시편을 만들지 않고, 서버가 후보를 좁히고,
하나로 안 정해지면 사람이 붙인다. 그 사이 상태가 여기 산다.

## 서버 원장이 정본이다

같은 내용(sha256)이 이미 있으면 받지 않고 기존 id 를 돌려준다. 에이전트가 죽었다
살아나 같은 파일을 다시 보내도 두 번 등록되지 않는다 — 에이전트의 「보냈다」
장부가 아니라 **이 표가** 무엇을 받았는지 정한다.

## 파일은 한 곳에만

원본은 `inbox/…` 에 떨어졌다가 시험이 되면 `test-runs/…` 로 **옮겨진다.** 복사가
아니다. 두 벌이면 정리 잡이 어느 것을 지워야 하는지 모른다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 수집함 항목의 상태.
#:   received        저장됨, 워커 대기
#:   parsed          파싱 성공, 후보 조회 중(짧게 지나간다)
#:   suggested       후보가 하나 — **승인 대기.** 사람이 「승인」 을 누르면 시험이 된다
#:   needs_specimen  후보가 0 또는 2 이상 — 사람이 붙인다
#:   registered      시험이 됐다(`test_run_id`)
#:   failed          파싱 실패(`error`) — 프로파일을 고치고 retry
#:   discarded       사람이 버렸다
INBOX_STATUSES = (
    "received",
    "parsed",
    "suggested",
    "needs_specimen",
    "registered",
    "failed",
    "discarded",
)

#: 사람이 손댈 수 없는 끝 상태. 붙이기·버리기·다시 파싱이 여기서는 409 다.
FINAL_STATUSES = ("registered", "discarded")

#: 에이전트가 보내는 힌트의 키. **이 일곱 개만 받는다** — 나머지는 버린다.
#: 힌트는 확정이 아니라 후보를 좁히는 재료다.
HINT_KEYS = (
    "material_code",
    "lot",
    "specimen",
    "orientation",
    "tested_at",
    "operator",
    "instrument",
)


class PipelineConnector(Base):
    """장비 PC 하나."""

    __tablename__ = "pipeline_connectors"
    __table_args__ = (
        # **재설치하면 기존 것을 돌려준다.** 같은 PC 가 둘로 보이면 관리 화면에서
        # 어느 것이 살아 있는지 알 수 없다.
        UniqueConstraint("workspace_id", "hostname", name="uq_pipeline_connectors_host"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    """**커넥터는 부서 것이다.** 이 커넥터로 들어온 파일은 이 부서의 시험이 된다 —
    남의 부서에 파일을 밀어 넣을 수 없어야 한다."""

    name: Mapped[str] = mapped_column(String(100))
    hostname: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_register: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """후보가 하나면 승인 없이 바로 시험을 만드나. **기본은 아니오** — 규칙이 「틀리게
    맞으면」 엉뚱한 시편에 시험이 붙고, 사람은 목록을 훑을 때에야 안다. 파일럿에서
    대조 열이 한동안 전부 맞으면 그 커넥터만 켠다."""

    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """마지막 보고 그대로. `{"sources": [{"key", "pending", "failed", "last_sent_at"}]}`.
    관리 화면의 대기·실패 수가 여기서 나온다 — 서버가 세는 값이 아니라 **에이전트가
    말한 값**이다. 아직 안 보낸 것은 서버가 알 수 없다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineInboxItem(Base):
    """반입된 파일 하나."""

    __tablename__ = "pipeline_inbox_items"
    __table_args__ = (
        # 관리 화면이 「이 커넥터의 대기 중인 것」 을 읽는다.
        Index("ix_pipeline_inbox_status_connector", "status", "connector_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("pipeline_connectors.id"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(40))
    """에이전트 쪽 소스(감시 폴더) 키. heartbeat 의 `sources[].key` 와 같은 값."""
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)

    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    client_path: Mapped[str] = mapped_column(String(1000))
    """장비 PC 의 원 경로. 사람이 「이게 어느 파일이지」 를 추적할 때 쓴다."""
    mtime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hints: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")

    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """filestore 상대경로. 시험이 되면 파일이 옮겨지고 여기는 비워진다 —
    **원본은 한 곳에만 있다.**"""

    test_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), nullable=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("format_profiles.id"), nullable=True
    )
    test_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_runs.id"), nullable=True, index=True
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """시편 후보. `[{"specimen_id", "specimen_name", "material_name", "sample_name",
    "reason"}]`.
    0개면 왜 없는지가 `error` 에, 2개 이상이면 여기서 사람이 고른다."""
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """파싱 결과 요약 — 채널 키·행 수·요약값 몇 개. 사람이 「맞는 파일인가」 를
    볼 만큼만."""
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    """사람이 붙였거나 버렸을 때 그 사람. 워커가 자동으로 등록했으면 비어 있다."""
    discard_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
