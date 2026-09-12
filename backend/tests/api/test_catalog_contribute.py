"""카탈로그에 직접 넣기 — **이관 밖의 물성·재료·값이 들어오고, 규칙이 지켜진다.**

정의의 키는 local. 으로       저쪽 키와 절대 안 겹친다
같은 물성은 또 못 만든다       이름·별칭이 같으면 그 키를 알려 주고 거절
값은 정의 단위로 환산           MPa 로 넣어도 Pa 로 저장 — 1000배 사고를 막는다
차원이 다르면 거절             밀도 자리에 온도를 못 넣는다
출처 없는 값은 없다            원본이 0건으로 지켜 온 불변식
추정값은 tier 4 이고 표지가 붙는다
이관해 온 것은 못 지운다        원본이 정본
직접 넣은 것은 넣은 사람·관리자만 지운다
검산은 직접 넣은 줄을 안 센다   이관 verify 가 늘 불일치를 내면 안 된다
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.catalog import importer
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyAlias
from app.modules.workspaces.models import Workspace

PROPERTY: dict[str, Any] = {
    "name": "습윤 굴곡탄성률",
    "domain": "mechanical",
    "slug": "flexural_modulus_wet",
    "si_unit": "Pa",
    "symbol": "E_f,wet",
    "test_standard": "ISO 178",
    "condition_axes": ["temperature_k"],
}

SOURCE = {"kind": "datasheet", "title": "PA66-GF30 기술자료", "year": 2024}


def member_headers(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    user = User(
        email="hong",
        password_hash=security.hash_password("member-password-1"),
        display_name="홍길동",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def imported(db: Session) -> CatalogMaterial:
    """이관해 온 것처럼 — 정의 하나, 재료 하나, 값 하나(mt_id 있음)."""
    db.add(
        CatalogDefinition(
            mt_id=900001,
            key="mechanical.youngs_modulus",
            name="탄성계수",
            domain="mechanical",
            si_unit="Pa",
            value_type="numeric",
        )
    )
    db.add(
        CatalogDefinition(
            mt_id=900002,
            key="physical.density",
            name="밀도",
            domain="physical",
            si_unit="kg/m3",
            value_type="numeric",
        )
    )
    material = CatalogMaterial(mt_id=900003, name="PA66-GF30", category="polymer")
    db.add(material)
    db.flush()
    db.add(
        CatalogValue(
            mt_id=900004,
            material_id=material.id,
            property_key="mechanical.youngs_modulus",
            value_num=9.0e9,
            unit="Pa",
            quality_tier=2,
        )
    )
    db.commit()
    return material


def make_property(client: TestClient, headers: dict[str, str], **override: Any) -> Any:
    return client.post(
        "/api/catalog/properties", json={**PROPERTY, **override}, headers=headers
    )


def make_value(
    client: TestClient, headers: dict[str, str], material_id: str, **override: Any
) -> Any:
    body = {
        "property_key": "mechanical.youngs_modulus",
        "value_num": 9.4,
        "unit": "GPa",
        "method": "handbook",
        "quality_tier": 2,
        "source": SOURCE,
        "source_detail": "표 2",
        **override,
    }
    return client.post(
        f"/api/catalog/materials/{material_id}/values", json=body, headers=headers
    )


class Test정의:
    def test_키는_local_로_시작하고_단위는_정본으로(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        made = make_property(client, admin_headers, si_unit="Pa")
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["key"] == "local.mechanical.flexural_modulus_wet"
        assert body["origin"] == "local"
        assert body["created_by"] == "시스템 관리자"
        assert body["si_unit"] == "Pa"

        # 사전과 매핑 표에 local 로 실린다.
        entry = next(
            one
            for one in client.get(
                "/api/catalog/properties/dictionary", headers=admin_headers
            ).json()["properties"]
            if one["key"] == body["key"]
        )
        assert entry["origin"] == "local"

    def test_이름이_같은_물성은_또_못_만든다(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        dup = make_property(client, admin_headers, name="탄성계수", slug="modulus_again")
        assert dup.status_code == 409, dup.text
        assert dup.json()["error"]["code"] == "MNX-CATALOG-0037"
        assert "mechanical.youngs_modulus" in dup.json()["error"]["message"]

    def test_별칭이_같아도_못_만든다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        imported: CatalogMaterial,
    ) -> None:
        db.add(
            PropertyAlias(
                property_key="mechanical.youngs_modulus",
                alias="영률",
                normalized="영률",
                source="manual",
            )
        )
        db.commit()
        dup = make_property(client, admin_headers, name="영률", slug="young")
        assert dup.status_code == 409, dup.text

    def test_모르는_단위와_도메인은_거절(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        assert make_property(client, admin_headers, si_unit="HV").status_code == 422
        assert make_property(client, admin_headers, domain="magic").status_code == 422
        assert make_property(client, admin_headers, slug="Flex Mod").status_code == 422

    def test_관리자만_만든다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        imported: CatalogMaterial,
    ) -> None:
        headers = member_headers(client, db, workspace)
        assert make_property(client, headers).status_code == 403

    def test_직접_만든_정의만_지우고_걸린_것이_있으면_못_지운다(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        key = make_property(client, admin_headers).json()["key"]
        gone = client.delete(f"/api/catalog/properties/{key}", headers=admin_headers)
        assert gone.status_code == 204
        # 이관해 온 것은 못 지운다.
        kept = client.delete(
            "/api/catalog/properties/mechanical.youngs_modulus", headers=admin_headers
        )
        assert kept.status_code == 422
        assert kept.json()["error"]["code"] == "MNX-CATALOG-0039"
        # 값이 걸린 local 정의도 못 지운다.
        key = make_property(client, admin_headers).json()["key"]
        make_value(client, admin_headers, str(imported.id), property_key=key)
        held = client.delete(f"/api/catalog/properties/{key}", headers=admin_headers)
        assert held.status_code == 409
        assert "값" in held.json()["error"]["message"]


class Test값:
    def test_다른_단위로_넣어도_정의_단위로_저장된다(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        made = make_value(client, admin_headers, str(imported.id), value_num=9.4, unit="GPa")
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["value"]["unit"] == "Pa"
        assert body["value"]["value_num"] == pytest.approx(9.4e9)
        assert body["value"]["origin"] == "local"
        assert body["value"]["created_by"] == "시스템 관리자"
        assert body["value"]["source"]["title"] == "PA66-GF30 기술자료"
        assert "GPa" in body["converted"] and "Pa" in body["converted"]

        # 상세에 이관해 온 값과 나란히 서고, 구별된다.
        detail = client.get(
            f"/api/catalog/materials/{imported.id}", headers=admin_headers
        ).json()
        origins = {one["origin"] for one in detail["values"]}
        assert origins == {"catalog", "local"}

    def test_차원이_다르면_거절(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        bad = make_value(client, admin_headers, str(imported.id), value_num=300, unit="K")
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0044"
        none = make_value(client, admin_headers, str(imported.id), unit=None)
        assert none.status_code == 422

    def test_출처_없는_값은_없다(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        bad = make_value(client, admin_headers, str(imported.id), source={"kind": "web"})
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0043"

    def test_같은_출처는_한_번만_만든다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        imported: CatalogMaterial,
    ) -> None:
        make_value(client, admin_headers, str(imported.id), value_num=9.0, unit="GPa")
        make_value(client, admin_headers, str(imported.id), value_num=9.2, unit="GPa")
        make_value(
            client,
            admin_headers,
            str(imported.id),
            value_num=9.3,
            unit="GPa",
            source={"kind": "journal", "doi": "10.1000/xyz", "title": "다른 논문"},
        )
        make_value(
            client,
            admin_headers,
            str(imported.id),
            value_num=9.5,
            unit="GPa",
            source={"kind": "journal", "doi": "10.1000/XYZ"},
        )
        assert db.scalar(select(CatalogSource).where(CatalogSource.year == 2024)) is not None
        assert len(db.scalars(select(CatalogSource)).all()) == 2

    def test_추정값은_tier_4_이고_가정_표지가_붙는다(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        wrong = make_value(
            client, admin_headers, str(imported.id), method="estimated", quality_tier=2
        )
        assert wrong.status_code == 422
        assert wrong.json()["error"]["code"] == "MNX-CATALOG-0045"
        made = make_value(
            client, admin_headers, str(imported.id), method="estimated", quality_tier=4
        )
        assert made.status_code == 201, made.text
        assert made.json()["value"]["conditions"]["assumption"] is True

    def test_넣은_사람과_관리자만_지우고_이관해_온_값은_못_지운다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
        imported: CatalogMaterial,
    ) -> None:
        hong = member_headers(client, db, workspace)
        mine = make_value(client, hong, str(imported.id)).json()["value"]["id"]
        theirs = make_value(client, admin_headers, str(imported.id)).json()["value"]["id"]
        assert client.delete(f"/api/catalog/values/{theirs}", headers=hong).status_code == 403
        assert client.delete(f"/api/catalog/values/{mine}", headers=hong).status_code == 204
        assert (
            client.delete(f"/api/catalog/values/{theirs}", headers=admin_headers).status_code
            == 204
        )
        imported_value = db.scalar(select(CatalogValue).where(CatalogValue.mt_id == 900004))
        assert imported_value is not None
        kept = client.delete(f"/api/catalog/values/{imported_value.id}", headers=admin_headers)
        assert kept.status_code == 422
        assert kept.json()["error"]["code"] == "MNX-CATALOG-0039"


class Test재료:
    def test_만들고_값을_달고_같은_이름은_거절(
        self, client: TestClient, admin_headers: dict[str, str], imported: CatalogMaterial
    ) -> None:
        made = client.post(
            "/api/catalog/materials",
            json={"name": "PA66-GF50", "category": "polymer", "manufacturer": "시험사"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert made.json()["origin"] == "local"
        material_id = made.json()["id"]
        dup = client.post(
            "/api/catalog/materials",
            json={"name": "pa66-gf30", "category": "polymer"},
            headers=admin_headers,
        )
        assert dup.status_code == 409
        assert dup.json()["error"]["details"]["catalog_material_id"] == str(imported.id)
        bad = client.post(
            "/api/catalog/materials",
            json={"name": "X", "category": "unobtainium"},
            headers=admin_headers,
        )
        assert bad.status_code == 422

        # 값이 달리면 못 지우고, 값을 지우면 지워진다.
        value_id = make_value(client, admin_headers, material_id).json()["value"]["id"]
        held = client.delete(f"/api/catalog/materials/{material_id}", headers=admin_headers)
        assert held.status_code == 409
        client.delete(f"/api/catalog/values/{value_id}", headers=admin_headers)
        gone = client.delete(f"/api/catalog/materials/{material_id}", headers=admin_headers)
        assert gone.status_code == 204
        kept = client.delete(f"/api/catalog/materials/{imported.id}", headers=admin_headers)
        assert kept.status_code == 422


class Test이관과_공존:
    def test_검산은_직접_넣은_줄을_안_센다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        imported: CatalogMaterial,
    ) -> None:
        """이관 verify 가 원본 행수와 견줄 때 local 줄이 섞이면 늘 불일치다."""
        make_property(client, admin_headers)
        make_value(client, admin_headers, str(imported.id))
        con = sqlite3.connect(":memory:")
        con.executescript(
            """
            create table property_definition(id);
            create table source(id);
            create table material(id);
            create table property_value(id, source_id, quality_tier);
            insert into property_definition values (1), (2);
            insert into material values (1);
            insert into property_value values (1, NULL, 2);
            """
        )
        assert importer.verify(db, con) == []
