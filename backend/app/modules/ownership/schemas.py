"""권한 넘기기 API 의 모양."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from app.shared.access import EditAccessOut

#: 등록자·편집 부서를 넘기는 것 — 자료 여섯과 정의 넷, 장비(ADR 0035 3단계).
#: 워크벤치 작업은 없다: 그 편집 부서는 작업의 부서 자체라 넘길 것이 아니다.
OwnedKind = Literal[
    "material",
    "sample",
    "specimen",
    "test_run",
    "property_card",
    "group_result",
    "test_type",
    "format_profile",
    "recipe",
    "export_profile",
    "equipment",
]


class OwnershipChildrenOut(BaseModel):
    """아래에 딸린 한 종류 — **몇 건이고, 그중 내가 넘길 수 있는 것이 몇 건인가.**

    「하위까지」 를 누르기 전에 보여 준다. 남이 붙인 것은 못 넘기므로(등록자와 관리자만)
    둘을 갈라 적어야 사람이 결과를 미리 안다.
    """

    kind: OwnedKind
    label: str
    total: int
    changeable: int


class OwnershipOut(BaseModel):
    kind: OwnedKind
    id: uuid.UUID
    name: str
    access: EditAccessOut
    children: list[OwnershipChildrenOut]


class OwnershipChangeRequest(BaseModel):
    """넘길 것. **안 보낸 칸은 그대로 둔다** — 부분 수정의 규칙(AGENTS.md).

    `edit_workspace_slug` 는 `null` 을 **보내면** 부여를 걷는다. 안 보내면 그대로다.
    등록자는 비울 수 없다 — 넘기기만 한다(등록자 없는 자료는 관리자만 고친다).
    """

    registrant_id: uuid.UUID | None = None
    edit_workspace_slug: str | None = None
    include_children: bool = False
    """아래에 딸린 것도 함께. 내가 넘길 수 없는 것(남이 붙인 것)은 건너뛰고 이름을 말한다."""


class OwnershipSkippedOut(BaseModel):
    kind: OwnedKind
    name: str
    reason: str


class OwnershipChangeOut(BaseModel):
    changed: int
    skipped: list[OwnershipSkippedOut]
    access: EditAccessOut
    """바꾼 뒤의 그 자료 — 화면이 다시 읽지 않아도 된다."""


class PersonOut(BaseModel):
    """넘겨받을 사람 후보. **아이디(메일)는 안 싣는다** — 고르는 데는 이름과 소속이면 된다."""

    id: uuid.UUID
    display_name: str
    workspace: str | None
    """대표 소속 — 같은 이름이 둘이면 이것으로 가른다."""
