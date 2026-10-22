"""물성 지도 — **이 재료에 어떤 물성이 어떤 조건에 어떤 등급으로 있나.**

무는 것이 셋이다.

    세 세계가 같은 줄 모양으로 선다     시험 · 선언 · 이어진 문헌값이 물성 키 하나 아래 모인다
    조건이 표준 키로 붙는다            시험 80 °C 와 문헌 temperature_c 80 이 같은 온도로
    안 이어진 것은 사라지지 않는다      공용어에 없는 항목은 unmapped 에 — 없는 줄 알면 안 된다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_condition_search import KEY, _catalog, _measured
from test_condition_search import (
    yield_def as yield_def,
)
from test_viscoelastic_api import _dma_run, _sibling_run

from app.modules.catalog.models import CatalogDefinition, CatalogLink, CatalogMaterial
from app.modules.materials.models import Material
from app.modules.viscoelastic.models import ModulusTable
from app.modules.workspaces.models import Workspace
from app.shared.coverage import TABLE_ROWS_ON_MAP


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


class Test온도별_탄성률_표:
    """**DMA 온도별 E′ 가 지도에 선다**(2026-10-22) — 온도 · 주파수가 조건이다.

    v1.285.0 보고로 점탄성 탭에 표를 만들었는데, 그 값이 물성 지도에는 안 섰다 — 지도만 보면
    E′ 를 잰 적이 없는 재료였다.
    """

    def _tables(
        self, client: TestClient, db: Session, headers: dict[str, str], count: int
    ) -> tuple[str, float, list[dict[str, Any]]]:
        first = _dma_run(client, db, headers, grade="MAPVE")
        material_id = client.get(f"/api/test-runs/{first['id']}", headers=headers).json()[
            "material_id"
        ]
        runs = [
            first,
            *(_sibling_run(client, db, headers, material_id) for _ in range(count - 1)),
        ]
        sweeps = client.get(
            f"/api/viscoelastic/runs/{first['id']}/sweeps", headers=headers
        ).json()["items"]
        low = max(one["minimum_frequency_hz"] for one in sweeps)
        high = min(one["maximum_frequency_hz"] for one in sweeps)
        frequency = float((low * high) ** 0.5)
        tables = []
        for run in runs:
            made = client.post(
                f"/api/viscoelastic/runs/{run['id']}/modulus-tables",
                json={"frequency_hz": frequency},
                headers=headers,
            )
            assert made.status_code == 201, made.text
            tables.append(made.json())
        return material_id, frequency, tables

    def test_시편끼리_온도마다_평균해_조건과_함께_선다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material_id, frequency, tables = self._tables(client, db, admin_headers, 3)
        # 첫 시험에 같은 주파수의 표를 한 번 더 — **시험마다 가장 최근 표 하나**만 센다.
        again = client.post(
            f"/api/viscoelastic/runs/{tables[0]['test_run_id']}/modulus-tables",
            json={"frequency_hz": frequency},
            headers=admin_headers,
        )
        assert again.status_code == 201, again.text
        # 둘째 시편의 E′ 를 1.2 배로 — 평균이 보이게. 셋째는 전단(G′)으로 잰 표로 바꾼다.
        second = db.get(ModulusTable, uuid.UUID(tables[1]["id"]))
        third = db.get(ModulusTable, uuid.UUID(tables[2]["id"]))
        assert second is not None and third is not None
        second.rows = [{**one, "storage_pa": one["storage_pa"] * 1.2} for one in second.rows]
        third.modulus_basis = "G"
        db.commit()

        body = _fetch(client, admin_headers, material_id)
        rows = {one["key"]: one for one in body["properties"]}
        storage = rows["mechanical.storage_modulus"]["entries"]
        mine = tables[0]["rows"]
        assert len(storage) == len(mine)
        coldest = min(storage, key=lambda one: one["conditions"]["temperature"])
        # 시편 둘(같은 시험의 두 표를 둘로 세지 않고, G′ 는 E′ 로 세지 않는다).
        assert coldest["count"] == 2
        assert coldest["value_si"] == pytest.approx(mine[0]["storage_pa"] * 1.1)
        assert coldest["conditions"]["temperature"] == pytest.approx(
            mine[0]["temperature_k"], abs=0.05
        )
        assert coldest["conditions"]["frequency"] == pytest.approx(frequency, rel=1e-2)
        assert coldest["origin"] == "measured" and coldest["ref_kind"] == "test_run"
        assert coldest["method"] == "온도별 탄성률 표"
        # tan δ 는 E 든 G 든 같다 — 셋 다 센다.
        tangent = rows["mechanical.loss_tangent"]["entries"]
        assert max(one["count"] for one in tangent) == 3
        # **채택이 없어도 잰 값이 있다** — 「없다」 는 measured 가 답한다.
        assert body["counts"]["adopted_results"] == 0
        assert body["counts"]["measured"] > 0

    def test_긴_표는_양끝을_남기고_솎는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material_id, _, tables = self._tables(client, db, admin_headers, 1)
        stored = db.get(ModulusTable, uuid.UUID(tables[0]["id"]))
        assert stored is not None
        # 승온 램프처럼 50줄 — 지도에는 20줄만, 양 끝 온도는 남는다.
        stored.rows = [
            {"temperature_k": 250.0 + index, "storage_pa": 1e9 - index * 1e7, "loss_pa": None}
            for index in range(50)
        ]
        db.commit()
        body = _fetch(client, admin_headers, material_id)
        storage = {one["key"]: one for one in body["properties"]}[
            "mechanical.storage_modulus"
        ]["entries"]
        assert len(storage) == TABLE_ROWS_ON_MAP
        temperatures = sorted(one["conditions"]["temperature"] for one in storage)
        assert temperatures[0] == pytest.approx(250.0) and temperatures[-1] == pytest.approx(
            299.0
        )
        assert storage[0]["method"] == f"온도별 탄성률 표 · 50줄 중 {TABLE_ROWS_ON_MAP}줄"
