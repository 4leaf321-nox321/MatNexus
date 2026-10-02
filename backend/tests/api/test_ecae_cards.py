"""ECAE · 광학 — **적어 둔 주파수 · 파장별 값이 카드의 표가 되고, 형식이 정한 단위로 나간다**
(2026-10-02, ADR 0052).

    적기      비유전율 · 유전손실을 1 MHz · 1 GHz · 10 GHz 에, 굴절률을 파장 넷에
    카드      전기 · 광학 블록을 고르면 값 하나와 **표**가 함께 앉는다(전에는 첫 점 하나뿐)
    내보내기  AEDT 는 mm·N·tonne 을 골라도 SI 로, 파일 이름도 `_si` — 내용과 이름이 같은 계
    목록      형식 목록이 「단위가 정해진 형식」 을 미리 말한다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.vocabulary.definitions import (
    ensure_builtin_axis_fields,
    ensure_builtin_property_items,
    ensure_builtin_vocabularies,
)

#: 카드 칸이 드는 문헌 키 — 연결(`property_links`)은 문헌 정의가 있어야 선다.
KEYS = {
    "electrical.dielectric_constant": "유전율",
    "electrical.dissipation_factor": "유전손실",
    "electrical.resistivity_volume": "체적저항률",
    "optical.refractive_index": "굴절률",
    "optical.extinction_coefficient": "소광계수",
}
UNITS = {"electrical.resistivity_volume": "ohm.m"}


@pytest.fixture(autouse=True)
def _seeded(db: Session) -> None:
    """운영은 배포가 심는다(`scripts/refresh_builtins.py`) — 항목 · 축 · 문헌 정의 · 연결."""
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    ensure_builtin_property_items(db)
    for key, name in KEYS.items():
        db.add(
            CatalogDefinition(
                key=key,
                domain=key.split(".")[0],
                name=name,
                value_type="numeric",
                si_unit=UNITS.get(key, "1"),
            )
        )
    db.flush()
    ensure_builtin_property_links(db)
    db.commit()


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _points(axis: str, pairs: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"value": value, axis: at} for at, value in pairs]


def _material(client: TestClient, headers: dict[str, str]) -> str:
    made = _ok(
        client.post(
            "/api/materials",
            json={"family": "Polymer", "category": "Laminate", "grade": "TU-862"},
            headers=headers,
        )
    )
    declared = [
        {
            "item": "비유전율",
            "points": _points("frequency_hz", [(1e6, 4.2), (1e9, 4.0), (1e10, 3.9)]),
            "source": "datasheet",
            "reference": "TU-862 데이터시트",
        },
        {
            "item": "유전손실계수(Df)",
            "points": _points("frequency_hz", [(1e6, 0.015), (1e9, 0.018), (1e10, 0.02)]),
            "source": "datasheet",
            "reference": "TU-862 데이터시트",
        },
        {
            "item": "체적저항률",
            "points": [{"value": 1e14, "temperature_k": 296.15}],
            "input_unit": "ohm.m",
            "source": "datasheet",
            "reference": "TU-862 데이터시트",
        },
        {
            "item": "굴절률",
            "points": _points(
                "wavelength_m",
                [
                    (4.861e-7, 1.5224),
                    (5.876e-7, 1.5168),
                    (6.563e-7, 1.5143),
                    (8.521e-7, 1.5098),
                ],
            ),
            "source": "literature",
            "reference": "핸드북",
        },
        {
            "item": "소광계수",
            "points": _points("wavelength_m", [(5.876e-7, 1e-8), (8.521e-7, 2e-8)]),
            "source": "literature",
            "reference": "핸드북",
        },
    ]
    _ok(
        client.patch(
            f"/api/materials/{made['id']}",
            json={"declared_properties": declared},
            headers=headers,
        ),
        200,
    )
    return str(made["id"])


def _card(client: TestClient, headers: dict[str, str], material_id: str) -> Any:
    return _ok(
        client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": material_id,
                "label": "TU-862 ECAE",
                "block_keys": ["electrical", "optical"],
            },
            headers=headers,
        )
    )


def test_주파수_파장별_값이_카드의_표가_된다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    card = _card(client, admin_headers, _material(client, admin_headers))

    electrical = card["blocks"]["electrical"]
    # 값 하나는 가장 낮은 주파수의 것 — 어느 주파수인지 함께 남는다.
    assert electrical["values"]["relative_permittivity"] == pytest.approx(4.2)
    assert electrical["values"]["relative_permittivity_frequency_hz"] == pytest.approx(1e6)
    assert electrical["values"]["resistivity_temperature_k"] == pytest.approx(296.15)
    assert electrical["values"]["relative_permittivity_source"] == "declared:datasheet"
    # **표가 함께 앉는다** — 전에는 1 MHz 의 값 하나만 실려 분산이 통째로 빠졌다.
    assert electrical["rows"] == [
        {"frequency": 1e6, "relative_permittivity": 4.2, "loss_tangent": 0.015},
        {"frequency": 1e9, "relative_permittivity": 4.0, "loss_tangent": 0.018},
        {"frequency": 1e10, "relative_permittivity": 3.9, "loss_tangent": 0.02},
    ]
    optical = card["blocks"]["optical"]
    # 파장 합집합 — 소광계수가 없는 파장은 칸을 비운다(0 으로 채우면 흡수 없는 재료가 된다).
    assert [row["wavelength"] for row in optical["rows"]] == pytest.approx(
        [4.861e-7, 5.876e-7, 6.563e-7, 8.521e-7]
    )
    assert "extinction_coefficient" not in optical["rows"][0]
    assert optical["rows"][1]["extinction_coefficient"] == pytest.approx(1e-8)
    # 낼 수 있는 형식에 전자기 · 광학 형식이 선다.
    assert {"aedt", "cst", "ansys_electric", "zemax_agf", "codev_prv", "nk_table"} <= set(
        card["available_formats"]
    )


def test_AEDT_는_고른_계와_상관없이_SI_로_나가고_이름도_그렇다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    card = _card(client, admin_headers, _material(client, admin_headers))

    got = client.get(
        f"/api/fitting/cards/{card['id']}/export",
        params={"format": "aedt", "units": "mm_n_tonne"},
        headers=admin_headers,
    )

    assert got.status_code == 200, got.text
    assert "_si.amat" in got.headers["content-disposition"]
    assert "permittivity='pwl($MNX" in got.text
    assert "conductivity='1e-14'" in got.text
    # 덱 머리(Notes)에 출처와 주파수가 실린다 — 1 MHz 의 Dk 인지 덱만 보고 안다.
    assert "비유전율(Dk): 사람이 적은 값" in got.text
    assert "@ 1 MHz" in got.text


def test_덱_검사도_형식이_정한_계로_대조한다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    card = _card(client, admin_headers, _material(client, admin_headers))

    checked = _ok(
        client.post(
            f"/api/fitting/cards/{card['id']}/export/check",
            json={"format": "nk_table", "units": "mm_n_tonne"},
            headers=admin_headers,
        ),
        200,
    )

    assert checked["units"] == "si"
    assert checked["filename"].endswith("_nk_si.txt")


def test_형식_목록이_단위가_정해진_형식을_미리_말한다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    listed = {
        one["key"]: one
        for one in _ok(client.get("/api/fitting/formats", headers=admin_headers), 200)
    }

    assert listed["aedt"]["fixed_units"] == "si"
    assert listed["zemax_agf"]["fixed_units"] == "si"
    assert listed["abaqus"]["fixed_units"] is None
