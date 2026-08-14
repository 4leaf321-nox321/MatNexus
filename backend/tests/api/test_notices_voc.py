"""공지와 VOC — 폐쇄망의 유일한 소통 창구 둘.

지키려는 것:
  - 초안은 발행 전까지 남에게 보이지 않는다
  - 팝업은 읽으면 다시 뜨지 않는다
  - VOC 는 남의 제보가 서로 보이지 않는다
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


def test_voc_is_private_between_users(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    created = client.post(
        "/api/voc",
        json={"title": "곡선이 안 보여요", "body": "인장 화면", "page_path": "/w/metal/tests"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["created_by"] == "홍길동"
    # 접수 당시 화면을 남긴다 — "그 화면에서 안 돼요" 를 재현하는 실마리다.
    assert created.json()["page_path"] == "/w/metal/tests"

    # 본인은 자기 것을 본다
    assert len(client.get("/api/voc", headers=headers).json()) == 1
    # 관리자는 전부 본다
    assert len(client.get("/api/voc", headers=admin_headers).json()) == 1


def test_admin_reply_sets_status(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = client.post(
        "/api/voc", json={"title": "요청", "body": "내용"}, headers=headers
    ).json()["id"]

    replied = client.post(
        f"/api/voc/{item_id}/reply",
        json={"reply": "다음 배포에 반영합니다.", "status": "resolved"},
        headers=admin_headers,
    )
    assert replied.status_code == 200
    assert replied.json()["status"] == "resolved"
    assert replied.json()["reply"] == "다음 배포에 반영합니다."


def test_member_cannot_reply(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    headers = member_headers(client, db, workspace)
    item_id = client.post(
        "/api/voc", json={"title": "요청", "body": "내용"}, headers=headers
    ).json()["id"]

    response = client.post(
        f"/api/voc/{item_id}/reply", json={"reply": "내가 답한다"}, headers=headers
    )
    assert response.status_code == 403
