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

    def test_출처_이름_빈_벌은_문헌_재료가_다르면_따로_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """2026-11-15: 열쇠가 (재료, 모델, source_ref) 라 `set_id` 가 빈 벌은 source_ref
        가 둘 다 "" 였다 — 다른 문헌 재료에서 받은 Anand 벌이 앞엣것을 **조용히 덮었다**. 문헌
        재료가
        열쇠에 든다. 이 칸이 생기기 전의 줄(문헌 재료 빔)은 같은 벌일 때만 올린다."""
        from sqlalchemy import select

        from app.modules.materials.models import MaterialParameterSet

        owners = [
            CatalogMaterial(mt_id=991004 + n, name=f"이름 없는 벌 {n}", category="metal")
            for n in range(2)
        ]
        db.add_all(owners)
        db.flush()
        for n, owner in enumerate(owners):
            for k, (term, value, unit) in enumerate(TERMS):
                db.add(
                    CatalogValue(
                        mt_id=991200 + 10 * n + k,
                        material_id=owner.id,
                        property_key=KEY,
                        value_num=value * (n + 2),
                        unit="1",
                        quality_tier=2,
                        source_detail=f"논문 {n}",
                        conditions={"term": term, "unit_of_term": unit, "model": "anand"},
                    )
                )
        db.commit()
        parameters.forget()
        material_id = _material(client, admin_headers)

        # 이 칸이 생기기 전에 받아 둔 줄 — 문헌 재료가 비어 있다. 출처 글이 첫 문헌 재료와
        # 같다.
        legacy = MaterialParameterSet(
            material_id=uuid.UUID(material_id),
            model="anand",
            label="옛 줄",
            origin="catalog",
            source_ref="",
            source_detail="논문 0",
            terms=[],
        )
        db.add(legacy)
        db.commit()

        made = [
            client.post(
                f"/api/materials/{material_id}/parameter-sets",
                json={"property_key": KEY, "catalog_material_id": str(owner.id)},
                headers=admin_headers,
            )
            for owner in owners
        ]
        assert all(one.status_code == 201 for one in made), [one.text for one in made]
        # 첫 문헌 재료는 옛 줄을 이어받고(같은 출처 글), 둘째는 덮지 않고 새 줄이다.
        assert made[0].json()["id"] == str(legacy.id)
        assert made[1].json()["id"] != made[0].json()["id"]

        db.expire_all()
        rows = {
            row.catalog_material_id: row
            for row in db.scalars(
                select(MaterialParameterSet).where(
                    MaterialParameterSet.material_id == uuid.UUID(material_id)
                )
            )
        }
        assert set(rows) == {owners[0].id, owners[1].id}
        values = {
            owner_id: {one["term"]: one["value"] for one in row.terms}
            for owner_id, row in rows.items()
        }
        assert values[owners[0].id]["a"] == pytest.approx(1.34 * 2)
        assert values[owners[1].id]["a"] == pytest.approx(1.34 * 3), "둘째가 첫째를 덮었다"

        # 다시 받으면 그 문헌 재료의 줄을 갱신한다 — 늘지 않는다.
        again = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(owners[1].id)},
            headers=admin_headers,
        )
        assert again.json()["id"] == made[1].json()["id"]
        listed = client.get(
            f"/api/materials/{material_id}/parameter-sets", headers=admin_headers
        )
        assert len(listed.json()) == 2

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


class TestCardCites:
    """카드는 벌을 **인용**한다 — 소유하지 않는다(ADR 0029 D3)."""

    def test_카드가_벌을_싣는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """**원본은 재료가 계속 든다.** 카드에는 어디서 왔는지가 행마다 적힌다."""
        _, single = literature
        material_id = _material(client, admin_headers)
        adopted = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(single.id)},
            headers=admin_headers,
        )
        assert adopted.status_code == 201, adopted.text

        made = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": material_id,
                "label": "파라미터 인용 카드",
                "parameter_set_ids": [adopted.json()["id"]],
            },
            headers=admin_headers,
        )
        assert made.status_code in (200, 201), made.text
        block = made.json()["blocks"]["model_params"]
        assert block["values"]["sets"] == 1
        assert block["values"]["models"] == "anand"

        rows = block["rows"]
        assert {row["name"] for row in rows} == {t[0] for t in TERMS}
        # **어디서 왔는지가 행마다 적힌다** — 카드만 봐도 되짚을 수 있어야 한다.
        assert {row["set"] for row in rows} == {"anand/only"}
        h0 = next(row for row in rows if row["name"] == "h0")
        assert h0["value"] == pytest.approx(2640.75)
        assert h0["unit"] == "MPa"

        # 재료 쪽 원본은 그대로 남는다.
        listed = client.get(
            f"/api/materials/{material_id}/parameter-sets", headers=admin_headers
        )
        assert len(listed.json()) == 1

    def test_남의_벌은_못_싣는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        literature: tuple[CatalogMaterial, CatalogMaterial],
    ) -> None:
        """다른 재료의 벌을 실으면 그 카드의 근거가 거짓이 된다."""
        _, single = literature
        mine = _material(client, admin_headers)
        other = _material(client, admin_headers)
        adopted = client.post(
            f"/api/materials/{other}/parameter-sets",
            json={"property_key": KEY, "catalog_material_id": str(single.id)},
            headers=admin_headers,
        )

        made = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": mine,
                "label": "남의 벌",
                "parameter_set_ids": [adopted.json()["id"]],
            },
            headers=admin_headers,
        )
        assert made.status_code == 422, made.text
        assert made.json()["error"]["code"] == "MNX-FITTING-0036"
