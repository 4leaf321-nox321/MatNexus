"""워크벤치 — 담아 두는 자리(ADR 0024·0025).

**여기에 도메인이 없다.** 담고·빼고·진행을 적어 두는 것이 전부라, 시험이 볼 것도
그 성질이다:

    담은 것이 사라져도 작업이 열린다     대상에 외래키를 안 걸었다
    지우려는 사람이 담긴 사실을 본다      의존성 레지스트리에 손으로 보탰다
    남의 부서 작업은 안 보인다           공유의 단위가 부서다
    안 보낸 칸은 안 고친다               진행만 밀었는데 제목이 지워지면 안 된다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import dependents


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    made: dict[str, Any] = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "SECC", "grade": "WB01", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    return made


@pytest.fixture
def run(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    made = client.post(
        "/api/workbench/runs",
        json={"workflow_key": "analysis_deck", "title": "EPDM 도어씰 2026-09"},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


class Test작업을_시작한다:
    def test_만들면_빈_바구니로_시작한다(self, run: dict[str, Any]) -> None:
        assert run["status"] == "running"
        assert run["item_count"] == 0
        assert run["items"] == []

    def test_목록에_뜬다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        """**「이어서 하기」 가 이 목록이다.** 어제 하던 것이 여기 없으면 서버에
        둔 뜻이 없다."""
        rows = client.get("/api/workbench/runs?status=running", headers=admin_headers).json()
        assert run["id"] in [one["id"] for one in rows]

    def test_누가_시작했는지_보인다(self, run: dict[str, Any]) -> None:
        """부서에서 함께 보는 자리라 「누구 것인가」 가 보여야 한다."""
        assert run["owner_name"]


class Test담고_뺀다:
    def test_담으면_이름이_붙어_온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        material: dict[str, Any],
    ) -> None:
        """담을 때는 id 만 적고 **읽을 때 푼다**(ADR 0025)."""
        response = client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "material", "target_ids": [material["id"]]},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        [item] = response.json()
        assert item["label"] == material["record_name"]
        assert item["missing"] is False

    def test_두_번_담아도_한_번만(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        material: dict[str, Any],
    ) -> None:
        """**두 번 담기는 실수이지 오류가 아니다.** 여럿을 한 번에 담을 때 하나가
        겹쳤다고 전부를 실패시키면 사람은 무엇이 들어갔는지 모른다."""
        body = {"kind": "material", "target_ids": [material["id"]]}
        client.post(f"/api/workbench/runs/{run['id']}/items", json=body, headers=admin_headers)
        second = client.post(
            f"/api/workbench/runs/{run['id']}/items", json=body, headers=admin_headers
        )
        assert second.status_code == 201, second.text
        assert second.json() == []

        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        assert detail["item_count"] == 1

    def test_빼면_사라진다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        material: dict[str, Any],
    ) -> None:
        [item] = client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "material", "target_ids": [material["id"]]},
            headers=admin_headers,
        ).json()
        gone = client.delete(
            f"/api/workbench/runs/{run['id']}/items/{item['id']}", headers=admin_headers
        )
        assert gone.status_code == 204, gone.text
        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        assert detail["items"] == []


class Test담은_것이_사라져도:
    """**작업은 계속 열린다.** 담아 두는 것은 메모지 소유가 아니다(ADR 0025)."""

    def test_사라졌다고_그_줄에_적는다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        # 있지도 않은 것을 담는다 — 지워진 뒤와 같은 상태다.
        client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "test_run", "target_ids": [str(uuid.uuid4())]},
            headers=admin_headers,
        )
        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers)
        assert detail.status_code == 200, detail.text
        [item] = detail.json()["items"]
        assert item["missing"] is True
        assert item["label"] == "사라졌습니다"

    def test_줄이_조용히_빠지지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        material: dict[str, Any],
    ) -> None:
        """빼 버리면 「내가 담았던 둘이 왜 하나지」 에 답할 데가 없다."""
        client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "material", "target_ids": [material["id"], str(uuid.uuid4())]},
            headers=admin_headers,
        )
        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        assert detail["item_count"] == 2
        assert sorted(one["missing"] for one in detail["items"]) == [False, True]


class Test지우려는_사람이_본다:
    def test_담긴_사실이_의존성으로_잡힌다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        material: dict[str, Any],
    ) -> None:
        """**막지 않고 말해 준다.** 대상에 외래키를 안 걸었으므로 FK 를 훑는 자동
        수집에는 안 잡힌다 — `EXTRA_CHECKS` 로 보탠 것이 이것이다."""
        client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "material", "target_ids": [material["id"]]},
            headers=admin_headers,
        )
        found = dependents.references_to(db, table="materials", pk=uuid.UUID(material["id"]))
        basket = [one for one in found if one.table == "workbench_items"]
        assert basket, [one.table for one in found]
        assert basket[0].count == 1
        # 담겼다는 이유로 못 지우게 되면 안 된다.
        assert basket[0].blocks_delete is False


class Test진행을_적어_둔다:
    def test_모양을_서버가_안_따진다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        """**단계의 뜻은 화면이 안다**(ADR 0025). 서버가 알면 화면을 고칠 때마다
        마이그레이션이 붙는다."""
        response = client.patch(
            f"/api/workbench/runs/{run['id']}",
            json={"steps": {"at": "pick", "done": ["choose"], "무엇이든": 3}},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["steps"]["at"] == "pick"

    def test_안_보낸_칸은_안_고친다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        """진행만 밀었는데 제목이 지워지면 사람은 무엇이 지웠는지 모른다."""
        client.patch(
            f"/api/workbench/runs/{run['id']}",
            json={"steps": {"at": "pick"}},
            headers=admin_headers,
        )
        body = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        assert body["title"] == run["title"]

    def test_끝내면_시각이_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> None:
        """**끝낸 작업을 안 지운다** — 그때 무엇을 묶었나가 곧 기록이다."""
        body = client.patch(
            f"/api/workbench/runs/{run['id']}",
            json={"status": "finished"},
            headers=admin_headers,
        ).json()
        assert body["status"] == "finished"
        assert body["finished_at"]


class Test남의_부서는_안_보인다:
    """**공유의 단위는 부서다.** 전사로 열면 남의 부서 작업이 목록에 섞이고, 그
    목록은 「이어서 하기」 로 쓰이는 자리라 금세 못 쓰게 된다."""

    @staticmethod
    def _outsider(client: TestClient, db: Session) -> dict[str, str]:
        other = Workspace(slug="polymer", name="고분자팀")
        db.add(other)
        db.flush()
        user = User(
            email="outsider",
            password_hash=security.hash_password("member-password-1"),
            display_name="남의 부서 사람",
            status="active",
            home_workspace_id=other.id,
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=other.id, user_id=user.id, role="member"))
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "outsider", "password": "member-password-1"}
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_못_연다(self, client: TestClient, db: Session, run: dict[str, Any]) -> None:
        headers = self._outsider(client, db)
        response = client.get(f"/api/workbench/runs/{run['id']}", headers=headers)
        assert response.status_code == 404, response.text

    def test_목록에도_안_뜬다(
        self, client: TestClient, db: Session, run: dict[str, Any]
    ) -> None:
        headers = self._outsider(client, db)
        rows = client.get("/api/workbench/runs", headers=headers).json()
        assert run["id"] not in [one["id"] for one in rows]
