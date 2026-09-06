"""[계획] 관리자 기능 개발 — 2026-09-05 에 붙인 것들이 무는가.

1  백업          마지막 백업 시각이 서버 화면에 선다 — 없으면 없다고, 밀렸으면 밀렸다고
2  큐            실패한 작업이 보이고 다시 시도할 수 있다
3  홈 경고        디스크·보존기간 초과·실패 작업·백업이 시스템 관리자에게만 실린다
4  계정          활성 시스템 관리자 수를 서버가 센다 / 로그인 실패는 늦추되 잠그지 않는다
5  부서          관리자가 시스템 관리자뿐인 부서를 표시한다
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import queue
from app.jobs.models import Job
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth import services as auth_services
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import ops


@pytest.fixture
def backup_root(tmp_path: Path) -> Any:
    settings = get_settings()
    original = settings.backup_dir
    settings.backup_dir = tmp_path / "backup"
    try:
        yield settings.backup_dir
    finally:
        settings.backup_dir = original


class Test1_백업:
    def test_설정이_없으면_없다고_말한다(self) -> None:
        settings = get_settings()
        original = settings.backup_dir
        settings.backup_dir = None
        try:
            found = ops.backup_status()
        finally:
            settings.backup_dir = original
        assert found.configured is False and found.stale is True
        # 무엇을 어디에 적을지 예시까지 — 「설정이 없다」 만으로는 다음 손이 안 움직인다.
        assert "BACKUP_DIR=D:\MatNexus-backup" in (found.problem or "")

    def test_가장_최근_덤프의_시각을_읽는다(self, backup_root: Path) -> None:
        (backup_root / "db").mkdir(parents=True)
        old = backup_root / "db" / "db-20260901-030000.dump"
        new = backup_root / "db" / "db-20260905-030000.dump"
        old.write_bytes(b"x")
        new.write_bytes(b"y")
        found = ops.backup_status()
        assert found.last_at is not None and found.stale is False and found.problem is None
        assert abs((found.last_at - datetime.now(UTC)).total_seconds()) < 60

    def test_밀리면_밀렸다고_말한다(self, backup_root: Path) -> None:
        (backup_root / "db").mkdir(parents=True)
        (backup_root / "db" / "db-old.dump").write_bytes(b"x")
        later = datetime.now(UTC) + timedelta(hours=ops.BACKUP_STALE_HOURS + 1)
        found = ops.backup_status(now=later)
        assert found.stale is True and "시간 전" in (found.problem or "")

    def test_서버_화면에_실린다(
        self, client: TestClient, admin_headers: dict[str, str], backup_root: Path
    ) -> None:
        body = client.get("/api/server/info", headers=admin_headers)
        assert body.status_code == 200, body.text
        assert body.json()["backup"]["stale"] is True
        assert "없습니다" in body.json()["backup"]["problem"]


class Test2_큐:
    def _failed(self, db: Session) -> Job:
        job = queue.enqueue(db, kind="notifications.deliver", payload={}, max_attempts=1)
        job.status = "failed"
        job.attempts = 1
        job.last_error = "SMTP 연결 거부"
        job.finished_at = datetime.now(UTC)
        db.commit()
        return job

    def test_실패한_작업이_보인다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        job = self._failed(db)
        body = client.get("/api/server/queue", headers=admin_headers)
        assert body.status_code == 200, body.text
        assert body.json()["failed"] >= 1
        mine = [row for row in body.json()["failures"] if row["id"] == str(job.id)]
        assert mine and mine[0]["kind_label"] == "알림 보내기"
        assert mine[0]["last_error"] == "SMTP 연결 거부"

    def test_다시_시도하면_처음부터_대기한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        job = self._failed(db)
        done = client.post(f"/api/server/queue/{job.id}/retry", headers=admin_headers)
        assert done.status_code == 200, done.text
        db.expire_all()
        again = db.get(Job, job.id)
        assert again is not None
        assert again.status == "queued" and again.attempts == 0 and again.finished_at is None

    def test_실패한_것만_다시_시도한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        job = queue.enqueue(db, kind="notifications.deliver", payload={})
        db.commit()
        done = client.post(f"/api/server/queue/{job.id}/retry", headers=admin_headers)
        assert done.status_code == 422

    def test_시스템_관리자만_본다(self, client: TestClient, db: Session) -> None:
        assert client.get("/api/server/queue").status_code == 401


class Test3_홈_경고:
    def test_시스템_관리자에게만_실린다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], workspace: Any
    ) -> None:
        body = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert body["ops"] is not None
        assert body["ops"]["disk_alert_percent"] == get_settings().disk_alert_percent
        assert body["ops"]["failed_jobs"] >= 0
        # 백업 설정이 없으면 그 말이 실린다 — 없는 것과 같으면 안 된다.
        assert body["ops"]["backup_problem"]

        user = User(
            email="plain",
            password_hash=security.hash_password("pw12345678"),
            display_name="구성원",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
        db.commit()
        login = client.post(
            "/api/auth/login", json={"email": "plain", "password": "pw12345678"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/statistics/overview", headers=headers).json()["ops"] is None


class Test4_계정:
    def test_활성_시스템_관리자_수를_센다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/accounts/summary", headers=admin_headers)
        assert body.status_code == 200, body.text
        assert body.json()["active_system_admins"] >= 1

    def test_실패가_쌓이면_늦추되_잠그지_않는다(
        self, client: TestClient, db: Session, workspace: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """5회부터 2초씩 늘어 최대 30초. 맞는 비밀번호는 여전히 통한다."""
        slept: list[float] = []
        monkeypatch.setattr(auth_services, "_sleep", lambda seconds: slept.append(seconds))
        user = User(
            email="slowpoke",
            password_hash=security.hash_password("right-pw-1234"),
            display_name="느린이",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.commit()

        for _ in range(6):
            wrong = client.post(
                "/api/auth/login", json={"email": "slowpoke", "password": "wrong"}
            )
            assert wrong.status_code == 401
        # 1~4회는 안 늦추고, 5회에 2초, 6회에 4초.
        assert slept == [2.0, 4.0]
        db.expire_all()
        assert db.get(User, user.id).failed_logins == 6  # type: ignore[union-attr]

        ok = client.post(
            "/api/auth/login", json={"email": "slowpoke", "password": "right-pw-1234"}
        )
        assert ok.status_code == 200, ok.text
        db.expire_all()
        assert db.get(User, user.id).failed_logins == 0  # type: ignore[union-attr]

    def test_지연은_최대치에서_멈춘다(self) -> None:
        settings = get_settings()
        assert auth_services.login_delay_seconds(settings.login_delay_after - 1) == 0
        assert auth_services.login_delay_seconds(10**6) == settings.login_delay_max_seconds

    def test_창이_지나면_처음부터_센다(self, db: Session, workspace: Any) -> None:
        user = User(
            email="stale-fail",
            password_hash=security.hash_password("pw"),
            display_name="옛 실패",
            status="active",
            home_workspace_id=workspace.id,
            failed_logins=9,
            last_failed_login_at=datetime.now(UTC) - timedelta(hours=3),
        )
        db.add(user)
        db.commit()
        delay = auth_services._note_failure(db, user)
        assert delay == 0 and user.failed_logins == 1


class Test5_부서:
    def test_관리자가_시스템_관리자뿐이면_표시한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        slug = f"ws-{uuid.uuid4().hex[:5]}"
        made = client.post(
            "/api/workspaces", json={"slug": slug, "name": "새 부서"}, headers=admin_headers
        )
        assert made.status_code == 201, made.text
        # 만든 시스템 관리자가 manager 로 들어간다 — 아직 부서장이 없다.
        assert made.json()["managers_only_system_admin"] is True

        workspace = db.get(Workspace, uuid.UUID(made.json()["id"]))
        assert workspace is not None
        lead = User(
            email=f"lead-{slug}",
            password_hash=security.hash_password("pw12345678"),
            display_name="부서장",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(lead)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=lead.id, role="manager"))
        db.commit()
        rows = client.get(
            "/api/workspaces?include_inactive=true", headers=admin_headers
        ).json()
        mine = [row for row in rows if row["slug"] == slug]
        assert mine and mine[0]["managers_only_system_admin"] is False
