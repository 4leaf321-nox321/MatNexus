"""물성 핸드북 — **검토 없이 정본이 바뀌는 길이 없어야 한다.**

무는 자리를 「절이 보인다」 보다 **「초안이 바로 본문이 되지 않는다」·「검토자가 아니면
승인 못 한다」·「그림이 아닌 것은 안 받는다」** 에 둔다. 앞엣것은 화면에서 바로
보이고, 뒤엣것은 조용히 틀린다 — 특히 나중에 AI 가 쓰게 될 때.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.guide import services

DOC = {
    "key": "dma-prony",
    "title": "DMA 에서 Prony 카드까지",
    "kind": "calculation",
    "topic": "dma",
}


def doc_body(*texts: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            for text in texts
        ],
    }


@pytest.fixture
def member_headers(client: TestClient, db: Session, workspace: Any) -> dict[str, str]:
    """검토자가 아닌 사람 — 부서 구성원."""
    from app.modules.accounts.models import User
    from app.modules.auth import security
    from app.modules.workspaces.models import WorkspaceMember

    user = User(
        email="member",
        password_hash=security.hash_password("pw12345678"),
        display_name="구성원",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    login = client.post("/api/auth/login", json={"email": "member", "password": "pw12345678"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def section(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    made = client.post("/api/guide/documents", json=DOC, headers=admin_headers)
    assert made.status_code == 201, made.text
    section = client.post(
        "/api/guide/documents/dma-prony/sections",
        json={
            "key": "master-curve",
            "title": "마스터커브",
            "body": doc_body("시간-온도 중첩"),
        },
        headers=admin_headers,
    )
    assert section.status_code == 201, section.text
    body: dict[str, Any] = section.json()
    return body


class Test초안과_승인:
    def test_구성원의_초안은_본문을_바꾸지_않는다(
        self, client: TestClient, member_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        """**여기가 진짜 지키는 것이다.**"""
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("고친 것"), "note": "오타"},
            headers=member_headers,
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["status"] == "pending"
        now = client.get(f"/api/guide/sections/{section['id']}", headers=member_headers).json()
        assert services.plain_text(now["body"]) == "시간-온도 중첩"
        assert now["pending_count"] == 1

    def test_구성원은_바로_승인_못_한다(
        self, client: TestClient, member_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("고친 것"), "publish": True},
            headers=member_headers,
        )
        assert sent.status_code == 403
        assert sent.json()["error"]["code"] == "MNX-GUIDE-0005"

    def test_승인하면_본문이_되고_판이_오른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        member_headers: dict[str, str],
        section: dict[str, Any],
    ) -> None:
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("고친 것")},
            headers=member_headers,
        ).json()
        queue = client.get("/api/guide/revisions?status=pending", headers=admin_headers).json()
        assert [r["id"] for r in queue] == [sent["id"]]

        done = client.post(
            f"/api/guide/revisions/{sent['id']}/approve",
            json={"note": "좋음"},
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        now = client.get(f"/api/guide/sections/{section['id']}", headers=admin_headers).json()
        assert services.plain_text(now["body"]) == "고친 것"
        assert now["revision_no"] == 2
        assert now["pending_count"] == 0

        # 두 번은 안 된다.
        again = client.post(
            f"/api/guide/revisions/{sent['id']}/approve", json={}, headers=admin_headers
        )
        assert again.status_code == 409

    def test_거절하면_본문은_그대로다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        member_headers: dict[str, str],
        section: dict[str, Any],
    ) -> None:
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("틀린 것")},
            headers=member_headers,
        ).json()
        client.post(
            f"/api/guide/revisions/{sent['id']}/reject",
            json={"note": "근거 없음"},
            headers=admin_headers,
        )
        now = client.get(f"/api/guide/sections/{section['id']}", headers=admin_headers).json()
        assert services.plain_text(now["body"]) == "시간-온도 중첩"
        history = client.get(
            f"/api/guide/sections/{section['id']}/revisions", headers=admin_headers
        ).json()
        assert history[0]["status"] == "rejected" and history[0]["review_note"] == "근거 없음"

    def test_검토자는_바로_낸다(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("검토자가 고침"), "publish": True},
            headers=admin_headers,
        )
        assert sent.status_code == 201 and sent.json()["status"] == "approved"
        now = client.get(f"/api/guide/sections/{section['id']}", headers=admin_headers).json()
        assert services.plain_text(now["body"]) == "검토자가 고침"

    def test_편집기_문서가_아니면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        """아무 JSON 이나 정본이 되면 화면이 그리다 죽고 그 절은 아무도 못 연다."""
        sent = client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": {"hello": "world"}},
            headers=admin_headers,
        )
        assert sent.status_code == 422


class Test구조:
    def test_구성원은_문서를_못_만든다(
        self, client: TestClient, member_headers: dict[str, str]
    ) -> None:
        made = client.post("/api/guide/documents", json=DOC, headers=member_headers)
        assert made.status_code == 403

    def test_같은_키는_한_번(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        again = client.post("/api/guide/documents", json=DOC, headers=admin_headers)
        assert again.status_code == 409

    def test_목차에_절이_순서대로(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        client.post(
            "/api/guide/documents/dma-prony/sections",
            json={"key": "prony", "title": "Prony 시리즈", "position": 2},
            headers=admin_headers,
        )
        docs = client.get("/api/guide/documents", headers=admin_headers).json()
        assert [s["key"] for s in docs[0]["sections"]] == ["master-curve", "prony"]


class Test검색:
    def test_가운데_일치로_찾고_자리를_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        hits = client.get("/api/guide/search?q=온도", headers=admin_headers).json()
        assert len(hits) == 1
        assert hits[0]["section_title"] == "마스터커브"
        assert "온도" in hits[0]["snippet"]

    def test_거절된_초안은_안_찾힌다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        member_headers: dict[str, str],
        section: dict[str, Any],
    ) -> None:
        """검색은 **승인된 본문**만 본다 — 초안의 글자가 걸리면 없는 내용을 찾는다."""
        client.post(
            f"/api/guide/sections/{section['id']}/revisions",
            json={"body": doc_body("초안에만 있는 낱말 XYZZY")},
            headers=member_headers,
        )
        hits = client.get("/api/guide/search?q=XYZZY", headers=admin_headers).json()
        assert hits == []


class Test그림:
    def test_그림은_주소가_되어_돌아온다(
        self, client: TestClient, admin_headers: dict[str, str], section: dict[str, Any]
    ) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        sent = client.post(
            "/api/guide/assets?document_key=dma-prony",
            files={"file": ("figure.png", png, "image/png")},
            headers=admin_headers,
        )
        assert sent.status_code == 201, sent.text
        url = sent.json()["url"]
        assert url.startswith("/api/guide/assets/")
        got = client.get(url, headers=admin_headers)
        assert got.status_code == 200 and got.content == png
        assert "sandbox" in got.headers.get("content-security-policy", "")

    def test_그림이_아니면_안_받는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        sent = client.post(
            "/api/guide/assets",
            files={"file": ("evil.html", b"<script>1</script>", "text/html")},
            headers=admin_headers,
        )
        assert sent.status_code == 415


def test_평문_뽑기는_문단_경계를_띄운다() -> None:
    """안 띄우면 앞 문단 끝과 뒤 문단 첫 글자가 붙어 없는 단어가 검색에 걸린다."""
    body = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "치수"}],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": "변수"}]},
        ],
    }
    assert services.plain_text(body) == "치수 변수"
    assert services.outline(body) == [{"level": 2, "text": "치수"}]
