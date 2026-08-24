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
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material
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
        assert stored.input_units == {"spec_thickness": "mm", "density": "kg/m3"}

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
        import uuid as uuid_module

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
        assert test_services.parse_run(db, uuid_module.UUID(runs[0]["id"])) == "parsed"
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
        failed = db.get(TestRun, uuid_module.UUID(runs[1]["id"]))
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
        assert changed.json()["standard"] == "JIS 5호"

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
                        "value": 206,
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
        assert row["value_si"] == pytest.approx(206e9)
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
                        "value": 45,
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
                "value": 206,
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
                        "value": 295,
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
                        "value": 295,
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
            "value": 206,
            "input_unit": "GPa",
            "source": "literature",
            "reference": "A",
        }
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={"declared_properties": [row, {**row, "value": 200, "reference": "B"}]},
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
                        "value": 1.17e-5,
                        "input_unit": "1/K",
                        "source": "standard",
                        "reference": "KS",
                    },
                    {
                        "item": "탄성계수",
                        "value": 206,
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

    MILL = {
        "item": "항복강도",
        "value": 295,
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
        assert row["value_si"] == pytest.approx(295e6)
        # 적은 단위를 그대로 돌려준다 — 2.95e8 로 보이면 자기가 적은 값인지 모른다.
        assert row["value"] == pytest.approx(295)
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
                        "value": 206,
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
                        "value": 400,
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
                        "value": 32,
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
