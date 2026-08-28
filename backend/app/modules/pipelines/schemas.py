"""장비 커넥터 API 의 모양. 계약의 정본은 MatPylon 쪽 `matpylon-openapi.yaml` 이다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pipelines.models import HINT_KEYS, INBOX_STATUSES

#: 소스 키 규칙. 에이전트가 같은 패턴으로 만든다.
SOURCE_KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,39}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    hostname: str = Field(min_length=1, max_length=255)
    workspace_id: uuid.UUID


class ConnectorUpdate(BaseModel):
    """「안 보낸 것」 과 「비운 것」 을 구별한다 — 없는 키는 그대로 둔다."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class ConnectorOut(BaseModel):
    id: uuid.UUID
    name: str
    hostname: str
    workspace_id: uuid.UUID
    workspace_name: str | None = None
    is_active: bool
    app_version: str | None
    last_seen_at: datetime | None
    next_run_at: datetime | None
    pending: int
    """마지막 heartbeat 기준 대기 합. **에이전트가 말한 값**이다."""
    failed: int
    waiting: int = 0
    """서버 쪽 수집함에서 사람을 기다리는 것(`needs_specimen`·`failed`)."""
    created_by_id: uuid.UUID | None
    created_at: datetime


class HeartbeatSource(BaseModel):
    key: str = Field(pattern=SOURCE_KEY_PATTERN)
    pending: int = Field(ge=0)
    failed: int = Field(ge=0)
    last_sent_at: datetime | None


class HeartbeatIn(BaseModel):
    app_version: str = Field(max_length=40)
    sources: list[HeartbeatSource] = Field(max_length=100)
    next_run_at: datetime | None


class HeartbeatOut(BaseModel):
    server_time: datetime
    upload_limit_bytes: int
    """에이전트가 413 을 미리 피하도록."""


class Hints(BaseModel):
    """에이전트가 파일 이름에서 뽑은 **힌트.** 확정이 아니다."""

    model_config = ConfigDict(extra="ignore")

    material_code: str | None = None
    lot: str | None = None
    specimen: str | None = None
    orientation: str | None = None
    tested_at: str | None = None
    operator: str | None = None
    instrument: str | None = None

    def compact(self) -> dict[str, str]:
        """빈 것을 뺀다. 저장할 때 `null` 이 일곱 개 늘어서는 것은 정보가 아니다."""
        out: dict[str, str] = {}
        for key in HINT_KEYS:
            value = getattr(self, key)
            if value is not None and str(value).strip():
                out[key] = str(value).strip()
        return out


class CandidateOut(BaseModel):
    specimen_id: uuid.UUID
    specimen_name: str
    material_name: str
    sample_name: str
    reason: str
    """어느 힌트·identity 로 맞았나. 사람이 고를 때 근거가 된다."""


class InboxItemOut(BaseModel):
    id: uuid.UUID
    status: str
    connector_id: uuid.UUID
    connector_name: str | None = None
    source_key: str
    filename: str
    size: int
    sha256: str
    hints: dict[str, str]
    test_type_key: str | None
    test_type_label: str | None = None
    profile_key: str | None
    test_run_id: uuid.UUID | None
    test_run_name: str | None = None
    error: str | None
    candidate_count: int = 0
    received_at: datetime
    resolved_at: datetime | None = None


class InboxItemDetail(InboxItemOut):
    client_path: str
    mtime: datetime
    candidates: list[CandidateOut]
    summary: dict[str, Any]
    discard_reason: str | None = None


class AssignIn(BaseModel):
    specimen_id: uuid.UUID
    test_type: str | None = Field(default=None, description="비우면 감지된 것")


class DiscardIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


__all__ = [
    "INBOX_STATUSES",
    "AssignIn",
    "CandidateOut",
    "ConnectorCreate",
    "ConnectorOut",
    "ConnectorUpdate",
    "DiscardIn",
    "HeartbeatIn",
    "HeartbeatOut",
    "HeartbeatSource",
    "Hints",
    "InboxItemDetail",
    "InboxItemOut",
]
