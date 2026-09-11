"""공지 — 폐쇄망의 소통 창구 하나(다른 하나 VOC 는 `test_voc.py`).

지키려는 것:
  - 초안은 발행 전까지 남에게 보이지 않는다
  - 팝업은 읽으면 다시 뜨지 않는다
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace


def member_headers(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    user = User(
        email="hong",
        password_hash=security.hash_password("member-password-1"),
        display_name="홍길동",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_draft_notice_is_hidden_until_published(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/notices",
        json={"title": "점검 안내", "body": "토요일 점검", "is_published": False},
        headers=admin_headers,
    )
    assert created.status_code == 201
    notice_id = created.json()["id"]

    headers = member_headers(client, db, workspace)
    assert client.get("/api/notices", headers=headers).json() == []

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )
    assert [n["title"] for n in client.get("/api/notices", headers=headers).json()] == [
        "점검 안내"
    ]


def test_popup_disappears_after_reading(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "필독", "body": "중요 변경", "is_popup": True},
        headers=admin_headers,
    ).json()["id"]

    headers = member_headers(client, db, workspace)
    assert len(client.get("/api/notices/popup", headers=headers).json()) == 1

    assert client.post(f"/api/notices/{notice_id}/read", headers=headers).status_code == 204
    assert client.get("/api/notices/popup", headers=headers).json() == []


def test_publish_time_is_stamped_once(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """수정할 때마다 발행 시각을 갱신하면 "언제 알려졌는가"를 잃는다."""
    notice_id = client.post(
        "/api/notices", json={"title": "안내", "body": "내용"}, headers=admin_headers
    ).json()["id"]
    first = client.get("/api/notices", headers=admin_headers).json()[0]["published_at"]

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": False}, headers=admin_headers
    )
    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin_headers
    )

    again = client.get("/api/notices", headers=admin_headers).json()[0]["published_at"]
    assert again == first


def test_공지를_지우면_읽음_기록도_함께_간다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """`notice_reads` 가 CASCADE 다. 안 지워지면 지운 공지를 가리키는 행이 남는다."""
    from app.modules.notices.models import NoticeRead

    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True, "is_popup": True},
        headers=admin_headers,
    ).json()["id"]
    headers = member_headers(client, db, workspace)
    client.post(f"/api/notices/{notice_id}/read", headers=headers)
    assert db.query(NoticeRead).count() == 1

    assert client.delete(f"/api/notices/{notice_id}", headers=admin_headers).status_code == 204
    assert client.get("/api/notices", headers=headers).json() == []
    db.expire_all()
    assert db.query(NoticeRead).count() == 0


def test_공지는_시스템_관리자만_지운다(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True},
        headers=admin_headers,
    ).json()["id"]
    headers = member_headers(client, db, workspace)

    assert client.delete(f"/api/notices/{notice_id}", headers=headers).status_code == 403
    assert client.delete(f"/api/notices/{notice_id}", headers=admin_headers).status_code == 204
