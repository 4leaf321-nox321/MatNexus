"""고치기는 사람 기준이다 — ADR 0035 D4 (2단계) · D5 (3단계).

자료를 고치는 사람은 넷이다: 시스템 관리자 · 자료 관리자 · 그 자료의 등록자 · 그 자료에
편집을 받은 부서의 멤버. 소속 부서는 권한을 정하지 않는다. 3단계에서 정의·장비·휴지통이
같은 규칙으로 들어왔고, 의뢰·커넥터·워크벤치는 보기를 전원에게 열었다.

무는 자리를 여기 둔다. 전부 **조용히 틀리는** 종류다 — 남의 시험이 지워지거나, 막힌
사람이 누구에게 물어야 할지 모르거나, 넘긴 권한이 엉뚱한 곳에 붙는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.pipelines.models import PipelineConnector, PipelineInboxItem
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.workspaces.models import Workspace

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


def _person(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    slug: str,
    email: str,
    name: str | None = None,
) -> tuple[str, dict[str, str]]:
    """`slug` 부서의 평범한 멤버. (계정 id, 로그인 헤더)."""
    made = client.post(
        "/api/accounts",
        json={
            "email": email,
            "display_name": name or email,
            "workspace_slug": slug,
            "role": "member",
        },
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    body = made.json()
    token = client.post(
        "/api/auth/login",
        json={"email": email, "password": body["temporary_password"]},
    ).json()["access_token"]
    return body["account"]["id"] if "account" in body else body["id"], {
        "Authorization": f"Bearer {token}"
    }


def _department(client: TestClient, admin_headers: dict[str, str], slug: str) -> None:
    made = client.post(
        "/api/workspaces", json={"name": f"{slug} 부서", "slug": slug}, headers=admin_headers
    )
    assert made.status_code == 201, made.text


#: 새 등급 낱말은 자료 관리자가 세운다(ADR 0032 · 0035) — 멤버가 만드는 재료는 **있는
#: 등급**을 쓰고 세부(details)로만 갈린다. 낱말은 `people` 이 관리자로 한 번 심는다.
TAXONOMY = {"family": "Metal", "category": "Steel", "grade": "EDGRADE"}


def _material(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={**TAXONOMY, "details": f"D{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _sample(client: TestClient, headers: dict[str, str], material_id: str) -> dict[str, Any]:
    made = client.post(f"/api/materials/{material_id}/samples", json={}, headers=headers)
    assert made.status_code == 201, made.text
    return dict(made.json())


def _specimen(client: TestClient, headers: dict[str, str], sample_id: str) -> dict[str, Any]:
    made = client.post(
        f"/api/samples/{sample_id}/specimens", json={"orientation": "MD"}, headers=headers
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _run(
    client: TestClient, db: Session, headers: dict[str, str], specimen_id: str
) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    made = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen_id, "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert made.status_code == 202, made.text
    return dict(made.json())


@pytest.fixture
def people(
    client: TestClient, admin_headers: dict[str, str]
) -> dict[str, tuple[str, dict[str, str]]]:
    """A 부서 둘(앨리스·앨런)과 B 부서 하나(보라)."""
    _department(client, admin_headers, "dept-a")
    _department(client, admin_headers, "dept-b")
    _material(client, admin_headers)  # 낱말을 심는다
    return {
        "alice": _person(
            client, admin_headers, slug="dept-a", email="alice@x.com", name="앨리스"
        ),
        "allen": _person(
            client, admin_headers, slug="dept-a", email="allen@x.com", name="앨런"
        ),
        "bora": _person(client, admin_headers, slug="dept-b", email="bora@x.com", name="보라"),
    }


class Test등록자:
    def test_새_자료는_등록자만_고친다_같은_부서여도(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """**새 자료의 기본은 등록자만이다**(ADR 0035). 같은 부서라고 고치게 되면 소속이
        다시 권한을 정한다 — 그러면 「왜 잠겼나」 가 또 소속에 숨는다."""
        _, alice = people["alice"]
        _, allen = people["allen"]
        material = _material(client, alice)
        assert material["access"]["can_edit"] is True
        assert material["access"]["edit_workspace"] is None

        mine = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "내 것"}, headers=alice
        )
        assert mine.status_code == 200, mine.text
        theirs = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "옆 사람"}, headers=allen
        )
        assert theirs.status_code == 403, theirs.text

    def test_막히면_누구에게_물어야_하는지_이름으로_말한다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """「권한이 없습니다」 만으로는 사람이 누구를 찾아갈지 모른다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        blocked = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "남"}, headers=bora
        )
        assert blocked.status_code == 403
        error = blocked.json()["error"]
        assert "등록자 앨리스" in error["message"]
        assert error["details"]["registrant"] == "앨리스"
        assert error["details"]["data_managers"], "물어볼 관리자가 비어 있다"

        # **화면은 누르기 전에 같은 말을 안다.**
        seen = client.get(f"/api/materials/{material['id']}", headers=bora).json()
        assert seen["access"]["can_edit"] is False
        assert "등록자 앨리스" in seen["access"]["reason"]


