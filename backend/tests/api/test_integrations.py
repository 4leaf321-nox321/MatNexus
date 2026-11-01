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

from app.config import get_settings
from app.modules.audit.models import AuditEntry
from app.modules.integrations import services
from app.modules.integrations.models import IntegrationConnection
from app.modules.workspaces.models import Workspace
from app.shared import secretbox, sp_connection
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
        assert [(one["system"], one["configured"]) for one in listed] == [
            ("testscope", False),
            ("sp_core", False),
        ]


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


# ── SP 코어 ────────────────────────────────────────────────────────────────────────────

SP_URL = "/api/integrations/sp_core"
#: 시험용 가짜 `core:read` 토큰.
SP_TOKEN = "sp_core_read_0001"
CATALOG = {
    "system": "SP-운영",
    "revision": "r12",
    "types": [
        {"slug": "organization", "label": "기관"},
        {"slug": "property", "label": "물성"},
    ],
}


@pytest.fixture
def sp() -> Iterator[list[httpx.Request]]:
    """모의 SP 코어 창구 — 카탈로그만 답한다. 토큰이 맞을 때만."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("Authorization") != f"Bearer {SP_TOKEN}":
            return httpx.Response(401, json={"error": {"code": "APP-AUTH"}})
        if request.url.path == "/api/core":
            return httpx.Response(200, json=CATALOG)
        return httpx.Response(404, json={"error": {"code": "APP-NOT-FOUND"}})

    services.SP_TRANSPORT = httpx.MockTransport(answer)
    try:
        yield seen
    finally:
        services.SP_TRANSPORT = None


def _save_sp(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.put(SP_URL, json={"base_url": "https://sp.example", **body}, headers=headers)


class TestSP코어:
    """SP 코어 온톨로지 받기의 주소 · 토큰도 이 화면에서(2026-10-27, 사용자 요청).

    처음(ADR 0063)에는 서버 `.env` 에만 넣을 수 있어, TestScope 를 화면으로 붙인 사람이 SP 를
    어디서 넣는지 찾지 못했다.
    """

    def test_주소를_코어_창구로_맞추고_토큰은_봉인한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        for typed in (
            "https://sp.example/",
            "https://sp.example/api",
            "https://sp.example/api/core/",
        ):
            saved = _save_sp(client, admin_headers, base_url=typed, token=SP_TOKEN)
            assert saved.status_code == 200, saved.text
            assert saved.json()["base_url"] == "https://sp.example/api/core", typed
        body = saved.json()
        assert body["label"] == "Standard Platform 코어 온톨로지"
        assert body["link_url"] == "https://sp.example"
        assert body["configured"] and not body["from_env"]
        assert SP_TOKEN not in saved.text
        found = sp_connection.connection(db)
        assert found == sp_connection.Connection(
            "https://sp.example/api/core", SP_TOKEN, "screen"
        )

    def test_화면이_env_보다_먼저고_env_만_있으면_그렇다고_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "sp_core_url", "https://old-sp.example/api/core")
        monkeypatch.setattr(settings, "sp_core_token", "env-token")
        shown = client.get(SP_URL, headers=admin_headers).json()
        assert shown["configured"] is False and shown["from_env"] is True
        assert sp_connection.connection(db) == sp_connection.Connection(
            "https://old-sp.example/api/core", "env-token", "env"
        )

        assert _save_sp(client, admin_headers, token=SP_TOKEN).status_code == 200
        shown = client.get(SP_URL, headers=admin_headers).json()
        assert shown["configured"] is True and shown["from_env"] is False
        found = sp_connection.connection(db)
        assert found is not None and (found.url, found.source) == (
            "https://sp.example/api/core",
            "screen",
        )

    def test_연결_확인은_카탈로그를_읽고_거절과_없는_주소를_가른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        sp: list[httpx.Request],
    ) -> None:
        assert _save_sp(client, admin_headers, token=SP_TOKEN).status_code == 200
        result = client.post(f"{SP_URL}/check", headers=admin_headers).json()
        assert result["ok"] is True and result["core_types"] == 2, result
        assert "판 r12" in result["message"] and "기관" in result["message"]
        assert [str(one.url) for one in sp] == ["https://sp.example/api/core"]
        assert client.get(SP_URL, headers=admin_headers).json()["check_ok"] is True

        assert _save_sp(client, admin_headers, token="expired").status_code == 200
        refused = client.post(f"{SP_URL}/check", headers=admin_headers).json()
        assert refused["ok"] is False and "거절" in refused["message"]

        moved = _save_sp(
            client, admin_headers, base_url="https://sp.example/elsewhere", token=SP_TOKEN
        )
        assert moved.status_code == 200
        missing = client.post(f"{SP_URL}/check", headers=admin_headers).json()
        assert missing["ok"] is False and "코어 API 가 없습니다" in missing["message"]

    def test_받기는_재기동_없이_화면의_값으로_돈다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        from app.modules.sp_core import sync

        assert sync.configured(db) is False
        refused = client.post("/api/sp-core/sync", json={}, headers=admin_headers)
        assert refused.status_code == 409 and "외부 연동" in refused.json()["error"]["message"]

        assert _save_sp(client, admin_headers, token=SP_TOKEN).status_code == 200
        assert sync.configured(db) is True
        asked: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            asked.append(request)
            return httpx.Response(200, json=CATALOG)

        with sync.open_client(db, transport=httpx.MockTransport(answer)) as sp_client:
            assert sp_client.catalog()["revision"] == "r12"
        assert str(asked[0].url).startswith("https://sp.example/api/core")
        assert asked[0].headers["Authorization"] == f"Bearer {SP_TOKEN}"

        status = client.get("/api/sp-core/status", headers=admin_headers).json()
        assert status["configured"] is True and status["source"] == "https://sp.example"
        assert (
            client.post("/api/sp-core/sync", json={}, headers=admin_headers).status_code == 202
        )
