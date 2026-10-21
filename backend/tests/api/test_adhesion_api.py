"""박리 · 이탈력 — 올리고, 처리하고, 묶어서 응집 영역 카드까지(2026-10-20).

사용자 보고: 이탈력(배터리 PTT · 테이프 · SIM 트레이 삽입 · 인출) 처리 단계 · 응집 영역 블록이
없었다. 곡선 모양은 시험이 아니라 단계가 본다 — 여기서는 기본 시험 종류 `adhesion` 으로 Zwick
`.tra` 를 읽어 그 길이 이어지는지 본다.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
WIDTH = 0.025


def _runs(client: TestClient, db: Session, headers: dict[str, str], count: int) -> list[str]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "Tape", "grade": "PEEL-1"},
        headers=headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=headers
    ).json()
    made: list[str] = []
    for _ in range(count):
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=headers,
        ).json()
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "adhesion", "conditions": "{}"},
            files={"file": ("peel.tra", TRA.read_bytes())},
            headers=headers,
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        assert test_services.parse_run(db, uuid.UUID(run_id)) == "parsed"
        made.append(run_id)
    return made


def _process(client: TestClient, headers: dict[str, str], run_id: str) -> dict[str, float]:
    stored = client.post(
        "/api/processing/results",
        json={
            "test_run_id": run_id,
            "steps": [
                {
                    "plugin": "adhesion.peel",
                    # 고정 파일이 18점뿐이라 안정 구간을 넓힌다(기본 25~75 % 면 3점).
                    "options": {
                        "width": WIDTH,
                        "peel_angle": math.pi / 2,
                        "window_start": 0.05,
                        "window_end": 0.95,
                    },
                }
            ],
        },
        headers=headers,
    )
    assert stored.status_code == 201, stored.text
    adopted = client.post(
        f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
    )
    assert adopted.status_code == 200, adopted.text
    return {one["key"]: one["value"] for one in stored.json()["scalars"]}


def test_박리_시험이_응집_영역_카드까지_간다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    run_ids = _runs(client, db, admin_headers, 2)
    steps = client.get(
        "/api/processing/steps", params={"test_type": "adhesion"}, headers=admin_headers
    ).json()
    assert "adhesion.peel" in {one["id"] for one in steps}
    tensile = client.get(
        "/api/processing/steps", params={"test_type": "tensile"}, headers=admin_headers
    ).json()
    assert "adhesion.peel" not in {one["id"] for one in tensile}, (
        "인장 목록에 박리가 뜨면 안 된다"
    )

    values: dict[str, Any] = {}
    for run_id in run_ids:
        values = _process(client, admin_headers, run_id)
    assert values["max_force"] > values["plateau_force"] > 0
    assert values["peel_strength"] == pytest.approx(values["plateau_force"] / WIDTH)
    assert values["adhesion_energy"] == pytest.approx(values["peel_strength"], rel=1e-9)

    group = client.post(
        "/api/groups",
        json={"plugin_id": "adhesion.summary", "run_ids": run_ids},
        headers=admin_headers,
    )
    assert group.status_code == 201, group.text
    assert group.json()["values"]["sample_count"] == 2
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group.json()["id"], "label": "테이프 박리"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    blocks = card.json()["blocks"]
    assert blocks["cohesive_zone"]["values"]["fracture_energy"] == pytest.approx(
        values["adhesion_energy"]
    )
    assert blocks["reference"]["values"]["peel_strength"] == pytest.approx(
        values["peel_strength"]
    )
