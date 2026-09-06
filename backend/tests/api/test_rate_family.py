"""속도별 묶음 — **조건의 속도가 묶음이 되고, 묶음이 카드가 되고, 카드가 덱이 된다.**

여기서 지키는 것은 사슬이다. 시험 조건에 적힌 소성역 속도와 시편의 게이지 길이가
변형률 속도가 되고(1/s), 그것으로 가른 묶음이 행으로 남고, 그 행에서 속도 의존
카드가 서고, 그 카드가 Abaqus 속도 의존 덱으로 나간다. 어느 마디가 끊겨도 「속도
의존」 은 화면에 있을 뿐 해석에 못 들어간다.

**속도가 없는 시험은 막는다.** 조용히 느린 쪽에 넣으면 그 묶음이 거짓말이 된다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 진응력·진소성변형률까지 내는 레시피. `Example.tra` 는 18점 발췌본이라 탄성계수는
#: 직접 넣는다(`test_fitting.py` 와 같은 판단).
STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "curve.sort_unique", "options": {"x": "strain_engineering"}},
    {"plugin": "tensile.strength", "options": {}},
    {
        "plugin": "tensile.elastic_modulus",
        "options": {"method": "manual", "manual_modulus": 200e9},
    },
    {"plugin": "tensile.true_plastic", "options": {"youngs_modulus": "@youngs_modulus"}},
]


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    sample_id: str,
    *,
    speed_m_s: float | None,
    adopt: bool = True,
) -> str:
    """시편(게이지 50 mm) 하나에 시험 하나. 소성역 속도를 조건으로 적는다."""
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": "MD", "gauge_length": 50.0, "length_unit": "mm"},
        headers=headers,
    )
    assert specimen.status_code == 201, specimen.text
    data: dict[str, str] = {
        "specimen_id": specimen.json()["id"],
        "test_type": "tensile",
        "conditions": json.dumps(
            {"speed_plastic": speed_m_s} if speed_m_s is not None else {}
        ),
        "condition_units": json.dumps(
            {"speed_plastic": "m/s"} if speed_m_s is not None else {}
        ),
    }
    created = client.post(
        "/api/test-runs",
        data=data,
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
    if adopt:
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=headers,
        )
        assert stored.status_code == 201, stored.text
        adopted = client.post(
            f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
        )
        assert adopted.status_code in (200, 204), adopted.text
    return run_id


@pytest.fixture
def sample(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"RATE-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.3,
            "density": 7850,
        },
        headers=admin_headers,
    )
    assert material.status_code == 201, material.text
    made = client.post(
        f"/api/materials/{material.json()['id']}/samples", json={}, headers=admin_headers
    )
    assert made.status_code == 201, made.text
    return {"material_id": material.json()["id"], "id": made.json()["id"]}


class Test묶는다:
    def test_레지스트리가_속도별_묶음을_인장에_준다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        for_tensile = client.get(
            "/api/groups/kinds?applies_to=tensile", headers=admin_headers
        ).json()
        found = next(one for one in for_tensile if one["id"] == "tensile.rate_family")
        assert "tensile" in found["applies_to"]
        # **화면이 후보를 이것으로 거른다** — 마스터커브가 아니라 채택 결과다.
        assert found["needs"] == "adopted_result"
        # Prony 는 인장에 안 뜬다(저장·손실 탄성률이 없다). 전체 목록에서 본다.
        everything = client.get("/api/groups/kinds", headers=admin_headers).json()
        assert "viscoelastic.prony_group" not in {one["id"] for one in for_tensile}
        prony = next(one for one in everything if one["id"] == "viscoelastic.prony_group")
        assert prony["needs"] == "master_curve"

    def test_속도가_조건과_게이지_길이에서_나와_묶음이_된다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        # 0.0005 m/s ÷ 0.05 m = 0.01 1/s, 0.05 m/s ÷ 0.05 m = 1 1/s.
        slow = [
            _run(client, db, admin_headers, sample["id"], speed_m_s=0.0005) for _ in range(2)
        ]
        fast = _run(client, db, admin_headers, sample["id"], speed_m_s=0.05)
        made = client.post(
            "/api/groups",
            json={"plugin_id": "tensile.rate_family", "run_ids": [*slow, fast], "options": {}},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["values"]["rate_count"] == 2
        # 진소성 곡선이 있으니 경화식 길이 열린다 — 화면이 이 값으로 단계를 보인다.
        stats = client.get(
            f"/api/statistics/materials/{sample['material_id']}", headers=admin_headers
        ).json()
        assert all(group["fittable"] for group in stats["groups"])
        assert body["values"]["reference_rate"] == pytest.approx(0.01, rel=1e-6)
        assert body["values"]["rate_max"] == pytest.approx(1.0, rel=1e-6)
        rates = body["detail"]["rates"]
        assert rates[0]["count"] == 2 and rates[1]["count"] == 1
        assert len(rates[0]["curve"]["strain_true_plastic"]) > 10

    def test_속도가_없는_시험은_막고_어느_시험인지_말한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        with_speed = _run(client, db, admin_headers, sample["id"], speed_m_s=0.0005)
        without = _run(client, db, admin_headers, sample["id"], speed_m_s=None)
        made = client.post(
            "/api/groups",
            json={"plugin_id": "tensile.rate_family", "run_ids": [with_speed, without]},
            headers=admin_headers,
        )
        assert made.status_code == 422, made.text
        said = made.json()["error"]["message"]
        assert "speed_plastic" in said
        assert (
            client.get(f"/api/test-runs/{without}", headers=admin_headers).json()[
                "record_name"
            ]
            in said
        )

    def test_채택_안_한_시험은_막는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        adopted = _run(client, db, admin_headers, sample["id"], speed_m_s=0.0005)
        raw = _run(client, db, admin_headers, sample["id"], speed_m_s=0.05, adopt=False)
        made = client.post(
            "/api/groups",
            json={"plugin_id": "tensile.rate_family", "run_ids": [adopted, raw]},
            headers=admin_headers,
        )
        assert made.status_code == 422, made.text
        assert "채택" in made.json()["error"]["message"]


class Test카드가_되고_덱이_된다:
    def test_묶음에서_속도_의존_카드가_서고_Abaqus_속도_의존_덱이_나간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        sample: dict[str, Any],
    ) -> None:
        runs = [
            _run(client, db, admin_headers, sample["id"], speed_m_s=speed)
            for speed in (0.0005, 0.005, 0.05)
        ]
        group = client.post(
            "/api/groups",
            json={
                "plugin_id": "tensile.rate_family",
                "run_ids": runs,
                "options": {"model": "johnson_cook"},
            },
            headers=admin_headers,
        ).json()

        card = client.post(
            "/api/fitting/cards/rate-dependent",
            json={"group_result_id": group["id"], "label": "속도 의존"},
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        body = card.json()
        blocks = body["blocks"]
        # `table` 은 기준 속도 하나, `rate_table` 은 셋 다.
        assert blocks["rate_table"]["values"]["rate_count"] == 3
        assert sorted(
            {row["strain_rate"] for row in blocks["rate_table"]["rows"]}
        ) == pytest.approx([0.01, 0.1, 1.0])
        assert len(blocks["table"]["rows"]) == len(blocks["rate_table"]["rows"]) // 3
        # 탄성계수는 채택 결과에서, 푸아송비·밀도는 재료에서 — 출처가 적힌다.
        assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(200e9)
        assert blocks["elastic"]["values"]["youngs_modulus_source"] == "statistics"
        assert blocks["elastic"]["values"]["poisson_ratio"] == pytest.approx(0.3)
        assert "jc_c" in blocks["rate_table"]["values"]
        assert body["source"]["sample_count"] == 3
        # **두 길이 다 열린다.** 속도를 안 받는 솔버도, 받는 솔버도.
        assert "abaqus" in body["available_formats"]
        assert "abaqus_rate" in body["available_formats"]

        deck = client.get(
            f"/api/fitting/cards/{body['id']}/export?format=abaqus_rate", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        text = deck.text
        assert text.count("*PLASTIC, HARDENING=ISOTROPIC, EXTRAPOLATION=CONSTANT, RATE=") == 3
        assert "Johnson-Cook summary" in text

    def test_다른_묶음으로는_못_만든다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = client.post(
            "/api/fitting/cards/rate-dependent",
            json={"group_result_id": str(uuid.uuid4())},
            headers=admin_headers,
        )
        assert made.status_code == 404
