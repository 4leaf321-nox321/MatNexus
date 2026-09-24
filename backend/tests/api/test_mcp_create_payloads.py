"""MCP 의 만들기 도구가 보내는 **그 모양 그대로** API 가 받는가.

`create_material` · `create_sample` · `create_specimen` 은 인자 이름에 단위를
박아 두고(`spec_thickness_mm` · `density_kg_m3` · `thickness_mm`) 서버에는 값과
단위를 함께 보낸다. 화면과 다른 단위로 보내는 자리라, 서버가 그 단위 문자열을
모르면 **만들기가 통째로 실패한다** — 그런데 MCP 로 불러 보기 전에는 안 드러난다.

여기서 지키는 것은 그 계약이다: 밀도는 `kg/m3` 로, 길이는 `mm` 로 보내면
받아 주고, 저장은 SI 로 된다.

`mcp_server` 자체는 이 스위트가 부를 수 없다(mcp SDK 가 backend 가상환경에
없다). 그래서 **도구가 만드는 본문을 여기 그대로 적고**, 어긋나면 이 시험이
물게 한다. 판단 쪽은 `tests/unit/test_mcp_term_gate.py` 가 본다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

#: `create_material` 이 만드는 본문(ADR 0032 문을 이미 지난 값들).
MATERIAL: dict[str, Any] = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": None,
    "spec_thickness": 1.2,
    "spec_thickness_unit": "mm",
    "alias": None,
    "note": None,
    "workspace_slug": None,
}

#: `create_sample` 이 만드는 본문.
SAMPLE: dict[str, Any] = {
    "lot_no": "L-2026-09",
    "alias": None,
    "manufacturer": None,
    "distributor": None,
    "primary_vendor": None,
    "sales_type": None,
    "production_date": "2026-09-01",
    "density": 7850.0,
    "density_unit": "kg/m3",
    "note": None,
}

#: `create_specimen` 이 만드는 본문.
SPECIMEN: dict[str, Any] = {
    "orientation": "MD",
    "standard": None,
    "thickness": 1.2,
    "width": 12.5,
    "gauge_length": 50.0,
    "length_unit": "mm",
    "note": None,
}


def test_재료_시료_시편을_그_본문으로_만든다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    material = client.post("/api/materials", json=MATERIAL, headers=admin_headers)
    assert material.status_code == 201, material.text
    material_id = material.json()["id"]

    sample = client.post(
        f"/api/materials/{material_id}/samples", json=SAMPLE, headers=admin_headers
    )
    assert sample.status_code == 201, sample.text
    # **응답은 SI(kg/m³)다**(2026-09-24). 도구가 `kg/m3` 을 적어 보낸 7850 이 그대로 돌아와야
    # 한다 — 7.85e-9 가 오면 서버가 단위를 무시하고 화면 단위로 읽은 것이다(1e12 배, 밀도는
    # 응력을 나누는 데 쓰이지 않아 한참 뒤에야 드러난다).
    assert sample.json()["density"] == pytest.approx(7850.0)
    assert sample.json()["density_unit"] == "kg/m3"

    specimen = client.post(
        f"/api/samples/{sample.json()['id']}/specimens",
        json=SPECIMEN,
        headers=admin_headers,
    )
    assert specimen.status_code == 201, specimen.text
    made = specimen.json()
    assert made["orientation"] == "MD"
    # 길이의 화면 단위도 mm 라 보낸 값이 그대로 돌아온다 — 여기서 어긋나면
    # `length_unit` 이 안 읽힌 것이다.
    assert abs(made["thickness"] - 1.2) < 1e-9
    assert abs(made["gauge_length"] - 50.0) < 1e-9


def test_미리보기는_이름과_닮은_이름을_준다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """`create_material(dry_run=True)` 가 사람에게 보여 주는 것. **이름은 서버가
    짓는다** — 여기서 화면·MCP 가 각자 조립하면 세 이름이 갈라진다."""
    made = client.post("/api/materials", json=MATERIAL, headers=admin_headers)
    assert made.status_code == 201, made.text

    preview = client.post(
        "/api/materials/preview-name",
        json={
            "grade": "SECC",
            "details": None,
            "spec_thickness": 1.2,
            "spec_thickness_unit": "mm",
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["record_name"] == made.json()["record_name"]
    # 같은 이름이 이미 있다 — 도구는 이것을 「그 재료를 쓰세요」 로 옮긴다.
    assert body["taken"] is True


def test_부서를_지정한_미리보기도_같은_길로_간다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """부서는 **쿼리**로 간다(본문이 아니다). MCP 는 경로에 붙여 보내므로, 그
    자리가 바뀌면 조용히 남의 부서 이름과 대조하게 된다."""
    got = client.post(
        "/api/materials/preview-name?workspace_slug=metal",
        json={"grade": "SECC", "spec_thickness": 1.2, "spec_thickness_unit": "mm"},
        headers=admin_headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["taken"] is False
