"""재료·시료·시편 API.

지키려는 것:
  - 이름은 서버가 만든다 — 미리보기와 실제 등록이 같은 값을 준다
  - 저장은 SI, 주고받는 것은 사람 단위 (왕복해도 값이 변하지 않는다)
  - 모르는 단위는 조용히 통과하지 않는다
  - 재료 이름이 바뀌면 하위 이름이 따라온다 (기존 앱에서는 불가능했다)
  - 하위가 남아 있으면 지우지 못한다
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.definitions import ensure_builtin_test_types

#: 인장 한 벌 — 밀시트 대조가 「우리가 잰 값」을 어디서 얻는지 보이려고 쓴다.
TENSILE_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
TENSILE_STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
]

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
        # 밀도도 입력 단위를 함께 적는다 — 값만 저장하면 나중에 kg/m³ 인지
        # tonne/mm³ 인지 알 수 없다(기존 앱이 후자로 저장해 겪은 일이다).
        assert stored.input_units == {"spec_thickness": "mm", "density": "tonne/mm3"}

    def test_밀도는_CAE_단위로_주고받고_SI_로_저장한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """화면이 `7.85e-9` 을 받고 DB 는 `7850` 을 갖는다(v1.88.0).

        **바뀐 것은 사람이 보는 단위뿐이다.** 저장까지 솔버 단위로 옮기면 다른
        솔버를 붙일 때 어디서 변환이 일어났는지 추적할 수 없다 — `matcore/units`
        첫 문단이 기존 앱에서 겪은 일로 적어 둔 것이다.
        """
        material = _create_material(client, admin_headers, density=7.85e-9)
        assert material["density_unit"] == "tonne/mm3"
        assert material["density"] == pytest.approx(7.85e-9)

        stored = db.scalar(select(Material).where(Material.id == material["id"]))
        assert stored is not None
        assert stored.density_si == pytest.approx(7850.0)

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

    def test_차원이_다른_단위를_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**실측으로 걸렸다**(2026-08-27, 전체 흐름 점검).

        두께 자리에 `kg` 을 보냈더니 201 로 통과했다. `kg` 은 아는 단위라
        `UnknownUnit` 이 안 나고, 환산이 질량 자리에서 무사히 끝나며, 그 결과가
        `spec_thickness_m` 에 들어간다 — **`1 kg` 이 두께 1 m(=1000 mm) 짜리
        재료**가 됐다. 화면에도 DB 에도 이상한 데가 없어서, 그 재료로 뽑은 덱이
        조용히 틀린다.
        """
        response = client.post(
            "/api/materials",
            json={**SECC, "spec_thickness_unit": "kg"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "MNX-MATERIALS-0028"
        # 무엇이 어긋났는지와 **무엇을 쓰면 되는지**를 함께 말한다.
        assert "mass" in error["message"] and "mm" in error["message"]

    def test_밀도_자리의_길이_단위도_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """두께만 막고 밀도를 놓치면 같은 일이 옆 칸에서 난다."""
        response = client.post(
            "/api/materials",
            json={**SECC, "density_unit": "mm"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-MATERIALS-0028"

    def test_고칠_때도_막는다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        """만들 때만 막으면 PATCH 로 같은 값이 들어간다 — 실제로 그 길이 있다."""
        material = _create_material(client, admin_headers)
        response = client.patch(
            f"/api/materials/{material['id']}",
            json={"spec_thickness": 1.0, "spec_thickness_unit": "kg"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-MATERIALS-0028"

    def test_시편_치수도_같은_검사를_받는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료만 막고 시편을 놓치면 같은 일이 한 층 아래에서 난다.

        시편 치수는 **응력의 분모**다 — 두께·폭이 틀리면 곡선 전체가 틀린 배로
        나오고, 그 곡선이 카드가 되어 솔버까지 간다.
        """
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        response = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD", "thickness": 1.0, "length_unit": "kg"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-MATERIALS-0028"


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

    def test_접힌_줄이_시험_상태를_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
    ) -> None:
        """**접힌 줄이 아무것도 말하지 않으면 접는 뜻이 없다.**

        화면이 시료와 시편을 접어 두는데, 상태가 안 보이면 "실패한 게 있나 ·
        채택된 게 몇 건인가" 를 알려고 전부 펼쳐야 한다. 특히 채택 수는 물성
        탭의 n 이 왜 그 수인지를 설명한다(ADR 0007).

        줄마다 물으면 N+1 이므로 목록이 한 번에 세어 준다.
        """

        from app.modules.tests import services as test_services
        from app.modules.tests.definitions import ensure_builtin_test_types
        from app.modules.tests.models import TestRun

        ensure_builtin_test_types(db)
        db.commit()

        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimens = [
            client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": "MD"},
                headers=admin_headers,
            ).json()
            for _ in range(2)
        ]

        tra = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
        runs = [
            client.post(
                "/api/test-runs",
                data={
                    "specimen_id": specimens[0]["id"],
                    "test_type": "tensile",
                    "conditions": "{}",
                },
                files={"file": ("Example.tra", tra.read_bytes())},
                headers=admin_headers,
            ).json()
            for _ in range(2)
        ]
        # 하나는 읽히고 채택까지, 하나는 읽다 실패한 상태로 둔다.
        assert test_services.parse_run(db, uuid.UUID(runs[0]["id"])) == "parsed"
        stored = client.post(
            "/api/processing/results",
            json={
                "test_run_id": runs[0]["id"],
                "steps": [
                    {
                        "plugin": "tensile.engineering",
                        "options": {"gauge_length": 0.05, "area": 12.12e-6},
                    }
                ],
            },
            headers=admin_headers,
        ).json()
        client.post(f"/api/processing/results/{stored['id']}/adopt", headers=admin_headers)
        failed = db.get(TestRun, uuid.UUID(runs[1]["id"]))
        assert failed is not None
        failed.status = "failed"
        db.commit()

        listed = client.get(
            f"/api/samples/{sample['id']}/specimens", headers=admin_headers
        ).json()
        by_name = {item["record_name"]: item for item in listed}
        first = by_name[specimens[0]["record_name"]]
        assert (first["test_run_count"], first["adopted_count"], first["failed_count"]) == (
            2,
            1,
            1,
        )
        second = by_name[specimens[1]["record_name"]]
        assert second["test_run_count"] == 0

        # 시료 줄은 그 시편들을 합쳐서 말한다 — 펼치지 않고도 보여야 한다.
        samples = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        assert (
            samples[0]["test_run_count"],
            samples[0]["adopted_count"],
            samples[0]["failed_count"],
        ) == (2, 1, 1)


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


class Test사슬_삭제:
    """*"재료를 삭제할 때 하위 시료/시편이 있으면 삭제 안 되는 문제가 있다"* —
    실사용에서 나왔다.

    `DELETE /materials/{id}` 가 막는 것은 맞다. 재료 하나를 지우는 뜻으로 누른
    버튼이 시험 200건을 함께 지우면 안 된다. 그런데 그러면 **정리할 방법이 아예
    없다** — 시편을 하나씩, 시료를 하나씩 지워 올라가야 하고, 이관을 다시 돌릴
    때마다 그 일을 한다.
    """

    def tree(
        self, client: TestClient, headers: dict[str, str], specimens: int = 2
    ) -> dict[str, Any]:
        material = _create_material(client, headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=headers
        ).json()
        made = [
            client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": "MD"},
                headers=headers,
            ).json()
            for _ in range(specimens)
        ]
        return {"material": material, "sample": sample, "specimens": made}

    def test_무엇이_사라지는지_먼저_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면이 세지 않게 한다.** 화면이 나름대로 세면 사람이 본 숫자와 실제로
        지워지는 것이 어긋나고, 그러면 그 「예」 는 다른 것에 대한 대답이 된다."""
        tree = self.tree(client, admin_headers, specimens=3)
        plan = client.get(
            f"/api/materials/{tree['material']['id']}/delete-plan", headers=admin_headers
        )
        assert plan.status_code == 200, plan.text
        assert plan.json() == {
            "material_name": tree["material"]["record_name"],
            "samples": 1,
            "specimens": 3,
            "test_runs": 0,
        }

    def test_아래까지_통째로_지운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        tree = self.tree(client, admin_headers)
        material_id = tree["material"]["id"]

        gone = client.post(
            f"/api/materials/{material_id}/delete-cascade",
            json={"include_test_runs": False},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        assert gone.json()["samples"] == 1
        assert gone.json()["specimens"] == 2

        # **셋 다 닿을 수 없어야 한다.** 재료만 사라지고 시편이 남으면 그 시편은
        # 화면 어디에서도 못 보는 채로 이름만 붙들고 있다.
        assert (
            client.get(f"/api/materials/{material_id}", headers=admin_headers).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/samples/{tree['sample']['id']}", headers=admin_headers
            ).status_code
            == 404
        )
        # **DB 로 본다.** `GET /specimens/{id}` 는 부모(시료)가 지워져도 404 라,
        # 시편 행이 그대로 살아 있어도 화면에서는 구별이 안 된다 — 사보타주로
        # 확인했다(시편을 안 지우게 해도 시험이 통과했다).
        db.expire_all()
        for one in tree["specimens"]:
            stored = db.get(Specimen, uuid.UUID(one["id"]))
            assert stored is not None
            assert stored.deleted_at is not None, "시편 행이 안 지워졌다"
        gone_sample = db.get(Sample, uuid.UUID(tree["sample"]["id"]))
        assert gone_sample is not None
        assert gone_sample.deleted_at is not None, "시료 행이 안 지워졌다"

    def test_시험은_따로_허락을_받는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """시료·시편은 이름표에 가깝지만 **시험은 잰 값이다** — 곡선과 처리 결과가
        거기 매달려 있다. 한 칸으로 묶으면 「시료 정리하려다 측정 데이터를
        날렸다」 가 난다."""
        from app.modules.tests.definitions import ensure_builtin_test_types

        ensure_builtin_test_types(db)
        db.commit()

        tree = self.tree(client, admin_headers, specimens=1)
        material_id = tree["material"]["id"]
        tra = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
        run = client.post(
            "/api/test-runs",
            data={
                "specimen_id": tree["specimens"][0]["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": ("Example.tra", tra.read_bytes())},
            headers=admin_headers,
        )
        assert run.status_code == 202, run.text

        plan = client.get(
            f"/api/materials/{material_id}/delete-plan", headers=admin_headers
        ).json()
        assert plan["test_runs"] == 1

        # 안 켜면 막고, **몇 건인지 말한다.**
        blocked = client.post(
            f"/api/materials/{material_id}/delete-cascade",
            json={"include_test_runs": False},
            headers=admin_headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "MNX-MATERIALS-0029"
        assert "1건" in blocked.json()["error"]["message"]

        # 막혔으면 **아무것도 안 지워져 있어야 한다.** 절반만 지워진 트리는
        # 화면에서 닿을 수 없다.
        assert (
            client.get(f"/api/materials/{material_id}", headers=admin_headers).status_code
            == 200
        )

        gone = client.post(
            f"/api/materials/{material_id}/delete-cascade",
            json={"include_test_runs": True},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        assert gone.json()["test_runs"] == 1
        assert (
            client.get(f"/api/test-runs/{run.json()['id']}", headers=admin_headers).status_code
            == 404
        )

    def test_빈_재료도_지워진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**막는 것이 목적이 아니다.** 아무것도 안 달렸으면 그냥 지워진다."""
        material = _create_material(client, admin_headers)
        gone = client.post(
            f"/api/materials/{material['id']}/delete-cascade",
            json={"include_test_runs": False},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        assert gone.json()["samples"] == 0

    def test_남의_부서_것은_못_지운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**새 문이 권한 검사를 우회하면 안 된다.** 통째로 지우는 길일수록 그렇다 —
        하나 뚫리면 사라지는 것이 재료 하나가 아니라 트리 전체다."""
        tree = self.tree(client, admin_headers, specimens=1)

        client.post(
            "/api/workspaces",
            json={"name": "남의 부서", "slug": "other-dept"},
            headers=admin_headers,
        )
        made = client.post(
            "/api/accounts",
            json={
                "email": "other@example.com",
                "display_name": "남",
                "workspace_slug": "other-dept",
                "role": "member",
            },
            headers=admin_headers,
        )
        assert made.status_code in (200, 201), made.text
        token = client.post(
            "/api/auth/login",
            json={"email": "other@example.com", "password": made.json()["temporary_password"]},
        ).json()["access_token"]

        response = client.post(
            f"/api/materials/{tree['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (403, 404), response.text

        # **여기까지는 「안 보인다」 일 뿐이다.** 전역 재료는 누구에게나 보이고
        # 관리자만 고칠 수 있다 — `require_writable` 이 실제로 걸리는 자리는
        # 그쪽이다. 사보타주로 확인했다(권한 검사를 빼도 위 단언은 통과했다).
        stored = db.get(Material, uuid.UUID(tree["material"]["id"]))
        assert stored is not None
        stored.owner_workspace_id = None
        db.commit()

        as_global = client.post(
            f"/api/materials/{tree['material']['id']}/delete-cascade",
            json={"include_test_runs": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert as_global.status_code == 403, as_global.text

        # **막혔으면 그대로 있어야 한다.**
        assert (
            client.get(
                f"/api/materials/{tree['material']['id']}", headers=admin_headers
            ).status_code
            == 200
        )


class Test여럿을_한꺼번에_사슬로:
    """목록 화면에서 고른 것들을 아래까지 통째로.

    상세 화면만 고치면 **목록은 여전히 막다른 길**이다 — 이관을 다시 돌릴 때는
    재료를 여러 개 지운다.
    """

    def tree(
        self, client: TestClient, headers: dict[str, str], grade: str, specimens: int = 2
    ) -> dict[str, Any]:
        material = _create_material(client, headers, grade=grade)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=headers
        ).json()
        for _ in range(specimens):
            client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": "MD"},
                headers=headers,
            )
        return material

    def test_고른_것을_합쳐_센다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**낱개로 안 보여 준다.** 200건을 고른 화면에서 200줄을 읽는 사람은 없다."""
        one = self.tree(client, admin_headers, "AAA", specimens=2)
        two = self.tree(client, admin_headers, "BBB", specimens=3)
        plan = client.post(
            "/api/materials/delete-plan",
            json={"material_ids": [one["id"], two["id"]]},
            headers=admin_headers,
        )
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert (body["materials"], body["samples"], body["specimens"]) == (2, 2, 5)
        assert body["blocked"] == []

    def test_켜면_아래까지_지운다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        one = self.tree(client, admin_headers, "CCC", specimens=2)
        two = self.tree(client, admin_headers, "DDD", specimens=1)
        gone = client.post(
            "/api/materials/delete",
            json={
                "material_ids": [one["id"], two["id"]],
                "cascade": True,
                "include_test_runs": False,
            },
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        body = gone.json()
        assert body["deleted"] == 2
        assert body["blocked"] == []
        # **딸려 간 것을 돌려준다.** 개수가 없으면 화면이 "2건 지웠습니다" 만
        # 말하게 되고, 사람은 시편 셋이 함께 사라진 것을 모른다.
        assert (body["samples"], body["specimens"]) == (2, 3)

        db.expire_all()
        for material in (one, two):
            stored = db.get(Material, uuid.UUID(material["id"]))
            assert stored is not None and stored.deleted_at is not None

    def test_끄면_전과_같다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        """**기본은 안 지우는 쪽이다.** 목록에서 고르고 지우기를 누르는 것이
        갑자기 트리를 날리는 뜻이 되면 안 된다."""
        one = self.tree(client, admin_headers, "EEE", specimens=1)
        gone = client.post(
            "/api/materials/delete",
            json={"material_ids": [one["id"]]},
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        assert gone.json()["deleted"] == 0
        assert "시료" in gone.json()["blocked"][0]["reason"]
        assert gone.json()["samples"] == 0

    def test_시험을_문_것만_막는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**하나 때문에 나머지를 못 지우게 하지 않는다.** 200건 중 하나가 시험을
        물고 있다고 199건을 막으면, 사람은 어느 것이 문제인지 모른 채 다시 고른다."""
        from app.modules.tests.definitions import ensure_builtin_test_types

        ensure_builtin_test_types(db)
        db.commit()

        plain = self.tree(client, admin_headers, "FFF", specimens=1)
        withrun = self.tree(client, admin_headers, "GGG", specimens=1)
        sample = client.get(
            f"/api/materials/{withrun['id']}/samples", headers=admin_headers
        ).json()[0]
        specimen = client.get(
            f"/api/samples/{sample['id']}/specimens", headers=admin_headers
        ).json()[0]
        tra = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
        client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": ("Example.tra", tra.read_bytes())},
            headers=admin_headers,
        )

        gone = client.post(
            "/api/materials/delete",
            json={
                "material_ids": [plain["id"], withrun["id"]],
                "cascade": True,
                "include_test_runs": False,
            },
            headers=admin_headers,
        )
        assert gone.status_code == 200, gone.text
        body = gone.json()
        assert body["deleted"] == 1
        assert len(body["blocked"]) == 1
        assert body["blocked"][0]["name"] == withrun["record_name"]
        assert "시험" in body["blocked"][0]["reason"]

        # 켜면 그것도 지워진다.
        again = client.post(
            "/api/materials/delete",
            json={
                "material_ids": [withrun["id"]],
                "cascade": True,
                "include_test_runs": True,
            },
            headers=admin_headers,
        )
        assert again.json()["deleted"] == 1
        assert again.json()["test_runs"] == 1


class Test방향_바꾸기:
    """*"시편 수정에도 안 보여"* — 실사용에서 나왔다.

    방향은 자를 때 정해지는 값이라 만들 때 정하면 그만인 것 같지만, **잘못 고른
    것을 되돌릴 길이 없었다** — 지우고 다시 만들면 그 시편의 시험이 함께
    사라진다.

    칸 하나를 고치는 일이 아니다. 방향은 **이름과 번호의 일부**다
    (`..._MD_03`, `(sample, orientation, seq_no)` 유니크).
    """

    def tree(self, client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
        material = _create_material(client, headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=headers
        ).json()
        return {"material": material, "sample": sample}

    def add(
        self, client: TestClient, headers: dict[str, str], sample_id: str, orientation: str
    ) -> dict[str, Any]:
        made = client.post(
            f"/api/samples/{sample_id}/specimens",
            json={"orientation": orientation},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        out: dict[str, Any] = made.json()
        return out

    def test_바꾸면_이름이_따라온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        tree = self.tree(client, admin_headers)
        specimen = self.add(client, admin_headers, tree["sample"]["id"], "MD")
        assert specimen["record_name"].endswith("__MD_01")

        changed = client.patch(
            f"/api/specimens/{specimen['id']}",
            json={"orientation": "TD"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["specimen"]["record_name"].endswith("__TD_01")
        # **무슨 일이 일어났는지 말한다.** 방향만 골랐는데 번호까지 달라지는 것은
        # 사람이 예상 못 하는 일이다.
        assert "→" in changed.json()["renamed"]

    def test_번호는_옮겨_가는_방향에서_새로_받는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**03 을 우겨 넣지 않는다.** TD 에 이미 03 이 있을 수 있고, 시편 번호는
        「그 방향에서 몇 번째로 자른 것인가」 이다."""
        tree = self.tree(client, admin_headers)
        sample_id = tree["sample"]["id"]
        for _ in range(3):
            self.add(client, admin_headers, sample_id, "TD")
        mover = self.add(client, admin_headers, sample_id, "MD")
        assert mover["record_name"].endswith("__MD_01")

        changed = client.patch(
            f"/api/specimens/{mover['id']}",
            json={"orientation": "TD"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        # TD 에 01·02·03 이 있으므로 04 를 받는다.
        assert changed.json()["specimen"]["record_name"].endswith("__TD_04")

    def test_시험_이름까지_내려간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**여기서 멈추면 시험만 옛 방향을 달고 있다.** 재료 이름 바꾸기가
        정확히 그 자리에서 한 번 걸렸다."""
        from app.modules.tests.definitions import ensure_builtin_test_types

        ensure_builtin_test_types(db)
        db.commit()

        tree = self.tree(client, admin_headers)
        specimen = self.add(client, admin_headers, tree["sample"]["id"], "MD")
        tra = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
        run = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": ("Example.tra", tra.read_bytes())},
            headers=admin_headers,
        )
        assert run.status_code == 202, run.text
        assert "__MD_01__TEN_01" in run.json()["record_name"]

        changed = client.patch(
            f"/api/specimens/{specimen['id']}",
            json={"orientation": "TD"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert "시험 1건" in changed.json()["renamed"]

        db.expire_all()
        after = client.get(f"/api/test-runs/{run.json()['id']}", headers=admin_headers)
        assert "__TD_01__TEN_01" in after.json()["record_name"]

    def test_모르는_방향은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        tree = self.tree(client, admin_headers)
        specimen = self.add(client, admin_headers, tree["sample"]["id"], "MD")
        response = client.patch(
            f"/api/specimens/{specimen['id']}",
            json={"orientation": "ZZ"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "MD" in response.json()["error"]["message"]

    def test_같은_방향이면_아무것도_안_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**번호를 괜히 올리지 않는다.** 다른 칸을 고치면서 방향을 그대로 보내는
        것은 흔한 일이고, 그때마다 번호가 밀리면 안 된다."""
        tree = self.tree(client, admin_headers)
        specimen = self.add(client, admin_headers, tree["sample"]["id"], "MD")
        changed = client.patch(
            f"/api/specimens/{specimen['id']}",
            json={"orientation": "MD", "note": "메모만"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["specimen"]["record_name"].endswith("__MD_01")
        assert changed.json()["renamed"] is None


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

    def test_보이는_것으로_찾는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**사람은 화면에 보이는 말로 찾는다.**

        이름·별칭·Grade 만 보면 목록에 떡하니 보이는 Family·Category·Details 로
        찾을 때 아무것도 안 나온다. "검색해도 안 나온다" 는 실사용 보고가 여기서
        나왔다 — 검색이 실패했다고 알려 주지도 않으니 재료가 없는 줄 안다.
        """
        _create_material(client, admin_headers)  # SECC / Metal / Steel / MDOI

        for term in ("Metal", "steel", "MDOI"):
            found = client.get(f"/api/materials?q={term}", headers=admin_headers).json()
            assert found["total"] == 1, f"{term!r} 로 못 찾았습니다"

    def test_띄어쓰기로_나눠_찾는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """이름은 `SECC_MDOI_1.0` 인데 사람은 `SECC 1.0` 이라고 친다.

        구분자가 밑줄이라 통째로 비교하면 안 맞는다. 낱말마다 나눠 **모두 들어
        있는가**로 본다 — 한 낱말이라도 없으면 다른 재료다.
        """
        _create_material(client, admin_headers)
        _create_material(client, admin_headers, grade="AL5052", spec_thickness=2.0)

        both = client.get("/api/materials?q=SECC 1.0", headers=admin_headers).json()
        assert both["total"] == 1

        # 순서가 달라도 찾는다 — 사람이 이름 규칙의 순서를 외우고 있지 않다.
        reversed_order = client.get("/api/materials?q=1.0 SECC", headers=admin_headers).json()
        assert reversed_order["total"] == 1

        # 낱말 하나가 안 맞으면 안 나온다.
        none = client.get("/api/materials?q=SECC 2.0", headers=admin_headers).json()
        assert none["total"] == 0


class TestClassifications:
    """무엇으로 거를 수 있는지는 **데이터가 정한다.**

    고정 목록을 화면에 박아 두면 부서가 새 분류를 쓰기 시작한 순간 고를 수
    없게 되고, 그때 사람은 "필터가 고장났다" 가 아니라 "그 재료가 없다" 로 읽는다.
    """

    def test_쓰이고_있는_조합만_센다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _create_material(client, admin_headers, grade="A")
        _create_material(client, admin_headers, grade="B")
        _create_material(client, admin_headers, grade="C", category="Aluminum")
        _create_material(client, admin_headers, grade="D", family="Polymer", category="PP")

        body = client.get("/api/materials/classifications", headers=admin_headers).json()
        found = {(row["family"], row["category"]): row["count"] for row in body}
        assert found[("Metal", "Steel")] == 2
        assert found[("Metal", "Aluminum")] == 1
        assert found[("Polymer", "PP")] == 1

    def test_분류로_거른다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        """**검색어와 다르다.** 검색은 부분 일치라 'Metal' 을 치면 Grade 에 그
        글자가 든 재료까지 걸린다. 분류는 정확히 일치여야 "Metal 인 것만" 이 된다.
        """
        _create_material(client, admin_headers, grade="A")
        _create_material(client, admin_headers, grade="B", family="Polymer", category="PP")

        metal = client.get("/api/materials?family=Metal", headers=admin_headers).json()
        assert metal["total"] == 1
        assert metal["items"][0]["family"] == "Metal"

        polymer = client.get(
            "/api/materials?family=Polymer&category=PP", headers=admin_headers
        ).json()
        assert polymer["total"] == 1

        # 있지도 않은 조합은 0건이다 — 화면이 그런 조합을 못 만들게 하는 이유다.
        crossed = client.get(
            "/api/materials?family=Metal&category=PP", headers=admin_headers
        ).json()
        assert crossed["total"] == 0


class Test기준정보로_읽기:
    """Contract — **목록·검색·집계가 문자열이 아니라 기준정보를 본다**(ADR 0010).

    문자열 컬럼은 아직 있다. 지우기 전에 FK 경로가 같은 답을 내는지 한 릴리스
    지켜보는 것이 이 단계의 목적이고, 이 시험들이 "같은 답" 의 뜻이다.
    """

    def test_없는_값으로_거르면_0건이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**기준정보를 못 찾았을 때가 함정이다.** `family_term_id == None` 으로 두면
        그 축이 비어 있는 재료가 전부 걸린다 — 거르려고 눌렀는데 늘어난다."""
        _create_material(client, admin_headers, grade="A")
        _create_material(client, admin_headers, grade="B", family="Polymer", category="PP")

        found = client.get("/api/materials?family=없는분류", headers=admin_headers).json()
        assert found["total"] == 0, f"없는 분류로 걸렀는데 {found['total']}건이 나왔다"

    def test_기준정보_이름을_고치면_필터도_새_이름을_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """FK 를 읽는다는 것의 뜻이다 — 기준정보 한 행을 고치면 목록·검색·집계가
        전부 따라온다."""
        _create_material(client, admin_headers, grade="A", family="Foam", category="EPP")
        term = client.get(
            "/api/vocabularies/family/terms", params={"q": "Foam"}, headers=admin_headers
        ).json()["items"][0]
        client.patch(
            f"/api/vocabularies/family/terms/{term['id']}",
            json={"value": "발포재"},
            headers=admin_headers,
        )

        renamed = client.get("/api/materials?family=발포재", headers=admin_headers).json()
        assert renamed["total"] == 1
        assert renamed["items"][0]["family"] == "발포재"

        # 집계도 새 이름으로 온다.
        rows = client.get("/api/materials/classifications", headers=admin_headers).json()
        assert ("발포재", "EPP") in {(row["family"], row["category"]) for row in rows}

        # 검색어로도 새 이름이 걸린다.
        searched = client.get("/api/materials?q=발포재", headers=admin_headers).json()
        assert searched["total"] == 1

    def test_낱말마다_AND_가_유지된다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """기준정보를 거치면서 낱말 조건이 OR 로 새면 좁히려고 더 친 것이 넓어진다."""
        _create_material(client, admin_headers, grade="ALPHA", category="Steel")
        _create_material(client, admin_headers, grade="BETA", family="Polymer", category="PP")

        both = client.get("/api/materials?q=Steel ALPHA", headers=admin_headers).json()
        assert both["total"] == 1

        neither = client.get("/api/materials?q=Polymer ALPHA", headers=admin_headers).json()
        assert neither["total"] == 0, "낱말 조건이 OR 로 샜다"


class Test시편규격:
    """**규격은 자를 때 정해진다. 시험할 때가 아니다.**

    전에는 시험 조건에 있었다. 그런데 규격은 게이지 길이·폭을 **정하는 쪽**이고,
    정해지는 값(치수)은 시편에 있었다 — 인과가 반대로 놓여 있었다. 게다가 장비
    파일에 없는 값이라 사람이 넣어야 하는데, 시험마다 넣게 하면 같은 시편의
    시험 두 건에 다른 규격이 적히는 것을 막을 수 없었다.
    """

    def test_시편에_규격을_적고_고친다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        created = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD", "standard": "ASTM E8 subsize"},
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["standard"] == "ASTM E8 subsize"

        changed = client.patch(
            f"/api/specimens/{created.json()['id']}",
            json={"standard": "JIS 5호"},
            headers=admin_headers,
        )
        # 응답이 `{specimen, renamed}` 로 감싸졌다 — 방향을 바꾸면 이름이
        # 다시 매겨지는데, 그 사실을 돌려줄 자리가 필요했다(v1.120.0).
        assert changed.json()["specimen"]["standard"] == "JIS 5호"

    def test_시험_조건에는_더_이상_없다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """두 자리에 있으면 어느 쪽이 맞는지 물어야 한다.

        정의를 남겨 두면 업로드 창에 칸이 계속 뜨고, 같은 값을 두 번 넣게 된다.
        """
        ensure_builtin_test_types(db)
        db.commit()
        types = {
            item["key"]: item
            for item in client.get("/api/test-types", headers=admin_headers).json()
        }
        keys = {field["key"] for field in types["tensile"]["conditions"]}
        assert "specimen_standard" not in keys
        # 시험할 때 정해지는 것들은 그대로 남는다.
        assert {"temperature", "speed_elastic", "sensor_type"} <= keys


class Test선언물성:
    """**시험이 주지 않는 물성을 사람이 적는다.**

    탄성계수는 처리 결과에서만 왔고 열팽창계수·비열·열전도도는 자리가 아예
    없었다 — 그런데 인장시험이 안 주는 값들이다. 시험을 안 한 재료가 대부분인데
    그 재료로는 해석용 카드를 만들 수 없었다.

    항목 목록은 **기준정보가 정한다**(D7). 열해석을 안 하는 부서에 비열 칸이 뜰
    이유가 없고, 코드에 박으면 필요한 항목 하나를 넣으려고 배포를 기다려야 한다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        db.commit()

    @pytest.fixture
    def material(self, client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
        made = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DECL",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        return dict(made.json())

    def test_넣을_수_있는_항목을_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """화면이 이 응답만으로 피커와 단위 칸을 그릴 수 있어야 한다."""
        body = client.get("/api/materials/property-items", headers=admin_headers).json()
        by_item = {row["item"]: row for row in body}
        assert by_item["탄성계수"]["dimension"] == "stress"
        assert by_item["탄성계수"]["si_unit"] == "Pa"
        assert by_item["탄성계수"]["symbol"] == "E"
        assert by_item["비열"]["si_unit"] == "J/(kg.K)"

    def test_적은_단위로_넣고_SI_로_담는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**시험 채널과 같은 규칙이다.** `GPa` 로 적어도 저장은 `Pa` 다."""
        saved = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 206}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "KS D 3512 표 3",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        row = saved.json()["declared_properties"][0]
        assert row["points"][0]["value_si"] == pytest.approx(206e9)
        # **적은 단위를 그대로 돌려준다.** 2.06e11 로 보이면 자기가 적은 값인지
        # 알기 어렵다.
        assert row["input_unit"] == "GPa"
        assert row["reference"] == "KS D 3512 표 3"

    def test_차원이_안_맞으면_막는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**이것이 이 기능의 절반이다.**

        비열 자리에 열전도도를 넣어도 숫자는 그럴듯하다 — 값은 멀쩡한데 뜻이
        다르다. ADR 0013 이 *"밀도 자리에 온도를 넣어도 아무도 모른다"* 고
        적어 둔 구멍이 이 축에서는 막혀 있다.
        """
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "비열",
                        "points": [{"value": 45}],
                        "input_unit": "W/(m.K)",
                        "source": "literature",
                        "reference": "ASM Handbook",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        message = refused.json()["error"]["message"]
        assert "specific_heat" in message and "thermal_conductivity" in message

    def test_출처_없이는_못_넣는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**카드가 자기 근거를 들고 있어야 한다**(ADR 0009·0012). 값만 있고
        어디서 왔는지 모르면 그 값으로 돌린 해석의 근거를 되짚을 수 없다."""
        for missing in ("source", "reference"):
            row = {
                "item": "탄성계수",
                "points": [{"value": 206}],
                "input_unit": "GPa",
                "source": "literature",
                "reference": "KS D 3512",
            }
            row.pop(missing)
            refused = client.patch(
                f"/api/materials/{material['id']}",
                json={"declared_properties": [row]},
                headers=admin_headers,
            )
            assert refused.status_code == 422, missing

    def test_등록_안_된_항목은_거절하고_있는_것을_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """거절만 하면 사람은 무엇을 넣을 수 있는지 모른다."""
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "자기저항",
                        "points": [{"value": 295}],
                        "input_unit": "MPa",
                        "source": "datasheet",
                        "reference": "MTC-2024-0812",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        message = refused.json()["error"]["message"]
        assert "있는 것:" in message and "탄성계수" in message

    def test_다른_층의_항목이면_어디에_적는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**"등록된 항목이 아닙니다" 만 말하면 안 된다.** 기준정보에 뻔히 있는
        이름을 두고 사람이 그것을 또 만들고, 그때부터 같은 물성이 두 항목이 된다.

        항복강도는 로트마다 다르다 — 재료에 적으면 첫 로트의 값이 그 Grade
        전체의 값이 되고, 두 번째 로트가 들어오는 순간 둘 중 하나가 조용히
        진다(ADR 0016)."""
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "항복강도",
                        "points": [{"value": 295}],
                        "input_unit": "MPa",
                        "source": "datasheet",
                        "reference": "MTC-2024-0812",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        message = refused.json()["error"]["message"]
        assert "시료" in message and "로트마다" in message

    def test_같은_항목을_두_번_못_넣는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """두 값이 있으면 **카드가 어느 것을 쓸지 정할 수 없다.** 그 판단을
        여기서 안 하면 나중에 조용히 하나가 이긴다."""
        row = {
            "item": "탄성계수",
            "points": [{"value": 206}],
            "input_unit": "GPa",
            "source": "literature",
            "reference": "A",
        }
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    row,
                    {**row, "points": [{"value": 200}], "reference": "B"},
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert "두 번" in refused.json()["error"]["message"]

    def test_항목_이름으로_정렬해_담는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """넣은 순서대로 두면 **같은 내용의 재료가 서로 다른 순서를 갖고**,
        비교·변경 이력에서 바뀐 것처럼 보인다."""
        saved = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "열팽창계수",
                        "points": [{"value": 1.17e-5}],
                        "input_unit": "1/K",
                        "source": "standard",
                        "reference": "KS",
                    },
                    {
                        "item": "탄성계수",
                        "points": [{"value": 206}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "ASM",
                    },
                ]
            },
            headers=admin_headers,
        ).json()
        assert [row["item"] for row in saved["declared_properties"]] == [
            "열팽창계수",
            "탄성계수",
        ]


class Test밀시트값:
    """**밀시트가 주는 것은 로트마다 다르다**(ADR 0016, EN 10204 3.1).

        문헌·규격   Grade 가 같으면 같다   E · ν · α · Cp · k   → 재료
        밀시트      로트마다 다르다        항복강도 · 인장강도    → 시료

    앞엣것을 재료에 적는 것이 v1.71.0~v1.72.0 이었고, 여기는 뒤엣것이다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        # 인장 한 벌을 실제로 태워야 「우리가 잰 값」이 생긴다.
        ensure_builtin_test_types(db)
        db.commit()

    @pytest.fixture
    def material(self, client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
        made: dict[str, Any] = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "MILL",
                "details": "MDOI",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        ).json()
        return made

    @pytest.fixture
    def sample(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> dict[str, Any]:
        made = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "L-2024-0812"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        created: dict[str, Any] = made.json()
        return created

    MILL: ClassVar[dict[str, Any]] = {
        "item": "항복강도",
        "points": [{"value": 295}],
        "input_unit": "MPa",
        "source": "datasheet",
        "reference": "MTC-2024-0812",
    }

    def test_시료에_적는다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        saved = client.patch(
            f"/api/samples/{sample['id']}",
            json={"declared_properties": [self.MILL]},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        row = saved.json()["declared_properties"][0]
        assert row["points"][0]["value_si"] == pytest.approx(295e6)
        # 적은 단위를 그대로 돌려준다 — 2.95e8 로 보이면 자기가 적은 값인지 모른다.
        assert row["points"][0]["value"] == pytest.approx(295)
        assert row["input_unit"] == "MPa"

    def test_재료_물성은_시료에_못_적는다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        """**같은 값을 로트 수만큼 적게 하면 그중 하나만 고쳐진다.**"""
        refused = client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 206}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "ASM",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        message = refused.json()["error"]["message"]
        assert "재료" in message and "Grade" in message

    def test_피커가_층으로_갈린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면이 층을 판정하지 않는다.** 목록을 서버가 갈라 준다."""
        at_sample = client.get(
            "/api/materials/property-items?level=시료", headers=admin_headers
        ).json()
        names = {row["item"] for row in at_sample}
        assert "항복강도" in names and "인장강도" in names
        assert "탄성계수" not in names

        at_material = client.get(
            "/api/materials/property-items?level=재료", headers=admin_headers
        ).json()
        assert "탄성계수" in {row["item"] for row in at_material}

        # 안 주면 전부. 이미 저장된 값을 읽어 보여 줄 때는 층으로 거르면 안 된다.
        every = client.get("/api/materials/property-items", headers=admin_headers).json()
        assert len(every) > len(at_sample)

    def test_잰_적이_없으면_없다고_말한다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        """**조용히 빼지 않는다.** 줄이 없으면 사람은 적은 값이 사라진 줄 안다."""
        client.patch(
            f"/api/samples/{sample['id']}",
            json={"declared_properties": [self.MILL]},
            headers=admin_headers,
        )
        found = client.get(f"/api/samples/{sample['id']}/mill-check", headers=admin_headers)
        assert found.status_code == 200, found.text
        row = found.json()["rows"][0]
        assert row["declared"] == pytest.approx(295e6)
        assert row["measured"] is None
        assert row["measured_count"] == 0
        assert row["difference"] is None
        assert "채택된 처리 결과가 없습니다" in row["note"]

    def test_잰_값과_나란히_놓는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        sample: dict[str, Any],
    ) -> None:
        """**이것이 시료 층 선언 물성의 쓸모다.** 값을 적어 두기만 하면 기록으로
        끝나는데, 같은 물성을 우리 처리 결과가 낸다 — 밀시트가 말한 인장강도와
        우리 인장시험이 낸 인장강도를 여기서 견준다."""
        from app.modules.tests import services as test_services

        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()
        made = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", TENSILE_FILE.read_bytes())},
            headers=admin_headers,
        )
        # 202 다 — 업로드는 받아 두고 워커가 판다. 시험에서는 직접 태운다.
        assert made.status_code == 202, made.text
        run = made.json()
        assert test_services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run["id"], "steps": TENSILE_STEPS},
            headers=admin_headers,
        )
        assert stored.status_code == 201, stored.text
        # **채택된 것만 센다**(ADR 0007). 채택 전에는 잰 값이 없는 것과 같다.
        before = client.get(f"/api/samples/{sample['id']}/mill-check", headers=admin_headers)
        client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "인장강도",
                        "points": [{"value": 400}],
                        "input_unit": "MPa",
                        "source": "datasheet",
                        "reference": "MTC-2024-0812",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert before.status_code == 200
        stale = client.get(
            f"/api/samples/{sample['id']}/mill-check", headers=admin_headers
        ).json()["rows"][0]
        assert stale["measured"] is None, "채택 전인데 셌습니다"

        client.post(
            f"/api/processing/results/{stored.json()['id']}/adopt", headers=admin_headers
        )
        row = client.get(
            f"/api/samples/{sample['id']}/mill-check", headers=admin_headers
        ).json()["rows"][0]
        assert row["measured_count"] == 1
        assert row["measured"] is not None
        assert row["si_unit"] == "Pa"
        # **판정을 안 한다.** 차이를 비율로 낼 뿐이다 — 몇 %부터 문제인지는
        # 규격과 용도가 정하고, 상수로 박으면 그 숫자가 규격 행세를 한다.
        assert row["difference"] == pytest.approx((row["measured"] - 400e6) / 400e6)
        assert row["note"] is None

    def test_이어져_있지_않으면_그렇다고_말한다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        """연신율은 우리가 재는 값에 안 이어져 있다 — 밀시트의 A 는 파단 후
        연신율인데 `elongation_observed` 는 시험 창 안의 관측 최대 변형률이라
        **가깝지만 같지 않다.** 이어 붙이면 화면이 「맞다/틀리다」를 말하게 되고,
        그 판정은 두 값이 같은 것일 때만 뜻이 있다."""
        client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "연신율",
                        "points": [{"value": 32}],
                        "input_unit": "%",
                        "source": "datasheet",
                        "reference": "MTC-2024-0812",
                    }
                ]
            },
            headers=admin_headers,
        )
        row = client.get(
            f"/api/samples/{sample['id']}/mill-check", headers=admin_headers
        ).json()["rows"][0]
        assert row["measured"] is None
        assert "이어져 있지 않습니다" in row["note"]


class Test경도척도:
    """**척도는 단위가 아니다.**

        MPa → Pa   곱하기 1e6      단위는 계수로 환산된다
        HV  → HB   불가능          척도는 안 된다

    `HV 200` 과 `HB 200` 은 다른 값이고 환산식이 없다 — 규격(ASTM E140)이
    참고표를 주지만 재료마다 다르고 그것도 「대략」이라고 명시한다. 한 칸에
    받으면 **숫자는 그럴듯한데 뜻이 다른** 값이 저장된다.

    v1.73.0 에서 경도를 일부러 뺀 이유가 이것이고, 여기서 그 자리를 만든다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        ensure_builtin_test_types(db)
        db.commit()

    @pytest.fixture
    def sample(self, client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "HARD",
                "details": "MDOI",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        ).json()
        made = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "L-1"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        created: dict[str, Any] = made.json()
        return created

    def test_척도를_고르면_환산_없이_담는다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        saved = client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "경도",
                        "points": [{"value": 200}],
                        "scale": "HV",
                        "source": "datasheet",
                        "reference": "MTC-2024-0812",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        row = saved.json()["declared_properties"][0]
        assert row["scale"] == "HV"
        # **환산이 없다.** 적은 값이 곧 저장 값이다.
        assert row["points"][0]["value_si"] == pytest.approx(200)
        assert row["points"][0]["value"] == pytest.approx(200)
        assert row["input_unit"] is None

    def test_척도를_안_고르면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        """**200 만 적으면 그것이 HV 인지 HB 인지 알 방법이 없다.**"""
        refused = client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "경도",
                        "points": [{"value": 200}],
                        "source": "datasheet",
                        "reference": "MTC",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        message = refused.json()["error"]["message"]
        assert "HV" in message and "환산" in message

    def test_모르는_척도는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        refused = client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "경도",
                        "points": [{"value": 200}],
                        "scale": "HZ",
                        "source": "datasheet",
                        "reference": "MTC",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text

    def test_피커가_단위_대신_척도를_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**둘 다 주면 화면이 어느 쪽을 그릴지 스스로 판단해야 하고, 그 판단이
        서버와 갈라진다.**"""
        items = client.get(
            "/api/materials/property-items?level=시료", headers=admin_headers
        ).json()
        by_item = {row["item"]: row for row in items}
        assert by_item["경도"]["scales"] == ["HV", "HB", "HRC", "HRB", "HS"]
        assert by_item["경도"]["units"] == []
        # 보통 물성은 그대로다.
        assert by_item["항복강도"]["scales"] == []
        assert "MPa" in by_item["항복강도"]["units"]

    def test_잰_값과_안_견주고_왜_그런지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], sample: dict[str, Any]
    ) -> None:
        """우리가 내는 스칼라는 SI 값이고 밀시트의 경도는 척도 위의 숫자다 —
        **둘을 빼면 숫자는 나오는데 뜻이 없다.**"""
        client.patch(
            f"/api/samples/{sample['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "경도",
                        "points": [{"value": 200}],
                        "scale": "HV",
                        "source": "datasheet",
                        "reference": "MTC",
                    }
                ]
            },
            headers=admin_headers,
        )
        row = client.get(
            f"/api/samples/{sample['id']}/mill-check", headers=admin_headers
        ).json()["rows"][0]
        assert row["measured"] is None
        assert row["declared_unit"] == "HV"
        assert "척도" in row["note"] and "환산되지 않습니다" in row["note"]


def _bulk(client: TestClient, headers: dict[str, str], materials: list[dict[str, Any]]) -> Any:
    response = client.post(
        "/api/materials/bulk", json={"materials": materials}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


class Test여러_개_한꺼번에:
    """실사용에서 나왔다 — *"여러 카테고리 재료를 한 번에"*,
    *"한 재료 안에 다양한 시료·시편"*."""

    def test_분류가_줄마다_달라도_된다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**한 판에 한 분류가 아니다.** 분류를 창 위에 하나만 두면 알루미늄 한
        줄을 넣으려고 창을 다시 열어야 한다."""
        body = _bulk(
            client,
            admin_headers,
            [
                {**SECC, "row": 0},
                {"family": "Metal", "category": "Aluminum", "grade": "A5052", "row": 1},
            ],
        )
        assert body["materials"] == 2
        assert body["blocked"] == []

        listing = client.get("/api/materials", headers=admin_headers).json()
        assert {row["category"] for row in listing["items"]} == {"Steel", "Aluminum"}

    def test_한_재료_아래에_시료를_여러_벌_넣는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료는 한 번만 만들어지고 시료가 둘 붙는다 — 이 기능의 요점이다."""
        body = _bulk(
            client,
            admin_headers,
            [
                {
                    **SECC,
                    "row": 0,
                    "samples": [
                        {"lot_no": "LOT-A", "row": 0},
                        {"lot_no": "LOT-B", "row": 1},
                    ],
                }
            ],
        )
        assert (body["materials"], body["samples"]) == (1, 2)
        names = [item["name"] for item in body["made"] if item["kind"] == "sample"]
        assert names == ["SECC_MDOI_1.0__01", "SECC_MDOI_1.0__02"]

    def test_시료_아래에_시편을_여러_개_넣는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = _bulk(
            client,
            admin_headers,
            [
                {
                    **SECC,
                    "row": 0,
                    "samples": [
                        {
                            "lot_no": "LOT-A",
                            "row": 0,
                            "specimens": [
                                {"orientation": "MD", "row": 0},
                                {"orientation": "MD", "row": 1},
                                {"orientation": "TD", "row": 2},
                            ],
                        }
                    ],
                }
            ],
        )
        assert (body["materials"], body["samples"], body["specimens"]) == (1, 1, 3)
        made = [item["name"] for item in body["made"] if item["kind"] == "specimen"]
        # 방향별로 채번한다 — LT 는 1·2, TD 는 다시 1.
        assert made == [
            "SECC_MDOI_1.0__01__MD_01",
            "SECC_MDOI_1.0__01__MD_02",
            "SECC_MDOI_1.0__01__TD_01",
        ]

    def test_있는_재료_아래에_붙인다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """어제 만든 재료에 오늘 온 판을 붙이는 것이 실제 작업이다."""
        _create_material(client, admin_headers)
        body = _bulk(
            client,
            admin_headers,
            [{**SECC, "row": 0, "samples": [{"lot_no": "LOT-C", "row": 1}]}],
        )
        assert body["materials"] == 0
        assert body["samples"] == 1
        reused = [item["reused"] for item in body["made"] if item["kind"] == "material"]
        assert reused == [True]

    def test_딸린_것_없이_이름만_겹치면_막는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**조용히 넘어가면 안 된다.** 아무것도 안 만들어졌는데 성공으로 읽힌다."""
        _create_material(client, admin_headers)
        body = _bulk(client, admin_headers, [{**SECC, "row": 3}])
        assert body["materials"] == 0
        assert body["blocked"][0]["row"] == 3
        reason = body["blocked"][0]["reason"]
        assert "같은 이름의 재료가 이미 있습니다: SECC_MDOI_1.0" in reason
        # **길을 알려 준다.** 이관에서 걸렸다 — 있는 재료에 시료·시편을 더하려는
        # 사람이 "추가가 안 된다" 로 읽고 멈췄다.
        assert "시료·시편을 함께 적으세요" in reason

    def test_막힌_줄만_빼고_나머지는_만든다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**한 줄이 막혔다고 전부 되돌리지 않는다.** 스무 줄을 다시 적게 된다."""
        _create_material(client, admin_headers)
        body = _bulk(
            client,
            admin_headers,
            [
                {**SECC, "row": 0},
                {"family": "Metal", "category": "Steel", "grade": "SGCC", "row": 1},
            ],
        )
        assert body["materials"] == 1
        assert [item["row"] for item in body["blocked"]] == [0]
        assert client.get("/api/materials?q=SGCC", headers=admin_headers).json()["total"] == 1

    def test_막힌_재료_아래는_줄마다_짚는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료가 안 만들어지면 그 아래 시료·시편도 못 만든다. **말 없이
        사라지게 두면** 사람은 표를 보며 「분명 넣었는데」 를 한다."""
        body = _bulk(
            client,
            admin_headers,
            [
                {
                    "family": "Metal",
                    "category": "Steel",
                    "grade": "SECC",
                    "spec_thickness": 1.0,
                    "spec_thickness_unit": "웁스",
                    "row": 0,
                    "samples": [{"row": 1, "specimens": [{"orientation": "MD", "row": 2}]}],
                }
            ],
        )
        assert [item["row"] for item in body["blocked"]] == [0, 1, 2]

    def test_시편이_막혀도_재료와_시료는_남는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """마디마다 세이브포인트를 두는 이유. 방향 하나가 틀렸다고 재료까지
        되돌리면 사람은 처음부터 다시 적는다."""
        body = _bulk(
            client,
            admin_headers,
            [
                {
                    **SECC,
                    "row": 0,
                    "samples": [
                        {
                            "row": 1,
                            "specimens": [
                                {"orientation": "MD", "row": 2},
                                {"orientation": "옆으로", "row": 3},
                            ],
                        }
                    ],
                }
            ],
        )
        assert (body["materials"], body["samples"], body["specimens"]) == (1, 1, 1)
        assert [item["row"] for item in body["blocked"]] == [3]
        # 세션이 살아 있다는 것도 함께 본다 — 되감기가 틀리면 다음 읽기가 터진다.
        assert client.get("/api/materials", headers=admin_headers).json()["total"] == 1

    def test_같은_번호를_두_번_적으면_뒤엣것만_막힌다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**여기가 세이브포인트가 실제로 필요한 자리다.**

        방향 이름이 틀린 것은 DB 에 닿기 전에 걸린다. 같은 방향·번호는 넣어
        본 뒤에야 걸리고, 그때 세션은 깨져 있다 — 되감지 않으면 그 뒤의 커밋과
        읽기가 엉뚱한 데서 터진다.
        """
        body = _bulk(
            client,
            admin_headers,
            [
                {
                    **SECC,
                    "row": 0,
                    "samples": [
                        {
                            "row": 1,
                            "specimens": [
                                {"orientation": "MD", "seq_no": 1, "row": 2},
                                {"orientation": "MD", "seq_no": 1, "row": 3},
                            ],
                        }
                    ],
                }
            ],
        )
        assert body["specimens"] == 1
        assert [item["row"] for item in body["blocked"]] == [3]
        assert "이미 있습니다" in body["blocked"][0]["reason"]
        # 커밋이 살아남았는지 — 세션이 깨졌으면 여기서 드러난다.
        listing = client.get("/api/materials", headers=admin_headers).json()
        assert listing["total"] == 1

    def test_상한을_서버가_강제한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """화면이 200줄까지만 그린다고 요청도 200줄이라는 보장은 없다."""
        rows = [
            {"family": "Metal", "category": "Steel", "grade": f"S{index}", "row": index}
            for index in range(2001)
        ]
        response = client.post(
            "/api/materials/bulk", json={"materials": rows}, headers=admin_headers
        )
        assert response.status_code == 422
        # **직접 쓴 검증기가 붙인 말이 그대로 와야 한다.** 「값이 올바르지
        # 않습니다」만 오면 무엇이 한도인지 알 수 없고, 전에는 이 자리에서
        # 직렬화가 터져 500 이 나갔다.
        # **상한을 2000 으로 올렸다**(v1.120.0) — 옛 DB 이관에서 200 에 걸렸고,
        # 시편이 수백 장인 판을 한 번에 넣는 것이 정상이다.
        assert "최대 2000개" in response.json()["error"]["message"]

    def test_시편까지_세어_상한을_넘기지_못한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료만 세면 시편 수천 개짜리 요청이 통과한다."""
        response = client.post(
            "/api/materials/bulk",
            json={
                "materials": [
                    {
                        **SECC,
                        "samples": [
                            {"specimens": [{"orientation": "MD"} for _ in range(2100)]}
                        ],
                    }
                ]
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-COMMON-0422"


class Test여러_개_한꺼번에_지우기:
    def test_고른_것을_지운다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        one = _create_material(client, admin_headers)
        two = _create_material(client, admin_headers, grade="SGCC")

        done = client.post(
            "/api/materials/delete",
            json={"material_ids": [one["id"], two["id"]]},
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        # **통째로 비교하지 않는다.** 응답에 칸이 늘 때마다 이 시험이 깨지는데,
        # 여기서 보는 것은 「둘을 지웠고 막힌 것이 없다」 이다.
        assert done.json()["deleted"] == 2
        assert done.json()["blocked"] == []
        assert client.get("/api/materials", headers=admin_headers).json()["total"] == 0

    def test_시료가_남은_것은_이유와_함께_돌려준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**막히는 이유가 둘이다** — 권한이 없는 것과 시료가 남은 것. 사람이
        해야 할 일이 다르니 개수만 주면 안 된다."""
        one = _create_material(client, admin_headers)
        two = _create_material(client, admin_headers, grade="SGCC")
        client.post(f"/api/materials/{two['id']}/samples", json={}, headers=admin_headers)

        body = client.post(
            "/api/materials/delete",
            json={"material_ids": [one["id"], two["id"]]},
            headers=admin_headers,
        ).json()
        assert body["deleted"] == 1
        assert len(body["blocked"]) == 1
        assert body["blocked"][0]["name"] == "SGCC_MDOI_1.0"
        assert "시료 1건" in body["blocked"][0]["reason"]
        # 막힌 것은 그대로 있다.
        assert (
            client.get(f"/api/materials/{two['id']}", headers=admin_headers).status_code == 200
        )

    def test_없는_것은_id_로_짚는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        ghost = str(uuid.uuid4())
        body = client.post(
            "/api/materials/delete", json={"material_ids": [ghost]}, headers=admin_headers
        ).json()
        assert body["deleted"] == 0
        assert body["blocked"][0]["id"] == ghost


class Test등록한_사람:
    """시료·시편도 **누가 넣었는지** 말한다.

    전에는 시험에만 있었다. 시료의 로트가 이상하거나 시편 치수가 의심스러울 때
    물어볼 데가 없었고, 상세를 열어도 알 수 없었다.
    """

    def test_시료_목록이_등록한_사람을_싣는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        made = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        )
        assert made.status_code == 201, made.text
        assert made.json()["registered_by"]

        listed = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        assert listed[0]["registered_by"] == made.json()["registered_by"]

    def test_시편_목록이_등록한_사람을_싣는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        made = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert made.json()["registered_by"]

        listed = client.get(
            f"/api/samples/{sample['id']}/specimens", headers=admin_headers
        ).json()
        assert listed[0]["registered_by"] == made.json()["registered_by"]

    def test_한_건짜리_조회에도_실린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """목록에만 있으면 상세를 열었을 때 사라진다."""
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()

        assert client.get(f"/api/samples/{sample['id']}", headers=admin_headers).json()[
            "registered_by"
        ]
        assert client.get(f"/api/specimens/{specimen['id']}", headers=admin_headers).json()[
            "registered_by"
        ]


class Test지운_이름을_다시_쓴다:
    """**지우고 다시 만드는 길이 아예 막혀 있었다** (2026-08-28).

    삭제는 소프트라 행이 남는데, 유니크 제약도 `name_taken` 도 그 행을 셌다.
    그래서 목록에는 없는 이름이 「이미 있습니다」 로 막혔고, 복구 기능이 없어
    화면에서 빠져나갈 길이 없었다.

    이관에서 그대로 터졌다 — 잘못 들어간 것을 지우고 다시 돌리면 그 재료 아래가
    통째로 안 들어간다. 금속 계열 전부가 그렇게 막혔다.

    **되돌릴 수 없는 자리라 사보타주 등급이 높다**(AGENTS: 삭제·병합). 그래서
    세 계층을 다 문다 — 재료 하나만 고치고 시료·시편을 빠뜨리면, 같은 벽이 한
    단계 아래에서 그대로 나온다.
    """

    def test_재료_이름을_다시_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        first = _create_material(client, admin_headers)
        assert (
            client.delete(f"/api/materials/{first['id']}", headers=admin_headers).status_code
            == 204
        )

        again = client.post("/api/materials", json=SECC, headers=admin_headers)
        assert again.status_code == 201, again.text
        assert again.json()["record_name"] == first["record_name"]
        assert again.json()["id"] != first["id"]

    def test_같은_이름이_둘_살아_있지는_않다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**푼 것은 지운 자리뿐이다.** 살아 있는 것끼리는 여전히 막아야 한다 —
        안 막으면 유니크를 두는 이유가 통째로 사라진다."""
        _create_material(client, admin_headers)
        again = client.post("/api/materials", json=SECC, headers=admin_headers)
        assert again.status_code == 409, again.text

    def test_시료를_지워도_다음_시료가_만들어진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**시료는 번호를 받지 않는다** — `SampleCreateRequest` 에 `seq_no` 가
        없고 언제나 `next_sample_seq` 가 매긴다. 그래서 지운 번호를 다시 달라고
        할 길이 API 에 없다.

        부분 인덱스는 그래도 함께 걸어 둔다. 셋이 같은 모양의 결함이었고, 번호를
        받게 되는 날 이 자리만 옛 규칙으로 남으면 그때 같은 벽을 다시 만난다.
        """
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        assert (
            client.delete(f"/api/samples/{sample['id']}", headers=admin_headers).status_code
            == 204
        )

        again = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        )
        assert again.status_code == 201, again.text
        # 지운 번호는 재사용하지 않는다 — 옛 문서에 적힌 이름이 다른 것을
        # 가리키면 안 된다(`next_sample_seq` 의 판단을 그대로 둔다).
        assert again.json()["seq_no"] == sample["seq_no"] + 1

    def test_시편_자리를_다시_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _create_material(client, admin_headers)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD", "seq_no": 1},
            headers=admin_headers,
        ).json()
        assert (
            client.delete(
                f"/api/specimens/{specimen['id']}", headers=admin_headers
            ).status_code
            == 204
        )

        again = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD", "seq_no": 1},
            headers=admin_headers,
        )
        assert again.status_code == 201, again.text
        assert again.json()["seq_no"] == 1
