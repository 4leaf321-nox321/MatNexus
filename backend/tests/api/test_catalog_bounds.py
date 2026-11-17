"""문헌 범위의 하한 · 상한 — 대표값 순위와 표지(2026-11-17).

개발 DB 실측: 하한 · 상한 줄만 있는 재료 · 물성 748쌍(영률 63 · 선팽창계수 214)에서 대표가
곧 그 끝이었고 표지가 없었다. 그 값이 덱의 탄성계수로 그대로 나갔다.

    가운데 값이 있으면 끝은 진다     등급이 좋은 하한도 typical 에 진다(`범위의 끝`)
    끝만 있으면 끝이 대표로 서되     상세의 `bound` 가 그렇다고 말한다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue


def _material(db: Session, values: list[tuple[float, int, dict[str, str]]]) -> CatalogMaterial:
    db.add(
        CatalogDefinition(
            mt_id=910001,
            key="mechanical.youngs_modulus",
            name="탄성계수",
            domain="mechanical",
            si_unit="Pa",
            value_type="numeric",
        )
    )
    material = CatalogMaterial(mt_id=910002, name="범위만 있는 재료", category="polymer")
    db.add(material)
    db.flush()
    for index, (number, tier, conditions) in enumerate(values):
        db.add(
            CatalogValue(
                mt_id=910010 + index,
                material_id=material.id,
                property_key="mechanical.youngs_modulus",
                value_num=number,
                unit="Pa",
                quality_tier=tier,
                conditions=conditions,
            )
        )
    db.commit()
    return material


def _values(
    client: TestClient, headers: dict[str, str], material: CatalogMaterial
) -> list[dict[str, Any]]:
    got = client.get(f"/api/catalog/materials/{material.id}", headers=headers)
    assert got.status_code == 200, got.text
    rows: list[dict[str, Any]] = got.json()["values"]
    return rows


class Test범위의_끝:
    def test_가운데_값이_있으면_등급이_좋은_하한도_진다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(
            db,
            [(2.0e9, 1, {"bound": "lower"}), (3.0e9, 3, {"value_type": "typical"})],
        )
        rows = {one["value_num"]: one for one in _values(client, admin_headers, material)}
        assert rows[3.0e9]["representative"] and rows[3.0e9]["bound"] is None
        assert rows[2.0e9]["separated_by"] == "범위의 끝"
        assert rows[2.0e9]["bound"] == "lower"

    def test_끝만_있으면_끝이_대표로_서되_bound_가_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(db, [(2.0e9, 1, {"bound": "lower — 원문은 `2-4 GPa` 구간"})])
        (row,) = _values(client, admin_headers, material)
        assert row["representative"] and row["bound"] == "lower"
