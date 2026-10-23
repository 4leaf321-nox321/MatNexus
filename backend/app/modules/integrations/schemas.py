from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationOut(BaseModel):
    """연결 하나 — **토큰은 싣지 않는다.** 「설정됨」 과 「이 서버가 풀 수 있나」 만."""

    system: str
    label: str
    base_url: str
    """이 서버가 부르는 API 주소(끝이 `/api`)."""
    web_url: str
    """사람이 여는 화면 주소. 비어 있으면 API 주소에서 `/api` 를 뗀 것을 쓴다."""
    link_url: str
    """실제로 링크에 쓰는 주소 — `web_url` 이 비면 API 주소에서 뗀 것."""
    has_token: bool
    token_readable: bool
    """봉인한 토큰을 이 서버가 풀 수 있나. 거짓이면(DB 를 다른 PC 로 옮겼거나 `JWT_SECRET` 이
    바뀌었다) 토큰을 다시 넣는다."""
    token_set_at: datetime | None
    configured: bool
    """주소와 풀 수 있는 토큰이 다 있다 — 바깥에 물을 수 있다."""
    checked_at: datetime | None
    check_ok: bool | None
    check_message: str | None
    updated_by: str | None
    updated_at: datetime | None


class IntegrationIn(BaseModel):
    """연결 고치기. 주소 둘은 늘 보낸 그대로 바뀐다(빈 값이면 비운다)."""

    base_url: str = Field(default="", max_length=500)
    web_url: str = Field(default="", max_length=500)
    token: str | None = Field(default=None, max_length=4000)
    """새 토큰. **안 보내거나 빈 값이면 그대로 둔다** — 입력 칸이 늘 비어 보이므로(토큰을 다시
    보여 주지 않는다) 빈 칸을 「지우기」 로 읽으면 주소만 고쳐도 토큰이 사라진다. 지우려면
    `clear_token`."""
    clear_token: bool = False


class IntegrationCheckOut(BaseModel):
    ok: bool
    message: str
    checked_at: datetime
    who: str | None = None
    """TestScope 가 알아본 토큰 주인 — 그 사람이 볼 수 있는 부서의 장비만 보인다."""
    linked_properties: int | None = None
    """시험 항목이 이어진 물성 수 — 0 이면 연결은 됐어도 물성으로 장비를 못 찾는다."""
