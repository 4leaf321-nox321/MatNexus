"""알림 — 큐를 거쳐 3분할 구조로 도달하는가.

여기서 지키려는 것 셋:
  - 가입 신청이 **요청 처리 안에서** 알림을 만들지 않는다(큐에 넣기만 한다)
  - 워커가 처리해야 실제 알림이 생긴다
  - **같은 사건이 두 번 들어와도 알림은 한 번**이다 (RuleState 의 존재 이유)
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import handlers, queue, worker
from app.jobs.models import Job
from app.modules.accounts.models import User
from app.modules.notifications.models import Notification
from app.modules.workspaces.models import Workspace

SIGNUP = {
    "email": "hong",
    "password": "applicant-password-1",
    "display_name": "홍길동",
    "workspace_slug": "metal",
}


def drain(db: Session, limit: int = 20) -> int:
    """큐가 빌 때까지 워커를 돌린다. 처리한 개수를 돌려준다."""
    handlers.load_all()
    processed = 0
    while processed < limit and worker.run_once(session=db):
        processed += 1
    return processed


def test_signup_only_enqueues_a_job(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    """요청 처리 안에서 알림을 만들지 않는다 — 수신자가 늘어도 응답이 느려지지 않게."""
    client.post("/api/accounts/signup", json=SIGNUP)

    assert db.scalar(select(Job).where(Job.kind == "notifications.deliver")) is not None
    assert db.scalars(select(Notification)).all() == []


def test_worker_delivers_signup_notification_to_admin(
    client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
) -> None:
    # 관리자에게 기본 규칙이 있어야 받는다. 규칙 생성도 큐를 거친다.
    queue.enqueue(db, kind="notifications.ensure_rules", payload={"user_id": str(admin.id)})
    db.commit()
    drain(db)

    client.post("/api/accounts/signup", json=SIGNUP)
    drain(db)

    inbox = client.get("/api/notifications", headers=admin_headers)
    assert inbox.status_code == 200
    titles = [item["title"] for item in inbox.json()]
    assert "새 가입 신청" in titles

    detail = inbox.json()[0]
    assert detail["link"] == "/admin/accounts"  # 무엇을 해야 할지 갈 곳을 준다
    assert "홍길동" in detail["body"]


def test_same_event_twice_notifies_once(
    client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
) -> None:
    """워커 재시도나 중복 이벤트로 알림이 두 번 가지 않는다 — RuleState 의 존재 이유."""
    queue.enqueue(db, kind="notifications.ensure_rules", payload={"user_id": str(admin.id)})
    db.commit()
    drain(db)

    account_id = client.post("/api/accounts/signup", json=SIGNUP).json()["id"]
    drain(db)

    # 같은 key 로 한 번 더 넣는다 (재시도가 만든 중복을 흉내)
    queue.enqueue(
        db,
        kind="notifications.deliver",
        payload={
            "event_kind": "account.signup",
            "key": account_id,
            "title": "새 가입 신청",
            "body": "중복",
            "link": "/admin/accounts",
            "to_user_id": None,
        },
    )
    db.commit()
    drain(db)

    count = len([n for n in client.get("/api/notifications", headers=admin_headers).json()])
    assert count == 1


def test_approval_notifies_the_applicant(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    account_id = client.post("/api/accounts/signup", json=SIGNUP).json()["id"]
    drain(db)

    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)
    drain(db)

    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    inbox = client.get("/api/notifications", headers=headers).json()
    assert [item["title"] for item in inbox] == ["가입이 승인되었습니다"]
    assert client.get("/api/notifications/unread-count", headers=headers).json()["unread"] == 1


def test_rejection_carries_the_reason(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """메일이 없어 앱 안이 유일한 통보 경로다. 사유가 함께 가야 한다."""
    account_id = client.post("/api/accounts/signup", json=SIGNUP).json()["id"]
    drain(db)

    client.post(
        f"/api/accounts/{account_id}/reject",
        json={"note": "부서 확인이 필요합니다."},
        headers=admin_headers,
    )
    drain(db)

    notification = db.scalar(
        select(Notification).where(Notification.event_kind == "account.decided")
    )
    assert notification is not None
    assert notification.body == "부서 확인이 필요합니다."


def test_read_marks_and_counts(
    client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
) -> None:
    queue.enqueue(db, kind="notifications.ensure_rules", payload={"user_id": str(admin.id)})
    db.commit()
    drain(db)
    client.post("/api/accounts/signup", json=SIGNUP)
    drain(db)

    assert (
        client.get("/api/notifications/unread-count", headers=admin_headers).json()["unread"]
        == 1
    )

    item_id = client.get("/api/notifications", headers=admin_headers).json()[0]["id"]
    read = client.post(f"/api/notifications/{item_id}/read", headers=admin_headers)
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert (
        client.get("/api/notifications/unread-count", headers=admin_headers).json()["unread"]
        == 0
    )


def test_cannot_read_someone_elses_notification(
    client: TestClient, db: Session, admin: User, admin_headers: dict[str, str]
) -> None:
    queue.enqueue(db, kind="notifications.ensure_rules", payload={"user_id": str(admin.id)})
    db.commit()
    drain(db)
    account_id = client.post("/api/accounts/signup", json=SIGNUP).json()["id"]
    drain(db)
    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)
    drain(db)

    admin_item = client.get("/api/notifications", headers=admin_headers).json()[0]["id"]

    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(f"/api/notifications/{admin_item}/read", headers=other_headers)
    assert response.status_code == 404  # 남의 것인지 없는 것인지 구분해 주지 않는다


def test_failed_job_is_retried_then_marked_failed(db: Session) -> None:
    """핸들러가 실패해도 워커는 죽지 않고, 한도까지 재시도한 뒤 failed 로 남긴다."""
    from app.jobs.handlers import handler

    calls: list[int] = []

    @handler("test.always_fails")
    def _always_fails(session: Session, payload: dict[str, object]) -> None:
        calls.append(1)
        raise RuntimeError("의도된 실패")

    job = queue.enqueue(db, kind="test.always_fails", max_attempts=2)
    db.commit()

    worker.run_once(session=db)
    db.refresh(job)
    assert job.status == "queued"  # 첫 실패는 재시도로 남는다
    assert "의도된 실패" in (job.last_error or "")

    job.run_after = job.created_at  # 백오프를 건너뛴다
    db.commit()
    worker.run_once(session=db)
    db.refresh(job)
    assert job.status == "failed"
    assert len(calls) == 2

    handlers._HANDLERS.pop("test.always_fails")
