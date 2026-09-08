"""온톨로지 — **AI 가 길을 찾는다.**

무는 것이 넷이다.

    지도가 실제 스키마와 같다        `GET /api/ontology` 가 레지스트리 그대로다
    이웃을 관계 이름과 함께 준다     「왜 이어져 있나」 가 답의 절반이다
    길을 찾는다                      시험 → 시편 → 시료 → 재료
    **안 보이는 마디에서 길이 끊긴다**  가장 값진 시험이다 ↓

마지막 것이 이 파일의 이유다. 트래버설은 부르는 쪽이 이름조차 모르는 표까지
걸어간다 — 「이 장비로 잰 시험」 을 물었을 뿐인데 남의 부서 재료가 딸려 나오면
그것은 조용한 유출이다. 이름만 가리고 이어졌다는 사실을 남겨도 마찬가지다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from app.modules.metrology.models import Instrument, InstrumentCapability
from app.modules.tests.definitions import ensure_builtin_test_types
from app.shared import relations

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

ONTOLOGY = "/api/ontology"
RELATED = "/api/ontology/related"
PATH = "/api/ontology/path"


def _login_member_of(
    client: TestClient, admin_headers: dict[str, str], *, slug: str, email: str
) -> dict[str, str]:
    made = client.post(
        "/api/accounts",
        json={"email": email, "display_name": email, "workspace_slug": slug, "role": "member"},
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    token = client.post(
        "/api/auth/login",
        json={"email": email, "password": made.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _chain(
    client: TestClient, db: Session, admin_headers: dict[str, str], *, owner_slug: str | None
) -> dict[str, str]:
    """재료 → 시료 → 시편 → 시험. **화면과 같은 길로 만든다.**"""
    ensure_builtin_test_types(db)
    db.commit()
    body: dict[str, str] = {
        "family": "Metal",
        "category": "Steel",
        "grade": f"ONT-{uuid.uuid4().hex[:6]}",
    }
    if owner_slug:
        body["workspace_slug"] = owner_slug
    material = client.post("/api/materials", json=body, headers=admin_headers)
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]

    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=admin_headers
    )
    assert sample.status_code == 201, sample.text
    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    )
    assert specimen.status_code == 201, specimen.text
    run = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": "tensile",
            "conditions": "{}",
        },
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    )
    assert run.status_code == 202, run.text
    return {
        "material": material_id,
        "sample": sample.json()["id"],
        "specimen": specimen.json()["id"],
        "test_run": run.json()["id"],
    }


class TestMap:
    def test_지도는_레지스트리_그대로다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """AI 에게는 이 응답이 지도의 전부다 — 코드와 갈리면 없는 길을 안내한다."""
        answer = client.get(ONTOLOGY, headers=admin_headers)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert {one["slug"] for one in body["kinds"]} == set(relations.KINDS)
        assert {one["slug"] for one in body["relations"]} == set(relations.RELATIONS)

    def test_관계가_어디_실려_있는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """`source` 가 빠지면 「표를 안 바꾸고 온톨로지를 얻는다」 가 설명되지 않는다."""
        body = client.get(ONTOLOGY, headers=admin_headers).json()
        found = {one["slug"]: one["source"] for one in body["relations"]}
        assert found["derived_from"] == "fk:samples.material_id"
        assert found["measured_by"].startswith("table:instrument_capabilities")

    def test_모르는_종류는_되묻게_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.get(
            RELATED,
            params={"kind": "얼렁뚱땅", "id": str(uuid.uuid4())},
            headers=admin_headers,
        )
        assert answer.status_code == 422
        assert answer.json()["error"]["code"] == "MNX-ONTOLOGY-0001"


class TestWalk:
    def test_이웃을_관계_이름과_함께_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        answer = client.get(
            RELATED, params={"kind": "specimen", "id": made["specimen"]}, headers=admin_headers
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        relations_seen = {one["relation"] for one in body["edges"]}
        assert {"part_of", "tested"} <= relations_seen
        # **관계별 개수를 먼저 준다** — AI 가 빈 길로 들어가지 않게.
        assert body["counts"]["part_of"] == 1

    def test_없는_마디는_404다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.get(
            RELATED,
            params={"kind": "material", "id": str(uuid.uuid4())},
            headers=admin_headers,
        )
        assert answer.status_code == 404
        assert answer.json()["error"]["code"] == "MNX-ONTOLOGY-0002"

    def test_시험에서_재료까지_길을_찾는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """사람이 사슬을 모를 때 쓰는 자리다 — 「이 값이 어느 재료에서 나왔나」."""
        made = _chain(client, db, admin_headers, owner_slug=None)
        answer = client.get(
            PATH,
            params={
                "from_kind": "test_run",
                "from_id": made["test_run"],
                "to_kind": "material",
                "to_id": made["material"],
            },
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["found"] is True
        assert [one["relation"] for one in body["steps"]] == [
            "tested",
            "part_of",
            "derived_from",
        ]

    def test_길이_없으면_없다고_한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**지어내지 않는다.** 못 찾은 것과 없는 것을 같은 모양으로 답한다."""
        first = _chain(client, db, admin_headers, owner_slug=None)
        second = _chain(client, db, admin_headers, owner_slug=None)
        answer = client.get(
            PATH,
            params={
                "from_kind": "material",
                "from_id": first["material"],
                "to_kind": "material",
                "to_id": second["material"],
                "max_depth": 2,
            },
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["found"] is False
        assert answer.json()["note"]


class TestProperty:
    def test_물성에서_장비로_간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """「이 물성을 재는 장비는 뭐야」 — 계획서의 첫 질문이다."""
        definition = CatalogDefinition(
            mt_id=770001,
            key="mechanical.yield_strength",
            name="항복강도",
            domain="mechanical",
            si_unit="Pa",
            value_type="number",
        )
        instrument = Instrument(
            mt_id=770002, vendor="MTS", model="Landmark 370", category="uts"
        )
        db.add_all([definition, instrument])
        db.flush()
        db.add(
            InstrumentCapability(
                mt_id=770003, instrument_id=instrument.id, property_key=definition.key
            )
        )
        db.commit()

        answer = client.get(
            RELATED,
            params={"kind": "property", "id": definition.key, "relation": ["measured_by"]},
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["node"]["name"] == "항복강도"
        assert [one["name"] for one in body["nodes"]] == ["MTS Landmark 370"]
        assert body["edges"][0]["relation"] == "measured_by"


class TestVisibility:
    def test_안_보이는_마디에서_길이_끊긴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**이 파일에서 가장 값진 시험이다.**

        잠근 부서의 재료는 남에게 「없는 것」이어야 한다. 이름만 가리고 「이 시험은
        어떤 재료와 이어져 있다」 를 남기면 그 사실 자체가 유출이다.
        """
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        made = _chain(client, db, admin_headers, owner_slug="dept-a")
        locked = client.patch(
            "/api/workspaces/dept-a", json={"restricted": True}, headers=admin_headers
        )
        assert locked.status_code == 200, locked.text

        outsider = _login_member_of(
            client, admin_headers, slug="dept-b", email="ont-outsider@example.com"
        )

        # 마디 자체가 없다.
        assert (
            client.get(
                RELATED, params={"kind": "material", "id": made["material"]}, headers=outsider
            ).status_code
            == 404
        )
        # 사슬 아래쪽에서 걸어 올라와도 재료가 안 나온다.
        assert (
            client.get(
                RELATED, params={"kind": "specimen", "id": made["specimen"]}, headers=outsider
            ).status_code
            == 404
        )
        # 길도 안 난다.
        answer = client.get(
            PATH,
            params={
                "from_kind": "test_run",
                "from_id": made["test_run"],
                "to_kind": "material",
                "to_id": made["material"],
            },
            headers=outsider,
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["found"] is False

    def test_같은_부서_사람에게는_보인다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """가리는 쪽이 예외다 — 안 그러면 「아무것도 안 보인다」 를 유출 방지라 부르게 된다."""
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        made = _chain(client, db, admin_headers, owner_slug="dept-a")
        client.patch(
            "/api/workspaces/dept-a", json={"restricted": True}, headers=admin_headers
        )
        insider = _login_member_of(
            client, admin_headers, slug="dept-a", email="ont-insider@example.com"
        )
        answer = client.get(
            PATH,
            params={
                "from_kind": "test_run",
                "from_id": made["test_run"],
                "to_kind": "material",
                "to_id": made["material"],
            },
            headers=insider,
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["found"] is True
