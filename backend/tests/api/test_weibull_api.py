"""와이블 계수만 있는 외부 자료가 카드의 강도 분포 칸까지 가는 길(2026-10-20).

사용자 보고: 곡선 없이 파단 하중과 와이블 형상 · 척도만 있는 외부 자료가 있다. 시편마다
값이 있으면 「표로 시험 입력」 → 묶음이다(`tests/unit/test_ext_weibull.py`).
**형상만 있으면** 재료에 「와이블 계수」 를 적고 「재료 기본 정보 카드」 에서 「강도 분포」
항목란을 고른다 — 그 길이
**씨앗만으로** 이어지는지 본다. 항목 ↔ 문헌 키 연결이 씨앗이 아니면 개발 DB 에서 이어 둔 것이
운영에는 없어 값이 조용히 안 실린다(`catalog/links.py` 머리말).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.vocabulary.definitions import ensure_builtin_property_items

KEY = "mechanical.weibull_modulus"
BLOCK = "strength_distribution"


def test_적어_둔_와이블_계수가_강도_분포_칸에_앉는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    ensure_builtin_property_items(db)
    db.add(
        CatalogDefinition(
            key=KEY,
            domain="mechanical",
            name="Weibull modulus",
            value_type="numeric",
            si_unit="1",
        )
    )
    db.commit()
    assert any("와이블 계수" in line for line in ensure_builtin_property_links(db))
    db.commit()

    material = client.post(
        "/api/materials",
        json={"family": "Ceramic", "category": "Glass", "grade": f"WB-{uuid.uuid4().hex[:6]}"},
        headers=admin_headers,
    )
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]
    stated = client.patch(
        f"/api/materials/{material_id}",
        json={
            "declared_properties": [
                {
                    "item": "와이블 계수",
                    "points": [{"value": 12.0}],
                    "source": "literature",
                    "reference": "공급사 강도 시험 보고서",
                }
            ]
        },
        headers=admin_headers,
    )
    assert stated.status_code == 200, stated.text

    preview = client.get(
        "/api/fitting/cards/declared/preview",
        params={"material_id": material_id},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    option = next(one for one in preview.json()["fillable"] if one["key"] == BLOCK)
    assert [one["key"] for one in option["slots"]] == ["shape"]

    made = client.post(
        "/api/fitting/cards/declared",
        json={"material_id": material_id, "label": "외부 와이블", "block_keys": [BLOCK]},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    values = made.json()["blocks"][BLOCK]["values"]
    assert values["shape"] == pytest.approx(12.0)
    # 잰 값이 아니라는 사실이 칸에 붙는다 — 덱을 받는 사람이 그것을 물을 자리다.
    assert values["shape_source"] == "declared:literature"
