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


class WorkspaceReferenceOut(BaseModel):
    """이 부서를 가리키는 참조 하나. **삭제 버튼을 누르기 전에 보여 준다.**

    이름에 `Workspace` 를 붙인 이유: 계정 모듈에 이미 `ReferenceOut` 이 있다.
    같은 이름을 쓰면 FastAPI 가 **둘 다** `app__modules__…__ReferenceOut` 으로
    바꿔 버려서, 아무 관계도 없는 계정 화면의 프론트 타입이 깨진다(실제로 깨졌다).
    """

    table: str
    column: str
    label: str
    count: int
    on_delete: str | None
    blocks_delete: bool
    """지우려면 먼저 정리해야 하는가. `RESTRICT` 도 여기 들어간다 — DB 가 거부한다."""


class WorkspaceMoveRequest(BaseModel):
    """상위 부서 바꾸기. `null` 이면 뿌리로 올린다.

    이름 변경(PATCH)과 분리한 이유: PATCH 로 받으면 "안 바꿈"과 "뿌리로 올림"이
    둘 다 `null` 이라 구분할 수 없다.
    """

    parent_slug: str | None = None
    before_slug: str | None = None
    """이 부서 **앞에** 놓는다. 끌어 놓기는 '어디에' 뿐 아니라 '몇 번째에' 를 함께
    말한다 — 못 받으면 옮길 때마다 맨 끝으로 가서 다시 위/아래를 눌러야 한다."""


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


class WorkspaceMergeRequest(BaseModel):
    """어느 부서로 합칠까. 원본은 주소(URL)가 든다."""

    target_slug: str


class ImportRowOut(BaseModel):
    """가져오기 한 행의 운명. **줄 번호를 든다** — 오류를 파일에서 되짚을 수 있게."""

    line: int
    slug: str
    name: str
    parent_slug: str | None
    action: str
    """`create` | `skip_exists` | `skip_kind` | `error`."""
    reason: str


class ImportResultOut(BaseModel):
    rows: list[ImportRowOut]
    created: int
    skipped: int
    errors: int
