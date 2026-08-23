"""감사 로그 — **무엇이 바뀌었고 누가 승인했는가.**

접근 로그와 목적이 다르다. 접근 로그는 *"그 화면에서 안 돼요"* 를 재현하는
지원용이고, 이것은 무결성용이다.

여기서 지키는 것은 넷이다.

    쓰는 API 가 없다              만들 수 있으면 감사가 아니다
    지워져도 남는다               카드가 사라져도 누가 확정했는지는 남는다
    바뀐 것만 담는다              통째로 담으면 무엇이 바뀌었는지 안 보인다
    아무나 못 본다                "누가 무엇을 했나" 는 사람에 대한 정보다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from app.shared import audit


@pytest.fixture
def card(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    """확정할 수 있는 카드 하나. 값은 안 본다 — 감사 기록만 본다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "AUDIT", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    from app.modules.fitting.models import PropertyCard
    from app.modules.tests.models import TestType

    test_type = db.scalars(db.query(TestType).filter_by(key="tensile").statement).one()
    item = PropertyCard(
        material_id=uuid.UUID(material["id"]),
        test_type_id=test_type.id,
        orientation="MD",
        label="감사 대상",
        status="draft",
        source={},
        blocks={},
    )
    db.add(item)
    db.commit()
    return {"id": str(item.id), "material_id": material["id"]}


class Test기록:
    def test_확정이_남는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**이 값으로 해석이 돌 수 있다.** 누가 언제 올렸는지가 남아야 한다."""
        done = client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        assert done.status_code == 200, done.text

        entries = client.get(
            "/api/audit", params={"target_id": card["id"]}, headers=admin_headers
        ).json()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["action"] == "card.published"
        assert entry["target_label"] == "감사 대상"
        assert entry["changes"]["status"] == {"before": "draft", "after": "published"}
        # 접근 로그·파일 로그와 잇는 끈.
        assert entry["request_id"]

    def test_지워도_기록은_남는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**대상에 외래키를 안 건 이유가 이것이다.** 카드가 사라져도 "그 카드가
        있었고 누가 지웠다" 는 남아야 한다."""
        gone = client.delete(f"/api/fitting/cards/{card['id']}", headers=admin_headers)
        assert gone.status_code == 204, gone.text

        entries = client.get(
            "/api/audit", params={"target_id": card["id"]}, headers=admin_headers
        ).json()
        assert [item["action"] for item in entries] == ["card.deleted"]
        assert entries[0]["target_label"] == "감사 대상"

    def test_사람_이름을_함께_박는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """계정이 지워지면 누가 했는지 모르게 되는데, 그건 감사 로그가 존재하는
        이유와 정면으로 어긋난다."""
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        entry = client.get(
            "/api/audit", params={"target_id": card["id"]}, headers=admin_headers
        ).json()[0]
        assert entry["actor_label"]
        assert entry["actor_id"]

    def test_최근_것부터_준다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        client.post(f"/api/fitting/cards/{card['id']}/deprecate", headers=admin_headers)
        actions = [
            item["action"]
            for item in client.get(
                "/api/audit", params={"target_id": card["id"]}, headers=admin_headers
            ).json()
        ]
        assert actions == ["card.deprecated", "card.published"]


class Test쓰는길:
    def test_감사_기록을_만드는_API_는_없다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**만들 수 있으면 감사가 아니다.** 기록은 변경이 일어난 그 트랜잭션
        안에서만 생긴다."""
        for method in ("post", "patch", "delete"):
            response = getattr(client, method)("/api/audit", headers=admin_headers)
            assert response.status_code in (404, 405), f"{method}: {response.status_code}"


class Test가시성:
    def test_일반_사용자는_못_본다(self, client: TestClient, db: Session) -> None:
        """**"누가 무엇을 했나" 는 그 자체로 사람에 대한 정보다.**

        관리자가 아닌 사람에게는 목록을 비워 주지 않고 **막는다.** 빈 목록은
        "기록이 없다" 로 읽히는데 그건 사실이 아니다.
        """
        from app.modules.accounts.models import User
        from app.modules.auth import security

        db.add(
            User(
                email="member@example.com",
                password_hash=security.hash_password("member-password-1"),
                display_name="일반",
                status="active",
            )
        )
        db.commit()
        token = client.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": "member-password-1"},
        ).json()["access_token"]

        response = client.get("/api/audit", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert "관리자" in response.text


class Test바뀐것만:
    def test_안_바뀐_값은_안_담는다(self) -> None:
        """통째로 담으면 안 바뀐 값 스무 개 사이에서 바뀐 하나를 찾게 된다."""
        got = audit.diff({"a": 1, "b": 2}, {"a": 1, "b": 3})
        assert got == {"b": {"before": 2, "after": 3}}

    def test_없던_값이_생긴_것도_바뀐_것이다(self) -> None:
        assert audit.diff({}, {"a": 1}) == {"a": {"before": None, "after": 1}}
