"""BOM 혼합 덱 — **사내 카드 우선 + 문헌 보충, 한 파일** (MaterialTwin 이식 2.5단계).

카드가 있는 부품은 곡선 덱(*MAT_024), 없는 부품은 문헌 스칼라(*MAT_ELASTIC),
합쳐서 *KEYWORD/*END 한 번 — MID 는 부품표의 번호 그대로
모자란 줄은 거르지 않고 알린다 · MID 중복은 요청째 거부
매칭 기억(워크벤치)은 넣은 대로 돌아오고, 비우면 지워진다
솔버를 고른다(2026-09-16) — 한 파일은 한 솔버, 재료 id 만 줘도 카드를 서버가 고른다,
    단일 카드 export 도 MID 를 받는다
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
                ],
                # SI 숫자를 대조하는 시험이라 SI 를 고른다 — 기본은 mm·N·tonne(ADR 0036).
                "units": "si",
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


class Test합성_곡선:
    def add_yield(self, db: Session, material_id: Any) -> None:
        """스냅샷에는 강도 스칼라가 없다 — 항복강도 정의와 값을 심는다."""
        from app.modules.catalog.models import CatalogDefinition, CatalogValue

        db.add(
            CatalogDefinition(
                mt_id=901,
                key="mechanical.yield_strength",
                domain="mechanical",
                name="항복강도",
                symbol="sigy",
                si_unit="Pa",
                value_type="numeric",
            )
        )
        db.flush()
        db.add(
            CatalogValue(
                mt_id=901,
                material_id=material_id,
                property_key="mechanical.yield_strength",
                value_num=215e6,
                unit="Pa",
                quality_tier=2,
            )
        )
        db.commit()

    def test_합성을_켜면_문헌_스칼라로_곡선_덱이_나온다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        ids = catalog_ids(db, tmp_path)
        self.add_yield(db, ids["sus"])
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {
                        "mid": 5,
                        "name": "SUS304",
                        "catalog_material_id": str(ids["sus"]),
                        "synthesize": True,
                    }
                ]
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        made = body.json()
        assert made["synthetic_count"] == 1 and made["literature_count"] == 0
        # 곡선 덱(*MAT_024)으로 나가고, 지어냈다는 사실이 각주에 있다.
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in made["text"]
        assert "합성 곡선" in made["text"] and "실측이 아니다" in made["text"]
        # 어느 스칼라의 어느 출처였는지도 각주로 남는다.
        assert "항복강도" in made["text"]

    def test_스칼라가_모자라면_합성하지_않고_이유를_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """지어낼 근거가 없으면 지어내지 않는다 — FR-4 는 유리전이온도뿐이다."""
        ids = catalog_ids(db, tmp_path)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {"mid": 1, "name": "SUS304", "catalog_material_id": str(ids["sus"])},
                    {
                        "mid": 2,
                        "name": "FR-4",
                        "catalog_material_id": str(ids["fr4"]),
                        "synthesize": True,
                    },
                ]
            },
            headers=admin_headers,
        ).json()
        whys = {row["mid"]: row["why"] for row in body["skipped"]}
        assert "합성할 스칼라가 모자랍니다" in whys[2]


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


class Test솔버를_고른다:
    """연결된 플랫폼은 **재료 · MID · 솔버**만 안다 — 카드 id 를 모르고, LS-DYNA 만 쓰지
    않는다. 그래서 형식을 받고, 재료 id 로 카드를 서버가 고르고, 단일 export 도 MID 를
    박는다. 틀리면 조용히 다른 재료 번호가 해석에 들어간다."""

    def test_재료_id와_형식으로_한_파일(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, card = make_card(db)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "format": "openradioss",
                "rows": [{"mid": 7, "name": "도어", "material_id": str(material.id)}],
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        made = body.json()
        assert made["format_family"] == "openradioss"
        assert made["filename"].endswith(".rad")
        assert made["skipped"] == [] and made["card_count"] == 1
        # 요청의 MID 가 그 솔버의 자리에 박힌다 — 카드 유래 번호가 아니다.
        assert "/MAT/LAW36/7/1" in made["text"]
        from matcore import export

        assert f"/MAT/LAW36/{export.solver_id_from(str(card.id))}/1" not in made["text"]

    def test_abaqus_여러_재료가_한_파일에_이어_선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material, card = make_card(db)
        other = Material(
            record_name="SPCC_1.0", family="Metal", category="Steel", grade="SPCC"
        )
        db.add(other)
        db.flush()
        db.add(
            PropertyCard(
                material_id=other.id, label="대표", status="draft", blocks=card.blocks
            )
        )
        db.commit()
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "format": "abaqus",
                "rows": [
                    {"mid": 1, "name": "A", "material_id": str(material.id)},
                    {"mid": 2, "name": "B", "material_id": str(other.id)},
                ],
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        made = body.json()
        assert made["text"].count("*MATERIAL, NAME=") == 2
        assert made["filename"].endswith(".inp")
        assert made["card_count"] == 2

    def test_다른_솔버_줄과_문헌_줄은_건너뛰고_이유를_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
    ) -> None:
        """조용히 섞이면 솔버가 다른 카드를 읽는다. 문헌은 LS-DYNA 형식만 낼 수 있다."""
        material, _ = make_card(db)
        ids = catalog_ids(db, tmp_path)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "format": "abaqus",
                "rows": [
                    {"mid": 1, "name": "A", "material_id": str(material.id)},
                    {"mid": 2, "name": "B", "material_id": str(material.id), "format": "dyna"},
                    {"mid": 3, "name": "C", "catalog_material_id": str(ids["sus"])},
                ],
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        made = body.json()
        why = {one["mid"]: one["why"] for one in made["skipped"]}
        assert "다른 솔버" in why[2]
        assert "LS-DYNA" in why[3]
        assert made["card_count"] == 1

    def test_카드가_없는_재료는_이유와_함께_건너뛴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        bare = Material(record_name="빈재료", family="Metal", category="Steel", grade="X")
        db.add(bare)
        db.commit()
        _, card = make_card(db)
        body = client.post(
            "/api/fitting/decks/bom",
            json={
                "rows": [
                    {"mid": 1, "name": "A", "card_id": str(card.id)},
                    {"mid": 2, "name": "B", "material_id": str(bare.id)},
                ]
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        skipped = body.json()["skipped"]
        assert skipped and skipped[0]["mid"] == 2 and "카드가 없는" in skipped[0]["why"]

    def test_모르는_형식은_있는_것을_알려_준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _, card = make_card(db)
        refused = client.post(
            "/api/fitting/decks/bom",
            json={
                "format": "nastran",
                "rows": [{"mid": 1, "name": "A", "card_id": str(card.id)}],
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert "abaqus" in refused.json()["error"]["message"]

    def test_단일_export_도_MID_를_받는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _, card = make_card(db)
        got = client.get(
            f"/api/fitting/cards/{card.id}/export",
            params={"format": "dyna", "units": "si", "mid": 42},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        assert f"{42:>10d}{7850.0:>10.3E}" in got.text
        from matcore import export

        assert f"{export.solver_id_from(str(card.id)):>10d}" not in got.text
        # 범위 밖은 거절 — 솔버는 0 이나 음수를 조용히 다른 뜻으로 읽는다.
        assert (
            client.get(
                f"/api/fitting/cards/{card.id}/export",
                params={"format": "dyna", "mid": 0},
                headers=admin_headers,
            ).status_code
            == 422
        )
