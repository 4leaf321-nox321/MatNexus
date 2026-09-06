"""인증 흐름 — 로그인·갱신·폐기·강제 변경·PAT.

여기서 지키려는 것은 기능 동작만이 아니다. **폐기가 실제로 되는가**가 핵심이다.
RA는 refresh 를 stateless 로 두어 폐기 목록이 없고, 비교표는 그것을 그대로
따라하지 말라고 적어 두었다(구조결정 12).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace, WorkspaceMember

PASSWORD = "initial-password-1"


def make_user(
    db: Session, *, email: str = "tester@example.com", must_change: bool = False
) -> User:
    workspace = Workspace(slug="metal", name="금속재료팀")
    db.add(workspace)
    db.flush()

    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name="시험자",
        status="active",
        must_change_password=must_change,
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
    db.commit()
    return user


def login(client: TestClient, email: str = "tester@example.com", password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_returns_access_token_and_sets_refresh_cookie(
    client: TestClient, db: Session
) -> None:
    make_user(db)
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert body["user"]["home_workspace_slug"] == "metal"
    assert body["user"]["memberships"][0]["role"] == "manager"

    # refresh 는 본문에 실리지 않는다 — httpOnly 쿠키로만 오간다.
    assert "refresh" not in response.text
    assert client.cookies.get("mnx_refresh")


def test_login_rejects_wrong_password_without_revealing_account(
    client: TestClient, db: Session
) -> None:
    make_user(db)

    wrong = login(client, password="nope").json()["error"]
    unknown = login(client, email="ghost@example.com", password="nope").json()["error"]

    assert wrong["code"] == unknown["code"] == "MNX-AUTH-0001"
    assert wrong["message"] == unknown["message"]


def test_suspended_account_cannot_log_in(client: TestClient, db: Session) -> None:
    user = make_user(db)
    user.status = "suspended"
    db.commit()

    response = login(client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MNX-AUTH-0002"


def test_pending_account_gets_a_distinct_message(client: TestClient, db: Session) -> None:
    """승인 대기와 정지를 구분해 알려 준다.

    둘 다 '비활성' 이라고만 하면 신청자가 관리자에게 무엇을 요청해야 할지 모른다.
    """
    user = make_user(db)
    user.status = "pending"
    db.commit()

    response = login(client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MNX-AUTH-0008"
    assert "승인" in response.json()["error"]["message"]


def test_me_requires_token(client: TestClient, db: Session) -> None:
    make_user(db)
    assert client.get("/api/auth/me").status_code == 401

    token = login(client).json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "tester@example.com"


def test_refresh_rotates_and_old_token_is_revoked(client: TestClient, db: Session) -> None:
    make_user(db)
    login(client)
    first_cookie = client.cookies.get("mnx_refresh")

    assert client.post("/api/auth/refresh").status_code == 200
    second_cookie = client.cookies.get("mnx_refresh")
    assert second_cookie != first_cookie

    # 회전 직후 몇 초는 동시 갱신으로 봐 준다(아래 시험). 여기서는 그 유예를 지나
    # 보낸 것으로 두고 **재사용 탐지**를 본다.
    _age_rotations(db)

    # 폐기된 토큰을 다시 쓰면 탈취로 보고 그 사용자의 세션을 전부 끊는다.
    client.cookies.clear()
    client.cookies.set("mnx_refresh", first_cookie)
    reuse = client.post("/api/auth/refresh")
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "MNX-AUTH-0005"

    client.cookies.clear()
    client.cookies.set("mnx_refresh", second_cookie)
    assert client.post("/api/auth/refresh").status_code == 401


def _age_rotations(db: Session) -> None:
    """회전 시각을 유예 밖으로 밀어 둔다 — 「방금 회전됨」 이 아니게."""
    from datetime import timedelta

    from app.modules.auth.models import RefreshToken
    from app.modules.auth.services import REFRESH_GRACE

    # **유예는 초 단위여야 한다.** 여기서 상수만큼 밀어 두므로, 상수가 며칠로 늘어나면
    # 이 시험은 그대로 통과하면서 탈취 탐지가 사실상 꺼진다 — 그것을 이 단언이 막는다.
    assert timedelta(minutes=2) >= REFRESH_GRACE, REFRESH_GRACE

    for token in db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))):
        if token.revoked_at is not None:
            token.revoked_at = token.revoked_at - REFRESH_GRACE - timedelta(seconds=1)
    db.commit()


def test_유예_안이라도_후속_토큰이_죽어_있으면_안_이어_준다(
    client: TestClient, db: Session
) -> None:
    """로그아웃(또는 전체 폐기) 직후에 옛 값이 오면 그건 동시 갱신이 아니다 — 사슬이
    이미 끊겼다. 유예는 **살아 있는 후속 토큰**으로 갈아탈 때만 쓴다."""
    make_user(db)
    login(client)
    first_cookie = client.cookies.get("mnx_refresh")
    assert client.post("/api/auth/refresh").status_code == 200
    # 후속 토큰으로 로그아웃 — 사슬의 머리가 죽는다.
    assert client.post("/api/auth/logout").status_code == 204

    client.cookies.clear()
    client.cookies.set("mnx_refresh", first_cookie)
    assert client.post("/api/auth/refresh").status_code == 401


def test_회전_직후의_옛_값은_동시_갱신으로_보고_세션을_안_끊는다(
    client: TestClient, db: Session
) -> None:
    """**실측(2026-09-05).** 한 페이지 로드에서 refresh 가 둘 나가고(StrictMode), 서버가
    둘을 순서대로 처리하면 둘째는 방금 회전된 값을 든다. 그것을 탈취로 보고 admin 의
    세션 1,200개를 한꺼번에 끊었다 — 다시 로그인해도 다음 로드에서 또 끊긴다.

    회전한 지 몇 초 안이고 후속 토큰이 살아 있으면 같은 사람이다. 후속 토큰을 회전시켜
    사슬을 하나로 유지한다."""
    make_user(db)
    login(client)
    first_cookie = client.cookies.get("mnx_refresh")

    assert client.post("/api/auth/refresh").status_code == 200
    second_cookie = client.cookies.get("mnx_refresh")

    # 둘째 요청 — 회전 직후, 옛 값으로. (httpx 는 같은 이름의 쿠키가 둘이면 막으므로
    # 병을 비우고 하나만 둔다.)
    client.cookies.clear()
    client.cookies.set("mnx_refresh", first_cookie)
    late = client.post("/api/auth/refresh")
    assert late.status_code == 200, late.text
    third_cookie = late.cookies.get("mnx_refresh")
    assert third_cookie and third_cookie not in (first_cookie, second_cookie)

    # 사슬은 하나다 — 셋째가 살아 있고, 그것으로 이어 간다.
    client.cookies.clear()
    client.cookies.set("mnx_refresh", third_cookie)
    assert client.post("/api/auth/refresh").status_code == 200


def test_유예가_지난_옛_값은_여전히_재사용으로_본다(client: TestClient, db: Session) -> None:
    """유예는 동시 갱신을 위한 것이지 탈취를 봐주는 것이 아니다."""
    make_user(db)
    login(client)
    first_cookie = client.cookies.get("mnx_refresh")
    assert client.post("/api/auth/refresh").status_code == 200

    _age_rotations(db)

    client.cookies.clear()
    client.cookies.set("mnx_refresh", first_cookie)
    reuse = client.post("/api/auth/refresh")
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "MNX-AUTH-0005"


def test_logout_revokes_refresh(client: TestClient, db: Session) -> None:
    make_user(db)
    login(client)

    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401


def test_change_password_clears_flag_and_kills_sessions(
    client: TestClient, db: Session
) -> None:
    user = make_user(db, must_change=True)
    body = login(client).json()
    assert body["user"]["must_change_password"] is True

    token = body["access_token"]
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a-longer-password-2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    db.refresh(user)
    assert user.must_change_password is False
    # 기존 세션은 전부 끊긴다.
    assert client.post("/api/auth/refresh").status_code == 401
    assert login(client, password="a-longer-password-2").status_code == 200


def test_pat_authenticates_and_can_be_revoked(client: TestClient, db: Session) -> None:
    """장비 파이프라인(Phase 6)이 쓸 자격 증명. 사람 세션과 같은 지점에서 인증된다."""
    make_user(db)
    access = login(client).json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    created = client.post("/api/auth/tokens", json={"name": "인장시험기"}, headers=auth)
    assert created.status_code == 201
    raw = created.json()["token"]
    assert raw.startswith("mnx_pat_")

    pat_auth = {"Authorization": f"Bearer {raw}"}
    assert client.get("/api/auth/me", headers=pat_auth).json()["email"] == "tester@example.com"

    pat_id = created.json()["pat"]["id"]
    assert client.delete(f"/api/auth/tokens/{pat_id}", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=pat_auth).status_code == 401


def test_짧은_비밀번호도_받는다(client: TestClient, db: Session) -> None:
    """길이 하한을 두지 않는다.

    10자를 요구했더니 **설치 현장에서 그것이 막혔다.** 폐쇄망 서버의 비밀번호는
    기관 규칙이나 기존 계정 체계를 따르는 경우가 많고, 우리가 정한 숫자가 그것과
    어긋나면 사람은 규칙을 지키는 대신 **우회할 길을 찾는다** — 스크립트로 직접
    바꾸는 쪽이고, 그 경로가 오히려 강제 변경을 건너뛴다.
    """
    make_user(db, must_change=True)
    token = login(client).json()["access_token"]

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "짧다"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204, response.text
    assert login(client, password="짧다").status_code == 200


def test_바꾸고_나면_다시_묻지_않는다(client: TestClient, db: Session) -> None:
    """**실제로 갇혔던 자리다.**

    바꾸고 다시 로그인했는데 또 "처음 로그인했습니다" 가 떴다. 원인은 API 가
    아니라 `set_admin.py` 였지만(비밀번호를 넣을 때마다 강제를 되켰다), 사용자가
    보는 증상은 여기였다 — 로그인 응답의 `must_change_password` 다.
    """
    make_user(db, must_change=True)
    token = login(client).json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "새비번1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    again = login(client, password="새비번1")
    assert again.status_code == 200
    assert again.json()["user"]["must_change_password"] is False

    # 한 번 더 들어와도 마찬가지다 — 상태가 남는다.
    assert login(client, password="새비번1").json()["user"]["must_change_password"] is False


def test_표시_이름을_스스로_바꾼다(client: TestClient, db: Session) -> None:
    """이름 오타 하나를 고치려고 DB 를 직접 만지는 일이 실제로 생겼다."""
    user = make_user(db)
    token = login(client).json()["access_token"]

    response = client.patch(
        "/api/auth/me",
        json={"display_name": "박용진"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "박용진"

    db.refresh(user)
    assert user.display_name == "박용진"
    # 다시 로그인해도 남아 있다.
    assert login(client).json()["user"]["display_name"] == "박용진"


def test_아이디는_스스로_못_바꾼다(client: TestClient, db: Session) -> None:
    """**로그인 식별자다.** 본인이 바꾸면 감사 기록·알림·이관이 가리키는 대상이
    흔들린다. 관리자의 일로 남긴다(`set_admin.py --rename-from`).
    """
    user = make_user(db)
    token = login(client).json()["access_token"]
    before = user.email

    client.patch(
        "/api/auth/me",
        json={"display_name": "새 이름", "email": "다른아이디"},
        headers={"Authorization": f"Bearer {token}"},
    )
    db.refresh(user)
    assert user.email == before  # 조용히 무시된다 — 스키마에 없는 칸이다


def test_빈_이름은_거절한다(client: TestClient, db: Session) -> None:
    make_user(db)
    token = login(client).json()["access_token"]
    response = client.patch(
        "/api/auth/me",
        json={"display_name": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
