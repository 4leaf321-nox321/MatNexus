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


class Test나머지_경로:
    """**행위 상수만 있고 부르는 곳이 없으면 없는 기능이다.**

    v1.49.0 에 열 개를 선언했는데 실제로 남기는 곳은 카드 세 곳뿐이었다. 화면을
    붙이고 나서야 드러났다 — 목록이 거의 비어 있었다.
    """

    def test_계정_정지가_남는다(
        self, client: TestClient, admin_headers: dict[str, str], workspace: Any
    ) -> None:
        """정지는 되돌릴 수 있어도 **접근을 끊는다.** 누가 끊었는지 남지 않으면
        "왜 로그인이 안 되죠" 에 답할 근거가 없다."""
        made = client.post(
            "/api/accounts",
            json={
                "email": "정지@example.com",
                "display_name": "정지 대상",
                "role": "member",
                "workspace_slug": "metal",
            },
            headers=admin_headers,
        )
        assert made.status_code in (200, 201), made.text
        account_id = made.json()["account"]["id"]

        done = client.post(f"/api/accounts/{account_id}/suspend", headers=admin_headers)
        assert done.status_code == 200, done.text

        entries = client.get(
            "/api/audit", params={"action": "account.suspended"}, headers=admin_headers
        ).json()
        assert [item["target_id"] for item in entries] == [account_id]
        assert entries[0]["changes"]["status"]["after"] == "suspended"

    def test_기준정보_이름_변경이_남는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이름 하나가 수천 건을 바꾼다.** 외래키라 참조가 저절로 따라오고,
        강종이면 재료 이름까지 다시 만들어진다(ADR 0004)."""
        made = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "감사제철"},
            headers=admin_headers,
        )
        assert made.status_code in (200, 201), made.text
        term_id = made.json()["id"]

        changed = client.patch(
            f"/api/vocabularies/manufacturer/terms/{term_id}",
            json={"value": "감사제철(주)"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text

        entries = client.get(
            "/api/audit", params={"action": "vocabulary.renamed"}, headers=admin_headers
        ).json()
        assert len(entries) == 1
        assert entries[0]["changes"]["value"] == {
            "before": "감사제철",
            "after": "감사제철(주)",
        }

    def test_감추는_것은_안_남긴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**감춤은 피커에서만 사라지고 자료는 그대로다.** 이름 변경과 같은
        무게로 남기면 목록이 소음으로 찬다."""
        made = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "감출제철"},
            headers=admin_headers,
        )
        term_id = made.json()["id"]
        client.patch(
            f"/api/vocabularies/manufacturer/terms/{term_id}",
            json={"status": "deprecated"},
            headers=admin_headers,
        )
        entries = client.get(
            "/api/audit", params={"action": "vocabulary.renamed"}, headers=admin_headers
        ).json()
        assert entries == []

    def test_시험_종류_변경이_남는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """고치는 것은 **이미 저장된 곡선의 읽는 법을 바꾼다.**"""
        ensure_builtin_test_types(db)
        db.commit()
        before = client.get("/api/test-types", headers=admin_headers).json()
        target = next(item for item in before if item["key"] == "tensile")

        payload = {key: target[key] for key in target if key not in ("id", "key")}
        payload["expected_revision"] = payload.pop("revision")
        payload["label"] = "인장(감사)"
        changed = client.put("/api/test-types/tensile", json=payload, headers=admin_headers)
        assert changed.status_code == 200, changed.text

        entries = client.get(
            "/api/audit", params={"action": "test_type.changed"}, headers=admin_headers
        ).json()
        assert len(entries) == 1
        assert entries[0]["changes"]["label"]["after"] == "인장(감사)"

    def _shown(self, client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
        listed = client.get("/api/test-types", headers=headers).json()
        return next(item for item in listed if item["key"] == "tensile")

    def test_안_바뀌면_안_남는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**저장 버튼을 눌렀다는 사실은 감사 대상이 아니다.** 아무것도 안
        바뀐 저장이 기록으로 남으면, 진짜 변경이 그 사이에 묻힌다.

        이 시험은 한 번 뒤집혔다. 처음 썼을 때는 첫 저장에 `max_upload_bytes:
        None → 52428800` 이 남았다 — 응답이 *실효값*(50MB)을 주는데 저장 요청의
        같은 이름은 *저장할 값*이라, 받은 것을 돌려보내면 전역 기본값이 행에
        박혔기 때문이다. **감사 로그가 찾아낸 결함이었다**(§11).

        v1.53.0 에 출력을 `max_upload_bytes`(저장값)와
        `max_upload_bytes_effective`(실효값)로 가르면서 그 왕복이 진짜 무변경이
        됐다. 그래서 여기서 아무것도 안 남는 것이 **이제는 맞다.**
        """
        ensure_builtin_test_types(db)
        db.commit()
        shown = client.get("/api/test-types", headers=admin_headers).json()
        target = next(item for item in shown if item["key"] == "tensile")
        payload = {key: target[key] for key in target if key not in ("id", "key")}
        payload.pop("revision")

        # **매번 다시 읽는다.** 저장하면 리비전이 오르므로 같은 것을 두 번 보내면
        # 두 번째는 409 다(ADR 0015) — 그것이 맞는 동작이고, 실제 화면도 저장 뒤
        # 응답으로 새 리비전을 받는다.
        for _ in range(2):
            payload["expected_revision"] = self._shown(client, admin_headers)["revision"]
            assert (
                client.put(
                    "/api/test-types/tensile", json=payload, headers=admin_headers
                ).status_code
                == 200
            )
        entries = client.get(
            "/api/audit", params={"action": "test_type.changed"}, headers=admin_headers
        ).json()
        assert entries == [], [item["changes"] for item in entries]
