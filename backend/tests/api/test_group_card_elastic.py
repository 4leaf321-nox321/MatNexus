"""묶음이 낸 탄성 칸은 **그 칸만** 이긴다(2026-10-12, 공용 길 `/fitting/cards/from-group`).

응력완화 묶음이 Prony 의 순간 탄성률을 E 로 낸다 — 점탄성 덱이 E 를 순간 값으로 읽고 gᵢ 를
곱하기 때문이다. 전에는 묶음이 `elastic` 블록을 내면 물려받은 블록을 **통째로** 갈아
끼워 푸아송비 · 밀도가 사라졌다. 이제 묶음의 칸이 이기고 나머지는 물려받는다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from matcore import registry

PLUGIN = "test_only.elastic_from_group"
HEADER = "시편\t방향\t응력 진폭 (MPa)\tcycles_to_failure"


@pytest.fixture(autouse=True)
def _plugin() -> Any:
    def card(
        values: dict[str, float], detail: dict[str, Any], warnings: list[str]
    ) -> dict[str, Any]:
        return {"elastic": {"values": {"youngs_modulus": 4.0e9}}}

    def run(members: list[Any], **options: Any) -> Any:
        from matcore.groups import GroupOutcome

        return GroupOutcome(values={"n": float(len(members))}, used=[m.label for m in members])

    registry.register(
        id=PLUGIN,
        kind="grouping",
        label="시험용 탄성 묶음",
        applies_to=("fatigue",),
        makes_values=(),
        members={
            "from": "summary",
            "conditions": ["stress_amplitude"],
            "values": ["cycles_to_failure"],
        },
        card=card,
        version="1",
    )(run)
    yield
    registry._REGISTRY.pop(PLUGIN, None)


def test_묶음의_탄성계수가_이기고_푸아송비_밀도는_물려받는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Polymer",
            "category": "Rubber",
            "grade": "EPDM",
            "spec_thickness": 2.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "fatigue",
            "values": [HEADER, "1\tNA\t10\t1000", "2\tNA\t8\t5000"],
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    group = client.post(
        "/api/groups",
        json={"plugin_id": PLUGIN, "run_ids": [run["id"] for run in runs]},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    card = client.post(
        "/api/fitting/cards/from-group",
        json={
            "group_result_id": group.json()["id"],
            "label": "완화",
            "poisson_ratio": 0.45,
            "density": 1200.0,
        },
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    elastic = card.json()["blocks"]["elastic"]["values"]
    assert elastic["youngs_modulus"] == 4.0e9
    assert elastic["poisson_ratio"] == 0.45
    assert elastic["density"] == 1200.0
    notes = card.json()["source"]["notes"]
    assert any(line.startswith("탄성계수: 묶음이 낸 값") for line in notes)
