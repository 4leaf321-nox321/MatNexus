"""알림 API 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread: int


class NotificationRuleOut(BaseModel):
    """내가 받을 수 있는 알림 하나와, 지금 켜져 있는가."""

    event_kind: str
    label: str
    description: str
    enabled: bool


class NotificationRuleUpdate(BaseModel):
    enabled: bool
