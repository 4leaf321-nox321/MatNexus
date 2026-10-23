"""문헌 반입 묶음 — **외부 공개 데이터를 묶음 파일 하나로, 다시 들여도 같게**(ADR 0068).

미리보기는 남기지 않는다          들였을 때의 결과만 돌려준다
적용은 한 번에                   문제가 하나면 아무것도 적지 않는다
다시 들여도 같다                  같은 외부 키 · 같은 내용이면 그대로(중복 없음)
내용이 다르면 들이지 않는다        조용히 덮어쓰지 않는다
산점은 같은 x 를 받는다            S-N 런아웃 — 점은 대표값 후보에서 빠진다
라이선스가 남고 NC 는 거절         같은 출처에 다른 라이선스면 거절
지우기는 자료 관리자 · 쓰이면 막힘   사내가 받아 간 값 · 이은 재료가 있으면
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_catalog_contribute import member_headers

from app.modules.catalog import parameters
from app.modules.catalog.local_definitions import ensure_local_definitions
from app.modules.catalog.models import (
    CatalogBatch,
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSeries,
    CatalogSource,
    CatalogValue,
)
from app.modules.materials.models import Material
from app.modules.workspaces.models import Workspace

KEY = "materialcollector/fatigue-literature/2026-10-23"


@pytest.fixture
def defs(db: Session) -> CatalogMaterial:
    """이관해 온 것처럼 — 정의 셋과 이미 있는 문헌 재료 하나."""
    for key, name, unit, axes in (
        ("mechanical.youngs_modulus", "탄성계수", "Pa", ["temperature_k"]),
        ("mechanical.fatigue_strength", "피로강도", "Pa", ["cycles", "stress_ratio_R"]),
        ("mechanical.tensile_strength", "인장강도", "Pa", ["temperature_k"]),
    ):
        db.add(
            CatalogDefinition(
                key=key,
                name=name,
                domain="mechanical",
                si_unit=unit,
                value_type="numeric",
                condition_axes=axes,
            )
        )
    existing = CatalogMaterial(
        mt_id=920001, name="Ecoflex 00-30 (Smooth-On silicone)", category="rubber"
    )
    db.add(existing)
    db.commit()
    parameters.forget()
    return existing


def bundle(existing_id: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "batch": {"key": KEY, "title": "문헌 피로 1단계", "description": "SUS304 판재"},
        "sources": [
            {
                "key": "src-smith",
                "kind": "journal",
                "title": "Fatigue of AISI 304 sheet",
                "year": 2020,
                "doi": "10.3390/met-test-1",
                "license": "CC-BY-4.0",
                "attribution": "Smith et al. (2020), CC BY 4.0",
            }
        ],
        "materials": [
            {
                "key": "mat-304",
                "name": "AISI 304 sheet, annealed (Smith 2020)",
                "category": "metal",
                "grade": "AISI 304",
                "attributes": {"designation": "EN 1.4301", "product_form": "sheet"},
            }
        ],
        "values": [
            {
                "key": "v-uts",
                "material": "mat-304",
                "source": "src-smith",
                "property_key": "mechanical.tensile_strength",
                "value_num": 650,
                "unit": "MPa",
                "conditions": {"temperature_k": 296.15},
                "method": "measured",
                "quality_tier": 2,
                "source_detail": "Table 2",
            },
            {
                "key": "v-fatigue-limit",
                "material": "mat-304",
                "source": "src-smith",
                "property_key": "mechanical.fatigue_strength",
                "value_num": 240,
                "unit": "MPa",
                "conditions": {"cycles": 1e7, "stress_ratio_R": -1},
                "method": "measured",
                "quality_tier": 2,
            },
        ],
        "series": [
            {
                "key": "sn-r-1",
                "material": "mat-304",
                "source": "src-smith",
                "kind": "scatter",
                "label": "S-N R=-1",
                "x_key": "cycles",
                "columns": [{"property_key": "mechanical.fatigue_strength", "unit": "MPa"}],
                # 같은 수명 1e7 에 멈춘 런아웃 둘 — 곡선이면 거절될 줄이다.
                "rows": [[1.2e5, 400], [8.0e5, 330], [1e7, 250], [1e7, 245]],
                "row_conditions": [
                    {},
                    {},
                    {"runout": True},
                    {"runout": True, "specimen": "S7"},
                ],
                "conditions": {"stress_ratio_R": -1},
                "method": "digitized",
                "quality_tier": 3,
                "source_detail": "Fig. 5",
            }
        ],
    }
    if existing_id is not None:
        body["materials"].append({"key": "mat-eco", "existing_id": str(existing_id)})
        body["values"].append(
            {
                "key": "v-eco-e",
                "material": "mat-eco",
                "source": "src-smith",
                "property_key": "mechanical.youngs_modulus",
                "value_num": 0.07,
                "unit": "MPa",
                "method": "measured",
                "quality_tier": 2,
            }
        )
    return body


def _import(client: TestClient, headers: dict[str, str], body: Any, *, apply: bool) -> Any:
    return client.post(
        f"/api/catalog/batches/import?dry_run={'false' if apply else 'true'}",
        json=body,
        headers=headers,
    )


def _rows(db: Session) -> tuple[int, ...]:
    db.expire_all()
    return tuple(
        int(db.scalar(select(func.count()).select_from(model)) or 0)
        for model in (
            CatalogBatch,
            CatalogMaterial,
            CatalogSource,
            CatalogValue,
            CatalogSeries,
        )
    )


class Test들이기:
    def test_미리보기는_남기지_않고_적용은_한_번에_다시_들여도_같다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        before = _rows(db)
        shown = _import(client, admin_headers, bundle(defs.id), apply=False)
        assert shown.status_code == 200, shown.text
        body = shown.json()
        assert body["applied"] is False and body["problems"] == []
        assert body["materials"] == {"created": 1, "existing": 1}
        assert body["values"]["created"] == 3 and body["series"]["created"] == 1
        assert body["points"] == 4
        assert body["licenses"] == {"CC-BY-4.0": 1}
        assert _rows(db) == before

        applied = _import(client, admin_headers, bundle(defs.id), apply=True)
        assert applied.status_code == 200, applied.text
        assert applied.json()["applied"] is True
        after = _rows(db)
        # 묶음 1 · 재료 1(새) · 출처 1 · 값 3 + 점 4 · 벌 1
        assert after == (
            before[0] + 1,
            before[1] + 1,
            before[2] + 1,
            before[3] + 7,
            before[4] + 1,
        )

        material = db.scalar(
            select(CatalogMaterial).where(CatalogMaterial.external_key.is_not(None))
        )
        assert material is not None
        assert material.external_key == f"{KEY}:mat-304"
        assert (material.attributes or {})["designation"] == "EN 1.4301"
        points = db.scalars(
            select(CatalogValue).where(CatalogValue.series_id.is_not(None))
        ).all()
        assert all(one.scatter_point for one in points)
        assert sum(1 for one in points if (one.conditions or {}).get("runout") is True) == 2
        source = db.scalar(
            select(CatalogSource).where(CatalogSource.external_key.is_not(None))
        )
        assert source is not None and source.license == "CC-BY-4.0"
        assert source.attribution == "Smith et al. (2020), CC BY 4.0"

        again = _import(client, admin_headers, bundle(defs.id), apply=True)
        assert again.status_code == 200, again.text
        counts = again.json()
        assert counts["values"] == {"created": 0, "existing": 3}
        assert counts["series"] == {"created": 0, "existing": 1}
        assert _rows(db) == after

    def test_내용이_다르면_아무것도_들이지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        before = _rows(db)
        changed = bundle()
        changed["values"][0]["value_num"] = 700
        refused = _import(client, admin_headers, changed, apply=True)
        assert refused.status_code == 422, refused.text
        error = refused.json()["error"]
        assert error["code"] == "MNX-CATALOG-0077"
        assert [one["code"] for one in error["details"]["problems"]] == ["MNX-CATALOG-0076"]
        assert _rows(db) == before
        stored = db.scalar(
            select(CatalogValue).where(CatalogValue.external_key == f"{KEY}:v-uts")
        )
        assert stored is not None and stored.value_num == pytest.approx(6.5e8)

    def test_문제가_하나면_전부_안_들인다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        broken = bundle()
        broken["values"].append(copy.deepcopy(broken["values"][0]) | {"key": "v-bad"})
        broken["values"][-1]["property_key"] = "mechanical.no_such_key"
        before = _rows(db)
        shown = _import(client, admin_headers, broken, apply=False)
        assert [one["key"] for one in shown.json()["problems"]] == ["v-bad"]
        refused = _import(client, admin_headers, broken, apply=True)
        assert refused.status_code == 422, refused.text
        assert _rows(db) == before  # 묶음 줄도 안 남는다

    def test_곡선은_같은_x_를_거절하고_줄마다_조건은_정해진_칸만(
        self, client: TestClient, admin_headers: dict[str, str], defs: CatalogMaterial
    ) -> None:
        curve = bundle()
        curve["series"][0]["kind"] = "curve"
        shown = _import(client, admin_headers, curve, apply=False).json()
        assert "두 번" in shown["problems"][0]["message"]
        odd = bundle()
        odd["series"][0]["row_conditions"][0] = {"color": "red"}
        shown = _import(client, admin_headers, odd, apply=False).json()
        assert "color" in shown["problems"][0]["message"]

    def test_상업_이용이_안_되는_라이선스는_받지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], defs: CatalogMaterial
    ) -> None:
        nc = bundle()
        nc["sources"][0]["license"] = "CC-BY-NC-4.0"
        shown = _import(client, admin_headers, nc, apply=False).json()
        assert shown["problems"][0]["code"] == "MNX-CATALOG-0073"

    def test_일반_사용자는_들이지_못한다(
        self, client: TestClient, db: Session, workspace: Workspace, defs: CatalogMaterial
    ) -> None:
        refused = _import(client, member_headers(client, db, workspace), bundle(), apply=False)
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0075"


class Test산점:
    def test_산점의_점은_대표값에서_빠지고_낱값이_대표다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        material = db.scalar(
            select(CatalogMaterial).where(CatalogMaterial.external_key.is_not(None))
        )
        assert material is not None
        detail = client.get(
            f"/api/catalog/materials/{material.id}", headers=admin_headers
        ).json()
        fatigue = [
            one
            for one in detail["values"]
            if one["property_key"] == "mechanical.fatigue_strength"
        ]
        heads = [one for one in fatigue if one["representative"]]
        # 피로한도 낱값(240 MPa)이 대표 — S-N 점 넷은 대표 후보가 아니다.
        assert [one["value_num"] for one in heads] == [pytest.approx(2.4e8)]
        assert {one["separated_by"] for one in fatigue if one["series_id"]} == {"산점의 점"}
        assert detail["series"][0]["kind"] == "scatter"
        assert detail["series"][0]["batch_key"] == KEY


class Test출처_라이선스:
    def _value(
        self, client: TestClient, headers: dict[str, str], material_id: Any, license: Any
    ) -> Any:
        return client.post(
            f"/api/catalog/materials/{material_id}/values",
            json={
                "property_key": "mechanical.youngs_modulus",
                "value_num": 0.07,
                "unit": "MPa",
                "quality_tier": 2,
                "source": {
                    "kind": "journal",
                    "title": "실리콘 압축",
                    "doi": "10.1/x",
                    "license": license,
                },
            },
            headers=headers,
        )

    def test_빈_라이선스는_채우고_다른_라이선스는_거절한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        assert self._value(client, admin_headers, defs.id, None).status_code == 201
        assert self._value(client, admin_headers, defs.id, "CC-BY-4.0").status_code == 201
        db.expire_all()
        source = db.scalar(select(CatalogSource).where(CatalogSource.doi == "10.1/x"))
        assert source is not None and source.license == "CC-BY-4.0"
        refused = self._value(client, admin_headers, defs.id, "CC0-1.0")
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0074"


class Test지우기:
    def test_미리보기_숫자대로_지우고_있던_재료는_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        before = _rows(db)
        assert _import(client, admin_headers, bundle(defs.id), apply=True).status_code == 200
        plan = client.delete(f"/api/catalog/batches/{KEY}", headers=admin_headers)
        assert plan.status_code == 200, plan.text
        assert plan.json() == {
            "batch_key": KEY,
            "dry_run": True,
            "series": 1,
            "values": 7,
            "sources": 1,
            "materials": 1,
        }
        gone = client.delete(
            f"/api/catalog/batches/{KEY}?dry_run=false", headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        assert gone.json() == {**plan.json(), "dry_run": False}
        # 묶음 줄은 남고(지운 표시), 나머지는 들이기 전과 같다. 있던 재료(Ecoflex)는 남는다.
        assert _rows(db) == (before[0] + 1, *before[1:])
        db.expire_all()
        batch = db.scalar(select(CatalogBatch).where(CatalogBatch.key == KEY))
        assert batch is not None and batch.retired_at is not None
        assert db.get(CatalogMaterial, defs.id) is not None

    def test_사내가_받아_갔거나_이었으면_막는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        defs: CatalogMaterial,
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        value = db.scalar(
            select(CatalogValue).where(CatalogValue.external_key == f"{KEY}:v-uts")
        )
        material = db.scalar(
            select(CatalogMaterial).where(CatalogMaterial.external_key.is_not(None))
        )
        assert value is not None and material is not None
        mine = Material(
            record_name="사내 SUS304", family="Metal", category="Steel", grade="SUS304"
        )
        mine.declared_properties = [
            {
                "item": "인장강도",
                "catalog": {"value_ids": [str(value.id)], "tier": 2},
                "points": [],
            }
        ]
        db.add(mine)
        db.commit()
        refused = client.delete(f"/api/catalog/batches/{KEY}", headers=admin_headers)
        assert refused.status_code == 409, refused.text
        assert "사내 SUS304" in refused.json()["error"]["message"]

        mine.declared_properties = []
        db.add(CatalogLink(material_id=mine.id, catalog_material_id=material.id))
        db.commit()
        refused = client.delete(f"/api/catalog/batches/{KEY}", headers=admin_headers)
        assert refused.status_code == 409, refused.text
        assert "이어져" in refused.json()["error"]["message"]


class Test재료_미리보기:
    def test_비슷한_재료를_보여_주고_모르는_속성은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], defs: CatalogMaterial
    ) -> None:
        shown = client.post(
            "/api/catalog/materials/preview",
            json={
                "name": "Ecoflex 00-50",
                "category": "rubber",
                "attributes": {"designation": "00-50"},
            },
            headers=admin_headers,
        )
        assert shown.status_code == 200, shown.text
        assert [one["name"] for one in shown.json()["similar"]] == [defs.name]
        refused = client.post(
            "/api/catalog/materials/preview",
            json={"name": "X", "category": "rubber", "attributes": {"colour": "white"}},
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0072"

    def test_등급_규격명으로도_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], defs: CatalogMaterial
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        found = client.get(
            "/api/catalog/materials", params={"q": "EN 1.4301"}, headers=admin_headers
        )
        assert [one["name"] for one in found.json()["items"]] == [
            "AISI 304 sheet, annealed (Smith 2020)"
        ]


def test_기본_정의_씨앗은_없는_것만_만든다(db: Session) -> None:
    made = ensure_local_definitions(db)
    assert "local.mechanical.compressive_stress_at_strain" in made
    db.commit()
    assert ensure_local_definitions(db) == []
