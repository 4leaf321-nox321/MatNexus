"""데이터 내보내기 단추 — **큐에 넣고, 감사에 남기고, 무엇이 들었는지 보여 준다.**

여기서 지키는 것:

    시스템 관리자만          전 부서 데이터가 통째로 나간다 — 부서 관리자도 아니다
    요청 안에서 안 만든다     곡선까지면 수 분·수백 MB 다. 큐에 넣고 202 로 끝낸다
    감사에 남는다            나간 파일은 회수가 안 되고, 그 안에서는 부서 가시성도
                            뜻이 없다. 「누가 언제 무엇을」 이 반년 뒤에 물어진다
    폴더 이름은 요청 때 정한다 큐에서 기다린 만큼 이름이 밀리면 화면과 폴더가 달라진다
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import kinds
from app.jobs.models import Job
from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.server import services
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit

PASSWORD = "Passw0rd!export"


@pytest.fixture(autouse=True)
def _export_dir(tmp_path: Path) -> Any:
    """내보내기 폴더를 시험 전용으로. **개발 PC 의 진짜 폴더를 안 건드린다.**"""
    settings = get_settings()
    before = settings.export_dir
    settings.export_dir = tmp_path / "exports"
    yield
    settings.export_dir = before


def _manager(db: Session, workspace: Workspace) -> str:
    user = User(
        email="export-manager",
        password_hash=security.hash_password(PASSWORD),
        display_name="부서 관리자",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
    db.commit()
    return user.email


def _login(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def test_큐에_넣고_바로_돌려준다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    got = client.post(
        "/api/server/exports",
        json={"curves": False, "catalog": True, "note": "MatPylon 전달"},
        headers=admin_headers,
    )
    assert got.status_code == 202, got.text
    body = got.json()
    assert body["status"] == "queued"
    # 폴더 이름에 범위와 메모가 남는다 — 반년 뒤에 그 폴더가 무엇인지 알려면 이름뿐이다.
    assert body["folder"].endswith("-all-MatPylon_전달")
    assert body["folder"] in body["path"]

    job = db.scalars(
        select(Job)
        .where(Job.kind == kinds.DATA_EXPORT_DATASET)
        .order_by(Job.created_at.desc())
    ).first()
    assert job is not None
    assert job.payload["folder"] == body["folder"]
    assert job.payload["curves"] is False
    assert job.payload["catalog"] is True
    # **재시도하지 않는다** — 반쯤 만든 폴더 위에 다시 쓰면 무엇이 온전한지 모른다.
    assert job.max_attempts == 1


def test_감사에_남는다(client: TestClient, db: Session, admin_headers: dict[str, str]) -> None:
    """나간 파일은 회수가 안 된다. 그 안에서는 부서 가시성도 뜻이 없다."""
    made = client.post(
        "/api/server/exports",
        json={"curves": True, "catalog": True},
        headers=admin_headers,
    )
    assert made.status_code == 202, made.text

    entry = db.scalars(
        select(AuditEntry)
        .where(AuditEntry.action == audit.DATA_EXPORTED)
        .order_by(AuditEntry.created_at.desc())
    ).first()
    assert entry is not None
    assert entry.target_label == made.json()["folder"]
    assert entry.changes["workspace"] == "전 부서"
    assert entry.changes["curves"] is True


def test_부서_관리자는_못_뽑는다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """기준정보 새 값은 부서 관리자지만(ADR 0032) 이건 다르다 — 남의 부서 데이터가
    통째로 나간다."""
    email = _manager(db, workspace)
    got = client.post("/api/server/exports", json={}, headers=_login(client, email))
    assert got.status_code == 403, got.text


def test_목록이_무엇이_들었는지_말한다(
    client: TestClient, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    """폴더 이름만 보이면 「이게 곡선 포함이었나」 를 열어 봐야 알고, 그때는 이미
    건넨 뒤다."""
    root = services.export_root()
    done = root / "20260922-120000-all"
    done.mkdir(parents=True)
    (done / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-09-22T12:00:00+00:00",
                "scope": {"workspace": "전 부서", "curves": True, "catalog": False},
                "counts": {"materials.csv": 135, "test_runs.csv": 225},
            }
        ),
        encoding="utf-8",
    )
    # manifest 가 없는 폴더 — **만드는 중이거나 실패한 것**이다.
    (root / "20260922-130000-all").mkdir(parents=True)

    got = client.get("/api/server/exports", headers=admin_headers)
    assert got.status_code == 200, got.text
    rows = {one["name"]: one for one in got.json()}
    assert rows["20260922-120000-all"]["done"] is True
    assert rows["20260922-120000-all"]["curves"] is True
    assert rows["20260922-120000-all"]["catalog"] is False
    assert rows["20260922-120000-all"]["row_total"] == 360
    assert rows["20260922-130000-all"]["done"] is False


def test_워커가_그_폴더에_이_DB_의_것을_만든다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """**핸들러까지 돌려 본다.** 큐에 들어가는 것만 보면 「넣었는데 안 만들어진다」 를
    못 잡는다 — 거기가 실제로 자주 어긋나는 자리다.

    그리고 **건넨 세션의 DB 를 뽑는지**까지 본다. 전에는 내보내기가 제 세션을 열어서
    (`SessionLocal`) 워커가 준 것을 무시했다 — 운영에서는 같은 DB 라 표가 안 나고,
    시험만 조용히 개발 DB 를 뽑고 있었다. 그 DB 가 없는 CI 에서야 빨개졌다(2026-09-23).
    """
    from app.jobs import handlers

    handlers.load_all()
    grade = f"EXPORT-{uuid.uuid4().hex[:6]}"
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": grade},
        headers=admin_headers,
    )
    assert material.status_code == 201, material.text

    made = client.post(
        "/api/server/exports",
        json={"curves": False, "catalog": False},
        headers=admin_headers,
    )
    folder = made.json()["folder"]

    handlers.get(kinds.DATA_EXPORT_DATASET)(
        db, {"folder": folder, "workspace": None, "curves": False, "catalog": False}
    )

    out = services.export_root() / folder
    assert (out / "README.md").is_file()
    # **이 DB 의 재료가 들어 있다.** 다른 DB 를 뽑았으면 이 등급이 없다.
    assert grade in (out / "materials.csv").read_text(encoding="utf-8-sig")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["scope"]["curves"] is False
    # 문헌을 뺐으면 그 표는 아예 없다 — 빈 파일을 두면 「문헌이 없는 시스템」 으로 읽힌다.
    assert not (out / "catalog_values.csv").exists()
