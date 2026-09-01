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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.tests import models as test_models
from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import dependents

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"


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


@pytest.fixture
def dma_run(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """DMA 파일 하나를 올려 읽힌 시험. **읽자마자 마스터커브가 등록된다**(ADR 0023)."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Polymer",
            "category": "EPDM",
            "grade": "WB-VE",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("Example FreqTemp2.csv", FREQ_TEMP.read_bytes())},
        headers=admin_headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    run: dict[str, Any] = created
    return run


class Test담긴_것이_무엇을_갖췄는지_센다:
    """**판정의 재료는 서버가 준다.**

    화면이 「이 단계는 끝났나」 를 말하려면 마스터커브가 몇인지, 온도가 몇 단인지가
    필요하다. 그것을 화면이 도메인 API 로 따로 가져오면 워크벤치가 남의 도메인을
    알게 되고, 그 방향은 되돌리기 어렵다(ADR 0024) — 그래서 담긴 줄에 실어 보낸다.
    """

    def test_시험은_마스터커브와_온도_단_수를_달고_온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        dma_run: dict[str, Any],
    ) -> None:
        response = client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "test_run", "target_ids": [dma_run["id"]]},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        [item] = response.json()
        assert item["facts"]["master_curves"] == 1
        # 겹칠 수 있는 시험이다 — 한 단이면 화면이 「겹칠 수 없다」 고 말해야 한다.
        assert item["facts"]["temperature_steps"] >= 2
        assert item["facts"]["prony_fits"] == 0
        assert item["facts"]["adopted"] == 0

    def test_시험은_어느_재료의_것인지_달고_온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        dma_run: dict[str, Any],
    ) -> None:
        """글로벌 피팅은 **재료 화면에** 있는데(ADR 0020) 바구니에는 시험이 담긴다.
        이것이 없으면 사람이 재료를 이름으로 찾아 들어가야 한다.

        **주소가 아니라 id 를 준다** — 화면의 주소 체계를 서버가 알면 라우팅을 고칠
        때마다 서버도 고쳐야 한다."""
        [item] = client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "test_run", "target_ids": [dma_run["id"]]},
            headers=admin_headers,
        ).json()
        specimen = client.get(
            f"/api/specimens/{dma_run['specimen_id']}", headers=admin_headers
        ).json()
        sample = client.get(
            f"/api/samples/{specimen['sample_id']}", headers=admin_headers
        ).json()
        assert item["material_id"] == sample["material_id"]

    def test_안_세어_본_것은_모른다고_한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        dma_run: dict[str, Any],
    ) -> None:
        """**`0` 이 아니라 `-1` 이다.** 이 칸이 생기기 전에 읽은 시험은 「온도가 한
        단」 이 아니라 「안 세어 봤다」 다 — 0으로 보내면 화면이 「겹칠 수 없다」 고
        단정하고, 진짜 남은 일이 숨는다."""
        row = db.get(test_models.TestRun, uuid.UUID(dma_run["id"]))
        assert row is not None
        row.temperature_step_count = None
        db.commit()

        client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "test_run", "target_ids": [dma_run["id"]]},
            headers=admin_headers,
        )
        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        [item] = detail["items"]
        assert item["facts"]["temperature_steps"] == -1

    def test_사라진_것에는_사실이_없다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        dma_run: dict[str, Any],
    ) -> None:
        """세는 대상이 없으면 **비워 보낸다.** 0 으로 채우면 화면이 「마스터커브가
        없다」 로 읽고, 지워진 시험을 남은 일로 재촉한다."""
        client.post(
            f"/api/workbench/runs/{run['id']}/items",
            json={"kind": "test_run", "target_ids": [dma_run["id"]]},
            headers=admin_headers,
        )
        row = db.get(test_models.TestRun, uuid.UUID(dma_run["id"]))
        assert row is not None
        row.deleted_at = datetime.now(UTC)
        db.commit()

        detail = client.get(f"/api/workbench/runs/{run['id']}", headers=admin_headers).json()
        [item] = detail["items"]
        assert item["missing"] is True
        assert item["facts"] == {}


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
