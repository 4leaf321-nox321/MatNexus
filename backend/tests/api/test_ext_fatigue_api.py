"""피로 — 표로 넣은 시험들이 **요약값 구성원**으로 묶여 S-N 카드까지 간다.

곡선 파일이 없는 첫 시험 종류다. 「표로 시험 입력」 이 조건(응력 진폭·응력비)과
요약값(파단 수명·런아웃)을 시험마다 남기고, 묶음이 `from: summary` 선언으로 그것을
모은다 — 파이썬 수집기도, 채택 결과도 없이.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

A, B = 1000e6, -0.1
HEADER = "시편\t방향\t응력 진폭 (MPa)\t응력비 R\tcycles_to_failure\trunout"


def _rows() -> list[str]:
    lines = [HEADER]
    for index, stress_mpa in enumerate((600, 500, 420, 350, 300, 260), start=1):
        cycles = (stress_mpa * 1e6 / A) ** (1.0 / B)
        lines.append(f"{index}\tNA\t{stress_mpa}\t-1\t{cycles:.0f}\tno")
    lines.append("7\tNA\t240\t-1\t10000000\tyes")
    return lines


@pytest.fixture
def imported(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SM490", "spec_thickness": 3.0},
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
            "values": _rows(),
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    items = made.json()["items"]
    assert len(items) == 7 and all(one["status"] == "new" for one in items), items
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    assert len(runs) == 7
    return {"material_id": material["id"], "run_ids": [run["id"] for run in runs]}


def test_표로_넣은_피로_시험이_S_N_묶음과_카드가_된다(
    client: TestClient, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    # ① 묶음 목록이 피로에 S-N 을 주고, 구성원 조건이 「요약값」 이라고 말한다.
    kinds = client.get("/api/groups/kinds?applies_to=fatigue", headers=admin_headers).json()
    found = next(one for one in kinds if one["id"] == "fatigue.sn_curve")
    assert found["needs"] == "summary"
    assert found["makes_card"] is True

    # ② 묶는다 — 채택 결과 없이, 조건과 요약값만으로. 런아웃(yes)은 빠진다.
    made = client.post(
        "/api/groups",
        json={"plugin_id": "fatigue.sn_curve", "run_ids": imported["run_ids"]},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["values"]["basquin_a"] == pytest.approx(A, rel=1e-3)
    assert body["values"]["basquin_b"] == pytest.approx(B, rel=1e-3)
    assert body["values"]["point_count"] == 6
    assert body["values"]["runout_count"] == 1
    assert len(body["used"]) == 6
    assert any("런아웃" in one for one in body["warnings"])

    # ③ 카드 — 공용 길. 탄성계수는 없으니 탄성 블록은 비고, S-N 블록이 실린다.
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": body["id"], "label": "SM490 S-N"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    blocks = card.json()["blocks"]
    assert "sn_curve" in blocks
    assert len(blocks["sn_curve"]["rows"]) == 7
    assert blocks["sn_curve"]["values"]["strength_at_1e6"] == pytest.approx(
        A * 1e6**B, rel=1e-3
    )
