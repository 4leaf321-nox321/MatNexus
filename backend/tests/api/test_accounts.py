"""계정 생애 — 가입 신청, 승인·거절, 정지, 비밀번호 재설정.

이 흐름의 핵심은 **승인 전에는 아무것도 못 한다**는 것과, 상태가 바뀌면
**기존 세션이 즉시 끊긴다**는 것이다. 둘 중 하나라도 새면 승인 절차가 형식이 된다.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User

SIGNUP = {
    "email": "hong",
    "password": "applicant-password-1",
    "display_name": "홍길동",
    "workspace_slug": "metal",
}


def signup(client: TestClient, **overrides: object):  # type: ignore[no-untyped-def]
    return client.post("/api/accounts/signup", json={**SIGNUP, **overrides})


def test_signup_creates_pending_account_that_cannot_log_in(  # type: ignore[no-untyped-def]
    client: TestClient, workspace
) -> None:
    response = signup(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["requested_workspace_slug"] == "metal"
    assert body["memberships"] == []  # 승인 전에는 부서 소속이 없다

    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "MNX-AUTH-0008"


def test_signup_rejects_duplicate_id(client: TestClient, workspace) -> None:  # type: ignore[no-untyped-def]
    signup(client)
    again = signup(client)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "MNX-ACCOUNTS-0002"


def test_signup_rejects_unknown_workspace(client: TestClient, workspace) -> None:  # type: ignore[no-untyped-def]
    response = signup(client, workspace_slug="ghost")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MNX-ACCOUNTS-0001"


def test_approve_grants_membership_and_login(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]

    approved = client.post(
        f"/api/accounts/{account_id}/approve", json={"role": "member"}, headers=admin_headers
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "active"
    assert body["memberships"] == ["metal"]
    assert body["home_workspace_slug"] == "metal"
    assert body["decided_at"] is not None

    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert login.status_code == 200
    assert login.json()["user"]["memberships"][0]["role"] == "member"


def test_reject_records_the_reason(client: TestClient, admin_headers: dict[str, str]) -> None:
    account_id = signup(client).json()["id"]

    rejected = client.post(
        f"/api/accounts/{account_id}/reject",
        json={"note": "부서 확인이 필요합니다."},
        headers=admin_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "suspended"
    # SMTP 가 없어 통보가 앱 안에서만 되므로 사유가 남아야 한다.
    assert rejected.json()["decision_note"] == "부서 확인이 필요합니다."


def test_approving_twice_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]
    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)

    again = client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "MNX-ACCOUNTS-0004"


def test_only_system_admin_can_approve(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]
    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)

    member_login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    other = signup(client, email="kim").json()["id"]
    response = client.post(f"/api/accounts/{other}/approve", json={}, headers=member_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MNX-AUTH-0103"


def test_admin_creates_account_with_one_time_password(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/accounts",
        json={"email": "park", "display_name": "박연구", "workspace_slug": "metal"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    temporary = body["temporary_password"]
    assert temporary
    assert body["account"]["status"] == "active"
    # 임시 비밀번호가 그대로 남지 않게 첫 로그인에 변경을 강제한다.
    assert body["account"]["must_change_password"] is True

    login = client.post("/api/auth/login", json={"email": "park", "password": temporary})
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_reset_password_kills_sessions_and_issues_new_one(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]
    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)

    user_client_login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert user_client_login.status_code == 200

    reset = client.post(f"/api/accounts/{account_id}/reset-password", headers=admin_headers)
    assert reset.status_code == 200
    temporary = reset.json()["temporary_password"]

    # 옛 비밀번호는 더 이상 통하지 않는다.
    assert (
        client.post(
            "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": SIGNUP["email"], "password": temporary}
        ).status_code
        == 200
    )


def test_suspend_cuts_access_immediately(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]
    client.post(f"/api/accounts/{account_id}/approve", json={}, headers=admin_headers)

    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=member_headers).status_code == 200

    client.post(f"/api/accounts/{account_id}/suspend", headers=admin_headers)

    # 발급된 access 토큰이 남아 있어도 즉시 막힌다 — 세션이 살아 있으면 정지가 무의미하다.
    assert client.get("/api/auth/me", headers=member_headers).status_code == 403
    assert client.post("/api/auth/refresh").status_code == 401


def test_admin_cannot_change_own_status(
    client: TestClient, admin: User, admin_headers: dict[str, str]
) -> None:
    """자기 자신을 정지시켜 관리자가 0명이 되는 사고를 막는다."""
    response = client.post(f"/api/accounts/{admin.id}/suspend", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MNX-ACCOUNTS-0006"


def test_pending_list_shows_applicants(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    signup(client)
    signup(client, email="kim")

    pending = client.get("/api/accounts?status=pending", headers=admin_headers)
    assert pending.status_code == 200
    assert {row["email"] for row in pending.json()} == {"hong", "kim"}


# --- 대표 소속 ----------------------------------------------------------------
#
# **로그인해서 처음 서는 자리다.** 이 값이 없으면 `memberships[0]`, 즉 이름 순
# 첫 부서로 떨어진다 — 부서 하나뿐인 사람에게는 맞지만 여러 부서에 든 사람은
# 매번 엉뚱한 곳에 서게 된다. 그 순서를 정하는 것은 사람이지 가나다순이 아니다.


def _second_workspace(db: Session):  # type: ignore[no-untyped-def]
    from app.modules.workspaces.models import Workspace

    item = Workspace(slug="polymer", name="고분자팀")
    db.add(item)
    db.commit()
    return item


def test_대표_소속을_바꾸면_로그인이_그리로_선다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    account_id = signup(client).json()["id"]
    client.post(
        f"/api/accounts/{account_id}/approve", json={"role": "member"}, headers=admin_headers
    )
    second = _second_workspace(db)
    client.post(
        f"/api/workspaces/{second.slug}/members",
        json={"email": SIGNUP["email"], "role": "member"},
        headers=admin_headers,
    )

    changed = client.post(
        f"/api/accounts/{account_id}/home-workspace",
        json={"workspace_slug": "polymer"},
        headers=admin_headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["home_workspace_slug"] == "polymer"

    # **화면이 이 값으로 첫 부서를 고른다.** 응답에만 있고 로그인이 안 보면
    # 관리자가 정한 것이 아무 일도 안 한다.
    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert login.status_code == 200
    assert login.json()["user"]["home_workspace_slug"] == "polymer"


def test_멤버가_아닌_부서는_대표_소속이_못_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """주면 그 사람은 자기가 못 보는 부서에 서고, 목록이 비어 보인다 —
    데이터가 없는 것과 구별이 안 된다."""
    account_id = signup(client).json()["id"]
    client.post(
        f"/api/accounts/{account_id}/approve", json={"role": "member"}, headers=admin_headers
    )
    _second_workspace(db)

    denied = client.post(
        f"/api/accounts/{account_id}/home-workspace",
        json={"workspace_slug": "polymer"},
        headers=admin_headers,
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "MNX-ACCOUNTS-0014"

    db.expire_all()
    user = db.scalar(select(User).where(User.email == SIGNUP["email"]))
    assert user is not None
    assert user.home_workspace_id is not None  # 원래 것이 그대로다


def test_없는_부서와_없는_계정을_가른다(  # type: ignore[no-untyped-def]
    client: TestClient, admin_headers: dict[str, str], workspace
) -> None:
    """404 하나로 뭉치면 관리자는 무엇을 고쳐야 하는지 모른다."""
    account_id = signup(client).json()["id"]
    client.post(
        f"/api/accounts/{account_id}/approve", json={"role": "member"}, headers=admin_headers
    )

    ghost_workspace = client.post(
        f"/api/accounts/{account_id}/home-workspace",
        json={"workspace_slug": "ghost"},
        headers=admin_headers,
    )
    assert ghost_workspace.json()["error"]["code"] == "MNX-ACCOUNTS-0001"

    ghost_account = client.post(
        f"/api/accounts/{uuid.uuid4()}/home-workspace",
        json={"workspace_slug": "metal"},
        headers=admin_headers,
    )
    assert ghost_account.json()["error"]["code"] == "MNX-ACCOUNTS-0003"


def test_대표_소속은_시스템_관리자만_정한다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """자기 자리를 자기가 옮기는 것은 다른 기능이다 — 여기는 관리 화면이고,
    열어 두면 부서 배정이 승인 절차를 우회한다."""
    account_id = signup(client).json()["id"]
    client.post(
        f"/api/accounts/{account_id}/approve", json={"role": "member"}, headers=admin_headers
    )
    login = client.post(
        "/api/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = client.post(
        f"/api/accounts/{account_id}/home-workspace",
        json={"workspace_slug": "metal"},
        headers=headers,
    )
    assert denied.status_code == 403
