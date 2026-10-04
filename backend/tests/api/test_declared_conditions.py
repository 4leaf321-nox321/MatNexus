"""선언 물성의 **조건 축** — 온도 · 주파수 · 파장 (2026-10-01).

유전율(Dk) · 유전손실(Df)은 1 MHz 와 10 GHz 에서 값이 다르고, 굴절률은 파장마다 다르다.
선언 물성이 온도별 점만 받던 동안에는 「1 GHz 의 Dk」 를 담을 자리가 없었다 — 한 값만
적거나 온도 칸에 주파수를 우겨 넣어야 했고, 뒤엣것은 숫자는 그럴듯한데 뜻이 다른 값이다.

이 시험이 지키는 것:

    받기     항목의 축으로만 받는다 — 축이 다른 값은 거절(측정 온도는 예외, 점마다 같을 때)
    되보내기  응답의 점이 조건을 다 든다 — 화면 · MCP 가 그대로 되보내도 안 빠진다
    문헌      카탈로그 조건(frequency_hz · wavelength_nm · temperature_c)을 축으로 옮긴다
    카드      칸을 채운 값이 어느 주파수의 것인지 카드에 남는다
    내보내기  CSV 에 값과 주파수가 실린다(전에는 값 열이 늘 비었다)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.materials import declared
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import (
    BUILTIN_ITEM_CONDITIONS,
    BUILTIN_PROPERTY_ITEMS,
    ensure_builtin_axis_fields,
    ensure_builtin_property_items,
    refresh_builtin_axis_fields,
    refresh_builtin_property_items,
)
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared import dataset_export, declared_conditions, declared_slots
from app.shared.errors import AppError
from app.shared.text import compare_key

DK = "비유전율"
DF = "유전손실계수(Df)"


@pytest.fixture()
def material(db: Session) -> Material:
    ensure_builtin_property_items(db)
    one = Material(record_name="FR4_-_-", family="Polymer", category="Laminate", grade="FR4")
    db.add(one)
    db.commit()
    return one


def dk(points: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    return {
        "item": DK,
        "points": points,
        "input_unit": "1",
        "source": "datasheet",
        "reference": "Isola 370HR 데이터시트",
        **over,
    }


class Test문헌_조건_옮기기:
    def test_섭씨_온도도_켈빈으로_읽는다(self) -> None:
        """전에는 `temperature_k` 만 읽어 섭씨로 적힌 문헌 값의 온도가 빠졌다."""
        assert declared_conditions.from_catalog(
            {"temperature_c": 25}, declared_conditions.TEMPERATURE
        ) == pytest.approx(298.15)
        assert declared_conditions.from_catalog(
            {"temperature_k": 300, "temperature_c": 25}, declared_conditions.TEMPERATURE
        ) == pytest.approx(300)

    def test_주파수와_파장(self) -> None:
        assert declared_conditions.from_catalog(
            {"frequency_hz": 1e9}, declared_conditions.FREQUENCY
        ) == pytest.approx(1e9)
        assert declared_conditions.from_catalog(
            {"wavelength_nm": 587.6}, declared_conditions.WAVELENGTH
        ) == pytest.approx(587.6e-9)
        assert declared_conditions.from_catalog({}, declared_conditions.FREQUENCY) is None

    def test_주파수_이름이_달라도_읽는다(self) -> None:
        """`frequency_hz` 만 읽어서 `frequency_MHz` 194건 · `frequency_ghz` 68건 …은 반영하면
        주파수가 빠졌다(2026-10-04). 값 검색 · 커버리지와 같은 표를 읽는다."""
        frequency = declared_conditions.FREQUENCY
        assert declared_conditions.from_catalog(
            {"frequency_MHz": 100}, frequency
        ) == pytest.approx(1e8)
        assert declared_conditions.from_catalog({"frequency_ghz": 10}, frequency) == (
            pytest.approx(1e10)
        )
        assert declared_conditions.from_catalog(
            {"wavelength_um": 2.5}, declared_conditions.WAVELENGTH
        ) == pytest.approx(2.5e-6)
        # 글은 읽지 않는다 — 「1 MHz」 를 숫자로 풀면 짐작이 섞인다.
        assert declared_conditions.from_catalog({"frequency": "1 MHz"}, frequency) is None


class Test기본_항목:
    def test_문헌의_전기_물성_19개가_전부_사내_항목이다(self) -> None:
        """문헌 값을 반영할 자리가 사내 쪽에 없으면 그 값은 카드로 못 간다."""
        keys = {row[6] for row in BUILTIN_PROPERTY_ITEMS}
        electrical = {key for key in keys if key.startswith("electrical.")}
        assert len(electrical) == 19
        assert {
            "electrical.dielectric_constant",
            "electrical.dissipation_factor",
        } <= electrical

    def test_유전율_유전손실은_주파수_굴절률은_파장(self, db: Session) -> None:
        ensure_builtin_property_items(db)
        known = declared.catalog(db)
        assert known[DK]["condition"] == "주파수"
        assert known[DF]["condition"] == "주파수"
        assert known["굴절률"]["condition"] == "파장"
        assert known["탄성계수"]["condition"] == "온도"

    def test_이미_있는_항목에_조건이_채워진다(self, db: Session) -> None:
        """운영에는 비유전율이 조건 없이 이미 있다 — 배포가 빠진 속성만 채운다."""
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        db.add(
            VocabularyTerm(
                vocabulary_id=axis.id,
                value=DK,
                normalized=compare_key(DK),
                attributes={"dimension": "dimensionless", "symbol": "eps_r", "level": "재료"},
            )
        )
        db.flush()

        assert DK in refresh_builtin_property_items(db)
        assert declared.catalog(db)[DK]["condition"] == "주파수"

    def test_기준정보_칸이_배포로_더해진다(self, db: Session) -> None:
        ensure_builtin_axis_fields(db)
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        axis.base_fields = [one for one in axis.base_fields if one.get("key") != "condition"]
        db.flush()

        refresh_builtin_axis_fields(db)

        keys = [one.get("key") for one in axis.base_fields]
        assert "condition" in keys

    def test_조건이_정해진_항목은_전부_기본_항목이다(self) -> None:
        keys = {row[6] for row in BUILTIN_PROPERTY_ITEMS}
        assert set(BUILTIN_ITEM_CONDITIONS) <= keys


class Test받기:
    def test_주파수별_값을_받아_주파수순으로_둔다(
        self, db: Session, material: Material
    ) -> None:
        rows = declared.check(
            db,
            [dk([{"value": 3.6, "frequency_hz": 1e9}, {"value": 3.8, "frequency_hz": 1e6}])],
        )
        points = rows[0]["points"]
        assert [point["frequency_hz"] for point in points] == [1e6, 1e9]
        assert [point["value_si"] for point in points] == [3.8, 3.6]

    def test_측정_온도는_점마다_같으면_받는다(self, db: Session, material: Material) -> None:
        rows = declared.check(
            db,
            [
                dk(
                    [
                        {"value": 3.6, "frequency_hz": 1e9, "temperature_k": 296.15},
                        {"value": 3.8, "frequency_hz": 1e6, "temperature_k": 296.15},
                    ]
                )
            ],
        )
        assert {point["temperature_k"] for point in rows[0]["points"]} == {296.15}

    def test_측정_온도가_점마다_다르면_거절한다(self, db: Session, material: Material) -> None:
        """주파수와 온도의 2차원 표 — 한 축만 정렬해 두면 덱이 어느 축을 읽을지 모른다."""
        with pytest.raises(AppError) as caught:
            declared.check(
                db,
                [
                    dk(
                        [
                            {"value": 3.6, "frequency_hz": 1e9, "temperature_k": 296.15},
                            {"value": 3.8, "frequency_hz": 1e6, "temperature_k": 373.15},
                        ]
                    )
                ],
            )
        assert caught.value.code == "MNX-MATERIALS-0028"

    def test_유전율에_온도별_표를_적으면_거절한다(
        self, db: Session, material: Material
    ) -> None:
        """온도 칸에 값을 여럿 적으면 측정 온도가 점마다 달라진다 — 축이 다른 표다."""
        with pytest.raises(AppError):
            declared.check(
                db,
                [
                    dk(
                        [
                            {"value": 3.6, "temperature_k": 296.15},
                            {"value": 3.4, "temperature_k": 373.15},
                        ]
                    )
                ],
            )

    def test_다른_축의_조건은_거절한다(self, db: Session, material: Material) -> None:
        with pytest.raises(AppError) as caught:
            declared.check(db, [dk([{"value": 3.6, "wavelength_m": 5.9e-7}])])
        assert caught.value.code == "MNX-MATERIALS-0028"
        with pytest.raises(AppError) as caught:
            declared.check(
                db,
                [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 200, "frequency_hz": 1e9}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "핸드북",
                    }
                ],
            )
        assert caught.value.code == "MNX-MATERIALS-0028"

    def test_점이_여럿이면_주파수가_다_있어야_하고_달라야_한다(
        self, db: Session, material: Material
    ) -> None:
        with pytest.raises(AppError) as caught:
            declared.check(db, [dk([{"value": 3.6, "frequency_hz": 1e9}, {"value": 3.8}])])
        assert caught.value.code == "MNX-MATERIALS-0026"
        with pytest.raises(AppError) as caught:
            declared.check(
                db,
                [
                    dk(
                        [
                            {"value": 3.6, "frequency_hz": 1e9},
                            {"value": 3.8, "frequency_hz": 1e9},
                        ]
                    )
                ],
            )
        assert caught.value.code == "MNX-MATERIALS-0026"

    def test_주파수는_0_보다_커야_한다(self, db: Session, material: Material) -> None:
        with pytest.raises(AppError) as caught:
            declared.check(db, [dk([{"value": 3.6, "frequency_hz": 0}])])
        assert caught.value.code == "MNX-MATERIALS-0028"

    def test_한_점이면_주파수를_비워도_된다(self, db: Session, material: Material) -> None:
        """온도 축의 「비우면 상온」 과 같은 규칙 — 주파수를 모르는 문헌 값도 있다."""
        rows = declared.check(db, [dk([{"value": 4.2}])])
        assert rows[0]["points"][0]["frequency_hz"] is None


class TestAPI:
    def test_적고_읽으면_주파수가_그대로_온다(
        self, client: TestClient, admin_headers: dict[str, str], material: Material
    ) -> None:
        """응답의 점이 조건을 다 들어야 화면 · MCP 가 되보낼 때 안 빠진다."""
        changed = client.patch(
            f"/api/materials/{material.id}",
            json={
                "declared_properties": [
                    dk(
                        [
                            {"value": 3.6, "frequency_hz": 1e9},
                            {"value": 3.8, "frequency_hz": 1e6},
                        ]
                    )
                ]
            },
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        points = changed.json()["declared_properties"][0]["points"]
        assert [point["frequency_hz"] for point in points] == [1e6, 1e9]

        resent = client.patch(
            f"/api/materials/{material.id}",
            json={
                "declared_properties": [
                    dk(
                        [
                            {
                                key: point[key]
                                for key in (
                                    "temperature_k",
                                    "frequency_hz",
                                    "wavelength_m",
                                    "value",
                                )
                            }
                            for point in points
                        ]
                    )
                ]
            },
            headers=admin_headers,
        )
        assert resent.status_code == 200, resent.text
        again = resent.json()["declared_properties"][0]["points"]
        assert [point["frequency_hz"] for point in again] == [1e6, 1e9]

    def test_주파수로_물으면_그_주파수의_값이_걸린다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        """선언값 검색이 온도만 봐서 **10 GHz 에 적은 Dk 가 주파수 검색에 안 걸렸다**
        (2026-10-04).

        점이 주파수를 드는데 검색은 그것을 모르고 「그 조건에서 잰 값이 아니다」 로 뺐다.
        """
        db.add(
            CatalogDefinition(
                key="electrical.dielectric_constant",
                domain="electrical",
                name="유전율",
                value_type="numeric",
                si_unit="1",
            )
        )
        db.flush()
        ensure_builtin_property_links(db)
        material.declared_properties = declared.check(
            db,
            [dk([{"value": 3.8, "frequency_hz": 1e6}, {"value": 3.6, "frequency_hz": 1e10}])],
        )
        db.commit()

        def found(**condition: Any) -> list[float]:
            got = client.get(
                "/api/catalog/properties/search",
                params={
                    "q": "electrical.dielectric_constant",
                    "unit": "1",
                    "min": 3,
                    "max": 4,
                    "origins": "internal",
                    **condition,
                },
                headers=admin_headers,
            )
            assert got.status_code == 200, got.text
            return [one["value"] for one in got.json()["hits"]]

        assert found(condition="frequency", condition_unit="GHz", condition_near=10) == [3.6]
        assert found(condition="frequency", condition_unit="MHz", condition_near=1) == [3.8]
        # 점이 안 드는 조건(변형률속도)으로 물으면 선언값은 안 걸린다 — 있는 척하지 않는다.
        assert found(condition="strain_rate", condition_unit="1/s", condition_near=0.001) == []

    def test_항목_목록이_조건과_단위_배수를_준다(
        self, client: TestClient, admin_headers: dict[str, str], material: Material
    ) -> None:
        """배수는 서버가 낸다 — 화면이 GHz 를 1e9 로 따로 들면 환산 규칙이 두 곳이 된다."""
        listed = client.get("/api/materials/property-items", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        by_name = {one["item"]: one for one in listed.json()}
        assert by_name[DK]["condition"] == "주파수"
        assert by_name[DK]["condition_key"] == "frequency_hz"
        units = {one["unit"]: one["to_si"] for one in by_name[DK]["condition_units"]}
        assert units["GHz"] == pytest.approx(1e9)
        assert units["MHz"] == pytest.approx(1e6)
        assert by_name["탄성계수"]["condition_units"] == []


class Test카드와_내보내기:
    def test_칸을_채운_값의_주파수가_카드에_남는다(
        self, db: Session, material: Material
    ) -> None:
        db.add(
            CatalogDefinition(
                key="electrical.dielectric_constant",
                domain="electrical",
                name="유전율",
                value_type="numeric",
                si_unit="1",
            )
        )
        db.flush()
        ensure_builtin_property_links(db)
        material.declared_properties = declared.check(
            db, [dk([{"value": 3.6, "frequency_hz": 1e9}])]
        )
        db.commit()

        stated = declared_slots._declared_by_key(db, material)

        assert stated["electrical.dielectric_constant"]["conditions"] == {"frequency_hz": 1e9}

    def test_CSV_에_값과_주파수가_실린다(
        self, db: Session, material: Material, tmp_path: Path
    ) -> None:
        """전에는 저장에 없는 `value` 를 읽어 값 열이 늘 비어 나갔다(442점 전부)."""
        material.declared_properties = declared.check(
            db,
            [
                dk([{"value": 3.6, "frequency_hz": 1e9}]),
                {
                    "item": "탄성계수",
                    "points": [{"value": 200}],
                    "input_unit": "GPa",
                    "source": "literature",
                    "reference": "핸드북",
                },
            ],
        )
        db.commit()

        dataset_export.export(
            tmp_path, db=db, workspace=None, with_curves=False, with_catalog=False
        )

        with (tmp_path / "declared_properties.csv").open(encoding="utf-8-sig") as handle:
            rows = {row["item"]: row for row in csv.DictReader(handle)}
        assert float(rows["탄성계수"]["value_si"]) == pytest.approx(200e9)
        assert float(rows[DK]["frequency_hz"]) == pytest.approx(1e9)
        assert float(rows[DK]["value_si"]) == pytest.approx(3.6)
