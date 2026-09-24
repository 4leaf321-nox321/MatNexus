"""내 자료에 일어난 일 — **등록자가 묻는 자리**(2026-09-25, ADR 0035 남은 것).

고칠 권한이 등록자 밖으로 — 자료 관리자·편집을 받은 부서로 — 넓어졌는데, 등록자는 제 자료에
누가 손댔는지 볼 길이 없었다. 감사 화면은 관리자 것이고, **남이 칸을 고친 일은 감사에 아예
안 남았다**(값 수정은 원래 감사 대상이 아니다). 이제 판정 자리가 「남의 자료 고침」 을 근거와
함께 남기고, 등록자는 `GET /audit/mine` 으로 제 자료의 기록만 본다.

    남이 고치면 남는다              근거(편집을 받은 부서 · 자료 관리자)와 함께
    내가 고친 것은 안 남는다         감사를 값 수정으로 채우지 않는다
    일괄은 한 줄이다                 300건이 300줄이면 표를 못 쓴다
    미리보기는 안 남는다             커밋한 쓰기에만 — 기록이 그 변경과 한 트랜잭션이다
    지운 것 · 넘긴 것도 제 이력이다   기록마다 「누구의 자료였나」 가 채워진다
    내 토큰으로 AI 가 한 일은 보인다  손으로 한 일이 아니다
    남의 이력은 못 본다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry

TAXONOMY = {"family": "Metal", "category": "Steel", "grade": "HISTGRADE"}


def _person(
    client: TestClient, admin_headers: dict[str, str], *, slug: str, email: str, name: str
) -> tuple[str, dict[str, str]]:
    made = client.post(
        "/api/accounts",
        json={"email": email, "display_name": name, "workspace_slug": slug, "role": "member"},
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    body = made.json()
    token = client.post(
        "/api/auth/login", json={"email": email, "password": body["temporary_password"]}
    ).json()["access_token"]
    account_id = body["account"]["id"] if "account" in body else body["id"]
    return str(account_id), {"Authorization": f"Bearer {token}"}


@pytest.fixture
def people(
    client: TestClient, admin_headers: dict[str, str]
) -> dict[str, tuple[str, dict[str, str]]]:
    """앨리스(등록자) · 앨런(같은 부서) · 보라(다른 부서, 자료 관리자가 된다)."""
    for slug in ("hist-a", "hist-b"):
        made = client.post(
            "/api/workspaces",
            json={"name": f"{slug} 부서", "slug": slug},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
    # 등급 낱말은 관리자가 심는다 — 멤버는 있는 등급으로 만든다.
    seeded = client.post("/api/materials", json=TAXONOMY, headers=admin_headers)
    assert seeded.status_code == 201, seeded.text
    found = {
        "alice": _person(
            client, admin_headers, slug="hist-a", email="alice@h.com", name="앨리스"
        ),
        "allen": _person(
            client, admin_headers, slug="hist-a", email="allen@h.com", name="앨런"
        ),
        "bora": _person(client, admin_headers, slug="hist-b", email="bora@h.com", name="보라"),
    }
    granted = client.post(
        f"/api/accounts/{found['bora'][0]}/data-manager",
        json={"is_data_manager": True},
        headers=admin_headers,
    )
    assert granted.status_code == 200, granted.text
    return found


def _material(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={**TAXONOMY, "details": f"D{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _mine(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    got = client.get("/api/audit/mine", headers=headers)
    assert got.status_code == 200, got.text
    items: list[dict[str, Any]] = got.json()["items"]
    return items


class Test남이_고치면:
    def test_편집을_받은_부서_사람이_고치면_근거와_함께_남는다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, allen = people["allen"]
        material = _material(client, alice)
        given = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"edit_workspace_slug": "hist-a"},
            headers=alice,
        )
        assert given.status_code == 200, given.text

        edited = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "팀이 고침"}, headers=allen
        )
        assert edited.status_code == 200, edited.text

        seen = [one for one in _mine(client, alice) if one["action"] == "data.edited_by_other"]
        assert len(seen) == 1
        assert seen[0]["actor_label"] == "앨런"
        assert seen[0]["target_id"] == material["id"]
        assert seen[0]["target_label"] == material["record_name"]
        assert seen[0]["changes"]["basis"] == "편집을 받은 부서(hist-a 부서)"

    def test_자료_관리자가_고쳐도_남는다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        edited = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "관리자가 고침"}, headers=bora
        )
        assert edited.status_code == 200, edited.text
        seen = [one for one in _mine(client, alice) if one["action"] == "data.edited_by_other"]
        assert [one["changes"]["basis"] for one in seen] == ["자료 관리자"]

    def test_내가_고친_것은_안_남는다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        """**감사를 값 수정으로 채우지 않는다** — 제 자료를 제가 고친 것은 원래 규칙대로다."""
        _, alice = people["alice"]
        material = _material(client, alice)
        client.patch(f"/api/materials/{material['id']}", json={"alias": "내가"}, headers=alice)
        assert _mine(client, alice) == []
        rows = db.scalars(
            select(AuditEntry).where(AuditEntry.action == "data.edited_by_other")
        ).all()
        assert rows == []

    def test_일괄로_고친_것은_한_줄에_몇_건인지_싣는다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """300건이 300줄이면 이 표에서 정작 찾을 것을 못 찾는다(처리 배치를 한 줄로 남기는 것과
        같은 판단). 같은 요청 · 같은 등록자 · 같은 근거면 한 줄이다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=alice
        ).json()
        ids = [
            client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": "MD"},
                headers=alice,
            ).json()["id"]
            for _ in range(3)
        ]
        done = client.post(
            "/api/specimens/bulk-update",
            json={"specimen_ids": ids, "field": "orientation", "value": "TD"},
            headers=bora,
        )
        assert done.status_code == 200, done.text
        assert done.json()["updated"] == 3

        seen = [one for one in _mine(client, alice) if one["action"] == "data.edited_by_other"]
        assert len(seen) == 1, "일괄 수정이 여러 줄로 남았다"
        assert seen[0]["changes"]["count"] == 3
        assert len(seen[0]["changes"]["targets"]) == 3
        assert seen[0]["target_label"].endswith(" 외 2건")

    def test_미리보기는_안_남는다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """삭제 계획은 판정을 부르지만 **커밋하지 않는다** — 기록이 그 변경과 한 트랜잭션이라
        아무것도 안 남는다. 판정을 불렀다고 「고쳤다」 가 남으면 등록자는 없는 일을 본다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        plan = client.post(
            "/api/materials/delete-plan",
            json={"material_ids": [material["id"]], "cascade": True},
            headers=bora,
        )
        assert plan.status_code == 200, plan.text
        assert _mine(client, alice) == []


class Test제_이력:
    def test_남이_지운_것도_제_이력에_선다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """삭제 기록은 전부터 있었지만 **누구의 자료였는지**가 없어 등록자에게 못 보였다 — 이제
        기록마다 그때의 등록자가 채워진다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        gone = client.delete(f"/api/materials/{material['id']}", headers=bora)
        assert gone.status_code in (200, 204), gone.text
        actions = {one["action"] for one in _mine(client, alice)}
        assert "material.deleted" in actions

    def test_내가_지운_내_자료는_안_보인다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """삭제는 감사에 남지만(되돌릴 수 없다) **내가 한 일은 내가 안다** — 이 자리는 남이 한
        일을 보는 곳이다. 여기가 새면 제 손으로 한 일이 목록을 덮는다."""
        _, alice = people["alice"]
        material = _material(client, alice)
        gone = client.delete(f"/api/materials/{material['id']}", headers=alice)
        assert gone.status_code in (200, 204), gone.text
        assert _mine(client, alice) == []

    def test_넘겨받으면_받은_사람의_이력이다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """제 것을 제가 넘기면 그 일은 **받은 사람**의 것이다 — 「누가 나에게 넘겼나」. 넘긴
        사람에게는 제가 한 일이라 안 보인다."""
        allen_id, allen = people["allen"]
        _, alice = people["alice"]
        material = _material(client, alice)
        handed = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"registrant_id": allen_id},
            headers=alice,
        )
        assert handed.status_code == 200, handed.text
        got = [one for one in _mine(client, allen) if one["action"] == "ownership.changed"]
        assert len(got) == 1 and got[0]["actor_label"] == "앨리스"
        assert not [
            one for one in _mine(client, alice) if one["action"] == "ownership.changed"
        ]

    def test_관리자가_남에게_넘기면_원래_등록자의_이력이다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        allen_id, allen = people["allen"]
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        moved = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"registrant_id": allen_id},
            headers=bora,
        )
        assert moved.status_code == 200, moved.text
        taken = [one for one in _mine(client, alice) if one["action"] == "ownership.changed"]
        assert len(taken) == 1 and taken[0]["actor_label"] == "보라"
        assert not [
            one for one in _mine(client, allen) if one["action"] == "ownership.changed"
        ]

    def test_내_토큰으로_AI_가_한_일은_보인다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """내가 손으로 한 일은 빼지만 **AI 가 내 이름으로 한 일은 남긴다** — 손으로 한 일이
        아니다."""
        _, alice = people["alice"]
        material = _material(client, alice)
        changed = client.patch(
            f"/api/materials/{material['id']}",
            json={"alias": "AI 가 고침"},
            headers={**alice, "X-Client": "mcp"},
        )
        assert changed.status_code == 200, changed.text
        seen = _mine(client, alice)
        assert [one["action"] for one in seen] == ["values.changed_by_client"]
        assert seen[0]["client"] == "mcp"

    def test_남의_이력은_못_본다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, allen = people["allen"]
        _, bora = people["bora"]
        material = _material(client, alice)
        client.patch(
            f"/api/materials/{material['id']}", json={"alias": "관리자"}, headers=bora
        )
        assert _mine(client, alice), "앨리스에게는 보여야 한다"
        assert _mine(client, allen) == []
        # 감사 화면(관리자 것)은 여전히 막혀 있다.
        assert client.get("/api/audit", headers=allen).status_code == 403

    def test_쪽으로_나가고_최근_것이_위다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, bora = people["bora"]
        first = _material(client, alice)
        second = _material(client, alice)
        for one in (first, second):
            client.patch(f"/api/materials/{one['id']}", json={"alias": "x"}, headers=bora)
        page = client.get("/api/audit/mine", params={"limit": 1}, headers=alice).json()
        assert page["total"] == 2 and page["limit"] == 1 and len(page["items"]) == 1
        assert page["items"][0]["target_id"] == second["id"]
