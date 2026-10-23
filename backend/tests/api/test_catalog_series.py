"""문헌의 **이어진 값 한 벌** — 곡선 · 표 · 계수 묶음을 한 번에 넣는다(ADR 0067).

점은 문헌 값 한 줄씩            값 검색 · 물성 지도 · 사내 반영이 고치지 않고 읽는다
축은 정의의 조건축              temperature_c · temperature_k 로 갈리면 한 축으로 안 모인다
축 단위는 키의 단위로           °C 로 적어도 temperature_k 에는 K 로
열 단위는 정의 단위로           GPa 로 넣어도 Pa 로 — 값 하나와 같은 검사
계수 묶음은 항의 단위 그대로     Anand 처럼 무차원 키의 항은 환산하지 않는다(ADR 0029)
지우기는 넣은 사람 · 관리자      점과 함께, 감사에 남는다
지도는 한 벌에 20점까지          응력-변형률 수백 점이 지도를 덮지 않는다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_catalog_contribute import member_headers

from app.modules.audit.models import AuditEntry
from app.modules.catalog import parameters
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSeries,
    CatalogSource,
    CatalogValue,
)
from app.modules.materials.models import Material
from app.modules.workspaces.models import Workspace
from app.shared.coverage import TABLE_ROWS_ON_MAP

SOURCE = {"kind": "journal", "title": "SAC305 고온 인장", "year": 2014}


@pytest.fixture
def lit(db: Session) -> CatalogMaterial:
    """이관해 온 것처럼 — 조건축을 가진 정의들과 문헌 재료 하나."""
    for key, name, unit, axes in (
        ("mechanical.youngs_modulus", "탄성계수", "Pa", ["temperature_k", "strain_rate_s"]),
        ("mechanical.tensile_stress_at_strain", "변형률별 인장응력", "Pa", ["strain_pct"]),
        ("mechanical.anand_constant", "Anand 상수", "1", ["model", "term", "set_id"]),
        ("mechanical.prony_relaxation_time", "Prony 완화시간", "s", ["term", "set_id"]),
        ("mechanical.prony_relative_modulus", "Prony 상대 탄성률", "1", ["term", "set_id"]),
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
    material = CatalogMaterial(mt_id=910001, name="SAC305", category="metal")
    db.add(material)
    db.commit()
    parameters.forget()
    return material


def _curve(**override: Any) -> dict[str, Any]:
    return {
        "kind": "curve",
        "label": "온도별 탄성계수",
        "x_key": "temperature_k",
        "x_unit": "°C",
        "columns": [{"property_key": "mechanical.youngs_modulus", "unit": "GPa"}],
        # 차례가 뒤섞여 와도 축 차례로 선다.
        "rows": [[100, 45.0], [25, 50.0], [150, 40.0]],
        "method": "measured",
        "quality_tier": 1,
        "source": SOURCE,
        "source_detail": "Fig. 4",
        **override,
    }


def _post(client: TestClient, headers: dict[str, str], material: Any, body: Any) -> Any:
    return client.post(
        f"/api/catalog/materials/{material.id}/series", json=body, headers=headers
    )


class Test곡선:
    def test_한_번에_넣고_점은_문헌_값이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        made = _post(client, admin_headers, lit, _curve())
        assert made.status_code == 201, made.text
        body = made.json()
        series = body["series"]
        assert series["kind"] == "curve" and series["point_count"] == 3
        assert series["x_key"] == "temperature_k" and series["x_unit"] == "K"
        assert [
            (one["property_key"], one["property_name"], one["unit"], one["count"])
            for one in series["columns"]
        ] == [("mechanical.youngs_modulus", "탄성계수", "Pa", 3)]
        # 요약 화면이 점 없이 쓸 범위 — 값은 저장 단위, 축은 축 단위(ADR 0072).
        column = series["columns"][0]
        assert (column["low"], column["high"]) == pytest.approx((4.0e10, 5.0e10))
        assert (series["x_min"], series["x_max"]) == pytest.approx((298.15, 423.15))
        # 축은 °C → K, 값은 GPa → Pa, 축 차례로.
        assert [one["x"] for one in body["points"]] == pytest.approx([298.15, 373.15, 423.15])
        assert [one["value"] for one in body["points"]] == pytest.approx(
            [5.0e10, 4.5e10, 4.0e10]
        )
        assert body["converted"] == ["탄성계수: GPa → Pa (3점)"]

        stored = db.scalars(
            select(CatalogValue).where(CatalogValue.series_id == series["id"])
        ).all()
        assert len(stored) == 3
        assert {one.quality_tier for one in stored} == {1}
        assert all(one.mt_id is None and one.source_id is not None for one in stored)
        assert sorted(
            (one.conditions or {})["temperature_k"] for one in stored
        ) == pytest.approx([298.15, 373.15, 423.15])

        detail = client.get(f"/api/catalog/materials/{lit.id}", headers=admin_headers).json()
        assert [one["id"] for one in detail["series"]] == [series["id"]]
        assert detail["series"][0]["source"]["title"] == SOURCE["title"]
        # **상세에는 점이 안 실린다** — 대표로 뽑힌 점(실온) 하나만(ADR 0072).
        mine = [one for one in detail["values"] if one["series_id"] == series["id"]]
        assert [(one["value_num"], one["representative"]) for one in mine] == [
            (pytest.approx(5.0e10), True)
        ]
        # 점은 벌마다 따로, 축 차례로.
        points = client.get(
            f"/api/catalog/series/{series['id']}/points", headers=admin_headers
        ).json()
        assert points["series"]["point_count"] == 3
        assert [one["x"] for one in points["points"]] == pytest.approx(
            [298.15, 373.15, 423.15]
        )
        assert [one["value"] for one in points["points"]] == pytest.approx(
            [5.0e10, 4.5e10, 4.0e10]
        )

    def test_미리보기는_같은_검사를_하고_남기지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        before = db.scalar(select(func.count()).select_from(CatalogValue))
        shown = client.post(
            f"/api/catalog/materials/{lit.id}/series/preview",
            json=_curve(),
            headers=admin_headers,
        )
        assert shown.status_code == 200, shown.text
        assert len(shown.json()["points"]) == 3
        db.expire_all()
        assert db.scalar(select(func.count()).select_from(CatalogValue)) == before
        assert db.scalar(select(func.count()).select_from(CatalogSeries)) == 0
        assert db.scalar(select(func.count()).select_from(CatalogSource)) == 0
        refused = client.post(
            f"/api/catalog/materials/{lit.id}/series/preview",
            json=_curve(columns=[{"property_key": "mechanical.youngs_modulus", "unit": "kg"}]),
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0044"

    def test_응력_변형률_곡선은_열을_둘까지_든다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        made = _post(
            client,
            admin_headers,
            lit,
            _curve(
                label="공칭 응력-변형률",
                x_key="strain_pct",
                x_unit=None,
                columns=[
                    {"property_key": "mechanical.tensile_stress_at_strain", "unit": "MPa"}
                ],
                rows=[[0.0, 0.0], [0.2, 30.0], [1.0, 42.0], [5.0, 48.0]],
                conditions={"temperature_k": 298.15},
            ),
        )
        assert made.status_code == 201, made.text
        stored = db.scalars(
            select(CatalogValue).where(CatalogValue.series_id == made.json()["series"]["id"])
        ).all()
        # 공통 조건이 점마다 같이 든다.
        assert all((one.conditions or {})["temperature_k"] == 298.15 for one in stored)
        assert sorted(one.value_num or 0.0 for one in stored) == pytest.approx(
            [0, 3e7, 4.2e7, 4.8e7]
        )

    @pytest.mark.parametrize(
        ("override", "words"),
        [
            ({"x_key": "temperature_c", "x_unit": None}, "조건축에"),
            ({"rows": [[25, 50.0], [25.0, 49.0]]}, "두 번"),
            ({"rows": [[25, 50.0, 1.0], [100, 45.0, 1.0]]}, "칸이"),
            ({"rows": [[25, 50.0]]}, "2개 이상"),
            ({"rows": [[25, None], [100, 45.0]]}, "값이 하나도"),
            ({"conditions": {"temperature_k": 300}}, "공통 조건에 축"),
            ({"x_unit": "kg"}, "옮길 수 없습니다"),
            ({"kind": "parameter_set"}, "식 이름"),
        ],
    )
    def test_어긋나면_까닭을_대고_거절한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
        override: dict[str, Any],
        words: str,
    ) -> None:
        refused = _post(client, admin_headers, lit, _curve(**override))
        assert refused.status_code == 422, refused.text
        assert words in refused.json()["error"]["message"]


class Test계수_묶음:
    def test_무차원_키의_항은_그_단위_그대로_한_벌로_묶인다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        made = _post(
            client,
            admin_headers,
            lit,
            {
                "kind": "parameter_set",
                "label": "Anand · 리플로",
                "model": "anand",
                "property_key": "mechanical.anand_constant",
                "terms": [
                    {"term": "a", "value": 1.91, "unit": "1"},
                    {"term": "A", "value": 3776, "unit": "1/s"},
                    {"term": "h0", "value": 150000, "unit": "MPa"},
                ],
                "method": "computed",
                "quality_tier": 4,
                "source": SOURCE,
            },
        )
        assert made.status_code == 201, made.text
        points = {one["term"]: one for one in made.json()["points"]}
        # **환산하지 않는다** — 150000 MPa 를 Pa 로 바꾸면 식이 틀린다(ADR 0029 D2).
        assert points["h0"]["value"] == 150000 and points["h0"]["term_unit"] == "MPa"
        assert points["A"]["term_unit"] == "1/s"

        sets = client.get(
            f"/api/catalog/materials/{lit.id}/parameter-sets", headers=admin_headers
        ).json()
        assert len(sets) == 1
        assert sets[0]["model"] == "anand"
        assert {one["term"] for one in sets[0]["terms"]} == {"a", "A", "h0"}
        stored = db.scalars(
            select(CatalogValue).where(CatalogValue.series_id.is_not(None))
        ).all()
        # 추정값 표지는 점마다.
        assert all((one.conditions or {})["assumption"] is True for one in stored)

    def test_두_키에_걸친_Prony_는_항마다_키를_적고_단위는_환산한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        made = _post(
            client,
            admin_headers,
            lit,
            {
                "kind": "parameter_set",
                "label": "Prony 3항",
                "model": "prony",
                "terms": [
                    {
                        "term": "g1",
                        "value": 0.3,
                        "property_key": "mechanical.prony_relative_modulus",
                    },
                    {
                        "term": "tau1",
                        "value": 10,
                        "unit": "ms",
                        "property_key": "mechanical.prony_relaxation_time",
                    },
                ],
                "method": "computed",
                "quality_tier": 4,
                "source": SOURCE,
            },
        )
        assert made.status_code == 201, made.text
        points = {one["term"]: one for one in made.json()["points"]}
        assert points["tau1"]["value"] == pytest.approx(0.01)
        assert points["tau1"]["unit"] == "s"
        assert [
            (one["property_key"], one["property_name"], one["unit"], one["count"])
            for one in made.json()["series"]["columns"]
        ] == [
            ("mechanical.prony_relative_modulus", "Prony 상대 탄성률", "1", 1),
            ("mechanical.prony_relaxation_time", "Prony 완화시간", "s", 1),
        ]


class Test지우기:
    def test_넣은_사람과_관리자만_점과_함께_지우고_남긴다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Workspace,
        lit: CatalogMaterial,
    ) -> None:
        series_id = _post(client, admin_headers, lit, _curve()).json()["series"]["id"]
        member = member_headers(client, db, workspace)
        refused = client.delete(f"/api/catalog/series/{series_id}", headers=member)
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0047"

        gone = client.delete(f"/api/catalog/series/{series_id}", headers=admin_headers)
        assert gone.status_code == 204, gone.text
        db.expire_all()
        assert db.scalar(select(func.count()).select_from(CatalogSeries)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(CatalogValue)
                .where(CatalogValue.material_id == lit.id)
            )
            == 0
        )
        # 아무도 안 가리키는 직접 만든 출처는 같이 간다.
        assert db.scalar(select(func.count()).select_from(CatalogSource)) == 0
        logged = db.scalars(
            select(AuditEntry).where(AuditEntry.action == "catalog_series.deleted")
        ).all()
        assert len(logged) == 1 and "온도별 탄성계수" in logged[0].target_label

        missing = client.delete(f"/api/catalog/series/{series_id}", headers=admin_headers)
        assert missing.status_code == 404


class Test물성_지도:
    def test_한_벌은_양끝을_남기고_솎는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        lit: CatalogMaterial,
    ) -> None:
        mine = Material(
            record_name="사내 SAC305", family="Metal", category="Solder", grade="SAC305"
        )
        db.add(mine)
        db.flush()
        db.add(CatalogLink(material_id=mine.id, catalog_material_id=lit.id))
        db.commit()
        rows = [[float(index), 100.0 + index] for index in range(50)]
        made = _post(
            client,
            admin_headers,
            lit,
            _curve(
                label="응력-변형률",
                x_key="strain_pct",
                x_unit=None,
                columns=[
                    {"property_key": "mechanical.tensile_stress_at_strain", "unit": "MPa"}
                ],
                rows=rows,
            ),
        )
        assert made.status_code == 201, made.text
        coverage = client.get(
            f"/api/materials/{mine.id}/property-coverage", headers=admin_headers
        ).json()
        entries = {one["key"]: one for one in coverage["properties"]}[
            "mechanical.tensile_stress_at_strain"
        ]["entries"]
        assert len(entries) == TABLE_ROWS_ON_MAP
        values = sorted(one["value_si"] for one in entries)
        assert values[0] == pytest.approx(1.0e8) and values[-1] == pytest.approx(1.49e8)
        assert all("곡선 50점 중 20점" in (one["method"] or "") for one in entries)
