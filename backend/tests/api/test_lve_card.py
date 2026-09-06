"""DMA 변형률 스윕 → 선형 구간 탄성률 카드 — **처리 결과에서 끝나던 값이 덱까지 간다.**

전에는 「선형점탄성 탄성률」 이 낸 E′·한계 변형률이 처리 결과 스칼라로 끝났다. 카드
블록이 없어서 소변형·진동 해석에 넣을 탄성계수를 사람이 손으로 옮겨 적었다.

여기서 지키는 것: 시편 여럿이면 평균과 변동계수가 박히고, 하나면 「그 시편의 값」
이라고 말하며, 유효 범위(한계 변형률·주파수·온도)가 덱 주석에 적힌다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STRAIN_SWEEP = FIXTURES / "example_dma_strain_sweep.csv"
#: `scripts/make_example_dma.py` 가 넣은 평탄값. `test_dma_example.py` 와 같다.
TRUE_STRAIN_PLATEAU_PA = 1.20e9


def _adopted_sweep(
    client: TestClient, db: Session, headers: dict[str, str], sample_id: str
) -> str:
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens", json={"orientation": "NA"}, headers=headers
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": (STRAIN_SWEEP.name, STRAIN_SWEEP.read_bytes())},
        headers=headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    stored = client.post(
        "/api/processing/results",
        json={
            "test_run_id": created["id"],
            "steps": [{"plugin": "dma.lve_modulus", "options": {}}],
        },
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code in (200, 204), adopted.text
    return str(created["id"])


@pytest.fixture
def sample(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Polymer",
            "category": "EPDM",
            "grade": f"LVE-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.49,
        },
        headers=admin_headers,
    ).json()
    made = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    return {"material_id": material["id"], "id": made["id"]}


class Test카드가_선다:
    def test_시편_둘의_평균과_변동계수가_박히고_덱이_나간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        for _ in range(2):
            _adopted_sweep(client, db, admin_headers, sample["id"])
        card = client.post(
            "/api/fitting/cards/lve",
            json={
                "material_id": sample["material_id"],
                "test_type_key": "dma_sweep",
                "orientation": "NA",
                "label": "LVE",
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        body = card.json()
        lve = body["blocks"]["lve"]["values"]
        # 변형률 스윕에는 진소성 곡선이 없다 — 경화식 길이 안 열려야 한다(눌러서 422 를
        # 보던 자리).
        stats = client.get(
            f"/api/statistics/materials/{sample['material_id']}", headers=admin_headers
        ).json()
        assert stats["groups"] and not any(group["fittable"] for group in stats["groups"])
        assert lve["youngs_modulus"] == pytest.approx(TRUE_STRAIN_PLATEAU_PA, rel=0.02)
        assert lve["lve_strain_limit"] > 0
        assert lve["sample_count"] == 2
        # 같은 파일 둘이라 흩어짐이 0 이다 — 값이 **있는가**를 본다.
        assert lve["coefficient_of_variation"] == pytest.approx(0.0, abs=1e-9)
        assert lve["frequency_hz"] > 0
        assert lve["temperature_k"] > 200
        # 탄성 블록에도 같은 E 가 출처 `lve` 로 선다 — *ELASTIC 이 이것을 읽는다.
        elastic = body["blocks"]["elastic"]["values"]
        assert elastic["youngs_modulus"] == pytest.approx(lve["youngs_modulus"])
        assert elastic["youngs_modulus_source"] == "lve"
        assert elastic["poisson_ratio"] == pytest.approx(0.49)
        # 소성 표가 없으니 보통 Abaqus 는 안 열리고, LVE 형식과 JSON 이 열린다.
        assert "abaqus_lve" in body["available_formats"]
        assert "abaqus" not in body["available_formats"]

        deck = client.get(
            f"/api/fitting/cards/{body['id']}/export?format=abaqus_lve", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        assert "*ELASTIC" in deck.text
        assert "valid up to strain" in deck.text
        assert "from 2 specimen(s)" in deck.text

    def test_시편_하나면_그_시편의_값이라고_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        _adopted_sweep(client, db, admin_headers, sample["id"])
        body = client.post(
            "/api/fitting/cards/lve",
            json={
                "material_id": sample["material_id"],
                "test_type_key": "dma_sweep",
                "orientation": "NA",
            },
            headers=admin_headers,
        ).json()
        assert body["blocks"]["lve"]["values"]["sample_count"] == 1
        assert "coefficient_of_variation" not in body["blocks"]["lve"]["values"]
        assert any("한 건의 값" in line for line in body["source"]["notes"])

    def test_선형_구간을_안_낸_묶음이면_막는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        made = client.post(
            "/api/fitting/cards/lve",
            json={
                "material_id": sample["material_id"],
                "test_type_key": "dma_sweep",
                "orientation": "NA",
            },
            headers=admin_headers,
        )
        assert made.status_code == 404, made.text

    def test_재료_기본_정보를_함께_실으면_열물성_블록이_붙는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        """선형탄성구간 카드 한 장으로 열응력 해석까지 — 비열·열전도율이 따라온다."""
        from app.modules.vocabulary.definitions import ensure_builtin_property_items

        _adopted_sweep(client, db, admin_headers, sample["id"])
        # `db` 픽스처는 축만 심는다 — 물성 항목은 따로.
        ensure_builtin_property_items(db)
        db.commit()
        changed = client.patch(
            f"/api/materials/{sample['material_id']}",
            json={
                "declared_properties": [
                    {
                        "item": "열전도율",
                        "points": [{"value": 0.25}],
                        "source": "literature",
                        "reference": "예시",
                    },
                    {
                        "item": "비열",
                        "points": [{"value": 1500}],
                        "source": "literature",
                        "reference": "예시",
                    },
                ]
            },
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        body = {
            "material_id": sample["material_id"],
            "test_type_key": "dma_sweep",
            "orientation": "NA",
            "label": "LVE+열물성",
        }
        plain = client.post("/api/fitting/cards/lve", json=body, headers=admin_headers).json()
        assert "thermal" not in plain["blocks"]

        both = client.post(
            "/api/fitting/cards/lve",
            json={**body, "include_declared": True},
            headers=admin_headers,
        )
        assert both.status_code == 201, both.text
        thermal = both.json()["blocks"]["thermal"]["values"]
        assert thermal["thermal_conductivity"] == pytest.approx(0.25)
        assert thermal["specific_heat"] == pytest.approx(1500)
        # 탄성 블록의 E′ 는 잰 값 그대로다.
        assert both.json()["blocks"]["elastic"]["values"]["youngs_modulus_source"] == "lve"
        assert any("열물성" in line for line in both.json()["source"]["notes"])

    def test_덱_정의가_집을_수_있는_키를_카드에서_센다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        """정의 편집기가 「이 카드에 든 것」 을 보이는 데 쓴다 — 미리보기와 같은 조회 규칙."""
        _adopted_sweep(client, db, admin_headers, sample["id"])
        card = client.post(
            "/api/fitting/cards/lve",
            json={
                "material_id": sample["material_id"],
                "test_type_key": "dma_sweep",
                "orientation": "NA",
                "label": "키 목록",
            },
            headers=admin_headers,
        ).json()
        body = client.get(f"/api/fitting/cards/{card['id']}/deck-keys", headers=admin_headers)
        assert body.status_code == 200, body.text
        by_path = {row["path"]: row for row in body.json()["values"]}
        assert by_path["elastic.youngs_modulus"]["label"] == "탄성계수"
        assert by_path["elastic.youngs_modulus"]["si_unit"] == "Pa"
        assert by_path["lve.lve_strain_limit"]["label"] == "선형 한계 변형률"
        assert by_path["elastic.poisson_ratio"]["value"] == pytest.approx(0.49)
        # 글자 값(출처)은 덱 자리에 못 꽂으니 목록에 없다.
        assert "elastic.youngs_modulus_source" not in by_path
        assert body.json()["tables"] == []
