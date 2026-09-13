"""레오미터 파일 → 곡선 → 채택 → Carreau 적합 → 유변 카드 → Abaqus *VISCOSITY 덱.

인장이 아닌 시험이 **같은 적합·카드·덱 길**을 지나는지 보는 시험이다. 전에는
「적합할 수 있나」 가 진소성변형률·진응력을 상수로 들고 있어 레오미터 묶음이
적합 불가였고, 미리보기는 축이 안 맞는 경화식에서 422 로 멈췄다.
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

FLOW = Path(__file__).resolve().parents[1] / "fixtures" / "rheometer_flow_sweep.csv"


@pytest.fixture
def adopted(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "PP", "grade": "PP-MELT", "density": 900},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "NA"},
        headers=admin_headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen["id"],
            "test_type": "rheometer_flow",
            "conditions": '{"temperature": 25}',
            "condition_units": '{"temperature": "degC"}',
        },
        files={"file": ("flow.csv", FLOW.read_bytes())},
        headers=admin_headers,
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
    # 레시피는 정렬 하나 — 레오미터 곡선은 원본 채널이 곧 축이다.
    stored = client.post(
        "/api/processing/results",
        json={
            "test_run_id": run_id,
            "steps": [{"plugin": "curve.sort_unique", "options": {"x": "shear_rate"}}],
        },
        headers=admin_headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=admin_headers
    )
    assert adopted.status_code == 200, adopted.text
    return {"material_id": material["id"], "run_id": run_id}


def test_레오미터_곡선이_적합_카드_덱까지_간다(
    client: TestClient, admin_headers: dict[str, str], adopted: dict[str, Any]
) -> None:
    # ① 통계가 「적합할 수 있다」 고 말한다 — 등록된 식(Cross·Carreau)의 축이 이 묶음에 있다.
    stats = client.get(
        f"/api/statistics/materials/{adopted['material_id']}", headers=admin_headers
    )
    assert stats.status_code == 200, stats.text
    group = next(
        one for one in stats.json()["groups"] if one["test_type_key"] == "rheometer_flow"
    )
    assert group["fittable"] is True

    # ② 식을 안 고르고 미리보기 — 축이 안 맞는 경화식은 빠지고 유변 식만 견준다.
    preview = client.post(
        "/api/fitting/preview",
        json={
            "material_id": adopted["material_id"],
            "test_type_key": "rheometer_flow",
            "orientation": "NA",
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    fits = {one["family"]: one for one in preview.json()["fits"]}
    assert {"cross", "carreau"} <= set(fits)
    assert fits["carreau"]["x_label"] == "전단율"
    assert fits["carreau"]["block"] == "rheology"
    carreau = {p["name"]: p["value"] for p in fits["carreau"]["parameters"]}
    assert carreau["eta_0"] == pytest.approx(12.0, rel=1e-2)
    assert carreau["n"] == pytest.approx(0.35, rel=1e-2)

    # ③ 카드 — 유변 블록에 계수가 실리고 소성 표는 없다.
    card = client.post(
        "/api/fitting/cards",
        json={
            "material_id": adopted["material_id"],
            "test_type_key": "rheometer_flow",
            "orientation": "NA",
            "label": "PP 용융 점도",
            "family": "carreau",
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    body = card.json()
    assert "rheology" in body["blocks"]
    assert "table" not in body["blocks"]
    rheology = body["blocks"]["rheology"]
    assert rheology["values"]["zero_shear_viscosity"] == pytest.approx(12.0, rel=1e-2)
    assert {row["name"] for row in rheology["rows"]} == {"eta_0", "eta_inf", "lambda", "n"}
    assert "abaqus_viscosity" in body["available_formats"]
    assert "abaqus" not in body["available_formats"], "소성 표가 없으니 *PLASTIC 덱은 못 낸다"

    # ④ 덱 — Carreau-Yasuda a=2, 밀도는 재료에서.
    deck = client.get(
        f"/api/fitting/cards/{body['id']}/export?format=abaqus_viscosity",
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "*VISCOSITY, DEFINITION=CARREAU-YASUDA" in deck.text
    assert "*DENSITY" in deck.text
