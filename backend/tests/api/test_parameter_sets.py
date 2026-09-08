"""재료의 **모델 파라미터 집합** — 문헌에서 한 벌씩 받아 온다(ADR 0029).

무는 것이 여섯이다.

    한 벌이 통째로 온다            `A` 만 떼어 오면 뜻이 없다
    **단위를 환산하지 않는다**      이 값들은 SI 가 아니다 — 환산하면 모델이 못 쓴다
    같은 벌을 두 번 안 담는다      다시 채택하면 갱신이다
    다른 논문 벌은 나란히 남는다   후보를 견주는 것이 카드에 안 넣는 이유다
    벌이 여럿이면 되묻는다         조용히 하나를 고르지 않는다
    권한 밖 재료에는 못 담는다     읽기와 쓰기는 다른 축이다
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue

KEY = "mechanical.set_anand"

#: 단위가 항마다 다르다 — 이 한 벌이 이 기능의 이유다.
TERMS = [
    ("a", 1.34, "1"),
    ("A", 14900000.0, "1/s"),
    ("h0", 2640.75, "MPa"),
    ("Q/R", 10830.0, "K"),
]


@pytest.fixture
def literature(db: Session) -> Iterator[tuple[CatalogMaterial, CatalogMaterial]]:
    """같은 물성에 **벌이 둘인** 문헌 재료 하나와, 벌이 하나인 재료 하나."""
    parameters.forget()
    db.add(
        CatalogDefinition(
            mt_id=991001,
            key=KEY,
            name="시험용 Anand 상수",
            domain="mechanical",
            si_unit="1",
            value_type="number",
        )
    )
    two = CatalogMaterial(mt_id=991002, name="벌 둘 솔더", category="metal")
    one = CatalogMaterial(mt_id=991003, name="벌 하나 솔더", category="metal")
    db.add_all([two, one])
    db.flush()

    at = 0
    for material, sets in ((two, ("wang1998", "liu2014")), (one, ("only",))):
        for set_id in sets:
            for term, value, unit in TERMS:
                at += 1
                db.add(
                    CatalogValue(
                        mt_id=991100 + at,
                        material_id=material.id,
                        property_key=KEY,
                        value_num=value,
                        unit="1",
                        quality_tier=2,
                        source_detail=f"{set_id} 논문",
                        conditions={
                            "term": term,
                            "unit_of_term": unit,
                            "model": "anand",
                            "set_id": set_id,
                        },
                    )
                )
    db.commit()
    parameters.forget()
    yield two, one
    parameters.forget()


def _material(client: TestClient, admin_headers: dict[str, str]) -> str:
    made = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": f"PS-{uuid.uuid4().hex[:6]}"},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


class TestAdopt:
    def test_한_벌이_통째로_온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """**단위가 항마다 다른 채로** 와야 한다 — 그것이 이 표의 존재 이유다."""
        _, single = literature
        material_id = _material(client, admin_headers)

        answer = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(single.id)},
            headers=admin_headers,
        )
        assert answer.status_code == 201, answer.text
        body = answer.json()
        assert body["model"] == "anand"
        assert body["label"] == "시험용 Anand 상수"
        assert {one["term"] for one in body["terms"]} == {t[0] for t in TERMS}
        assert {one["unit"] for one in body["terms"]} == {"1", "1/s", "MPa", "K"}

    def test_단위를_환산하지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """h0 = 2640.75 MPa 다. SI 로 고치면 2.64e9 가 되어 모델이 못 쓴다."""
        _, single = literature
        material_id = _material(client, admin_headers)
        answer = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(single.id)},
            headers=admin_headers,
        )
        h0 = next(one for one in answer.json()["terms"] if one["term"] == "h0")
        assert h0["value"] == pytest.approx(2640.75)
        assert h0["unit"] == "MPa"

    def test_벌이_여럿이면_되묻는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """**조용히 하나를 고르지 않는다** — 논문이 다르면 값이 다르다."""
        two, _ = literature
        material_id = _material(client, admin_headers)
        answer = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(two.id)},
            headers=admin_headers,
        )
        assert answer.status_code == 422, answer.text
        assert answer.json()["error"]["code"] == "MNX-MATERIALS-0031"
        assert "wang1998" in answer.json()["error"]["message"]

    def test_다른_논문_벌은_나란히_남는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """**후보를 견주는 것이 카드에 바로 안 넣는 이유다**(ADR 0029 D3)."""
        two, _ = literature
        material_id = _material(client, admin_headers)
        for set_id in ("wang1998", "liu2014"):
            made = client.post(
                f"/api/materials/{material_id}/parameter-sets",
                json={
                    "property_key": KEY,
                    "catalog_material_id": str(two.id),
                    "set_id": set_id,
                },
                headers=admin_headers,
            )
            assert made.status_code == 201, made.text

        listed = client.get(
            f"/api/materials/{material_id}/parameter-sets", headers=admin_headers
        )
        assert {one["source_ref"] for one in listed.json()} == {"wang1998", "liu2014"}

    def test_같은_벌을_두_번_담으면_갱신이다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """줄이 둘로 늘면 카드가 어느 것을 쓸지 알 수 없다."""
        _, single = literature
        material_id = _material(client, admin_headers)
        body = {"property_key": KEY, "catalog_material_id": str(single.id)}
        first = client.post(
            f"/api/materials/{material_id}/parameter-sets", json=body, headers=admin_headers
        )
        again = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={**body, "notes": "다시 받음"},
            headers=admin_headers,
        )
        assert again.status_code == 201, again.text
        assert again.json()["id"] == first.json()["id"]
        assert again.json()["notes"] == "다시 받음"

        listed = client.get(
            f"/api/materials/{material_id}/parameter-sets", headers=admin_headers
        )
        assert len(listed.json()) == 1

    def test_없는_벌은_404다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        material_id = _material(client, admin_headers)
        answer = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={
                "property_key": "mechanical.nothing",
                "catalog_material_id": str(uuid.uuid4()),
            },
            headers=admin_headers,
        )
        assert answer.status_code == 404
        assert answer.json()["error"]["code"] == "MNX-MATERIALS-0030"

    def test_지울_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        _, single = literature
        material_id = _material(client, admin_headers)
        made = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(single.id)},
            headers=admin_headers,
        )
        dropped = client.delete(
            f"/api/materials/{material_id}/parameter-sets/{made.json()['id']}",
            headers=admin_headers,
        )
        assert dropped.status_code == 204
        listed = client.get(
            f"/api/materials/{material_id}/parameter-sets", headers=admin_headers
        )
        assert listed.json() == []
