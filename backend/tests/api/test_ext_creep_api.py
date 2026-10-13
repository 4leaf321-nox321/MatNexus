"""크리프 — 표로 넣은 시험(보고서의 최소 크리프 속도)이 Norton · Garofalo 묶음과 카드가 된다.

새 기본 시험 종류 `creep`(2026-10-12)의 사슬 전체: 시험 종류 시드 → 표로 입력(조건 · 요약값) →
묶음(`creep.law`, 구성원은 「잰 값 또는 적은 값」) → 카드의 모델 파라미터 블록. 덱은
`test_ext_creep_law.py` 가 본다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

A, N, Q, R = 1e-30, 5.0, 80e3, 8.314462618
HEADER = "시편\t방향\t가한 응력 (MPa)\t시험 온도 (K)\tmin_creep_rate"
#: 「표로 시험 입력」 창이 크리프를 고르면 채우는 열(`SummaryImportDialog.defaultColumns`) —
#: 온도는 °C, 속도는 단위를 붙인다. 둘 다 SI 로 바뀌어야 상수가 같게 나온다.
SCREEN_HEADER = "시편\t방향\t가한 응력 (MPa)\t시험 온도 (°C)\tmin_creep_rate (1/s)"


def _rows(header: str = HEADER) -> list[str]:
    lines = [header]
    index = 0
    for stress_mpa in (20, 40, 80):
        for temperature in (300.0, 350.0):
            index += 1
            rate = A * (stress_mpa * 1e6) ** N * math.exp(-Q / (R * temperature))
            shown = temperature - 273.15 if "°C" in header else temperature
            lines.append(f"{index}\tNA\t{stress_mpa}\t{shown:.2f}\t{rate:.10e}")
    return lines


@pytest.fixture(params=[HEADER, SCREEN_HEADER], ids=["켈빈", "화면 기본 열"])
def imported(
    request: pytest.FixtureRequest,
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Solder",
            "grade": "SAC305",
            "spec_thickness": 1.0,
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
            "test_type": "creep",
            "values": _rows(request.param),
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    assert all(one["status"] == "new" for one in made.json()["items"]), made.json()
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    assert len(runs) == 6
    return {"material_id": material["id"], "run_ids": [run["id"] for run in runs]}


def test_표로_넣은_크리프_속도가_Norton_묶음과_카드가_된다(
    client: TestClient, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    kinds = client.get("/api/groups/kinds?applies_to=creep", headers=admin_headers).json()
    found = next(one for one in kinds if one["id"] == "creep.law")
    assert found["needs"] == "summary" and found["makes_card"] is True

    made = client.post(
        "/api/groups",
        json={"plugin_id": "creep.law", "run_ids": imported["run_ids"]},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    values = made.json()["values"]
    assert values["norton_n"] == pytest.approx(N, rel=1e-4)
    assert values["activation_energy"] == pytest.approx(Q, rel=1e-4)
    assert values["norton_a"] == pytest.approx(A, rel=1e-3)
    assert values["temperature_count"] == 2

    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": made.json()["id"], "label": "SAC305 크리프"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    rows = card.json()["blocks"]["model_params"]["rows"]
    norton = {row["name"]: row for row in rows if row["set"].startswith("norton")}
    assert norton["A"]["unit"] == "1/(s.Pa^n)"
    assert norton["n"]["value"] == pytest.approx(N, rel=1e-4)
    assert norton["Q"]["unit"] == "J/mol"
