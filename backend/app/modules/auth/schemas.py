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
    must_change_password: bool
    home_workspace_slug: str | None
    memberships: list[WorkspaceMembershipOut]


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    """초 단위. 프론트가 만료 전에 갱신을 걸 수 있게 한다."""
    user: UserOut


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


class PatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class PatCreateResponse(BaseModel):
    token: str
    """평문은 이 응답에서 한 번만 나온다. 다시 볼 수 없다."""
    pat: PatOut
