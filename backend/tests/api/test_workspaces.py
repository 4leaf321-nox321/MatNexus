"""부서와 멤버.

지키려는 것 둘:
  - 부서에 **관리자가 최소 한 명** 남는다. 0명이 되면 그 부서는 스스로 풀 수 없다
  - 부서 권한과 시스템 권한은 **다른 축**이다. 부서 manager 가 다른 부서를 건드릴 수 없다
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
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
    # 경로도 함께 준다 — 같은 이름의 팀이 본부마다 있을 수 있어서, 이름만으로는
    # 신청자가 어느 쪽인지 고를 수 없다.
    assert response.json() == [
        {"slug": "metal", "name": "금속재료팀", "path": "금속재료팀", "depth": 0}
    ]


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


class Test부서계층:
    """조직은 평면이 아니다 — 본부 아래 팀이 있다(RA 의 부서 트리를 참조).

    같은 이름의 팀이 본부마다 있을 수 있다("품질팀"이 둘). 평면 목록으로 두면
    화면에서 그 둘을 구분할 방법이 없다.
    """

    def _make(
        self,
        client: TestClient,
        headers: dict[str, str],
        slug: str,
        name: str,
        parent: str | None = None,
    ) -> dict[str, object]:
        response = client.post(
            "/api/workspaces",
            json={"slug": slug, "name": name, "parent_slug": parent},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body: dict[str, object] = response.json()
        return body

    def test_경로와_깊이를_서버가_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """화면이 평면 목록으로 트리를 세우면 선택기·관리·가입 화면이 각자 다른
        정렬을 갖게 된다. 조직도 순서는 한 곳에서만 정한다."""
        self._make(client, admin_headers, "dev", "개발본부")
        team = self._make(client, admin_headers, "metal2", "금속재료팀", "dev")

        assert team["path"] == "개발본부 / 금속재료팀"
        assert team["depth"] == 1
        assert team["parent_slug"] == "dev"

    def test_트리_순서로_내려온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._make(client, admin_headers, "dev", "개발본부")
        self._make(client, admin_headers, "b-team", "나팀", "dev")
        self._make(client, admin_headers, "a-team", "가팀", "dev")

        rows = client.get("/api/workspaces?all=true", headers=admin_headers).json()
        order = [row["slug"] for row in rows if row["slug"] in {"dev", "a-team", "b-team"}]
        # 자식은 부모 바로 아래에. 형제는 만든 순서(sort_order)대로 — 이름순이 아니다.
        assert order == ["dev", "b-team", "a-team"]

    def test_하위_부서_아래로는_못_옮긴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**막지 않으면 트리에서 떨어져 나간 고리가 생긴다.** 화면에서 사라지고
        순회는 무한히 돈다."""
        self._make(client, admin_headers, "dev", "개발본부")
        self._make(client, admin_headers, "metal2", "금속재료팀", "dev")

        response = client.post(
            "/api/workspaces/dev/move",
            json={"parent_slug": "metal2"},
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert "순환" in response.json()["error"]["message"]

    def test_자기_자신은_상위가_될_수_없다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._make(client, admin_headers, "dev", "개발본부")
        response = client.post(
            "/api/workspaces/dev/move", json={"parent_slug": "dev"}, headers=admin_headers
        )
        assert response.status_code == 409

    def test_활성_하위가_있으면_보관하지_못한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """부모만 보관하고 자식을 남기면 조직도에 구멍이 난다 — 그 팀은 보관된
        본부에 매달린 채로 계속 돌아간다(RA 의 O1 과 같은 규칙)."""
        self._make(client, admin_headers, "dev", "개발본부")
        self._make(client, admin_headers, "metal2", "금속재료팀", "dev")

        blocked = client.patch(
            "/api/workspaces/dev", json={"is_active": False}, headers=admin_headers
        )
        assert blocked.status_code == 409
        assert "금속재료팀" in blocked.json()["error"]["message"]

        # 자식부터 보관하면 부모도 보관된다.
        assert (
            client.patch(
                "/api/workspaces/metal2", json={"is_active": False}, headers=admin_headers
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/workspaces/dev", json={"is_active": False}, headers=admin_headers
            ).status_code
            == 200
        )

    def test_옮겨도_자료는_그대로다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**참조가 id 라서 트리를 옮겨도 데이터는 하나도 안 움직인다.**

        65는 조직 식별자를 데이터에 직접 박아 개편에 대응할 수단이 없었다.
        """
        self._make(client, admin_headers, "dev", "개발본부")
        team = self._make(client, admin_headers, "metal2", "금속재료팀")
        before = db.scalar(select(Workspace).where(Workspace.slug == "metal2"))
        assert before is not None
        before_id = before.id

        moved = client.post(
            "/api/workspaces/metal2/move", json={"parent_slug": "dev"}, headers=admin_headers
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["id"] == str(before_id) == str(team["id"])
        assert moved.json()["path"] == "개발본부 / 금속재료팀"

    def test_형제_순서를_사람이_정한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """조직도 순서는 이름순도 생성순도 아니다."""
        self._make(client, admin_headers, "one", "1팀")
        self._make(client, admin_headers, "two", "2팀")

        client.post(
            "/api/workspaces/two/reorder", json={"direction": "up"}, headers=admin_headers
        )
        rows = client.get("/api/workspaces?all=true", headers=admin_headers).json()
        order = [row["slug"] for row in rows if row["slug"] in {"one", "two"}]
        assert order == ["two", "one"]

    def test_끝에서_더_밀어도_망가지지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._make(client, admin_headers, "one", "1팀")
        response = client.post(
            "/api/workspaces/one/reorder", json={"direction": "up"}, headers=admin_headers
        )
        assert response.status_code == 200


class Test부서삭제:
    """**보관이 기본 수단이다.** 삭제는 잘못 만든 부서처럼 자료가 아예 없는
    경우를 위한 것이다.

    참조 목록을 손으로 관리하지 않는 것이 핵심이다 — RA 의 부서 삭제 500 버그가
    "참조 테이블 목록이 검사 함수에 하드코딩돼 새 테이블을 못 따라감" 이었고,
    시험 테이블이 늘어난 지금 그 위험이 현실이다.
    """

    def test_빈_부서는_지운다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        client.post(
            "/api/workspaces", json={"slug": "temp", "name": "임시팀"}, headers=admin_headers
        )
        # 만든 사람이 멤버로 들어가 있지만 멤버십은 CASCADE 라 막지 않는다.
        response = client.delete("/api/workspaces/temp", headers=admin_headers)
        assert response.status_code == 204
        assert (
            client.get("/api/workspaces/temp/references", headers=admin_headers).status_code
            == 404
        )

    def test_하위_부서가_있으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """FK 가 `RESTRICT` 다. **'DB 가 알아서 한다' 로 세면 화면은 삭제 가능이라
        해 놓고 누르는 순간 500 이 난다.**"""
        client.post(
            "/api/workspaces", json={"slug": "dev", "name": "개발본부"}, headers=admin_headers
        )
        client.post(
            "/api/workspaces",
            json={"slug": "team", "name": "팀", "parent_slug": "dev"},
            headers=admin_headers,
        )

        blockers = client.get("/api/workspaces/dev/references", headers=admin_headers).json()
        by_table = {row["table"]: row for row in blockers}
        assert by_table["workspaces"]["blocks_delete"] is True

        response = client.delete("/api/workspaces/dev", headers=admin_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MNX-WORKSPACES-0016"

    def test_자료가_있으면_거절하고_무엇인지_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str], workspace: Workspace
    ) -> None:
        created = client.post(
            "/api/materials",
            json={"family": "Metal", "category": "Steel", "grade": "SECC"},
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text

        references = client.get(
            f"/api/workspaces/{workspace.slug}/references", headers=admin_headers
        ).json()
        assert any(row["table"] == "materials" and row["blocks_delete"] for row in references)

        response = client.delete(f"/api/workspaces/{workspace.slug}", headers=admin_headers)
        assert response.status_code == 409
        assert "재료" in response.json()["error"]["message"]

    def test_끌어_놓은_자리에_들어간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """끌어 놓기는 '어디에' 뿐 아니라 '몇 번째에' 를 함께 말한다. 못 받으면
        옮길 때마다 맨 끝으로 가서 다시 위/아래를 눌러야 한다."""
        for slug, name in (("aa", "가"), ("bb", "나"), ("cc", "다")):
            client.post(
                "/api/workspaces", json={"slug": slug, "name": name}, headers=admin_headers
            )

        moved = client.post(
            "/api/workspaces/cc/move",
            json={"parent_slug": None, "before_slug": "aa"},
            headers=admin_headers,
        )
        assert moved.status_code == 200, moved.text

        rows = client.get("/api/workspaces?all=true", headers=admin_headers).json()
        order = [row["slug"] for row in rows if row["slug"] in {"aa", "bb", "cc"}]
        assert order == ["cc", "aa", "bb"]
