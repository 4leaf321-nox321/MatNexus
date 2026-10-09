"""피로 — 표로 넣은 시험들이 **요약값 구성원**으로 묶여 S-N 카드까지 간다.

곡선 파일이 없는 첫 시험 종류다. 「표로 시험 입력」 이 조건(응력 진폭·응력비)과
요약값(파단 수명·런아웃)을 시험마다 남기고, 묶음이 `from: summary` 선언으로 그것을
모은다 — 파이썬 수집기도, 채택 결과도 없이.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

A, B = 1000e6, -0.1
HEADER = "시편\t방향\t응력 진폭 (MPa)\t응력비 R\tcycles_to_failure\trunout"


def _rows() -> list[str]:
    lines = [HEADER]
    for index, stress_mpa in enumerate((600, 500, 420, 350, 300, 260), start=1):
        cycles = (stress_mpa * 1e6 / A) ** (1.0 / B)
        lines.append(f"{index}\tNA\t{stress_mpa}\t-1\t{cycles:.0f}\tno")
    lines.append("7\tNA\t240\t-1\t10000000\tyes")
    return lines


@pytest.fixture
def imported(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SM490", "spec_thickness": 3.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    made = client.post(
        "/api/test-runs/import",
        json={
            "sample_id": sample["id"],
            "test_type": "fatigue",
            "values": _rows(),
            "create_missing": True,
        },
        headers=admin_headers,
    )
    assert made.status_code == 200, made.text
    items = made.json()["items"]
    assert len(items) == 7 and all(one["status"] == "new" for one in items), items
    runs = client.get(
        "/api/test-runs", params={"material_id": material["id"]}, headers=admin_headers
    ).json()["items"]
    assert len(runs) == 7
    return {"material_id": material["id"], "run_ids": [run["id"] for run in runs]}


def test_표로_넣은_피로_시험이_S_N_묶음과_카드가_된다(
    client: TestClient, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    # ① 묶음 목록이 피로에 S-N 을 주고, 구성원 조건이 「요약값」 이라고 말한다.
    kinds = client.get("/api/groups/kinds?applies_to=fatigue", headers=admin_headers).json()
    found = next(one for one in kinds if one["id"] == "fatigue.sn_curve")
    assert found["needs"] == "summary"
    assert found["makes_card"] is True

    # ② 묶는다 — 채택 결과 없이, 조건과 요약값만으로. 런아웃(yes)은 빠진다.
    made = client.post(
        "/api/groups",
        json={"plugin_id": "fatigue.sn_curve", "run_ids": imported["run_ids"]},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["values"]["basquin_a"] == pytest.approx(A, rel=1e-3)
    assert body["values"]["basquin_b"] == pytest.approx(B, rel=1e-3)
    assert body["values"]["point_count"] == 6
    assert body["values"]["runout_count"] == 1
    assert len(body["used"]) == 6
    assert any("런아웃" in one for one in body["warnings"])

    # ③ 카드 — 공용 길. 탄성계수는 없으니 탄성 블록은 비고, S-N 블록이 실린다.
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": body["id"], "label": "SM490 S-N"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    blocks = card.json()["blocks"]
    assert "sn_curve" in blocks
    assert len(blocks["sn_curve"]["rows"]) == 7
    assert blocks["sn_curve"]["values"]["strength_at_1e6"] == pytest.approx(
        A * 1e6**B, rel=1e-3
    )


def test_재료에_적어_둔_인장강도가_S_N_카드에_실리고_OptiStruct_Nastran_이_열린다(
    client: TestClient, db: Session, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    """MATFAT · MATFTG 는 인장강도가 필수인데 피로 시험은 그 값을 안 준다(2026-10-08).

    S-N 블록의 칸이 물성 키를 들고, 카드를 저장할 때 **재료에 적어 둔 값**이 빈 칸을 채운다
    (`shared/declared_slots`). 기본 항목 「인장강도」 는 씨앗 연결로 그 키에 이어진다.
    """
    from app.modules.catalog.links import ensure_builtin_property_links
    from app.modules.catalog.models import CatalogDefinition
    from app.modules.vocabulary.definitions import ensure_builtin_property_items

    ensure_builtin_property_items(db)
    db.add(
        CatalogDefinition(
            key="mechanical.tensile_strength",
            domain="mechanical",
            name="Tensile strength",
            value_type="numeric",
            si_unit="Pa",
        )
    )
    db.commit()
    ensure_builtin_property_links(db)
    db.commit()

    stated = client.patch(
        f"/api/materials/{imported['material_id']}",
        json={
            "declared_properties": [
                {
                    "item": "인장강도",
                    "points": [{"value": 680}],
                    "input_unit": "MPa",
                    "source": "standard",
                    "reference": "KS D 3503",
                }
            ]
        },
        headers=admin_headers,
    )
    assert stated.status_code == 200, stated.text

    group = client.post(
        "/api/groups",
        json={"plugin_id": "fatigue.sn_curve", "run_ids": imported["run_ids"]},
        headers=admin_headers,
    ).json()
    card = client.post(
        "/api/fitting/cards/from-group",
        json={"group_result_id": group["id"], "label": "SM490 S-N"},
        headers=admin_headers,
    )
    assert card.status_code == 201, card.text
    body = card.json()
    values = body["blocks"]["sn_curve"]["values"]
    assert values["tensile_strength"] == pytest.approx(680e6)
    assert values["tensile_strength_source"] == "declared:standard"
    assert {"optistruct_fatigue", "nastran_fatigue"} <= set(body["available_formats"])

    deck = client.get(
        f"/api/fitting/cards/{body['id']}/export?format=optistruct_fatigue",
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "MATFAT*" in deck.text and "6.80000000E+02" in deck.text  # mm·N·tonne 기본


def test_묶음_결과가_물성_지도와_값_검색에_선다(
    client: TestClient, db: Session, admin_headers: dict[str, str], imported: dict[str, Any]
) -> None:
    """Basquin 은 처리 결과가 아니라 **묶음 결과**에 산다 — 전에는 문헌 키를 달아도 물성 지도 ·
    값 검색이 처리 결과만 읽어 안 섰다(2026-10-08). 문헌 σf′ 은 2N 기준이라 A·2^(-b) 로 낸다.
    다시 묶으면 **가장 최근 결과 하나만** 센다."""
    from app.modules.catalog.models import CatalogDefinition

    for key, unit, name in (
        ("mechanical.fatigue_strength_exponent", "1", "Fatigue strength exponent"),
        ("mechanical.fatigue_strength_coefficient", "Pa", "Fatigue strength coefficient"),
    ):
        db.add(
            CatalogDefinition(
                key=key, domain="mechanical", name=name, value_type="numeric", si_unit=unit
            )
        )
    db.commit()
    for options in ({"exclude_runouts": False}, {}):  # 둘째(런아웃 뺀 것)가 최신
        made = client.post(
            "/api/groups",
            json={
                "plugin_id": "fatigue.sn_curve",
                "run_ids": imported["run_ids"],
                "options": options,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
    latest = made.json()
    assert latest["values"]["fatigue_strength_coefficient"] == pytest.approx(
        A * 2.0 ** (-B), rel=1e-3
    )

    coverage = client.get(
        f"/api/materials/{imported['material_id']}/property-coverage", headers=admin_headers
    ).json()
    rows = {row["key"]: row for row in coverage["properties"]}
    exponent = [one for one in rows["mechanical.fatigue_strength_exponent"]["entries"]]
    assert len(exponent) == 1, exponent  # 옛 묶음은 안 센다
    assert exponent[0]["value_si"] == pytest.approx(B, rel=1e-3)
    assert exponent[0]["ref_kind"] == "group_result"
    sigma = rows["mechanical.fatigue_strength_coefficient"]["entries"][0]
    assert sigma["value_si"] == pytest.approx(A * 2.0 ** (-B), rel=1e-3)

    found = client.get(
        "/api/catalog/properties/search",
        params={
            "q": "mechanical.fatigue_strength_exponent",
            "unit": "1",
            "min": -0.2,
            "max": -0.05,
        },
        headers=admin_headers,
    )
    assert found.status_code == 200, found.text
    hits = [one for one in found.json()["hits"] if one["world"] == "measured"]
    assert [one["material_id"] for one in hits] == [imported["material_id"]]
    assert hits[0]["value_si"] == pytest.approx(B, rel=1e-3)

    # **재료 목록의 「물성 값」 거르기**도 같은 규칙으로 묶음 결과를 본다.
    listed = client.get(
        "/api/materials",
        params={
            "value_key": "mechanical.fatigue_strength_exponent",
            "value_unit": "1",
            "value_min": -0.2,
            "value_max": -0.05,
        },
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    assert [one["id"] for one in listed.json()["items"]] == [imported["material_id"]]
