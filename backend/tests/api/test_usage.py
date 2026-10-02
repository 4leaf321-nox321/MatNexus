"""사용 현황 — **실제로 얼마나 잘 쓰고 있나**(2026-10-02).

요청: 「사용 현황 · 조회 집계를 관리자 페이지로. 특히 MCP 로 쓰는 숫자와 가입자까지 — 실제로
얼마나 잘 쓰고 있는지 보이게.」 접근 로그는 쓰기 · 로그인만 남겨 조회와 MCP 를 못 셌다.

이 시험이 지키는 것:

    계량기    로그인한 요청을 라우트 틀 · 길(화면 / MCP)로 센다 — 상세 조회는 무엇을 봤는지도
    안 세기   로그인 전 요청 · 폴링 · MCP 의 호출 보고 · 없는 주소
    도구      MCP 서버의 보고가 도구별 호출 · 실패 · 걸린 시간으로 쌓인다
    요약      쓴 사람(화면 / MCP / 둘 다) · 도구 순위 · 많이 본 재료 · 가입 · 토큰
              — 시스템 관리자만
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth import services as auth_services
from app.modules.materials.models import Material
from app.modules.usage import services
from app.modules.usage.models import McpToolDaily, UsageDaily, UsageViewDaily
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import usage_meter

PASSWORD = "Passw0rd!usage"
MCP = {"X-Client": "mcp"}


def _user(db: Session, workspace: Workspace, email: str, *, status: str = "active") -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=email.split("@")[0],
        status=status,
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def _material(db: Session) -> Material:
    one = Material(record_name="SECC_-_1.0", family="Metal", category="Steel", grade="SECC")
    db.add(one)
    db.commit()
    return one


def _counts(db: Session) -> list[tuple[str, str, str, int, int]]:
    db.expire_all()
    return [
        (row.client, row.method, row.route, row.requests, row.errors)
        for row in db.scalars(select(UsageDaily))
    ]


class Test계량기:
    def test_로그인한_요청을_라우트_틀과_길로_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(db)

        client.get(f"/api/materials/{material.id}", headers=admin_headers)
        client.get(f"/api/materials/{material.id}", headers=admin_headers)
        client.get(f"/api/materials/{material.id}", headers={**admin_headers, **MCP})

        counts = _counts(db)
        assert ("web", "GET", "/materials/{material_id}", 2, 0) in counts
        assert ("mcp", "GET", "/materials/{material_id}", 1, 0) in counts

    def test_상세_조회는_무엇을_봤는지도_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(db)

        client.get(f"/api/materials/{material.id}", headers=admin_headers)
        client.get(f"/api/materials/{material.id}", headers={**admin_headers, **MCP})

        db.expire_all()
        views = {
            (row.kind, row.entity_id, row.client): row.views
            for row in db.scalars(select(UsageViewDaily))
        }
        assert views[("material", str(material.id), "web")] == 1
        assert views[("material", str(material.id), "mcp")] == 1

    def test_실패한_요청은_오류로_센다_조회로는_안_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        missing = "00000000-0000-0000-0000-000000000001"

        got = client.get(f"/api/materials/{missing}", headers=admin_headers)

        assert got.status_code == 404
        assert ("web", "GET", "/materials/{material_id}", 1, 1) in _counts(db)
        db.expire_all()
        assert db.scalars(select(UsageViewDaily)).all() == []

    def test_로그인_전_폴링_없는_주소는_안_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        client.get("/api/materials")  # 로그인 전 — 누가 썼는지 모른다
        client.get("/api/notifications/unread-count", headers=admin_headers)  # 폴링
        client.get("/api/no-such-thing", headers=admin_headers)  # 맞는 라우트가 없다

        routes = {route for _c, _m, route, _r, _e in _counts(db)}
        assert "/notifications/unread-count" not in routes
        assert not any("no-such-thing" in route or "full_path" in route for route in routes)
        # 로그인 자체(POST /auth/login)는 로그인 전 요청이라 안 센다 — 로그인 수는 접근
        # 로그가 센다.
        assert "/auth/login" not in routes


class Test도구_보고:
    def test_도구별로_호출_실패_걸린_시간이_쌓이고_보고는_요청으로_안_센다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        headers = {**admin_headers, **MCP}
        for body in (
            {"tool": "get_material", "ok": True, "elapsed_ms": 100},
            {"tool": "get_material", "ok": True, "elapsed_ms": 200},
            {"tool": "get_material", "ok": False, "elapsed_ms": 30},
        ):
            got = client.post("/api/usage/mcp-calls", json=body, headers=headers)
            assert got.status_code == 204, got.text

        db.expire_all()
        row = db.scalar(select(McpToolDaily).where(McpToolDaily.tool == "get_material"))
        assert row is not None
        assert (row.calls, row.failures, row.elapsed_ms) == (3, 1, 330)
        assert not any(route == "/usage/mcp-calls" for _c, _m, route, _r, _e in _counts(db))

    def test_로그인_없이는_못_보고한다(self, client: TestClient) -> None:
        got = client.post("/api/usage/mcp-calls", json={"tool": "x"})
        assert got.status_code == 401


class Test요약:
    def test_쓴_사람_도구_조회_가입_토큰이_한_장에_선다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin: User,
        admin_headers: dict[str, str],
    ) -> None:
        material = _material(db)
        _user(db, workspace, "newbie@example.com", status="pending")
        _user(db, workspace, "web@example.com")
        ai_user = _user(db, workspace, "ai@example.com")
        auth_services.create_pat(db, ai_user, "AI 연결", None)
        web = _headers(client, "web@example.com")
        ai = {**_headers(client, "ai@example.com"), **MCP}

        client.get(f"/api/materials/{material.id}", headers=web)
        client.get(f"/api/materials/{material.id}", headers=ai)
        client.post(
            "/api/usage/mcp-calls",
            json={"tool": "property_coverage", "elapsed_ms": 50},
            headers=ai,
        )

        got = client.get("/api/usage/summary", params={"days": 7}, headers=admin_headers)

        assert got.status_code == 200, got.text
        body = got.json()
        assert body["users"]["pending"] == 1
        assert body["users"]["signups"] >= 4  # 관리자 · 대기 · 화면 · AI
        assert body["activity"]["mcp_users"] == 1
        # 이 요약을 연 관리자의 요청은 응답 **뒤에** 세므로 이 요약에는 아직 안 들어 있다.
        assert body["activity"]["web_users"] == 1
        assert body["activity"]["any_users"] == 2
        assert body["mcp"]["calls"] == 1
        assert body["mcp"]["by_tool"][0]["tool"] == "property_coverage"
        assert body["mcp"]["by_user"][0]["name"] == "ai"
        assert body["mcp"]["tokens"]["users"] == 1
        top = body["views"]["materials"][0]
        assert top["id"] == str(material.id)
        assert top["views"] == 2 and top["viewers"] == 2 and top["mcp_views"] == 1
        assert "SECC_-_1.0" in top["label"]
        areas = {one["area"]: one for one in body["requests"]["by_area"]}
        assert areas["materials"]["label"] == "재료"
        assert areas["materials"]["mcp"] == 1
        created = {one["key"]: one["created"] for one in body["content"]}
        assert created["materials"] == 1
        names = {one["name"] for one in body["people"]}
        assert {"web", "ai"} <= names
        assert body["measured_since"] is not None
        assert len(body["activity"]["by_day"]) == 7

    def test_시스템_관리자만_본다(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        _user(db, workspace, "member@example.com")

        got = client.get("/api/usage/summary", headers=_headers(client, "member@example.com"))

        assert got.status_code == 403

    def test_계량기가_쌓기_전_날짜는_measured_since_로_가른다(self, db: Session) -> None:
        """집계를 들인 날 전은 0 으로 보인다 — 안 쓴 것이 아니라 안 셌던 것이다."""
        some = User(
            email="x@example.com", password_hash="x", display_name="x", status="active"
        )
        db.add(some)
        db.commit()
        earlier = usage_meter.today() - timedelta(days=3)
        usage_meter.record_request(
            db,
            user_id=some.id,
            client="web",
            method="GET",
            route="/materials",
            failed=False,
            day=earlier,
        )
        db.commit()

        got = services.summary(db, days=30)

        assert got.measured_since == earlier
        assert services.area_of("/test-runs/{run_id}") == "test-runs"
