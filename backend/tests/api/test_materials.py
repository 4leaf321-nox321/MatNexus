"""재료·시료·시편 API.

지키려는 것:
  - 이름은 서버가 만든다 — 미리보기와 실제 등록이 같은 값을 준다
  - 저장은 SI, 주고받는 것은 사람 단위 (왕복해도 값이 변하지 않는다)
  - 모르는 단위는 조용히 통과하지 않는다
  - 재료 이름이 바뀌면 하위 이름이 따라온다 (기존 앱에서는 불가능했다)
  - 하위가 남아 있으면 지우지 못한다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
}


def _create_material(
    client: TestClient, headers: dict[str, str], **overrides: object
) -> dict[str, Any]:
    response = client.post("/api/materials", json={**SECC, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


class TestNaming:
    def test_이름을_값에서_조합한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        assert material["record_name"] == "SECC_MDOI_1.0"

    def test_미리보기와_실제_이름이_같다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """화면이 이름 규칙을 다시 구현하면 두 구현이 갈라진다.

        기존 앱은 화면(DOM)이 이름을 만들어서, 서버·배치에서 같은 이름을 만들
        방법 자체가 없었다.
        """
        preview = client.post(
            "/api/materials/preview-name",
            json={"grade": "SECC", "details": "MDOI", "spec_thickness": 1.0},
            headers=admin_headers,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["taken"] is False

        material = _create_material(client, admin_headers)
        assert material["record_name"] == preview.json()["record_name"]

        again = client.post(
            "/api/materials/preview-name",
            json={"grade": "SECC", "details": "MDOI", "spec_thickness": 1.0},
            headers=admin_headers,
        )
        assert again.json()["taken"] is True  # 등록 버튼을 누르기 전에 알려 준다

    def test_빈_칸도_자리를_지킨다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """기존 앱은 빈 값을 걸러내 칸이 사라졌다."""
        material = _create_material(client, admin_headers, details=None)
        assert material["record_name"] == "SECC_-_1.0"

    def test_같은_이름은_거절하되_이유를_알려준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _create_material(client, admin_headers)
        response = client.post("/api/materials", json=SECC, headers=admin_headers)
        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "MNX-MATERIALS-0004"
        assert "SECC_MDOI_1.0" in body["message"]


class TestUnits:
    def test_mm_로_넣고_mm_로_받는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers, spec_thickness=0.45)
        assert material["spec_thickness"] == 0.45
        assert material["spec_thickness_unit"] == "mm"

        stored = db.scalar(select(Material).where(Material.id == material["id"]))
        assert stored is not None
        assert stored.spec_thickness_m == 0.00045  # 저장은 SI
        assert stored.input_units == {"spec_thickness": "mm"}

    def test_모르는_단위는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """계수 1로 조용히 통과시키면 잘못된 값이 SI 인 척 저장된다."""
        response = client.post(
            "/api/materials",
            json={**SECC, "spec_thickness_unit": "inch"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-MATERIALS-0005"


class TestHierarchy:
    def test_계층_이름이_이어진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)

        first = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "L240612"},
            headers=admin_headers,
        )
        assert first.status_code == 201, first.text
        assert first.json()["record_name"] == "SECC_MDOI_1.0__01"
        assert first.json()["lot_no"] == "L240612"  # 로트는 속성이지 이름이 아니다

        second = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        )
        assert second.json()["record_name"] == "SECC_MDOI_1.0__02"

        specimen = client.post(
            f"/api/samples/{first.json()['id']}/specimens",
            json={"orientation": "MD", "thickness": 1.02, "width": 20.0},
            headers=admin_headers,
        )
        assert specimen.status_code == 201, specimen.text
        assert specimen.json()["record_name"] == "SECC_MDOI_1.0__01__MD_01"
        assert specimen.json()["thickness"] == 1.02

    def test_방향별로_따로_채번한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()

        names = []
        for orientation in ("MD", "MD", "TD"):
            response = client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": orientation},
                headers=admin_headers,
            )
            names.append(response.json()["record_name"])

        assert names == [
            "SECC_MDOI_1.0__01__MD_01",
            "SECC_MDOI_1.0__01__MD_02",
            "SECC_MDOI_1.0__01__TD_01",
        ]


class TestRename:
    def test_재료_이름이_바뀌면_하위가_따라온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """ADR 0004 의 핵심 성질.

        기존 앱은 이름이 곧 참조 키라 이것을 할 수 없었다 — Grade 오타를 고치면
        하위 시험과의 계보가 끊어졌다. 여기서는 참조가 UUID 라 이름을 다시
        계산해 덮으면 그만이다.
        """
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()

        renamed = client.patch(
            f"/api/materials/{material['id']}", json={"grade": "SGCC"}, headers=admin_headers
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["record_name"] == "SGCC_MDOI_1.0"

        moved_sample = client.get(f"/api/samples/{sample['id']}", headers=admin_headers)
        assert moved_sample.json()["record_name"] == "SGCC_MDOI_1.0__01"

        moved_specimen = client.get(f"/api/specimens/{specimen['id']}", headers=admin_headers)
        assert moved_specimen.json()["record_name"] == "SGCC_MDOI_1.0__01__MD_01"


class TestDeletion:
    def test_하위가_남아_있으면_지우지_못한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        client.post(f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers)

        response = client.delete(f"/api/materials/{material['id']}", headers=admin_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MNX-MATERIALS-0006"

    def test_비어_있으면_지워지고_목록에서_사라진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        assert (
            client.delete(
                f"/api/materials/{material['id']}", headers=admin_headers
            ).status_code
            == 204
        )

        listing = client.get("/api/materials", headers=admin_headers)
        assert listing.json()["total"] == 0
        assert (
            client.get(f"/api/materials/{material['id']}", headers=admin_headers).status_code
            == 404
        )


class TestListing:
    def test_상한을_서버가_강제한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """`?limit=1000` 을 그대로 믿으면 서버가 죽는다."""
        _create_material(client, admin_headers)
        response = client.get("/api/materials?limit=1000", headers=admin_headers)
        assert response.status_code == 200, response.text
        assert response.json()["limit"] == 200  # MAX_LIMIT

    def test_이름과_별칭으로_찾는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _create_material(client, admin_headers, alias="도어 이너 강판")
        _create_material(client, admin_headers, grade="AL5052", details=None)

        by_name = client.get("/api/materials?q=SECC", headers=admin_headers).json()
        assert by_name["total"] == 1

        by_alias = client.get("/api/materials?q=도어", headers=admin_headers).json()
        assert by_alias["total"] == 1
