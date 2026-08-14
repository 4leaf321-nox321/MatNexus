"""모든 ORM 모델을 한 곳에서 import 한다.

Alembic autogenerate는 Base.metadata에 등록된 것만 본다. 모듈이 늘어날 때
여기에 한 줄을 더하지 않으면, 새 테이블이 안 보이는 정도가 아니라 **기존 테이블을
지우는 마이그레이션**이 생성된다. 그래서 모으는 지점을 하나로 고정한다.
"""

from __future__ import annotations

from app.database import Base
from app.modules.accounts.models import User
from app.modules.auth.models import PersonalAccessToken, RefreshToken
from app.modules.workspaces.models import Workspace, WorkspaceMember

__all__ = [
    "Base",
    "PersonalAccessToken",
    "RefreshToken",
    "User",
    "Workspace",
    "WorkspaceMember",
]
