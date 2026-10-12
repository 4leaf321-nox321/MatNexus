"""크리프 · 응력완화 — **표준 CSV 를 올려 곡선에서 카드 · 덱까지**(2026-10-12).

새 기본 시험 종류 둘은 장비 실파일이 아직 없어서, 기본 형식 프로파일이 「MatNexus 표준 CSV」 를
읽는다(첫 줄 열 이름, 둘째 줄 단위). 여기서 지키는 것:

    단위       시간 h · 변형률 % 로 적은 파일이 SI(s · 1)로 들어와 최소 크리프 속도가 맞는가
    사슬       응력완화 곡선 → E(t) → 시간 영역 Prony → 점탄성 카드(E = 순간 탄성률, ν · 밀도는
               물려받음) → 점탄성 덱
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


def _upload(
    client: TestClient,
    db: Session,
    headers: dict[str, str],
    test_type: str,
    fixture: str,
    conditions: str,
    count: int = 1,
) -> tuple[str, list[str]]:
    """같은 재료의 시편 `count` 개에 같은 파일을 올린다 — 묶음은 시험 2건 이상이다."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "Adhesive", "grade": "EPOXY-1"},
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    run_ids: list[str] = []
    for _ in range(count):
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "NA"},
            headers=headers,
        ).json()
        created = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": test_type,
                "conditions": conditions,
            },
            files={"file": (fixture, (FIXTURES / fixture).read_bytes())},
            headers=headers,
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
        run_ids.append(run_id)
    return material["id"], run_ids


def _adopt(
    client: TestClient, headers: dict[str, str], run_id: str, plugin: str
) -> dict[str, Any]:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": [{"plugin": plugin, "options": {}}]},
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code == 200, adopted.text
    body: dict[str, Any] = stored.json()
    return body


def test_표준_CSV_의_시간_h_변형률_퍼센트가_SI_로_들어와_최소_속도가_맞다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    detected = client.post(
        "/api/test-types/detect",
        files={"file": ("creep.csv", (FIXTURES / "creep_standard.csv").read_bytes())},
        headers=admin_headers,
    )
    assert detected.status_code == 200, detected.text
    assert detected.json()["profile_key"] == "mnx_creep_csv"
    _, (run_id,) = _upload(
        client,
        db,
        admin_headers,
        "creep",
        "creep_standard.csv",
        '{"applied_stress": 20000000, "temperature": 398.15}',
    )
    result = _adopt(client, admin_headers, run_id, "creep.rate")
    rate = next(one["value"] for one in result["scalars"] if one["key"] == "min_creep_rate")
    # 0.005 %/h = 5e-5 / 3600 s.
    assert rate == pytest.approx(5e-5 / 3600, rel=0.03)


def test_응력완화_곡선이_Prony_점탄성_카드와_덱이_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    material_id, run_ids = _upload(
        client,
        db,
        admin_headers,
        "stress_relaxation",
        "relaxation_standard.csv",
        '{"held_strain": 0.005, "temperature": 296.15}',
        count=2,
    )
    for run_id in run_ids:
        _adopt(client, admin_headers, run_id, "relaxation.modulus")
    group = client.post(
        "/api/groups",
        json={"plugin_id": "relaxation.prony", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    values = group.json()["values"]
    assert values["equilibrium_pa"] == pytest.approx(1e9, rel=0.03)
    assert values["instantaneous_pa"] == pytest.approx(4e9, rel=0.03)

    card = client.post(
        "/api/fitting/cards/from-group",
        json={
            "group_result_id": group.json()["id"],
            "label": "완화 Prony",
            "poisson_ratio": 0.4,
            "density": 1150.0,
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    blocks = card.json()["blocks"]
    assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(
        values["instantaneous_pa"]
    )
    assert blocks["elastic"]["values"]["poisson_ratio"] == 0.4
    assert blocks["viscoelastic"]["rows"]
    deck = client.get(
        f"/api/fitting/cards/{card.json()['id']}/export?format=abaqus_viscoelastic&units=si",
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "*VISCOELASTIC" in deck.text
    assert material_id