class Test층마다_제_등록자:
    def test_남의_재료_밑에_시료를_붙이고_그_시료는_내가_고친다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """**재료의 권한에 딸려 가지 않는다.** 딸려 가면 SECC 를 처음 올린 사람만 그
        아래를 늘릴 수 있다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)

        sample = _sample(client, bora, material["id"])
        assert sample["registered_by"] == "보라"
        assert sample["access"]["can_edit"] is True
        edited = client.patch(
            f"/api/samples/{sample['id']}", json={"note": "내 로트"}, headers=bora
        )
        assert edited.status_code == 200, edited.text
        # 재료의 등록자라도 남의 시료는 못 고친다.
        blocked = client.patch(
            f"/api/samples/{sample['id']}", json={"note": "재료 주인"}, headers=alice
        )
        assert blocked.status_code == 403, blocked.text

    def test_남이_붙인_것이_있으면_통째로_못_지우고_누구의_것인지_말한다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        sample = _sample(client, bora, material["id"])
        specimen = _specimen(client, bora, sample["id"])
        _run(client, db, bora, specimen["id"])

        blocked = client.post(
            f"/api/materials/{material['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=alice,
        )
        assert blocked.status_code == 409, blocked.text
        message = blocked.json()["error"]["message"]
        assert "시험 1건(보라)" in message and "시료 1건(보라)" in message

        # 일괄 지우기도 같은 판단이다 — 이유를 건별로 돌려준다.
        many = client.post(
            "/api/materials/delete",
            json={
                "material_ids": [material["id"]],
                "cascade": True,
                "include_test_runs": True,
            },
            headers=alice,
        ).json()
        assert many["deleted"] == 0
        assert "남의 자료" in many["blocked"][0]["reason"]


class Test편집_부서:
    def test_부서에_주면_그_부서_사람이_고친다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, allen = people["allen"]
        material = _material(client, alice)

        given = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"edit_workspace_slug": "dept-a"},
            headers=alice,
        )
        assert given.status_code == 200, given.text
        assert given.json()["access"]["edit_workspace"] == "dept-a 부서"

        edited = client.patch(
            f"/api/materials/{material['id']}", json={"alias": "팀 것"}, headers=allen
        )
        assert edited.status_code == 200, edited.text

    def test_받은_부서_사람은_고쳐도_넘기지는_못한다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """넘기게 두면 받은 권한으로 등록자의 권한을 걷는 길이 된다."""
        allen_id, allen = people["allen"]
        _, alice = people["alice"]
        material = _material(client, alice)
        client.put(
            f"/api/ownership/material/{material['id']}",
            json={"edit_workspace_slug": "dept-a"},
            headers=alice,
        )
        grab = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"registrant_id": allen_id},
            headers=allen,
        )
        assert grab.status_code == 403, grab.text
        assert "등록자 앨리스" in grab.json()["error"]["message"]

    def test_안_보낸_칸은_그대로_보낸_null_은_걷는다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """부분 수정의 규칙(AGENTS.md) — 등록자만 넘기려다 부서 부여가 사라지면 안 된다."""
        bora_id, _ = people["bora"]
        _, alice = people["alice"]
        material = _material(client, alice)
        client.put(
            f"/api/ownership/material/{material['id']}",
            json={"edit_workspace_slug": "dept-a"},
            headers=alice,
        )
        handed = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"registrant_id": bora_id},
            headers=alice,
        ).json()
        assert handed["access"]["registrant"] == "보라"
        assert handed["access"]["edit_workspace"] == "dept-a 부서", (
            "안 보낸 부서 부여가 사라졌다"
        )

        # 앨리스는 이제 등록자가 아니지만 dept-a 사람이라 여전히 고친다.
        assert handed["access"]["can_edit"] is True
        assert handed["access"]["can_hand_over"] is False


class Test넘기기:
    def test_하위까지_넘기면_내_것만_넘어가고_남의_것은_이름과_함께_건너뛴다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        _, alice = people["alice"]
        allen_id, _ = people["allen"]
        _, bora = people["bora"]
        material = _material(client, alice)
        mine = _sample(client, alice, material["id"])
        _sample(client, bora, material["id"])

        seen = client.get(f"/api/ownership/material/{material['id']}", headers=alice).json()
        samples = next(one for one in seen["children"] if one["kind"] == "sample")
        assert (samples["total"], samples["changeable"]) == (2, 1)

        done = client.put(
            f"/api/ownership/material/{material['id']}",
            json={"registrant_id": allen_id, "include_children": True},
            headers=alice,
        ).json()
        assert done["changed"] == 2  # 재료 + 내 시료
        assert [one["reason"] for one in done["skipped"]] == [
            "등록자 보라 — 등록자와 자료 관리자만 넘길 수 있습니다."
        ]
        moved = client.get(f"/api/samples/{mine['id']}", headers=alice).json()
        assert moved["registered_by"] == "앨런"


class Test자료_관리자:
    def test_모든_자료를_고치고_카드를_확정한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        bora_id, bora = people["bora"]
        _, alice = people["alice"]
        material = _material(client, alice)

        assert (
            client.patch(
                f"/api/materials/{material['id']}", json={"alias": "관리"}, headers=bora
            ).status_code
            == 403
        )
        # **시스템 관리자만 준다.**
        assert (
            client.post(
                f"/api/accounts/{bora_id}/data-manager",
                json={"is_data_manager": True},
                headers=alice,
            ).status_code
            == 403
        )
        granted = client.post(
            f"/api/accounts/{bora_id}/data-manager",
            json={"is_data_manager": True},
            headers=admin_headers,
        )
        assert granted.status_code == 200, granted.text
        assert granted.json()["is_data_manager"] is True
        assert client.get("/api/auth/me", headers=bora).json()["is_data_manager"] is True

        assert (
            client.patch(
                f"/api/materials/{material['id']}", json={"alias": "관리"}, headers=bora
            ).status_code
            == 200
        )

    def test_카드_확정은_등록자가_스스로_못_하고_초안은_등록자가_고친다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        """확정된 카드는 다른 시스템으로 넘어가는 공식 물성이라(ADR 0035 D3) 검토의 뜻이
        있다. 초안은 만든 사람의 것이다."""
        from app.modules.fitting.models import PropertyCard

        alice_id, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        card = PropertyCard(
            material_id=uuid.UUID(material["id"]),
            label="초안",
            created_by_id=uuid.UUID(alice_id),
        )
        db.add(card)
        db.commit()

        renamed = client.patch(
            f"/api/fitting/cards/{card.id}", json={"label": "고친 초안"}, headers=alice
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["access"]["can_edit"] is True
        assert (
            client.patch(
                f"/api/fitting/cards/{card.id}", json={"label": "남"}, headers=bora
            ).status_code
            == 403
        )
        published = client.post(f"/api/fitting/cards/{card.id}/publish", headers=alice)
        assert published.status_code == 403, published.text
        assert "자료 관리자" in published.json()["error"]["message"]


class Test시험:
    def test_남의_시험은_일괄_지우기에서_이유와_함께_빠진다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        sample = _sample(client, alice, material["id"])
        specimen = _specimen(client, alice, sample["id"])
        run = _run(client, db, alice, specimen["id"])
        assert run["access"]["can_edit"] is True

        out = client.post(
            "/api/test-runs/delete", json={"run_ids": [run["id"]]}, headers=bora
        ).json()
        assert out["deleted"] == 0
        assert "등록자 앨리스" in out["blocked"][0]

    def test_치수를_적는_것은_시편을_고치는_일이다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        sample = _sample(client, alice, material["id"])
        specimen = _specimen(client, alice, sample["id"])
        blocked = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"thickness": 1.0}},
            headers=bora,
        )
        assert blocked.status_code == 403, blocked.text


# --- 3단계 -----------------------------------------------------------------------

#: 해석용 물성 정의 하나 — 저장할 때 실제로 그려 본다(`fitting.routes._checked`).
DECK: dict[str, Any] = {
    "label": "부서 덱",
    "definition": {
        "extension": "fem",
        "describe": "정의로 붙인 솔버.",
        "lines": [{"text": "$ {name}"}, {"text": "MAT1"}],
    },
}


def _space(db: Session, slug: str) -> Workspace:
    found = db.scalar(select(Workspace).where(Workspace.slug == slug))
    assert found is not None
    return found


class Test정의와_장비:
    def test_정의는_누구나_만들고_등록자가_고치며_부서에_주면_그_부서가_고친다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """전에는 부서 관리자가 만들고 고쳤다 — 그리고 화면은 부서를 안 보내서, 부서
        관리자가 「정의 생성」 을 누르면 「전역」 으로 읽혀 403 이 났다. 이제 등록 부서는
        안 보내면 내 소속이다."""
        _, alice = people["alice"]
        _, allen = people["allen"]
        made = client.post("/api/fitting/export-profiles", json=DECK, headers=alice)
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["owner_workspace_slug"] == "dept-a"
        assert body["access"]["registrant"] == "앨리스"

        change = {**DECK, "label": "앨런이 고친 덱"}
        blocked = client.put(
            f"/api/fitting/export-profiles/{body['key']}", json=change, headers=allen
        )
        assert blocked.status_code == 403, blocked.text
        assert "등록자 앨리스" in blocked.json()["error"]["message"]

        given = client.put(
            f"/api/ownership/export_profile/{body['id']}",
            json={"edit_workspace_slug": "dept-a"},
            headers=alice,
        )
        assert given.status_code == 200, given.text
        edited = client.put(
            f"/api/fitting/export-profiles/{body['key']}", json=change, headers=allen
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["access"]["edit_workspace"] == "dept-a 부서"

    def test_장비는_누구나_올리고_남의_장비는_못_고친다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """전에는 「어느 부서든 관리자면」 — 남의 조직 장비를 누구 관리자든 고쳤다."""
        _, bora = people["bora"]
        _, alice = people["alice"]
        unit = client.post("/api/equipment/units", json={"name": "보라의 DMA"}, headers=bora)
        assert unit.status_code == 201, unit.text
        unit_id = unit.json()["id"]
        blocked = client.patch(
            f"/api/equipment/units/{unit_id}", json={"notes": "남"}, headers=alice
        )
        assert blocked.status_code == 403, blocked.text
        assert "등록자 보라" in blocked.json()["error"]["message"]
        # 부속·교정도 장비를 따라간다.
        part = client.post(
            f"/api/equipment/units/{unit_id}/parts",
            json={"kind": "load_cell", "label": "5 kN"},
            headers=alice,
        )
        assert part.status_code == 403, part.text


class Test휴지통:
    def test_등록자가_지운_것을_제_손으로_되살린다(
        self, client: TestClient, people: dict[str, tuple[str, dict[str, str]]]
    ) -> None:
        """전에는 시스템 관리자만 되살렸다 — 잘못 누른 사람이 제 손으로 되돌릴 길이
        없었다. 목록에는 **내가 되살릴 수 있는 것만** 뜬다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        gone = client.delete(f"/api/materials/{material['id']}", headers=alice)
        assert gone.status_code == 204, gone.text

        mine = client.get("/api/trash", headers=alice).json()
        assert material["id"] in {row["id"] for row in mine}
        theirs = client.get("/api/trash", headers=bora).json()
        assert material["id"] not in {row["id"] for row in theirs}

        stranger = client.post(f"/api/trash/material/{material['id']}/restore", headers=bora)
        assert stranger.status_code == 403, stranger.text
        assert stranger.json()["error"]["code"] == "MNX-TRASH-0006"
        # **영영 지우기는 시스템 관리자만** — 되돌릴 수 없고 디스크를 치운다.
        purge = client.delete(
            f"/api/trash/material/{material['id']}", params={"confirm": True}, headers=alice
        )
        assert purge.status_code == 403, purge.text

        back = client.post(f"/api/trash/material/{material['id']}/restore", headers=alice)
        assert back.status_code == 200, back.text
        assert client.get(f"/api/materials/{material['id']}", headers=alice).status_code == 200

    def test_남의_것이_함께_돌아오면_못_되살리고_누구의_것인지_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        """지우기와 같은 규칙이다 — 되살리기가 더 넓으면 지울 수 없던 남의 것을
        되살리기로 건드리게 된다."""
        _, alice = people["alice"]
        _, bora = people["bora"]
        material = _material(client, alice)
        _sample(client, bora, material["id"])
        # 관리자는 남의 것이 딸려도 통째로 지운다.
        gone = client.post(
            f"/api/materials/{material['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text

        row = next(
            one
            for one in client.get("/api/trash", headers=alice).json()
            if one["id"] == material["id"]
        )
        assert row["blocked"] and "시료 1건(보라)" in row["blocked"]
        refused = client.post(f"/api/trash/material/{material['id']}/restore", headers=alice)
        assert refused.status_code == 403, refused.text
        assert "시료 1건(보라)" in refused.json()["error"]["message"]


class Test보기와_고치기를_뗐다:
    def test_남의_부서_커넥터도_보이고_다루는_것은_그_부서_관리자다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        _, bora = people["bora"]
        made = client.post(
            "/api/pipelines/connectors",
            json={
                "name": "A 부서 DMA PC",
                "hostname": "dma-a",
                "workspace_id": str(_space(db, "dept-a").id),
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        listed = client.get("/api/pipelines/connectors", headers=bora).json()
        row = next(one for one in listed if one["id"] == made.json()["id"])
        assert row["can_manage"] is False
        assert row["workspace_name"] == "dept-a 부서"
        blocked = client.patch(
            f"/api/pipelines/connectors/{row['id']}", json={"is_active": False}, headers=bora
        )
        assert blocked.status_code == 403, blocked.text

    def test_홈의_수신함_대기는_내_부서_커넥터만_센다(
        self,
        client: TestClient,
        db: Session,
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        """할 일을 세는 자리라 내 부서 것만. **전에는 모든 커넥터를 셌다** — 서브쿼리를
        곱하는 SQL 이라, 커넥터가 하나라도 보이면 남의 부서 것까지 잡혔다."""
        _, alice = people["alice"]
        for slug in ("dept-a", "dept-b"):
            connector = PipelineConnector(
                workspace_id=_space(db, slug).id, name=f"{slug} PC", hostname=f"host-{slug}"
            )
            db.add(connector)
            db.flush()
            db.add(
                PipelineInboxItem(
                    connector_id=connector.id,
                    source_key="dma",
                    status="needs_specimen",
                    filename=f"{slug}.csv",
                    size=1,
                    sha256=uuid.uuid4().hex * 2,
                    client_path=f"C:/{slug}.csv",
                    mtime=connector.created_at or datetime.now(UTC),
                )
            )
        db.commit()
        overview = client.get("/api/statistics/overview", headers=alice).json()
        assert overview["inbox_waiting"] == 1


class Test물어볼_사람:
    def test_자료_관리자를_이름으로_대고_없으면_시스템_관리자를_댄다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        people: dict[str, tuple[str, dict[str, str]]],
    ) -> None:
        """막히기 **전에** 물을 자리 — 새 등급을 미리보기로 막은 AI 가 이름을 못 댔다
        (2026-09-24 점검). 403 의 `details.data_managers` 와 같은 규칙이다."""
        bora_id, bora = people["bora"]
        before = client.get("/api/ownership/stewards", headers=bora).json()
        assert [one["display_name"] for one in before] == ["시스템 관리자"]

        client.post(
            f"/api/accounts/{bora_id}/data-manager",
            json={"is_data_manager": True},
            headers=admin_headers,
        )
        after = client.get("/api/ownership/stewards", headers=bora).json()
        assert [one["display_name"] for one in after] == ["보라"]
        assert after[0]["workspace"] == "dept-b 부서"
