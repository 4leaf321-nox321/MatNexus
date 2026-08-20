"""모든 ORM 모델을 한 곳에서 import 한다.

Alembic autogenerate는 Base.metadata에 등록된 것만 본다. 모듈이 늘어날 때
여기에 한 줄을 더하지 않으면, 새 테이블이 안 보이는 정도가 아니라 **기존 테이블을
지우는 마이그레이션**이 생성된다. 그래서 모으는 지점을 하나로 고정한다.
"""

from __future__ import annotations

import app.modules.vocabulary.models  # noqa: F401
from app.database import Base
from app.jobs.models import Job
from app.modules.accounts.models import User
from app.modules.audit.models import AccessLog
from app.modules.auth.models import PersonalAccessToken, RefreshToken
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.notices.models import Notice, NoticeRead
from app.modules.notifications.models import (
    Notification,
    NotificationRule,
    NotificationRuleState,
)
from app.modules.processing.models import ProcessingRecipe, ProcessingResult
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.models import (
    Curve,
    FormatProfile,
    TestChannel,
    TestConditionField,
    TestRun,
    TestSummary,
    TestType,
)
from app.modules.voc.models import VocItem
from app.modules.workspaces.models import Workspace, WorkspaceMember

__all__ = [
    "AccessLog",
    "Base",
    "Curve",
    "EnsembleResult",
    "FormatProfile",
    "Job",
    "Material",
    "Notice",
    "NoticeRead",
    "Notification",
    "NotificationRule",
    "NotificationRuleState",
    "PersonalAccessToken",
    "ProcessingRecipe",
    "ProcessingResult",
    "PropertyCard",
    "RefreshToken",
    "Sample",
    "Specimen",
    "TestChannel",
    "TestConditionField",
    "TestRun",
    "TestSummary",
    "TestType",
    "User",
    "VocItem",
    "Workspace",
    "WorkspaceMember",
]
