"""재료 기본 칸(밀도 · 푸아송비)의 **근거** — 문헌에서 받아 온 값은 그 등급을 든다
(2026-11-14, VOC 50).

문헌값을 채택하면 밀도 · 푸아송비는 숫자만 재료 칸에 써지고 출처가 버려졌다. 카드는 그 값을
「재료에 적힌 공칭값(등급 3)」 으로 봐, 문헌 등급 4(추정)가 3으로 올라가 보였다. 이 시험이
지키는 것:

    잇는다      받아 온 문헌 값의 등급 · 출처 · 근거 문서가 칸과 카드에 간다
    대 본다     숫자가 받아 왔다는 문헌 값과 다르면 거절한다
    묶인다      같은 값을 되보내면 그대로, 값만 고치면 근거가 풀려 등급 3 으로
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.fitting import card_tiers
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.shared import declared_card

DENSITY = "physical.density"
POISSON = "mechanical.poisson_ratio"


@pytest.fixture()
def material(db: Session) -> Material:
    one = Material(record_name="PA66_GF30_-", family="Polymer", category="PA", grade="PA66")
    db.add(one)
    db.commit()
    return one


def _values(db: Session) -> dict[str, CatalogValue]:
    """문헌 재료 하나의 밀도(등급 4 · 추정)와 푸아송비(등급 2)."""
    for key, name, unit in ((DENSITY, "밀도", "kg/m^3"), (POISSON, "푸아송비", "1")):
        if db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key)) is None:
            db.add(
                CatalogDefinition(
                    key=key, domain="physical", name=name, si_unit=unit, value_type="numeric"
                )
            )
    paper = CatalogSource(kind="handbook", title="Plastics Handbook")
    owner = CatalogMaterial(name="PA66 GF30", category="polymer")
    db.add_all([paper, owner])
    db.flush()
    made = {
        DENSITY: CatalogValue(
            material_id=owner.id,
            property_key=DENSITY,
            value_num=1360.0,
            unit="kg/m^3",
            quality_tier=4,
            source_id=paper.id,
            method="estimated",
        ),
        POISSON: CatalogValue(
            material_id=owner.id,
            property_key=POISSON,
            value_num=0.35,
            unit="1",
            quality_tier=2,
            source_id=paper.id,
            method="measured",
        ),
    }
    db.add_all(made.values())
    db.commit()
    return made


def _adopt(
    client: TestClient, headers: dict[str, str], material: Material, **over: Any
) -> Any:
    return client.patch(
        f"/api/materials/{material.id}",
        json={
            "density": 1360.0,
            "density_unit": "kg/m3",
            "density_source": "literature",
            "density_reference": "Plastics Handbook (문헌 물성 카탈로그, 추정)",
            "poisson_ratio": 0.35,
            "poisson_ratio_source": "literature",
            "poisson_ratio_reference": "Plastics Handbook (문헌 물성 카탈로그, 실측)",
            **over,
        },
        headers=headers,
    )


class Test받아_온_근거:
    def test_문헌_등급과_근거가_칸과_카드에_간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        values = _values(db)
        saved = _adopt(
            client,
            admin_headers,
            material,
            density_catalog_value_ids=[str(values[DENSITY].id)],
            poisson_ratio_catalog_value_ids=[str(values[POISSON].id)],
        )
        assert saved.status_code == 200, saved.text
        sources = saved.json()["column_sources"]
        assert sources["density"]["catalog_tier"] == 4
        assert sources["poisson_ratio"]["catalog_tier"] == 2
        assert "Plastics Handbook" in sources["density"]["reference"]

        db.refresh(material)
        density = declared_card.inherit_density(material, [], None)
        assert density.source == "declared:literature+catalog4"
        assert density.reference and "Plastics Handbook" in density.reference
        poisson = declared_card.inherit_poisson(material, None)
        assert poisson.source == "declared:literature+catalog2"

        # 카드가 싣는 모양 그대로 — 값 · 출처 · 근거 문서(카드 경로 다섯이 같은 식으로 싣는다).
        elastic: dict[str, Any] = {
            "density": density.value,
            "density_source": density.source,
            **density.reference_of("density"),
            "poisson_ratio": poisson.value,
            "poisson_ratio_source": poisson.source,
            **poisson.reference_of("poisson_ratio"),
        }
        assert "Plastics Handbook" in elastic["density_reference"]
        card = PropertyCard(
            material_id=material.id,
            label="문헌 밀도 카드",
            status="draft",
            source={"sample_count": 3},
            blocks={"elastic": {"values": elastic}},
        )
        graded = card_tiers.value_tiers(card)
        # 추정(등급 4)이 「재료 공칭(3)」 으로 올라가 보이지 않는다.
        assert graded["elastic.density"] == 4
        assert graded["elastic.poisson_ratio"] == 2

    def test_숫자가_다르면_거절한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        values = _values(db)
        refused = _adopt(
            client,
            admin_headers,
            material,
            density=1400.0,
            density_catalog_value_ids=[str(values[DENSITY].id)],
        )
        assert refused.status_code == 422, refused.text

    def test_같은_값은_그대로_값만_고치면_근거가_풀린다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        values = _values(db)
        _adopt(
            client,
            admin_headers,
            material,
            density_catalog_value_ids=[str(values[DENSITY].id)],
        )
        # 화면이 폼째 저장 — 같은 값을 근거 없이 되보낸다.
        again = client.patch(
            f"/api/materials/{material.id}",
            json={"density": 1360.0, "density_unit": "kg/m3", "note": "메모만 고침"},
            headers=admin_headers,
        )
        assert again.json()["column_sources"]["density"]["catalog_tier"] == 4
        # 사람이 값을 고쳤다 — 근거는 그 값의 것이 아니다.
        edited = client.patch(
            f"/api/materials/{material.id}",
            json={"density": 1380.0, "density_unit": "kg/m3"},
            headers=admin_headers,
        )
        assert "density" not in edited.json()["column_sources"]
        db.refresh(material)
        assert declared_card.inherit_density(material, [], None).source == "material"

    def test_출처만_있고_근거_문서가_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], material: Material
    ) -> None:
        refused = _adopt(client, admin_headers, material, density_reference="")
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0070"
