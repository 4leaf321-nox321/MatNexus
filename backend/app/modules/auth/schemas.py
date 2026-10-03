"""인증 API의 요청·응답 형태.

이 파일이 프론트 타입의 원본이다 — OpenAPI를 거쳐 `schema.d.ts` 가 생성된다(D13).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    """EmailStr 을 쓰지 않는다.

    email-validator 는 `.local` 처럼 특수 용도로 예약된 도메인을 문법 단계에서
    거부하는데, 폐쇄망 사내 계정은 그런 주소를 쓰는 경우가 흔하다(실측: 초기
    관리자 admin@matnexus.local 이 422로 막혔다). 형식을 강하게 검사해서 얻는
    것보다 로그인 자체가 성립하지 않는 손해가 크다.
    """

    password: str = Field(min_length=1, max_length=200)


class WorkspaceMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    slug: str
    name: str
    path: str
    """`개발본부 / 금속재료팀`. 부서 선택기가 이름만 보여 주면 같은 이름의 팀이
    본부마다 있을 때 어느 쪽인지 알 수 없다."""
    depth: int
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    status: str
    is_system_admin: bool
    is_data_manager: bool = False
    """자료 관리자(ADR 0035). 화면이 확정 단추를 보일지 정한다."""
    must_change_password: bool
    home_workspace_slug: str | None
    memberships: list[WorkspaceMembershipOut]


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    """초 단위. 프론트가 만료 전에 갱신을 걸 수 있게 한다."""
    user: UserOut
    notice: str | None = None
    """로그인은 됐는데 알아야 할 것 — 친 아이디에 도메인이 붙어 계정 아이디가 다를 때."""


class ProfileUpdateRequest(BaseModel):
    """자기 정보 수정.

    **표시 이름만 바꾼다.** 아이디(`email`)는 로그인 식별자라 본인이 바꾸면
    감사 로그·알림·이관 기록이 가리키는 대상이 흔들린다 — 그것은 관리자의 일로
    남긴다(`set_admin.py --rename-from`).

    이름 오타 하나를 고치려고 DB 를 직접 만지는 일이 실제로 생겨서 넣었다.
    """

    display_name: str = Field(min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)
    """길이 하한을 두지 않는다.

    10자를 요구했더니 **설치 현장에서 그것이 막혔다.** 폐쇄망 서버의 비밀번호는
    기관 규칙이나 기존 계정 체계를 따르는 경우가 많고, 우리가 정한 숫자가 그것과
    어긋나면 사람은 규칙을 지키는 대신 **우회할 길을 찾는다**(스크립트로 직접
    바꾸기 등) — 그 경로가 오히려 강제 변경을 건너뛴다.

    지키려던 것("시드 비밀번호가 그대로 남지 않게")은 길이가 아니라 `이전과 다른
    비밀번호` 검사와 `must_change_password` 가 한다.
    """


class PatCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    read_only: bool = False
    """읽기만 하는 토큰 — 바깥 시스템에 목록을 읽게 줄 때. GET 밖의 요청은 막힌다."""


class PatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    read_only: bool = False


class PatCreateResponse(BaseModel):
    token: str
    """평문은 이 응답에서 한 번만 나온다. 다시 볼 수 없다."""
    pat: PatOut


# --- HWAX 포털 게이트웨이 · MCP 연결 (2026-10-03, ADR 0056) ----------------------------------


class GatewayTokenData(BaseModel):
    """HWAX 위임 창구가 내주는 토큰 — 포털 요청서(`ra-request.md`)의 봉투 그대로."""

    access_token: str
    """`mnx_pat_…` 평문(읽기 전용). 게이트웨이가 12시간 캐시한다 — 다시 볼 수 없다."""
    token_type: str = "bearer"
    expires_in: int
    """초. 게이트웨이는 이보다 일찍 버리고 다시 받는다."""
    needs_workspace: bool
    """아직 소속 부서가 없는 사람. 참고용 — 지금 소비자는 안 읽는다."""


class GatewayTokenOut(BaseModel):
    success: bool = True
    data: GatewayTokenData


class GatewayRevokeOut(BaseModel):
    ok: bool = True
    revoked: int
    """폐기한 수. 사람이 없거나 토큰이 없어도 0 — 폐기할 것이 없을 뿐이다."""


class PortalConnectionOut(BaseModel):
    """HWAX 포털 게이트웨이로 붙는 길 — 포털의 모든 앱이 같은 주소로 붙는다."""

    gateway_url: str
    """포털 공용 MCP 게이트웨이 — `<포털>/mcp-gw/mcp`. 포털 토큰으로 한 번 등록한다."""
    tokens_url: str
    """포털 토큰을 받는 화면."""
    auto_token: bool
    """위임 창구가 켜져 있다 — 포털 사용자는 MatNexus 토큰을 따로 등록하지 않는다."""


class McpConnectionOut(BaseModel):
    """사람에게 줄 MCP 연결 주소 — **서버가 준다.** 화면이 짐작하면 옮긴 날 틀린다."""

    direct_url: str | None = None
    """MatNexus MCP 서버에 직접 붙는 주소(`MCP_PUBLIC_URL`). 비면 서버도 모른다."""
    portal: PortalConnectionOut | None = None
    """HWAX 포털 게이트웨이(`HWAX_PORTAL_URL`). 비면 포털로 붙는 길이 없다."""
