"""계정 API의 요청·응답 형태."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: 아이디 최소 길이. 이메일 형식을 강제하지 않는다(ADR 0002) — 사내 관리자 계정은
#: `admin` 처럼 짧은 아이디를 쓰고, 폐쇄망은 `.local` 같은 도메인을 쓴다.
_ID_FIELD = Field(min_length=3, max_length=254)
_PASSWORD_FIELD = Field(min_length=10, max_length=200)


class SignupRequest(BaseModel):
    email: str = _ID_FIELD
    password: str = _PASSWORD_FIELD
    display_name: str = Field(min_length=1, max_length=100)
    workspace_slug: str = Field(min_length=1, max_length=50)
    """희망 부서. 승인 시 이 부서의 멤버가 된다."""


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    status: str
    is_system_admin: bool
    must_change_password: bool
    home_workspace_slug: str | None
    requested_workspace_slug: str | None
    memberships: list[str]
    """부서 slug 목록. 상세 역할은 부서 멤버 화면에서 다룬다."""
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class ApproveRequest(BaseModel):
    workspace_slug: str | None = None
    """비우면 신청한 부서를 그대로 쓴다."""
    role: str = "member"


class RejectRequest(BaseModel):
    note: str = Field(min_length=1, max_length=500)
    """거절 사유. SMTP 가 없어 통보가 앱 안에서만 되므로 반드시 남긴다."""


class CreateAccountRequest(BaseModel):
    """관리자가 직접 계정을 만들 때. 승인 절차 없이 바로 활성이다."""

    email: str = _ID_FIELD
    display_name: str = Field(min_length=1, max_length=100)
    workspace_slug: str = Field(min_length=1, max_length=50)
    role: str = "member"
    is_system_admin: bool = False


class HomeWorkspaceRequest(BaseModel):
    """대표 소속을 정한다.

    **비우는 길은 두지 않는다.** 대표 소속이 없으면 로그인이 `memberships[0]`,
    즉 이름 순 첫 부서로 떨어지는데 그것은 사람이 정한 값이 아니다. 지우고 싶은
    상황은 실제로는 "다른 부서로 옮긴다" 이므로 그때도 새 값을 준다.
    """

    workspace_slug: str = Field(min_length=1, max_length=50)


class ReferenceOut(BaseModel):
    """이 계정을 가리키는 참조 하나. 삭제 전에 보여 준다."""

    table: str
    label: str
    column: str
    count: int
    on_delete: str | None
    blocks_delete: bool


class DeleteAccountRequest(BaseModel):
    transfer_to_id: uuid.UUID | None = None
    """소유 자료를 넘겨받을 계정. 비우면 소유자 참조가 그대로 남는다."""


class DeleteAccountResponse(BaseModel):
    transferred: list[ReferenceOut]
    """무엇이 넘어갔는지. 화면이 결과를 보여 줄 수 있어야 한다."""


class TemporaryPasswordResponse(BaseModel):
    """임시 비밀번호는 이 응답에서 한 번만 나온다.

    SMTP 가 없어 메일로 보낼 수 없으므로, 관리자가 화면에서 읽어 구두·메신저로
    전달한다. 받는 사람은 첫 로그인 때 변경이 강제된다.
    """

    account: AccountOut
    temporary_password: str
