"""외부 연동 설정 — **토큰은 넣을 수만 있고 다시 볼 수 없다**(2026-10-23).

시스템 관리자만             보기까지 — 주소 · 토큰 주인이 사내 배치를 말한다
토큰은 봉인해 둔다           DB 덤프에 평문이 없다 · 응답 · 감사에도 없다
안 보낸 토큰은 그대로         주소만 고쳐도 토큰이 사라지지 않는다 · 지우기는 따로
연결 확인은 실제로 묻는다      토큰 주인 · 이어진 물성 수 · 거절 · 못 닿음을 가른다
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_catalog_contribute import member_headers

from app.modules.audit.models import AuditEntry
from app.modules.integrations import services
from app.modules.integrations.models import IntegrationConnection
from app.modules.workspaces.models import Workspace
from app.shared import secretbox
from app.shared import testscope as testscope_client

URL = "/api/integrations/testscope"
#: 시험용 가짜 토큰 — 어디에도 닿지 않는다.
TOKEN = "tsp_test_read_only_0001"


def _save(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.put(URL, json={"base_url": "http://127.0.0.1:8020", **body}, headers=headers)


@pytest.fixture
def testscope() -> Iterator[list[httpx.Request]]:
    """모의 TestScope — 받은 요청을 모은다. 토큰이 맞을 때만 답한다."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"error": {"code": "TS-AUTH"}})
        if request.url.path == "/api/auth/me":
            return httpx.Response(200, json={"display_name": "연동 계정", "email": "bot"})
        if request.url.path == "/api/properties":
            return httpx.Response(200, json=[{"code": "mechanical.tensile_strength"}] * 3)
        return httpx.Response(404)

    testscope_client.TRANSPORT = httpx.MockTransport(answer)
    try:
        yield seen
    finally:
        testscope_client.TRANSPORT = None


class Test설정:
    def test_토큰은_봉인해_두고_어디에도_다시_싣지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        saved = _save(client, admin_headers, token=TOKEN)
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["base_url"] == "http://127.0.0.1:8020/api"
        assert body["link_url"] == "http://127.0.0.1:8020"
        assert body["has_token"] and body["token_readable"] and body["configured"]
        assert TOKEN not in saved.text
        assert TOKEN not in client.get(URL, headers=admin_headers).text

        row = db.scalar(select(IntegrationConnection))
        assert row is not None
        assert row.token_sealed.startswith(secretbox.PREFIX) and TOKEN not in row.token_sealed
        assert secretbox.unseal(row.token_sealed) == TOKEN
        assert services.credentials(db, "testscope") == ("http://127.0.0.1:8020/api", TOKEN)

        entry = db.scalar(select(AuditEntry).where(AuditEntry.action == "integration.updated"))
        assert entry is not None and entry.changes["token"] == "(바뀜)"
        assert TOKEN not in str(entry.changes)

    def test_안_보낸_토큰은_그대로_지우기는_따로(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        assert _save(client, admin_headers, token=TOKEN).status_code == 200
        moved = _save(client, admin_headers, base_url="http://10.0.0.5:8020/api/", token="")
        assert moved.status_code == 200, moved.text
        assert moved.json()["base_url"] == "http://10.0.0.5:8020/api"
        assert services.credentials(db, "testscope") == ("http://10.0.0.5:8020/api", TOKEN)

        cleared = _save(client, admin_headers, clear_token=True)
        assert cleared.json()["has_token"] is False
        assert services.credentials(db, "testscope") is None

    def test_주소는_http_로만(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        refused = _save(client, admin_headers, base_url="testscope:8020")
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-INTEGRATIONS-0002"
        assert (
            client.get("/api/integrations/nowhere", headers=admin_headers).status_code == 404
        )

    def test_시스템_관리자만_본다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> None:
        member = member_headers(client, db, workspace)
        assert client.get("/api/integrations", headers=member).status_code == 403
        assert _save(client, member, token=TOKEN).status_code == 403
        assert client.post(f"{URL}/check", headers=member).status_code == 403
        assert db.scalar(select(IntegrationConnection)) is None
        listed = client.get("/api/integrations", headers=admin_headers).json()
        assert [(one["system"], one["configured"]) for one in listed] == [("testscope", False)]


class Test연결_확인:
    def test_토큰_주인과_이어진_물성_수를_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        testscope: list[httpx.Request],
    ) -> None:
        assert _save(client, admin_headers, token=TOKEN).status_code == 200
        checked = client.post(f"{URL}/check", headers=admin_headers)
        assert checked.status_code == 200, checked.text
        result = checked.json()
        assert result["ok"] is True
        assert (result["who"], result["linked_properties"]) == ("연동 계정", 3)
        assert [one.url.path for one in testscope] == ["/api/auth/me", "/api/properties"]
        shown = client.get(URL, headers=admin_headers).json()
        assert shown["check_ok"] is True and "연동 계정" in shown["check_message"]

        # 주소를 바꾸면 지난 확인은 옛 주소의 것이다 — 지운다.
        assert _save(client, admin_headers, base_url="http://10.0.0.5:8020").status_code == 200
        assert client.get(URL, headers=admin_headers).json()["check_ok"] is None

    def test_거절과_못_닿음을_가른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        testscope: list[httpx.Request],
    ) -> None:
        assert _save(client, admin_headers, token="tsp_expired").status_code == 200
        refused = client.post(f"{URL}/check", headers=admin_headers).json()
        assert refused["ok"] is False and "거절" in refused["message"]
        # 거절이면 거기서 멈춘다 — 토큰 주인을 모르는 채 물성까지 묻지 않는다.
        assert [one.url.path for one in testscope] == ["/api/auth/me"]

        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("연결 거부", request=request)

        testscope_client.TRANSPORT = httpx.MockTransport(down)
        unreachable = client.post(f"{URL}/check", headers=admin_headers).json()
        assert unreachable["ok"] is False and "닿지 못했습니다" in unreachable["message"]

    def test_설정이_없으면_묻지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        testscope: list[httpx.Request],
    ) -> None:
        answer = client.post(f"{URL}/check", headers=admin_headers).json()
        assert answer["ok"] is False and "API 주소" in answer["message"]
        assert _save(client, admin_headers).status_code == 200
        answer = client.post(f"{URL}/check", headers=admin_headers).json()
        assert "토큰을 먼저" in answer["message"]
        assert testscope == []
