"""재료·문헌을 **JSON 파일로** 내보낸다.

## 무는 것

    봉투가 있다            맨 배열이면 무엇의 어느 시점 자료인지 알 방법이 없다
    거르는 규칙이 같다      「화면에서 본 것」 과 「받아 간 파일」 이 달라지면 안 된다
    권한을 지킨다          목록에 안 보이던 것이 파일로 새어 나가면 안 된다
    출처를 한 번만 적는다   3,013개를 42,209번 되풀이하면 그것만 13MB 다
    항 이름이 숫자여도 된다  Ogden 은 항 번호가 곧 이름이다

## 왜 봉투가 첫 시험인가

반년 뒤 그 파일이 폴더에서 나왔을 때 **설명할 수 있어야 한다.** 언제 뽑았는지,
어느 판이었는지, 무슨 조건으로 걸렀는지가 없으면 「전부인 줄 알았는데 아니었다」
가 나중에 드러나고, 그때는 이미 그 파일로 무언가를 계산한 뒤다.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue

MATERIALS = "/api/materials/export"
CATALOG = "/api/catalog/export"


def _material(client: TestClient, headers: dict[str, str], **over: Any) -> dict[str, Any]:
    body = {
        "family": "Metal",
        "category": "Steel",
        "grade": "EXP",
        "details": "MDOI",
        "spec_thickness": 1.0,
        **over,
    }
    made = client.post("/api/materials", json=body, headers=headers)
    assert made.status_code == 201, made.text
    got: dict[str, Any] = made.json()
    return got


def _download(client: TestClient, headers: dict[str, str], path: str, **params: Any) -> Any:
    got = client.get(path, params=params, headers=headers)
    assert got.status_code == 200, got.text
    # **파일로 내려간다.** 화면에 JSON 이 그려지면 사람이 복사해 붙이게 된다.
    assert "attachment" in got.headers["content-disposition"]
    assert "charset=utf-8" in got.headers["content-type"]
    return json.loads(got.content.decode("utf-8"))


class Test재료:
    @pytest.fixture(autouse=True)
    def _items(self, db: Session) -> None:
        """선언 물성은 **기준정보에 있는 항목만** 받는다 — 시험 DB 에 심어 둔다."""
        from app.modules.vocabulary.definitions import (
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_property_items(db)
        db.commit()

    def test_봉투가_스스로를_설명한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _material(client, admin_headers)
        body = _download(client, admin_headers, MATERIALS)
        assert body["kind"] == "matnexus.materials"
        assert body["app_version"]
        assert body["exported_at"]
        assert body["count"] == len(body["materials"])

    def test_거른_조건을_적어_둔다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**「전부인 줄 알았는데 아니었다」 를 막는다.** 조건이 파일에 없으면
        나중에 그 파일이 무엇의 부분집합인지 알 방법이 없다."""
        _material(client, admin_headers, grade="EXPFIND")
        _material(client, admin_headers, grade="EXPOTHER")
        body = _download(client, admin_headers, MATERIALS, q="EXPFIND")
        assert body["filters"] == {"q": "EXPFIND"}
        assert body["count"] == 1
        assert body["materials"][0]["record_name"].startswith("EXPFIND")

    def test_선언_물성이_함께_간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """재료만 있고 값이 없으면 이 파일로 할 수 있는 일이 없다."""
        made = _material(client, admin_headers, grade="EXPDECL")
        saved = client.patch(
            f"/api/materials/{made['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 200.0}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "KS D 3512 표 3",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        body = _download(client, admin_headers, MATERIALS, q="EXPDECL")
        found = body["materials"][0]["declared_properties"]
        assert found and found[0]["item"] == "탄성계수"
        # **SI 로 담는다.** 화면 표시 단위로 바꾸면 그 파일은 화면 설정에 따라
        # 달라지고, 받아서 계산에 쓰는 쪽은 그것을 알 수 없다.
        assert found[0]["points"][0]["value_si"] == pytest.approx(200e9)

    def test_목록과_같은_것이_나간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**「화면에서 본 것」 과 「받아 간 파일」 이 달라지면 안 된다.**

        거르는 규칙과 가시 범위를 목록과 한 함수로 쓴다 — 여기서 따로 물으면 그
        규칙이 두 벌이 되고, 언젠가 한쪽만 고쳐진다. 받아 간 쪽이 틀렸다는 것을
        알아챌 방법이 없다.
        """
        _material(client, admin_headers, grade="EXPSAME")
        _material(client, admin_headers, grade="EXPSAME", details="TD")

        listed = client.get(
            "/api/materials", params={"q": "EXPSAME", "limit": 1000}, headers=admin_headers
        )
        assert listed.status_code == 200, listed.text
        seen = {one["id"] for one in listed.json()["items"]}

        body = _download(client, admin_headers, MATERIALS, q="EXPSAME")
        assert {one["id"] for one in body["materials"]} == seen
        assert len(seen) == 2

    def test_값은_고른_단위계_하나로_나간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**한 파일에 계가 하나다**(ADR 0036). 전에는 「값은 SI 그대로」 라고 적어 두고 화면
        응답을 그대로 담아서 밀도만 tonne/mm3, 두께는 mm 였다 — 해석 연동이 그 파일을 「전부
        SI」 로 읽을 뻔했다(2026-09-24). 기본은 해석이 쓰는 mm·N·tonne, SI 는 골라야 나온다.
        """
        made = _material(
            client, admin_headers, grade="EXPUNIT", spec_thickness=1.2, density=2.68e-9
        )
        saved = client.patch(
            f"/api/materials/{made['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 70.3}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "핸드북",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

        got = client.get(MATERIALS, params={"q": "EXPUNIT"}, headers=admin_headers)
        assert "_mm_n_tonne.json" in got.headers["content-disposition"]
        body = _download(client, admin_headers, MATERIALS, q="EXPUNIT")
        # 파일 머리가 계를 말한다 — 숫자를 읽기 전에 볼 자리다.
        assert body["unit_system"]["key"] == "mm_n_tonne"
        assert body["unit_system"]["stress"] == "MPa"
        one = body["materials"][0]
        assert one["density"] == pytest.approx(2.68e-9) and one["density_unit"] == "tonne/mm3"
        assert one["density_si"] == pytest.approx(2680.0)
        assert one["spec_thickness"] == pytest.approx(1.2)
        assert one["spec_thickness_unit"] == "mm"
        row = one["declared_properties"][0]
        assert row["unit"] == "MPa" and row["si_unit"] == "Pa"
        assert row["points"][0]["value"] == pytest.approx(70300.0)
        assert row["points"][0]["value_si"] == pytest.approx(7.03e10)
        # 사람이 적은 단위(GPa)는 뺀다 — 여기 `value` 는 그 단위가 아니다.
        assert "input_unit" not in row

        si = _download(client, admin_headers, MATERIALS, q="EXPUNIT", units="si")
        assert si["unit_system"]["key"] == "si"
        one = si["materials"][0]
        assert one["density"] == pytest.approx(2680.0) and one["density_unit"] == "kg/m3"
        assert one["spec_thickness"] == pytest.approx(0.0012)
        assert one["spec_thickness_unit"] == "m"
        assert one["declared_properties"][0]["points"][0]["value"] == pytest.approx(7.03e10)

        # 모르는 계는 조용히 기본으로 떨어지지 않는다 — 쓸 수 있는 것을 말하고 거절한다.
        refused = client.get(MATERIALS, params={"units": "mks"}, headers=admin_headers)
        assert refused.status_code == 422
        assert "mm_n_tonne" in refused.json()["error"]["message"]


class Test문헌:
    def test_값은_고른_단위계로_못_옮기는_단위는_그대로_두고_적는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        stocked: CatalogMaterial,
    ) -> None:
        """기본은 mm·N·tonne(ADR 0036). 문헌에는 그 계가 기호를 정해 두지 않은 물리량(저항률
        같은 것)도 있다 — **지어내 옮기지 않고** 받은 그대로 두되 파일 머리에 적는다. 모델
        파라미터의 항은 제 단위로 적혀 있어 옮기지 않는다."""
        parameters.forget()
        for mt, key, unit in (
            (991201, "mechanical.youngs_modulus_probe", "Pa"),
            (991202, "physical.density_probe", "kg/m^3"),
            (991203, "electrical.resistivity_probe", "ohm*m"),
        ):
            db.add(
                CatalogDefinition(
                    mt_id=mt,
                    key=key,
                    name=key,
                    domain=key.split(".")[0],
                    si_unit=unit,
                    value_type="number",
                )
            )
        item = CatalogMaterial(mt_id=991210, name="단위 시험재", category="metal")
        db.add(item)
        db.flush()
        for at, (key, value, unit, spread) in enumerate(
            (
                ("mechanical.youngs_modulus_probe", 2.0e11, "Pa", 1.0e9),
                ("physical.density_probe", 7850.0, "kg/m^3", None),
                ("electrical.resistivity_probe", 7.2e-7, "ohm*m", None),
            )
        ):
            db.add(
                CatalogValue(
                    mt_id=991220 + at,
                    material_id=item.id,
                    property_key=key,
                    value_num=value,
                    unit=unit,
                    uncertainty=spread,
                    quality_tier=2,
                )
            )
        db.commit()
        parameters.forget()

        body = _download(client, admin_headers, CATALOG, q="단위 시험재")
        assert body["unit_system"]["key"] == "mm_n_tonne"
        values = {one["property_key"]: one for one in body["materials"][0]["values"]}
        modulus = values["mechanical.youngs_modulus_probe"]
        assert modulus["value_num"] == pytest.approx(200000.0) and modulus["unit"] == "MPa"
        assert modulus["value_si"] == pytest.approx(2.0e11) and modulus["si_unit"] == "Pa"
        # 같은 단위의 곁값도 같은 계로 — 불확도만 Pa 로 남으면 그 줄에 계가 둘이다.
        assert modulus["uncertainty"] == pytest.approx(1000.0)
        density = values["physical.density_probe"]
        assert density["value_num"] == pytest.approx(7.85e-9)
        assert density["unit"] == "tonne/mm3"
        # 이 계에 기호가 없는 단위 — 받은 그대로, 파일 머리에 적는다.
        resistivity = values["electrical.resistivity_probe"]
        assert resistivity["value_num"] == pytest.approx(7.2e-7)
        assert resistivity["unit"] == "ohm*m"
        assert "ohm*m" in body["kept_units"]

        # 모델 파라미터의 항은 제 단위로 적혀 있어 옮기지 않는다.
        rubber = _download(client, admin_headers, CATALOG, q="시험용 고무")
        terms = rubber["materials"][0]["values"]
        assert {one["value_num"] for one in terms} == {1000.0, 1001.0, 1002.0}
        assert {one["unit"] for one in terms} == {"Pa"}

        si = _download(client, admin_headers, CATALOG, q="단위 시험재", units="si")
        values = {one["property_key"]: one for one in si["materials"][0]["values"]}
        assert values["mechanical.youngs_modulus_probe"]["value_num"] == pytest.approx(2.0e11)
        assert values["mechanical.youngs_modulus_probe"]["unit"] == "Pa"

    @pytest.fixture
    def stocked(self, db: Session) -> CatalogMaterial:
        """값 셋과 출처 하나를 가진 문헌 재료. 항 이름 하나는 **숫자**다."""
        parameters.forget()
        db.add(
            CatalogDefinition(
                mt_id=991001,
                key="mechanical.hyperelastic_coefficient",
                name="초탄성 계수",
                domain="mechanical",
                si_unit="Pa",
                value_type="number",
            )
        )
        item = CatalogMaterial(mt_id=991002, name="시험용 고무", category="polymer")
        db.add(item)
        db.flush()
        for at, term in enumerate((1, 2, "mu")):
            db.add(
                CatalogValue(
                    mt_id=991100 + at,
                    material_id=item.id,
                    property_key="mechanical.hyperelastic_coefficient",
                    value_num=1000.0 + at,
                    unit="Pa",
                    quality_tier=2,
                    conditions={"term": term, "model": "ogden", "set_id": "s1"},
                )
            )
        db.commit()
        parameters.forget()
        return item

    def test_봉투와_값이_함께_온다(
        self, client: TestClient, admin_headers: dict[str, str], stocked: CatalogMaterial
    ) -> None:
        body = _download(client, admin_headers, CATALOG, q="시험용 고무")
        assert body["kind"] == "matnexus.catalog"
        assert body["count"] == 1
        assert body["value_count"] == 3
        one = body["materials"][0]
        assert one["name"] == "시험용 고무"
        assert len(one["values"]) == 3

    def test_항_이름이_숫자여도_나간다(
        self, client: TestClient, admin_headers: dict[str, str], stocked: CatalogMaterial
    ) -> None:
        """**Ogden 은 항 번호가 곧 이름이다.**

        실측(2026-09-10): 4,453건 중 4건이 숫자였고, 그 재료는 상세 화면도 500 이
        났다 — 내보내기를 만들다 드러났다.
        """
        body = _download(client, admin_headers, CATALOG, q="시험용 고무")
        terms = {one["term"] for one in body["materials"][0]["values"]}
        assert terms == {"1", "2", "mu"}, terms

    def test_상세_화면도_같이_고쳐진다(
        self, client: TestClient, admin_headers: dict[str, str], stocked: CatalogMaterial
    ) -> None:
        """값 만드는 함수를 **한 벌로** 쓰니 한쪽만 고쳐질 수 없다."""
        got = client.get(f"/api/catalog/materials/{stocked.id}", headers=admin_headers)
        assert got.status_code == 200, got.text
        assert {one["term"] for one in got.json()["values"]} == {"1", "2", "mu"}

    def test_대표_표시가_붙는다(
        self, client: TestClient, admin_headers: dict[str, str], stocked: CatalogMaterial
    ) -> None:
        """대표 표시 없이 값만 내보내면 받은 사람은 **아무거나 고르게 된다.**"""
        body = _download(client, admin_headers, CATALOG, q="시험용 고무")
        marks = [one["representative"] for one in body["materials"][0]["values"]]
        assert any(marks), "대표가 하나도 없다"

    def test_출처는_한_번만_적는다(
        self, client: TestClient, admin_headers: dict[str, str], stocked: CatalogMaterial
    ) -> None:
        """값마다 통째로 박으면 파일이 커질 뿐 아니라 **「출처가 4만 개」** 라고
        말하는 셈이 된다."""
        body = _download(client, admin_headers, CATALOG, q="시험용 고무")
        assert isinstance(body["sources"], list)
        ids = [one["id"] for one in body["sources"]]
        assert len(ids) == len(set(ids)), "출처가 중복으로 실렸다"
        for one in body["materials"][0]["values"]:
            assert "source" not in one, "값 안에 출처가 통째로 박혔다"
