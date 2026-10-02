"""사용 현황 응답 — 관리자 화면 한 장이 이것 하나로 그려진다."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class McpCallIn(BaseModel):
    """MCP 서버가 도구 하나를 마칠 때 알리는 것."""

    tool: str = Field(min_length=1, max_length=80)
    ok: bool = True
    elapsed_ms: int = Field(default=0, ge=0, le=3_600_000)


class PeriodOut(BaseModel):
    start: date
    end: date
    days: int


class DayCountOut(BaseModel):
    day: date
    count: int


class ActiveDayOut(BaseModel):
    """그날 쓴 사람 수 — 화면 · MCP · 둘 중 하나라도."""

    day: date
    web: int
    mcp: int
    any: int


class RequestDayOut(BaseModel):
    day: date
    web: int
    mcp: int
    mcp_tools: int
    """그날의 MCP 도구 호출 수(요청 수와 다르다 — 도구 하나가 여러 요청을 낸다)."""


class SignupOut(BaseModel):
    name: str
    email: str
    workspace: str | None
    status: str
    """`pending`(승인 대기) · `active` · `suspended` · `rejected`."""
    created_at: datetime


class UsersOut(BaseModel):
    active_accounts: int
    """지금 쓸 수 있는 계정(활성, 지우지 않음)."""
    pending: int
    """가입 승인을 기다리는 계정."""
    signups: int
    """기간 안에 가입한 계정."""
    signups_by_day: list[DayCountOut]
    recent_signups: list[SignupOut]


class ActivityOut(BaseModel):
    any_users: int
    """기간 안에 한 번이라도 쓴 사람."""
    web_users: int
    mcp_users: int
    """기간 안에 MCP(AI)로 쓴 사람."""
    both_users: int
    """화면과 MCP 를 둘 다 쓴 사람."""
    average_daily: float
    """하루 평균 사용자(쓴 날만이 아니라 기간 전체 날로 나눈다)."""
    by_day: list[ActiveDayOut]
    logins: int
    login_users: int


class AreaOut(BaseModel):
    area: str
    label: str
    reads: int
    writes: int
    mcp: int
    """그중 MCP 로 들어온 요청."""
    errors: int


class RequestsOut(BaseModel):
    total: int
    reads: int
    writes: int
    errors: int
    by_client: dict[str, int]
    """`web` · `mcp` · `pylon` · `script` → 요청 수."""
    by_day: list[RequestDayOut]
    by_area: list[AreaOut]


class ToolOut(BaseModel):
    tool: str
    calls: int
    failures: int
    users: int
    average_ms: float


class McpUserOut(BaseModel):
    name: str
    calls: int
    tools: int
    """이 사람이 쓴 서로 다른 도구 수."""
    last_day: date


class TokensOut(BaseModel):
    active: int
    """폐기 · 만료 안 된 개인 토큰 — MCP · 장비 연동이 쓰는 자격."""
    users: int
    """쓸 수 있는 토큰을 가진 사람."""
    used_in_period: int
    """기간 안에 한 번이라도 쓰인 토큰."""


class McpOut(BaseModel):
    calls: int
    failures: int
    users: int
    average_ms: float
    tools_used: int
    """기간 안에 한 번이라도 불린 도구의 가짓수."""
    writes_recorded: int
    """MCP 로 들어와 감사에 남은 변경(AI 경유 기록) — 도구 집계 전의 기간까지 센다."""
    by_tool: list[ToolOut]
    by_user: list[McpUserOut]
    tokens: TokensOut


class ViewedOut(BaseModel):
    id: str
    label: str
    views: int
    viewers: int
    mcp_views: int


class ViewsOut(BaseModel):
    total: int
    materials: list[ViewedOut]
    catalog_materials: list[ViewedOut]
    test_runs: list[ViewedOut]
    cards: list[ViewedOut]
    guides: list[ViewedOut]


class ContentOut(BaseModel):
    """기간 안에 **만든 것** — 쓰는 것이 실제로 자료로 남았나."""

    key: str
    label: str
    created: int


class UsagePersonOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str | None
    workspace: str | None
    last_day: date
    active_days: int
    web_requests: int
    writes: int
    mcp_calls: int
    views: int


class UsageSummaryOut(BaseModel):
    period: PeriodOut
    measured_since: date | None
    """요청 · 조회 · 도구 집계가 쌓이기 시작한 날. 그 전 날짜는 0 으로 보인다 — 안 쓴 것이
    아니다."""
    users: UsersOut
    activity: ActivityOut
    requests: RequestsOut
    mcp: McpOut
    views: ViewsOut
    content: list[ContentOut]
    people: list[UsagePersonOut]
