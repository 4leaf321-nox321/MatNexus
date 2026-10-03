"""받아 온 문헌 값의 **등급** — 그 문헌 값의 등급을 잇는다(2026-10-03, 사용자 보고).

「문헌 재료를 선언 물성으로 받아 오면 문헌 1등급인 것도 3등급으로 찍힌다.」 선언 값의 등급이
출처로만 정해져 문헌은 늘 3 이었다. 받아 온 값은 그 문헌 값의 등급을 안다 — 그것이 근거다.
이 시험이 지키는 것:

    잇는다      1등급 문헌 값을 받아 오면 1 — 출처가 「문헌」 이어도
    대 본다     서버가 그 값과 숫자를 대 본다. 다르면 거절(id 만 붙여 아무 숫자에 1등급 금지)
    묶인다      통째 교체로 그대로 되보내면 이어받고, 값을 고치면 풀려 출처의 등급(3)으로
    낮은 쪽     여러 값이면 가장 낮은 등급 · 묶은 중앙값은 묶인 값 중 가장 낮은 등급
    퍼진다      카드 칸의 출처 표지 · 카드 등급 · 덱 각주가 받아 온 등급을 안다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.fitting.routes import _origin
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.shared import declared_approval, tiers

E = "탄성계수"
KEY = "mechanical.youngs_modulus"


@pytest.fixture()
def material(db: Session) -> Material:
    ensure_builtin_property_items(db)
    one = Material(record_name="SAC305_-_-", family="Metal", category="Solder", grade="SAC305")
    db.add(one)
    db.commit()
    return one


def _catalog(
    db: Session, *values: tuple[float, int, dict[str, Any] | None]
) -> list[CatalogValue]:
    """문헌 재료 하나와 그 탄성계수 값들 — (Pa, 등급, 조건)."""
    if db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == KEY)) is None:
        db.add(
            CatalogDefinition(
                key=KEY,
                domain="mechanical",
                name="탄성계수",
                symbol="E",
                si_unit="Pa",
                value_type="numeric",
            )
        )
    paper = CatalogSource(kind="journal", title="Mechanical Characterization of SAC305")
    owner = CatalogMaterial(name="SAC305", category="metal")
    db.add_all([paper, owner])
    db.flush()
    made = [
        CatalogValue(
            material_id=owner.id,
            property_key=KEY,
            value_num=number,
            unit="Pa",
            quality_tier=tier,
            conditions=conditions,
            source_id=paper.id,
            method="measured",
        )
        for number, tier, conditions in values
    ]
    db.add_all(made)
    db.commit()
    return made


def _row(**over: Any) -> dict[str, Any]:
    return {
        "item": E,
        "points": [{"value": 4.3e10}],
        "source": "literature",
        "reference": "Mechanical Characterization of SAC305 (문헌 물성 카탈로그, 실측)",
        **over,
    }


def _save(
    client: TestClient, headers: dict[str, str], material: Material, *rows: dict[str, Any]
) -> Any:
    return client.patch(
        f"/api/materials/{material.id}",
        json={"declared_properties": list(rows)},
        headers=headers,
    )


def _stored(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    rows: dict[str, dict[str, Any]] = {
        one["item"]: one for one in response.json()["declared_properties"]
    }
    return rows[E]


class Test받아_온_등급:
    def test_1등급_문헌_값을_받아_오면_1등급이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        (paper_value,) = _catalog(db, (4.3e10, 1, None))
        row = _stored(
            _save(
                client, admin_headers, material, _row(catalog_value_ids=[str(paper_value.id)])
            )
        )
        # 출처는 그대로 「문헌」 — 등급만 그 문헌 값의 것이다.
        assert row["source"] == "literature"
        assert row["quality_tier"] == 1
        assert row["catalog"] == {"tier": 1, "value_ids": [str(paper_value.id)]}
        # 승인해도 1 위로는 없다.
        assert row["tier_if_approved"] == 1

    def test_숫자가_다르거나_없는_값이면_거절한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        """id 만 붙여 아무 숫자에 1등급을 달 수 없다 — 등급은 사람이 매기지 않는다."""
        (paper_value,) = _catalog(db, (4.3e10, 1, None))
        edited = _save(
            client,
            admin_headers,
            material,
            _row(points=[{"value": 5.0e10}], catalog_value_ids=[str(paper_value.id)]),
        )
        assert edited.status_code == 422
        assert edited.json()["error"]["code"] == "MNX-MATERIALS-0048"
        gone = _save(
            client,
            admin_headers,
            material,
            _row(catalog_value_ids=["00000000-0000-0000-0000-000000000000"]),
        )
        assert gone.status_code == 422
        assert gone.json()["error"]["code"] == "MNX-MATERIALS-0047"

    def test_그대로_되보내면_이어받고_값을_고치면_출처의_등급으로(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        (paper_value,) = _catalog(db, (4.3e10, 1, None))
        _stored(
            _save(
                client, admin_headers, material, _row(catalog_value_ids=[str(paper_value.id)])
            )
        )
        # 화면 · MCP 는 다른 항목을 고칠 때 이 줄을 id 없이 되보낸다 — 등급이 남아야 한다.
        kept = _stored(_save(client, admin_headers, material, _row(note="비고만 고침")))
        assert kept["quality_tier"] == 1 and kept["catalog"]["tier"] == 1
        # 값을 고치면 받아 온 값이 아니다 — 근거가 풀리고 문헌 3 으로.
        changed = _stored(
            _save(client, admin_headers, material, _row(points=[{"value": 4.4e10}]))
        )
        assert changed["quality_tier"] == 3 and changed["catalog"] is None

    def test_여러_값이면_가장_낮은_등급이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        cold, hot = _catalog(
            db,
            (4.3e10, 1, {"temperature_k": 298.15}),
            (3.1e10, 3, {"temperature_k": 398.15}),
        )
        row = _stored(
            _save(
                client,
                admin_headers,
                material,
                _row(
                    points=[
                        {"temperature_k": 298.15, "value": 4.3e10},
                        {"temperature_k": 398.15, "value": 3.1e10},
                    ],
                    catalog_value_ids=[str(cold.id), str(hot.id)],
                ),
            )
        )
        assert row["quality_tier"] == 3
        assert sorted(row["catalog"]["value_ids"]) == sorted([str(cold.id), str(hot.id)])

    def test_묶은_중앙값은_묶인_값_중_가장_낮은_등급이다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        material: Material,
    ) -> None:
        """조건이 같은 중복이면 화면은 대표값 자리에서 그 중앙값을 받아 온다."""
        first, *_ = _catalog(db, (4.0e10, 1, None), (4.2e10, 2, None), (4.6e10, 2, None))
        median = 4.2e10
        row = _stored(
            _save(
                client,
                admin_headers,
                material,
                _row(points=[{"value": median}], catalog_value_ids=[str(first.id)]),
            )
        )
        assert row["quality_tier"] == 2


class Test퍼짐:
    def test_카드_표지와_카드_등급과_덱_각주가_받아_온_등급을_안다(self) -> None:
        row = {
            "item": E,
            "points": [{"value_si": 4.3e10}],
            "si_unit": "Pa",
            "source": "literature",
            "reference": "논문",
        }
        stamped = {
            **row,
            declared_approval.CATALOG_KEY: {
                "tier": 1,
                "value_ids": ["x"],
                "digest": declared_approval.digest(row),
            },
        }
        assert declared_approval.origin(stamped) == "declared:literature+catalog1"
        assert declared_approval.tier(stamped) == 1
        # 값이 바뀌면 지문이 갈려 근거가 없는 것 — 출처의 등급으로.
        moved = {**stamped, "points": [{"value_si": 4.4e10}]}
        assert declared_approval.tier(moved) == 3
        assert declared_approval.origin(moved) == "declared:literature"

        mark = "literature+catalog1+approved"
        assert tiers.split_declared(mark) == ("literature", True)
        assert tiers.catalog_tier_in(mark) == 1
        assert tiers.declared_tier("literature", approved=True, catalog_tier=3) == 2
        # 옛 카드의 표지는 그대로 읽힌다.
        assert tiers.split_declared("literature+approved") == ("literature", True)
        assert tiers.catalog_tier_in("literature") is None
        assert "문헌 카탈로그 1등급 값" in _origin("declared:literature+catalog1")
