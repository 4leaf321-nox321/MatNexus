"""물성 지도 — **이 재료에 어떤 물성이 어떤 조건에 어떤 등급으로 있나.**

무는 것이 셋이다.

    세 세계가 같은 줄 모양으로 선다     시험 · 선언 · 이어진 문헌값이 물성 키 하나 아래 모인다
    조건이 표준 키로 붙는다            시험 80 °C 와 문헌 temperature_c 80 이 같은 온도로
    안 이어진 것은 사라지지 않는다      공용어에 없는 항목은 unmapped 에 — 없는 줄 알면 안 된다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_condition_search import KEY, _catalog, _measured
from test_condition_search import (
    yield_def as yield_def,
)

from app.modules.catalog.models import CatalogDefinition, CatalogLink, CatalogMaterial
from app.modules.materials.models import Material
from app.modules.workspaces.models import Workspace


def _fetch(client: TestClient, headers: dict[str, str], material_id: Any) -> dict[str, Any]:
    got = client.get(f"/api/materials/{material_id}/property-coverage", headers=headers)
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


def test_세_세계가_한_물성_아래_모인다(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    workspace: Workspace,
    yield_def: CatalogDefinition,
) -> None:
    material = _measured(
        db, workspace, name="MAP", temperature_k=353.15, values=[300e6, 310e6, 305e6]
    )
    # 선언 물성 — 공용어에 안 이어진 항목 하나(「경도」)와, 이어진 항목은 없다(사전 비움).
    material.declared_properties = [
        {
            "item": "경도",
            "source": "millsheet",
            "reference": "성적서 #1",
            "points": [{"value_si": 200.0, "temperature_k": 296.15}],
        }
    ]
    db.commit()
    _catalog(db, name="LIT", value=500e6, conditions={"temperature_c": 80}, tier=2)
    lit = db.scalar(select(CatalogMaterial).where(CatalogMaterial.name == "LIT"))
    assert lit is not None
    db.add(CatalogLink(material_id=material.id, catalog_material_id=lit.id))
    db.commit()

    body = _fetch(client, admin_headers, material.id)
    rows = {one["key"]: one for one in body["properties"]}
    assert KEY in rows
    row = rows[KEY]
    assert row["name"] == "항복강도" and row["si_unit"] == "Pa"
    by_origin = {one["origin"]: one for one in row["entries"]}
    # 시험 — 표본 셋을 한 줄로, 등급 1, 조건은 표준 키로.
    measured = by_origin["measured"]
    assert measured["count"] == 3 and measured["tier"] == 1
    assert abs(measured["conditions"]["temperature"] - 353.15) < 0.1  # 0.1 K 로 묶인다
    assert measured["ref_kind"] == "test_run"
    # 문헌 — temperature_c 80 이 같은 온도(K)로.
    catalog = by_origin["catalog"]
    assert catalog["tier"] == 2 and catalog["ref_label"] == "LIT"
    assert abs(catalog["conditions"]["temperature"] - 353.15) < 1e-6
    # 안 이어진 선언 항목은 사라지지 않고 이름이 남는다.
    assert body["unmapped"]["items"] == ["경도"]
    # **셈이 함께 온다** — 「잰 값이 정말 있나」 를 다시 묻지 않게.
    counts = body["counts"]
    assert counts["samples"] >= 1 and counts["specimens"] >= 1
    assert counts["test_runs"] == 3 and counts["adopted_results"] == 3
    assert counts["measured"] == 1 and counts["catalog"] == 1


def test_아무것도_없는_재료는_빈_지도를_준다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    bare = Material(record_name="빈재료", family="Metal", category="Steel", grade="X")
    db.add(bare)
    db.commit()
    body = _fetch(client, admin_headers, bare.id)
    assert body["properties"] == [] and body["unmapped"] == {}
    # **「없다」 가 셈으로도 말해진다**(2026-09-18). 기준선 4차에서 AI 가 빈 지도를
    # 받고도 `list_test_runs`·`get_statistics`·`get_material` 로 다섯 번을 더 불러
    # 「정말 없나」 를 확인했다 — 지도만 봐서는 「없다」 와 「안 이어졌다」 가 안 갈렸다.
    assert body["counts"] == {
        "samples": 0,
        "specimens": 0,
        "test_runs": 0,
        "adopted_results": 0,
        "measured": 0,
        "internal": 0,
        "catalog": 0,
    }
