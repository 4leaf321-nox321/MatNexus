"""접근 로그 — 사용자 지원용 기록.

지키려는 것:
  - 상태를 바꾼 요청은 남는다 (누가 언제 무엇을)
  - 폴링·헬스체크는 남지 않는다 — 남기면 정작 찾을 것을 못 찾는다
  - 요청 id 가 함께 남아 파일 로그와 이어진다
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AccessLog
from app.modules.workspaces.models import Workspace


def test_login_is_recorded_with_request_id(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    logs = list(db.scalars(select(AccessLog).where(AccessLog.action == "LOGIN")))
    assert len(logs) == 1
    entry = logs[0]
    assert entry.method == "POST"
    assert entry.status_code == 200
    # 파일 로그(app.log)와 잇는 끈. 이게 없으면 사용자 신고를 로그에서 찾을 수 없다.
    assert entry.request_id


def test_state_changing_request_records_the_user(  # type: ignore[no-untyped-def]
    client: TestClient, db: Session, admin_headers: dict[str, str], admin
) -> None:
    client.post(
        "/api/workspaces", json={"slug": "polymer", "name": "고분자팀"}, headers=admin_headers
    )

    entry = db.scalar(
        select(AccessLog).where(
            AccessLog.path == "/api/workspaces", AccessLog.method == "POST"
        )
    )
    assert entry is not None
    assert entry.user_id == admin.id  # 미들웨어는 인증 바깥이라 scope 로 전달받는다
    assert entry.status_code == 201


def test_polling_and_health_are_not_recorded(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    client.get("/api/health")
    client.get("/api/notifications/unread-count", headers=admin_headers)
    client.get("/api/workspaces", headers=admin_headers)

    paths = {entry.path for entry in db.scalars(select(AccessLog))}
    assert "/api/health" not in paths
    assert "/api/notifications/unread-count" not in paths
    # 조회(GET)도 기본적으로 남기지 않는다 — 양이 많고 지원에 쓸모가 적다.
    assert "/api/workspaces" not in paths


def test_failed_request_is_recorded_too(client: TestClient, db: Session) -> None:
    """실패야말로 남아야 한다. 로그인 실패가 반복되면 그것이 신호다."""
    client.post("/api/auth/login", json={"email": "ghost", "password": "nope"})

    entry = db.scalar(select(AccessLog).where(AccessLog.action == "LOGIN"))
    assert entry is not None
    assert entry.status_code == 401
    assert entry.user_id is None
