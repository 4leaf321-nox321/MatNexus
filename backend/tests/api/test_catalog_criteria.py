"""허용치 조회 — 문헌 값을 재질 · 고장모드 · 지표 · 시험법으로 묶어 대표 · 하한 · 상한으로.

무는 것:

    한 범위의 하한 · 상한은 같은 줄로     범위 표지를 뺀 조건이 같으면 가운데 값과 한 줄
    조건이 다르면 다른 줄                방향 MD · TD 는 섞지 않는다(평균하지 않는다)
    끝만 있으면 대표가 비고 그렇다고     하한을 대표처럼 옮기지 않게
    거르개                               고장모드 · 지표 · 시험법(포함, 대소문자 무시) · 등급
    재질                                 문헌 id · 이름 · 사내 재료(이어진 문헌), 없으면 422
    곡선 · 산점의 점은 허용치가 아니다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSeries,
    CatalogValue,
)
from app.modules.materials.models import Material

ROOM = 296.15
MD = {"direction": "MD", "test_standard": "ASTM E8/E8M", "temperature_k": ROOM}


@pytest.fixture
def steel(db: Session) -> CatalogMaterial:
    for index, (key, name) in enumerate(
        (
            ("mechanical.yield_strength", "항복강도"),
            ("mechanical.tensile_strength", "인장강도(UTS)"),
            ("mechanical.flexural_strength", "굽힘강도"),
        )
    ):
        db.add(
            CatalogDefinition(
                mt_id=920001 + index,
                key=key,
                name=name,
                domain="mechanical",
                si_unit="Pa",
                value_type="numeric",
            )
        )
    material = CatalogMaterial(mt_id=920010, name="허용치 시험강 DP780", category="metal")
    db.add(material)
    db.flush()
    series = CatalogSeries(
        material_id=material.id,
        kind="curve",
        label="곡선",
        method="digitized",
        quality_tier=3,
        columns=["mechanical.yield_strength"],
    )
    db.add(series)
    db.flush()
    rows: list[tuple[str, float, int, dict[str, Any], dict[str, Any]]] = [
        ("mechanical.yield_strength", 500e6, 2, {**MD}, {}),
        ("mechanical.yield_strength", 480e6, 1, {**MD, "bound": "lower"}, {}),
        ("mechanical.yield_strength", 530e6, 1, {**MD, "bound": "upper"}, {}),
        ("mechanical.yield_strength", 510e6, 2, {**MD, "direction": "TD"}, {}),
        ("mechanical.flexural_strength", 900e6, 1, {"bound": "lower — 원문은 구간"}, {}),
        ("mechanical.tensile_strength", 780e6, 4, {"assumption": True}, {}),
        # 곡선의 점 · 산점의 점은 허용치가 아니다.
        ("mechanical.yield_strength", 999e6, 3, {}, {"series_id": series.id}),
        ("mechanical.yield_strength", 998e6, 3, {}, {"scatter_point": True}),
    ]
    for index, (key, number, tier, conditions, extra) in enumerate(rows):
        db.add(
            CatalogValue(
                mt_id=920100 + index,
                material_id=material.id,
                property_key=key,
                value_num=number,
                unit="Pa",
                quality_tier=tier,
                conditions=conditions,
                **extra,
            )
        )
    db.commit()
    return material


def _criteria(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    return client.get("/api/catalog/criteria", params=params, headers=headers)


class Test묶기:
    def test_한_범위의_하한_상한은_가운데_값과_한_줄(
        self, client: TestClient, admin_headers: dict[str, str], steel: CatalogMaterial
    ) -> None:
        got = _criteria(client, admin_headers, catalog_material_id=str(steel.id))
        assert got.status_code == 200, got.text
        body = got.json()
        md = next(
            row
            for row in body["rows"]
            if row["property_key"] == "mechanical.yield_strength"
            and row["stress_component"].get("direction") == "MD"
        )
        assert md["representative"]["value_si"] == pytest.approx(500e6)
        assert md["lower"]["value_si"] == pytest.approx(480e6)
        assert md["upper"]["value_si"] == pytest.approx(530e6)
        assert md["failure_mode"] == "yield" and md["metric"] == "stress"
        assert md["loading"] == "tension" and md["si_unit"] == "Pa"
        assert md["test_method"] == "ASTM E8/E8M"
        assert md["temperature_k"] == pytest.approx(ROOM)
        # 조건이 다르면 다른 줄 — 평균하지 않는다.
        td = [row for row in body["rows"] if row["stress_component"].get("direction") == "TD"]
        assert [row["representative"]["value_si"] for row in td] == [pytest.approx(510e6)]
        # 곡선 · 산점의 점은 허용치가 아니다.
        values = [
            row[part]["value_si"]
            for row in body["rows"]
            for part in ("representative", "lower", "upper")
            if row[part]
        ]
        assert 999e6 not in values and 998e6 not in values

    def test_끝만_있으면_대표가_비고_그렇다고_말한다(
        self, client: TestClient, admin_headers: dict[str, str], steel: CatalogMaterial
    ) -> None:
        body = _criteria(
            client, admin_headers, catalog_material_id=str(steel.id), failure_mode="ultimate"
        ).json()
        flexural = next(
            row
            for row in body["rows"]
            if row["property_key"] == "mechanical.flexural_strength"
        )
        assert flexural["representative"] is None
        assert flexural["lower"]["value_si"] == pytest.approx(900e6)
        assert "범위의 끝만" in flexural["caveat"]
        assert flexural["loading"] == "bending"


class Test거르개:
    def test_고장모드_시험법_등급(
        self, client: TestClient, admin_headers: dict[str, str], steel: CatalogMaterial
    ) -> None:
        base = {"catalog_material_id": str(steel.id)}
        yields = _criteria(client, admin_headers, **base, failure_mode="yield").json()
        assert {row["failure_mode"] for row in yields["rows"]} == {"yield"}
        assert len(yields["rows"]) == 2
        by_method = _criteria(client, admin_headers, **base, test_method="e8/e8m").json()
        assert len(by_method["rows"]) == 2  # MD · TD 둘 다 ASTM E8/E8M
        everything = _criteria(client, admin_headers, **base).json()
        tensile = [row for row in everything["rows"] if row["failure_mode"] == "ultimate"]
        # tier 4 도 기본으로 싣는다 — 등급 · 주의가 붙는다.
        assert any(
            row["representative"] and row["representative"]["quality_tier"] == 4
            for row in tensile
        )
        trimmed = _criteria(client, admin_headers, **base, max_tier=3).json()
        assert all(
            (row["representative"] or row["lower"])["quality_tier"] <= 3
            for row in trimmed["rows"]
        )

    def test_모르는_고장모드와_재질_없음은_거절(
        self, client: TestClient, admin_headers: dict[str, str], steel: CatalogMaterial
    ) -> None:
        bad = _criteria(
            client, admin_headers, catalog_material_id=str(steel.id), failure_mode="melting"
        )
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "MNX-CATALOG-0080"
        none = _criteria(client, admin_headers, failure_mode="yield")
        assert none.status_code == 422 and none.json()["error"]["code"] == "MNX-CATALOG-0081"

    def test_어휘(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        got = client.get("/api/catalog/criteria/modes", headers=admin_headers).json()
        assert "yield" in got["failure_modes"] and "stress" in got["metrics"]
        keys = {one["property_key"]: one for one in got["properties"]}
        assert keys["mechanical.flexural_strength"]["loading"] == "bending"


class Test재질:
    def test_이름과_사내_재료로도_찾는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        steel: CatalogMaterial,
    ) -> None:
        by_name = _criteria(client, admin_headers, q="허용치 시험강").json()
        assert [one["id"] for one in by_name["materials"]] == [str(steel.id)]
        own = Material(
            record_name=f"DP780_{uuid.uuid4().hex[:4]}_1.2",
            family="Metal",
            category="Steel",
            grade="DP780",
        )
        db.add(own)
        db.flush()
        unlinked = _criteria(client, admin_headers, material_id=str(own.id)).json()
        assert unlinked["rows"] == [] and "이어진 문헌 재료가 없습니다" in unlinked["notes"][0]
        db.add(CatalogLink(material_id=own.id, catalog_material_id=steel.id))
        db.commit()
        linked = _criteria(client, admin_headers, material_id=str(own.id)).json()
        assert linked["rows"] and linked["materials"][0]["id"] == str(steel.id)
