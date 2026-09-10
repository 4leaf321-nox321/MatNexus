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
from sqlalchemy import select
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


class Test출처와_파라미터_벌:
    """온톨로지에 늦게 들어온 두 마디.

    문헌 자료를 훑다 **「이 논문에서 온 값이 어디어디 쓰였나」 를 물을 방법이
    없다**는 것이 드러났다(실측 2026-09-10) — 출처가 값에 붙은 글자였지 마디가
    아니었다. 값(42,209건)을 마디로 만들면 그래프가 값으로 뒤덮이므로, **값은
    관계를 나르는 표로만** 쓰고 출처만 마디로 뒀다.
    """

    def test_출처가_지도에_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.get("/api/ontology", headers=admin_headers)
        assert got.status_code == 200, got.text
        body = got.json()
        kinds = {one["slug"] for one in body["kinds"]}
        assert {"source", "parameter_set"} <= kinds
        relations = {one["slug"] for one in body["relations"]}
        assert {"cited_by", "measured_in", "set_of"} <= relations

    def test_같은_이음을_값_수만큼_되풀이하지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**값 표가 관계를 나른다** — 한 쌍에 행이 수십 개다.

        안 묶으면 이웃 목록이 같은 출처로 채워지고, 상한에 값 몇 개로 닿는다
        (실측: Ecoflex 이웃 47개가 실제로는 출처 8개였다).
        """
        from app.modules.catalog.models import CatalogMaterial, CatalogSource, CatalogValue

        source = CatalogSource(mt_id=994001, kind="journal", title="한 논문")
        item = CatalogMaterial(mt_id=994002, name="온톨로지 시험재료", category="metal")
        # 값은 정의를 가리키는 FK 를 든다 — 없는 키로 넣으면 DB 가 막는다.
        definition = CatalogDefinition(
            mt_id=994003,
            key="physical.test_density",
            name="시험용 밀도",
            domain="physical",
            si_unit="kg/m^3",
            value_type="number",
        )
        db.add_all([source, item, definition])
        db.flush()
        for at in range(6):
            db.add(
                CatalogValue(
                    mt_id=994100 + at,
                    material_id=item.id,
                    source_id=source.id,
                    property_key="physical.test_density",
                    value_num=7800.0 + at,
                    unit="kg/m^3",
                    quality_tier=2,
                )
            )
        db.commit()

        got = client.get(
            "/api/ontology/related",
            params={"kind": "catalog_material", "id": str(item.id)},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        cited = [one for one in got.json()["edges"] if one["relation"] == "cited_by"]
        assert len(cited) == 1, cited

    def test_파라미터_벌은_재료의_가시_범위를_따른다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**안 붙이면 남의 부서 재료가 받아 온 벌이 검색에 뜬다.**

        그리고 열면 404 가 난다 — 「검색에는 뜨는데 열면 없다」 가 이 규칙을 한
        곳에 둔 이유다.
        """
        from app.modules.accounts.models import User
        from app.modules.materials.models import MaterialParameterSet
        from app.shared import graph, relations

        for slug, name in (("pset-a", "A 부서"), ("pset-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        made = _chain(client, db, admin_headers, owner_slug="pset-a")
        db.add(
            MaterialParameterSet(
                material_id=uuid.UUID(made["material"]),
                model="anand",
                label="가려질 벌",
                origin="catalog",
                terms=[{"term": "A", "value": 1.0, "unit": "1", "text": None}],
            )
        )
        db.commit()
        client.patch(
            "/api/workspaces/pset-a", json={"restricted": True}, headers=admin_headers
        )

        outsider = db.scalar(select(User).where(User.email == "ont-pset-outsider@example.com"))
        if outsider is None:
            _login_member_of(
                client, admin_headers, slug="pset-b", email="ont-pset-outsider@example.com"
            )
            outsider = db.scalar(
                select(User).where(User.email == "ont-pset-outsider@example.com")
            )
        assert outsider is not None

        allowed = graph.visible_ids(db, outsider, relations.KINDS["parameter_set"])
        assert allowed is not None, "가리는 규칙이 아예 없다"
        assert db.scalars(allowed).all() == [], "남의 부서 벌이 보인다"
