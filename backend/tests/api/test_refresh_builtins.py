"""코드의 씨앗을 DB 에 맞춘다 — **빠진 것만 채우고, 관리자가 고친 것은 안 건드린다.**

실측(2026-09-12): `ensure_*` 는 있으면 통째로 건너뛰어서, 코드가 뒤에 더한 채널·
프로파일 규칙·차원 선택지·항목 속성이 기존 DB 에 못 들어갔다. `ta_dma850` 의
마스터커브 자동 등록 규칙이 그렇게 08-31 부터 빠져 있었다 — 오류 없이 기능이 없었다.

  빠진 것은 들어온다             refresh 뒤에 코드의 키·채널·속성이 있다
  관리자가 고친 것은 그대로다     열 이름·라벨·값을 바꿔 뒀으면 refresh 가 안 되돌린다
  두 번째는 할 일이 없다          멱등
  역할이 바뀌면 알림 규칙이 따라간다
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import handlers, worker
from app.modules.accounts.models import User
from app.modules.notifications.models import NotificationRule
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import FormatProfile, TestChannel, TestType
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.modules.workspaces.models import Workspace

BACKEND = Path(__file__).resolve().parents[2]


def _script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "refresh_builtins", BACKEND / "scripts" / "refresh_builtins.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_builtins"] = module
    spec.loader.exec_module(module)
    return module


def drain(db: Session) -> None:
    handlers.load_all()
    while worker.run_once(session=db):
        pass


class Test씨앗_맞추기:
    def test_프로파일에_뒤에_더한_규칙이_들어오고_고친_열_이름은_남는다(
        self, db: Session
    ) -> None:
        ensure_builtin_test_types(db)
        ensure_builtin_format_profiles(db)
        db.commit()
        profile = db.scalar(
            select(FormatProfile).where(
                FormatProfile.key == "ta_dma850", FormatProfile.owner_workspace_id.is_(None)
            )
        )
        assert profile is not None
        # 08-21 씨앗처럼 — master_curve 규칙이 없고, 관리자가 열 이름 하나를 고쳤다.
        old = dict(profile.definition)
        old["tables"] = {
            key: value for key, value in old["tables"].items() if key != "master_curve"
        }
        old["columns"] = {**old["columns"], "부서가 바꾼 열": {"channel": "temperature"}}
        profile.definition = old
        db.commit()

        report = _script().run(db)
        db.commit()
        assert report["형식 프로파일 맞춤"] == ["ta_dma850"]
        db.expire_all()
        assert profile.definition["tables"]["master_curve"]["pattern"]  # 들어왔다
        assert "부서가 바꾼 열" in profile.definition["columns"]  # 남았다
        assert _script().run(db)["형식 프로파일 맞춤"] == []  # 멱등

    def test_시험_종류에_빠진_채널이_들어오고_있는_것은_안_바뀐다(self, db: Session) -> None:
        ensure_builtin_test_types(db)
        db.commit()
        dma = db.scalar(select(TestType).where(TestType.key == "dma_sweep"))
        assert dma is not None
        gone = db.scalar(
            select(TestChannel).where(
                TestChannel.test_type_id == dma.id, TestChannel.key == "phase_angle"
            )
        )
        assert gone is not None
        db.delete(gone)
        kept = db.scalar(
            select(TestChannel).where(
                TestChannel.test_type_id == dma.id, TestChannel.key == "temperature"
            )
        )
        assert kept is not None
        kept.label = "부서가 고친 이름"
        dma.label = "우리 DMA"
        db.commit()

        assert _script().run(db)["시험 종류 맞춤"] == ["dma_sweep"]
        db.commit()
        db.expire_all()
        keys = set(
            db.scalars(select(TestChannel.key).where(TestChannel.test_type_id == dma.id))
        )
        assert "phase_angle" in keys
        assert kept.label == "부서가 고친 이름" and dma.label == "우리 DMA"

    def test_물성_항목의_빠진_속성만_채운다(self, db: Session) -> None:
        _script().run(db)
        db.commit()
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        term = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == axis.id, VocabularyTerm.value == "탄성계수"
            )
        )
        assert term is not None
        term.attributes = {"dimension": "stress", "symbol": "부서 기호"}  # level 이 없다
        db.commit()
        assert _script().run(db)["물성 항목 맞춤"] == ["탄성계수"]
        db.commit()
        db.expire_all()
        assert term.attributes["level"] == "재료"
        assert term.attributes["symbol"] == "부서 기호"


class Test역할이_바뀌면_알림_규칙이_따라간다:
    def _kinds(self, db: Session, user: User) -> set[str]:
        return set(
            db.scalars(
                select(NotificationRule.event_kind).where(NotificationRule.user_id == user.id)
            )
        )

    def test_관리자로_올리면_받고_내리면_안_받는다(
        self, client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
    ) -> None:
        from app.modules.auth import security

        hong = User(
            email="hong",
            password_hash=security.hash_password("member-password-1"),
            display_name="홍길동",
            status="active",
            home_workspace_id=admin.home_workspace_id,
        )
        db.add(hong)
        db.commit()

        client.post(
            f"/api/accounts/{hong.id}/system-admin",
            json={"is_system_admin": True},
            headers=admin_headers,
        )
        drain(db)
        assert {"account.signup", "voc.registered"} <= self._kinds(db, hong)

        client.post(
            f"/api/accounts/{hong.id}/system-admin",
            json={"is_system_admin": False},
            headers=admin_headers,
        )
        drain(db)
        kinds = self._kinds(db, hong)
        assert "account.signup" not in kinds and "voc.registered" not in kinds
        assert "voc.changed" in kinds  # 누구나 받는 것은 남는다

    def test_부서_관리자가_되면_시편_못_정한_파일을_받는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin: User,
        admin_headers: dict[str, str],
    ) -> None:
        from app.modules.auth import security

        hong = User(
            email="hong",
            password_hash=security.hash_password("member-password-1"),
            display_name="홍길동",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(hong)
        db.commit()
        client.post(
            f"/api/workspaces/{workspace.slug}/members",
            json={"email": "hong", "role": "member"},
            headers=admin_headers,
        )
        drain(db)
        assert "pipelines.needs_specimen" not in self._kinds(db, hong)

        client.patch(
            f"/api/workspaces/{workspace.slug}/members/{hong.id}",
            json={"role": "manager"},
            headers=admin_headers,
        )
        drain(db)
        assert "pipelines.needs_specimen" in self._kinds(db, hong)
