"""사업부별 현황 — **시험에만 붙는 축을 재료·시편으로 펼쳐 세는 자리.**

무는 자리: 같은 재료를 두 사업부가 시험하면 **양쪽 모두**에 세어져야 한다 —
한쪽에만 세면 「우리 사업부는 이 재료를 시험한 적 없다」 로 읽힌다. 그리고
사업부를 안 적은 시험은 「미지정」 으로 **보여야** 한다 — 숨기면 채울 일이
안 보인다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


@pytest.fixture
def specimens(client: TestClient, db: Session, admin_headers: dict[str, str]) -> list[str]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "SECC",
            "details": "DIV",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    out = []
    for orientation in ("MD", "TD"):
        made = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": orientation},
            headers=admin_headers,
        ).json()
        out.append(made["id"])
    return out


def _upload(
    client: TestClient, headers: dict[str, str], specimen_id: str, division: str | None
) -> None:
    data: dict[str, Any] = {
        "specimen_id": specimen_id,
        "test_type": "tensile",
        "conditions": "{}",
    }
    if division is not None:
        data["division"] = division
    made = client.post(
        "/api/test-runs",
        data=data,
        files={
            "file": (
                "Example.tra",
                TRA.read_bytes() + division.encode() if division else TRA.read_bytes(),
            )
        },
        headers=headers,
    )
    assert made.status_code == 202, made.text


def test_사업부별로_시험과_걸친_재료를_센다(
    client: TestClient, admin_headers: dict[str, str], specimens: list[str]
) -> None:
    first, second = specimens
    _upload(client, admin_headers, first, "MX")
    _upload(client, admin_headers, second, "MX")
    _upload(client, admin_headers, first, "VD")  # 같은 재료를 다른 사업부도 시험한다
    _upload(client, admin_headers, second, None)  # 안 적은 것

    body = client.get("/api/statistics/divisions", headers=admin_headers).json()
    rows = body["divisions"]
    by = {row["division"]: row for row in rows}

    assert by["MX"]["run_count"] == 2
    assert by["MX"]["specimen_count"] == 2
    assert by["MX"]["sample_count"] == 1
    assert by["MX"]["material_count"] == 1

    # **같은 재료가 양쪽 모두에 세어진다** — 한쪽에만 세면 「우리는 이 재료를
    # 시험한 적 없다」 로 읽힌다.
    assert by["VD"]["material_count"] == 1
    assert by["VD"]["run_count"] == 1

    # 안 적은 것은 「미지정」 으로 **보인다.** 숨기면 채울 일이 안 보인다.
    assert by["미지정"]["run_count"] == 1

    # **순서는 고정이다** — MX · VD · DA · NW · 의료기기, 미지정은 맨 뒤.
    assert [row["division"] for row in rows] == ["MX", "VD", "미지정"]

    # 연간 — 그래프가 그린다. 올해 시험이니 해가 하나다.
    yearly = body["yearly"]
    assert {(row["division"], row["run_count"]) for row in yearly} == {
        ("MX", 2),
        ("VD", 1),
        ("미지정", 1),
    }
    assert len({row["year"] for row in yearly}) == 1
