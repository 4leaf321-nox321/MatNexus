"""부서 API의 요청·응답 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: URL 에 들어가므로 소문자·숫자·하이픈만 받는다. 한글 부서명은 `name` 이 갖는다.
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,49}$"


class WorkspaceOption(BaseModel):
    """가입 화면에서 희망 부서를 고르기 위한 최소 정보. 인증 없이 노출된다."""

    slug: str
    name: str
    path: str
    """`개발본부 / 금속재료팀`. **같은 이름의 팀이 본부마다 있을 수 있다** —
    이름만 보여 주면 신청자가 어느 쪽인지 고를 수 없다."""
    depth: int


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    kind: str
    parent_slug: str | None
    depth: int
    path: str
    sort_order: int
    is_active: bool
    created_at: datetime
    member_count: int
    my_role: str | None
    """요청한 사람의 역할. 화면이 버튼을 보일지 정하는 데 쓴다."""


class WorkspaceCreateRequest(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    parent_slug: str | None = None


class WorkspaceMoveRequest(BaseModel):
    """상위 부서 바꾸기. `null` 이면 뿌리로 올린다.

    이름 변경(PATCH)과 분리한 이유: PATCH 로 받으면 "안 바꿈"과 "뿌리로 올림"이
    둘 다 `null` 이라 구분할 수 없다.
    """

    parent_slug: str | None = None


class WorkspaceReorderRequest(BaseModel):
    direction: str = Field(pattern=r"^(up|down)$")


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    """false 로 두면 보관 상태. 자료는 남기고 새 활동만 막는다(삭제하지 않는다)."""


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    status: str
    role: str
    joined_at: datetime


class MemberAddRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = "member"


class MemberRoleRequest(BaseModel):
    role: str
