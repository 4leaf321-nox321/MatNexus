"""카드가 빈칸으로 두면 물려받을 값 — `GET /fitting/cards/inherited`.

모달이 「재료에 있으면 비워 두세요」 라고만 하면 사람은 그 값이 무엇인지 모른 채
비운다(2026-09-05). 그래서 카드를 만드는 계산과 **같은 함수**가 미리 말해 준다.
여기서 지키는 것은 하나다 — 이 응답과 실제 카드의 값·출처가 갈리면 안 된다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient


def _material(client: TestClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"INH-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "density_unit": "kg/m3",
            **extra,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    created: dict[str, Any] = made.json()
    return created


def _inherited(
    client: TestClient, headers: dict[str, str], material_id: str
) -> dict[str, Any]:
    body = client.get(
        f"/api/fitting/cards/inherited?material_id={material_id}", headers=headers
    )
    assert body.status_code == 200, body.text
    return {row["key"]: row for row in body.json()}


class TestInherited:
    def test_재료_값을_출처와_함께_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers, poisson_ratio=0.29, density=7850)
        found = _inherited(client, admin_headers, material["id"])
        assert found["poisson_ratio"]["value"] == 0.29
        assert found["poisson_ratio"]["source"] == "material"
        assert found["density"]["value"] == 7850
        assert found["density"]["source"] == "material"
        assert found["density"]["detail"]

    def test_시료_실측이_재료_공칭을_이긴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """로트마다 다를 수 있는 값이라, 잰 것이 있으면 그것이다."""
        material = _material(client, admin_headers, density=7850)
        made = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "L1", "density": 7900, "density_unit": "kg/m3"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        found = _inherited(client, admin_headers, material["id"])
        assert found["density"]["value"] == 7900
        assert found["density"]["source"] == "sample"

    def test_시료마다_다르면_말없이_고르지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers, density=7850)
        for lot, density in (("L1", 7900), ("L2", 7800)):
            made = client.post(
                f"/api/materials/{material['id']}/samples",
                json={"lot_no": lot, "density": density, "density_unit": "kg/m3"},
                headers=admin_headers,
            )
            assert made.status_code == 201, made.text
        found = _inherited(client, admin_headers, material["id"])
        assert found["density"]["value"] is None
        assert found["density"]["source"] == "conflict"
        assert "직접" in found["density"]["detail"]

    def test_없으면_왜_없는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers)
        found = _inherited(client, admin_headers, material["id"])
        assert found["poisson_ratio"]["value"] is None
        assert found["poisson_ratio"]["source"] == "missing"
        assert found["density"]["source"] == "missing"

    def test_카드가_실제로_받는_값과_같다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**미리 말한 값과 실린 값이 갈리면 화면을 믿을 근거가 없다.**"""
        material = _material(client, admin_headers, poisson_ratio=0.29, density=7850)
        client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 205}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "예시",
                    }
                ]
            },
            headers=admin_headers,
        )
        said = _inherited(client, admin_headers, material["id"])
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "기본"},
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        elastic = card.json()["blocks"]["elastic"]["values"]
        assert elastic["poisson_ratio"] == said["poisson_ratio"]["value"]
        assert elastic["poisson_ratio_source"] == said["poisson_ratio"]["source"]
        assert elastic["density"] == said["density"]["value"]
        assert elastic["density_source"] == said["density"]["source"]
