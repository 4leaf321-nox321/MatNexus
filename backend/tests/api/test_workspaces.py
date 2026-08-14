"""부서와 멤버.

지키려는 것 둘:
  - 부서에 **관리자가 최소 한 명** 남는다. 0명이 되면 그 부서는 스스로 풀 수 없다
  - 부서 권한과 시스템 권한은 **다른 축**이다. 부서 manager 가 다른 부서를 건드릴 수 없다
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace, WorkspaceMember


def make_active_user(db: Session, email: str, password: str = "member-password-1") -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        display_name=email,
        status="active",
    )
    db.add(user)
    db.commit()
    return user


def headers_for(
    client: TestClient, email: str, password: str = "member-password-1"
) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_options_are_public_for_signup(client: TestClient, workspace: Workspace) -> None:
    """가입 화면은 로그인 전이라 인증 없이 부서 목록이 필요하다."""
    response = client.get("/api/workspaces/options")
    assert response.status_code == 200
    assert response.json() == [{"slug": "metal", "name": "금속재료팀"}]


def test_create_workspace_makes_creator_a_manager(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/workspaces", json={"slug": "polymer", "name": "고분자팀"}, headers=admin_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "polymer"
    # manager 0명인 부서는 아무도 멤버를 넣을 수 없어 태어나자마자 잠긴다.
    assert body["my_role"] == "manager"
    assert body["member_count"] == 1


def test_slug_must_be_url_safe(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/workspaces", json={"slug": "고분자팀", "name": "고분자팀"}, headers=admin_headers
    )
    assert response.status_code == 422


def test_duplicate_slug_is_rejected(
    client: TestClient, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/workspaces", json={"slug": "metal", "name": "다른 팀"}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MNX-WORKSPACES-0004"


def test_only_system_admin_creates_workspaces(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    make_active_user(db, "member")
    headers = headers_for(client, "member")
    response = client.post(
        "/api/workspaces", json={"slug": "rubber", "name": "고무팀"}, headers=headers
    )
    assert response.status_code == 403


def test_manager_adds_and_promotes_members(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    make_active_user(db, "hong")

    added = client.post(
        f"/api/workspaces/{workspace.slug}/members",
        json={"email": "hong", "role": "member"},
        headers=admin_headers,
    )
    assert added.status_code == 201
    assert added.json()["role"] == "member"
    user_id = added.json()["user_id"]

    promoted = client.patch(
        f"/api/workspaces/{workspace.slug}/members/{user_id}",
        json={"role": "manager"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "manager"


def test_pending_account_cannot_be_added(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """부서 추가로 승인 절차를 우회하는 길을 막는다."""
    user = User(
        email="waiting",
        password_hash=security.hash_password("x" * 12),
        display_name="대기자",
        status="pending",
    )
    db.add(user)
    db.commit()

    response = client.post(
        f"/api/workspaces/{workspace.slug}/members",
        json={"email": "waiting"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MNX-WORKSPACES-0006"


def test_last_manager_cannot_be_demoted_or_removed(
    client: TestClient,
    db: Session,
    admin: User,
    workspace: Workspace,
    admin_headers: dict[str, str],
) -> None:
    demote = client.patch(
        f"/api/workspaces/{workspace.slug}/members/{admin.id}",
        json={"role": "member"},
        headers=admin_headers,
    )
    assert demote.status_code == 409
    assert demote.json()["error"]["code"] == "MNX-WORKSPACES-0009"

    removed = client.delete(
        f"/api/workspaces/{workspace.slug}/members/{admin.id}", headers=admin_headers
    )
    assert removed.status_code == 409


def test_removing_member_moves_home_workspace(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """소속을 비워 두면 로그인 후 갈 곳이 없다."""
    user = make_active_user(db, "hong")
    client.post(
        f"/api/workspaces/{workspace.slug}/members",
        json={"email": "hong"},
        headers=admin_headers,
    )
    db.refresh(user)
    assert user.home_workspace_id == workspace.id

    client.delete(f"/api/workspaces/{workspace.slug}/members/{user.id}", headers=admin_headers)
    db.refresh(user)
    assert user.home_workspace_id is None


def test_manager_of_one_workspace_cannot_touch_another(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """부서 권한은 그 부서 안에서만이다."""
    other = Workspace(slug="polymer", name="고분자팀")
    db.add(other)
    db.flush()
    manager = make_active_user(db, "boss")
    db.add(WorkspaceMember(workspace_id=other.id, user_id=manager.id, role="manager"))
    db.commit()

    headers = headers_for(client, "boss")
    make_active_user(db, "hong")

    response = client.post(
        f"/api/workspaces/{workspace.slug}/members",
        json={"email": "hong"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MNX-WORKSPACES-0003"


def test_member_list_requires_membership(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    make_active_user(db, "outsider")
    headers = headers_for(client, "outsider")
    response = client.get(f"/api/workspaces/{workspace.slug}/members", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MNX-WORKSPACES-0002"


def test_archived_workspace_disappears_from_signup_options(
    client: TestClient, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    client.patch(
        f"/api/workspaces/{workspace.slug}", json={"is_active": False}, headers=admin_headers
    )
    assert client.get("/api/workspaces/options").json() == []
