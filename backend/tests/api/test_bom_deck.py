"""BOM 혼합 덱 — **사내 카드 우선 + 문헌 보충, 한 파일** (MaterialTwin 이식 2.5단계).

카드가 있는 부품은 곡선 덱(*MAT_024), 없는 부품은 문헌 스칼라(*MAT_ELASTIC),
합쳐서 *KEYWORD/*END 한 번 — MID 는 부품표의 번호 그대로
모자란 줄은 거르지 않고 알린다 · MID 중복은 요청째 거부
매칭 기억(워크벤치)은 넣은 대로 돌아오고, 비우면 지워진다
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_catalog import make_snapshot

from app.modules.catalog import importer as catalog_importer
from app.modules.catalog.models import CatalogMaterial
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material


def make_card(db: Session) -> tuple[Material, PropertyCard]:
    """전역 재료 + 확정 카드(탄성 + 소성 표) — 곡선 덱이 나올 수 있는 최소."""
    material = Material(
        record_name="SGARC440_-_1.2", family="Metal", category="Steel", grade="SGARC440"
    )
    db.add(material)
    db.flush()
    card = PropertyCard(
        material_id=material.id,
        label="대표 TD",
        status="published",
        blocks={
            "elastic": {
                "values": {
                    "youngs_modulus": 205e9,
                    "poisson_ratio": 0.29,
                    "density": 7850.0,
                }
            },
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 440e6},
                    {"plastic_strain": 0.05, "true_stress": 520e6},
                ]
            },
        },
    )
    db.add(card)
    db.commit()
    return material, card


def catalog_ids(db: Session, tmp_path: Path) -> dict[str, Any]:
    catalog_importer.run(db, make_snapshot(tmp_path))
    db.commit()
    sus = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 1))
    fr4 = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 2))
    assert sus is not None and fr4 is not None
    return {"sus": sus.id, "fr4": fr4.id}


class Test혼합_한_파일:
    def test_카드는_곡선으로_문헌은_스칼라로_한_파일에(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        _, card = make_card(db)
        ids = catalog_ids(db, tmp_path)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {"mid": 1, "name": "SGARC440", "card_id": str(card.id)},
                    {"mid": 2, "name": "SUS304", "catalog_material_id": str(ids["sus"])},
                ]
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        made = body.json()
        text = made["text"]
        # 한 파일 — *KEYWORD/*END 는 한 번씩만.
        assert text.count("*KEYWORD") == 1 and text.count("*END") == 1
        # 카드 부품은 곡선 덱, 문헌 부품은 스칼라 덱 — 같은 파일에 선다.
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in text
        assert "*MAT_ELASTIC" in text
        assert made["card_count"] == 1 and made["literature_count"] == 1
        assert made["skipped"] == []
        # **MID 는 부품표의 번호다** — 카드의 자체 번호(uuid 유래)가 나가면
        # 부품-재료 연결이 조용히 틀린다. 고정 10칸 mid+ro 자리를 직접 문다.
        from matcore import export

        assert f"{1:>10d}{7850.0:>10.3E}" in text  # 카드 부품 — MID 1
        assert f"{2:>10d}{7930.0:>10.3E}" in text  # 문헌 부품 — MID 2
        assert str(export.solver_id_from(str(card.id))) not in text
        # 문헌값 출처 각주가 파일에 있다 — 덱만 받은 사람의 근거.
        assert "문헌 카탈로그: SUS304" in text
        # 사내 카드의 근거 줄도 있다.
        assert "SGARC440" in text

    def test_모자란_줄은_거르지_않고_알린다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        ids = catalog_ids(db, tmp_path)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {"mid": 1, "name": "SUS304", "catalog_material_id": str(ids["sus"])},
                    # FR-4 는 유리전이온도뿐 — 탄성 덱에 못 실린다.
                    {"mid": 2, "name": "FR-4", "catalog_material_id": str(ids["fr4"])},
                    # 매칭을 안 정한 줄.
                    {"mid": 3, "name": "미확정 부품"},
                ]
            },
            headers=admin_headers,
        ).json()
        assert body["literature_count"] == 1
        whys = {row["mid"]: row["why"] for row in body["skipped"]}
        assert "문헌값이 모자랍니다" in whys[2]
        assert "매칭" in whys[3]

    def test_MID_중복은_요청째_거부한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        ids = catalog_ids(db, tmp_path)
        refused = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {"mid": 7, "name": "a", "catalog_material_id": str(ids["sus"])},
                    {"mid": 7, "name": "b", "catalog_material_id": str(ids["sus"])},
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert "MID 7" in refused.json()["error"]["message"]


class Test매칭_기억:
    def test_넣은_대로_돌아오고_비우면_지워진다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
    ) -> None:
        material, _ = make_card(db)
        put = client.put(
            "/api/workbench/bom-aliases",
            json={"query": "SGARC440-CSP", "material_id": str(material.id)},
            headers=admin_headers,
        )
        assert put.status_code == 200, put.text

        # 대소문자·공백이 달라도 같은 기억이다.
        found = client.post(
            "/api/workbench/bom-aliases/lookup",
            json={"queries": ["sgarc440-csp", "모르는 이름"]},
            headers=admin_headers,
        ).json()["found"]
        assert found[0] is not None
        assert found[0]["material_id"] == str(material.id)
        assert found[1] is None

        # 비우면 지워진다 — 그 이름은 다시 물어보라는 뜻.
        client.put(
            "/api/workbench/bom-aliases",
            json={"query": "SGARC440-CSP"},
            headers=admin_headers,
        )
        again = client.post(
            "/api/workbench/bom-aliases/lookup",
            json={"queries": ["SGARC440-CSP"]},
            headers=admin_headers,
        ).json()["found"]
        assert again == [None]
