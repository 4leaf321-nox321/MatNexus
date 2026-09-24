"""화면이 **누르기 전에** 아는 권한 — 자료마다 「고칠 수 있나, 못 하면 누구에게」.

판정은 `permissions` 가 한다. 여기는 그 판정을 응답에 싣는다(ADR 0035 D4).

## 왜 응답에 싣나

전에는 단추를 누르고 403 을 받아야 알았다. 보기를 전원에게 연 뒤로는 화면에 보이는
자료 대부분이 남의 것이라, 그대로 두면 단추 대부분이 누르면 막히는 단추가 된다.
`frontend/src/shared/auth/roles.ts` 가 적어 둔 원칙 — 「눌러 보고 403 을 알게 하지
않는다」 — 을 자료 단위로 지킨다.

## 이름은 한 번에 읽는다

행마다 등록자·부서 이름을 읽으면 목록 한 장에 질의가 수백 번 나간다. `prime` 으로
먼저 모아 두고 `of` 가 꺼내 쓴다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace
from app.shared import permissions


class EditAccessOut(BaseModel):
    """이 자료를 **지금 이 사람이** 고칠 수 있나."""

    can_edit: bool
    can_hand_over: bool
    """등록자·편집 부서를 바꿀 수 있나 — 등록자와 관리자만."""
    registrant_id: uuid.UUID | None
    registrant: str | None
    """등록자 이름. 비어 있으면 등록자가 없는 자료다(커넥터가 스스로 붙인 시험 등)."""
    edit_workspace_slug: str | None
    edit_workspace: str | None
    """편집을 받은 부서. 비어 있으면 등록자와 관리자만 고친다."""
    reason: str | None
    """못 고치면 **누구에게 물으면 되는지**. 고칠 수 있으면 비어 있다."""


class AccessBook:
    """여러 행의 `EditAccessOut` — 이름을 한 번에 읽는다."""

    def __init__(self, db: Session, user: User) -> None:
        self._db = db
        self.editor = permissions.editor(db, user)
        self._people: dict[uuid.UUID, str] = {}
        self._spaces: dict[uuid.UUID, tuple[str, str]] = {}

    def prime(self, rows: Iterable[permissions.Owned]) -> AccessBook:
        people: set[uuid.UUID] = set()
        spaces: set[uuid.UUID] = set()
        for row in rows:
            registrant, workspace = permissions.owner_of(row)
            if registrant is not None and registrant not in self._people:
                people.add(registrant)
            if workspace is not None and workspace not in self._spaces:
                spaces.add(workspace)
        if people:
            for user_id, name in self._db.execute(
                select(User.id, User.display_name).where(User.id.in_(people))
            ):
                self._people[user_id] = name
        if spaces:
            for space_id, slug, name in self._db.execute(
                select(Workspace.id, Workspace.slug, Workspace.name).where(
                    Workspace.id.in_(spaces)
                )
            ):
                self._spaces[space_id] = (slug, name)
        return self

    def of(self, row: permissions.Owned) -> EditAccessOut:
        registrant_id, workspace_id = permissions.owner_of(row)
        if (registrant_id is not None and registrant_id not in self._people) or (
            workspace_id is not None and workspace_id not in self._spaces
        ):
            self.prime([row])
        registrant = self._people.get(registrant_id) if registrant_id else None
        space = self._spaces.get(workspace_id) if workspace_id else None
        allowed = self.editor.allows(row)
        return EditAccessOut(
            can_edit=allowed,
            can_hand_over=self.editor.can_hand_over(row),
            registrant_id=registrant_id,
            registrant=registrant,
            edit_workspace_slug=space[0] if space else None,
            edit_workspace=space[1] if space else None,
            reason=None
            if allowed
            else permissions.locked_reason(
                registrant=registrant, workspace=space[1] if space else None
            ),
        )


def access_of(db: Session, user: User, row: permissions.Owned) -> EditAccessOut:
    """한 행만 — 저장 뒤 응답처럼."""
    return AccessBook(db, user).of(row)
