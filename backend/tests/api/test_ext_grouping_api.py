"""확장 폴더의 처리 단계·묶음이 **API 를 거쳐** 내장과 똑같이 도는가.

단위 시험(`tests/unit/test_ext_tensile_extras.py`)은 커널만 본다. 여기서는 시험을
올리고 처리·채택한 뒤, 레시피에 확장 단계를 넣고, 확장 묶음을 **파이썬 수집기 없이
선언만으로** 모아 행으로 남기는 데까지 간다.
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

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {"plugin": "curve.sort_unique", "options": {"x": "strain_engineering"}},
    {"plugin": "tensile.strength", "options": {}},
    {
        "plugin": "tensile.elastic_modulus",
        "options": {"method": "manual", "manual_modulus": 200e9},
    },
    {"plugin": "tensile.proof_stress", "options": {"youngs_modulus": "@youngs_modulus"}},
    # **확장 단계** — 앞 단계의 값을 `@` 로 받는다.
    {
        "plugin": "tensile.yield_ratio",
        "options": {"proof_stress": "@proof_stress", "tensile_strength": "@tensile_strength"},
    },
    {
        "plugin": "tensile.true_plastic",
        "options": {"youngs_modulus": "@youngs_modulus", "proof_stress": "@proof_stress"},
    },
]


def _run(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    sample_id: str,
    *,
    temperature_k: float,
) -> dict[str, Any]:
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": "MD", "gauge_length": 50.0, "length_unit": "mm"},
        headers=headers,
    )
    assert specimen.status_code == 201, specimen.text
    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": "tensile",
            "conditions": json.dumps({"temperature": temperature_k}),
            "condition_units": json.dumps({"temperature": "K"}),
        },
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
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
    return {"run_id": run_id, "result": stored.json()}


@pytest.fixture
def sample(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"EXT-{uuid.uuid4().hex[:6]}",
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


def test_확장_단계가_레시피에서_돌고_확장_묶음이_선언만으로_모인다(
    client: TestClient, db: Session, admin_headers: dict[str, str], sample: dict[str, Any]
) -> None:
    runs = [
        _run(client, db, admin_headers, sample["id"], temperature_k=kelvin)
        for kelvin in (293.15, 323.15, 353.15)
    ]

    # ① 확장 처리 단계 — 결과 스칼라에 항복비가 있다.
    scalars = {one["key"]: one["value"] for one in runs[0]["result"]["scalars"]}
    assert 0.0 < scalars["yield_ratio"] < 1.0
    assert scalars["yield_ratio"] == pytest.approx(
        scalars["proof_stress"] / scalars["tensile_strength"]
    )

    # ② 레지스트리가 확장 묶음을 인장에 주고, 화면이 거를 근거(needs)를 선언에서 읽는다.
    kinds = client.get("/api/groups/kinds?applies_to=tensile", headers=admin_headers).json()
    found = next(one for one in kinds if one["id"] == "tensile.temperature_family")
    assert found["needs"] == "adopted_result"

    # ③ 파이썬 수집기 없이 — 채택된 결과의 두 열과 온도 조건으로 묶인다.
    made = client.post(
        "/api/groups",
        json={
            "plugin_id": "tensile.temperature_family",
            "run_ids": [one["run_id"] for one in runs],
            "options": {"levels": "0.01"},
        },
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["values"]["temperature_count"] == 3
    assert body["values"]["temperature_min"] == pytest.approx(293.15)
    assert body["values"]["temperature_max"] == pytest.approx(353.15)
    assert len(body["used"]) == 3
    # 같은 파일 셋이라 응력이 같다 — 기울기는 0 에 가깝다. 값이 「나온다」 가 요점이다.
    assert abs(body["values"]["softening_slope"]) < 1e3
    assert found["makes_card"] is True

    # ③-1 묶음 → 카드, 중심 코드 한 줄 없이 — 플러그인이 선언한 `card=` 가 블록을 낸다.
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": body["id"], "label": "온도 의존 시험"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    made_card = card.json()
    assert set(made_card["blocks"]) >= {"elastic", "table", "temperature_table"}
    temperature_table = made_card["blocks"]["temperature_table"]
    assert temperature_table["values"]["temperature_count"] == 3
    assert {round(row["temperature"], 2) for row in temperature_table["rows"]} == {
        293.15,
        323.15,
        353.15,
    }
    assert made_card["blocks"]["elastic"]["values"]["youngs_modulus"] == pytest.approx(200e9)
    assert made_card["source"]["plugin_id"] == "tensile.temperature_family"

    # ③-2 그 카드는 확장이 등록한 Abaqus 온도 의존 덱으로 나간다.
    assert "abaqus_temperature" in made_card["available_formats"]
    deck = client.get(
        f"/api/fitting/cards/{made_card['id']}/export?format=abaqus_temperature",
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "*PLASTIC, HARDENING=ISOTROPIC" in deck.text
    assert "3.531500000000E+02" in deck.text

    # ④ 채택 결과가 없는 시험은 선언 수집기도 같은 문장으로 막는다.
    bare = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "TD", "gauge_length": 50.0, "length_unit": "mm"},
        headers=admin_headers,
    ).json()
    unprocessed = client.post(
        "/api/test-runs",
        data={"specimen_id": bare["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    ).json()
    refused = client.post(
        "/api/groups",
        json={
            "plugin_id": "tensile.temperature_family",
            "run_ids": [runs[0]["run_id"], unprocessed["id"]],
        },
        headers=admin_headers,
    )
    assert refused.status_code == 422
    assert "채택된 처리 결과가 없습니다" in refused.json()["error"]["message"]
