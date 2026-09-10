"""문헌 물성의 **변수** — 한 키에 여러 개가 들어 있다(ADR 0029).

실측(2026-09-08): 271개 정의 중 52개 · 값 4,453건이 파라미터 묶음이었다.
`mechanical.anand_constant` 하나에 Anand 9개 상수가 들어 있고 단위는 항마다
`1`·`1/s`·`MPa`·`K` 로 다르다. 그런데 정의는 `si_unit="1"` 하나만 말한다.

무는 것이 다섯이다.

    변수가 여럿인 키를 알아본다        하나뿐인 키는 파라미터형이 아니다
    변수마다 진짜 단위를 준다          정의가 말하는 단위가 아니다
    **변수를 안 정하면 값을 안 찾는다**  섞어서 답하면 조용히 틀린다
    단위를 안 맞추면 거절한다          이 값들은 SI 가 아니라 환산이 안 된다
    한 벌로 묶어 준다                  `A` 만 떼어 가면 뜻이 없다
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue

KEY = "mechanical.test_anand"

#: 실제 데이터에서 가져온 모양 — SAC305 의 Anand 한 벌(단위가 항마다 다르다).
TERMS = [
    ("a", 1.72, "1"),
    ("A", 2800.0, "1/s"),
    ("h0", 150000.0, "MPa"),
    ("Q/R", 9380.0, "K"),
    ("s_hat", 44.67, "MPa"),
]


@pytest.fixture
def anand(db: Session) -> Iterator[CatalogMaterial]:
    """변수 다섯이 든 정의 하나와, 그 한 벌을 가진 재료 하나."""
    parameters.forget()
    db.add(
        CatalogDefinition(
            mt_id=990001,
            key=KEY,
            name="시험용 점소성 상수",
            domain="mechanical",
            si_unit="1",  # **거짓말이다** — 항마다 단위가 다르다
            value_type="number",
        )
    )
    material = CatalogMaterial(mt_id=990002, name="시험용 솔더", category="metal")
    db.add(material)
    db.flush()
    for at, (term, value, unit) in enumerate(TERMS):
        db.add(
            CatalogValue(
                mt_id=990100 + at,
                material_id=material.id,
                property_key=KEY,
                value_num=value,
                unit="1",
                quality_tier=2,
                conditions={
                    "term": term,
                    "unit_of_term": unit,
                    "model": "anand",
                    "set_id": "test_set",
                },
            )
        )
    db.commit()
    parameters.forget()
    yield material
    parameters.forget()


class TestDetect:
    def test_변수가_여럿인_키를_알아본다(self, db: Session, anand: CatalogMaterial) -> None:
        assert parameters.is_parameterized(db, KEY)
        assert {one.name for one in parameters.terms(db, KEY)} == {t[0] for t in TERMS}

    def test_변수마다_진짜_단위를_준다(self, db: Session, anand: CatalogMaterial) -> None:
        """정의는 `1` 이라고 한다 — 그 말을 믿으면 MPa 값을 무차원으로 다룬다."""
        assert parameters.unit_of(db, KEY, "h0") == "MPa"
        assert parameters.unit_of(db, KEY, "Q/R") == "K"
        assert parameters.unit_of(db, KEY, "a") == "1"

    def test_한_벌로_묶어_준다(self, db: Session, anand: CatalogMaterial) -> None:
        """**`A` 만 떼어 가면 뜻이 없다** — 채택의 단위는 한 벌이다."""
        found = parameters.sets(db, key=KEY, material_id=anand.id)
        assert len(found) == 1
        one = found[0]
        assert one.model == "anand"
        assert one.set_id == "test_set"
        assert {row["term"] for row in one.terms} == {t[0] for t in TERMS}
        assert {row["unit"] for row in one.terms} == {"1", "1/s", "MPa", "K"}

    def test_표시_이름이_변수를_말한다(self, db: Session, anand: CatalogMaterial) -> None:
        definition = db.query(CatalogDefinition).filter_by(key=KEY).one()
        assert parameters.label(definition) == "시험용 점소성 상수"
        assert parameters.label(definition, "h0") == "시험용 점소성 상수 · h0"


class TestSearchGuard:
    def test_변수를_안_정하면_값을_안_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], anand: CatalogMaterial
    ) -> None:
        """**이 시험이 이 기능의 이유다.**

        안 막으면 `A`(2800, 1/s)와 `h0`(150000, MPa)를 같은 자로 재서 답한다.
        """
        answer = client.get(
            "/api/catalog/properties/search",
            params={"q": "시험용 점소성 상수", "unit": "1", "near": 1000},
            headers=admin_headers,
        )
        assert answer.status_code == 422, answer.text
        body = answer.json()["error"]
        assert body["code"] == "MNX-CATALOG-0034"
        assert "h0" in body["message"], "고를 변수 목록을 함께 줘야 한다"

    def test_변수의_단위와_다르면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], anand: CatalogMaterial
    ) -> None:
        """이 값들은 SI 가 아니라 환산할 수 없다 — 짐작해 환산하면 조용히 틀린다."""
        answer = client.get(
            "/api/catalog/properties/search",
            params={"q": "시험용 점소성 상수", "unit": "Pa", "term": "h0", "near": 150000},
            headers=admin_headers,
        )
        assert answer.status_code == 422, answer.text
        assert answer.json()["error"]["code"] == "MNX-CATALOG-0035"

    def test_변수를_정하면_환산_없이_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], anand: CatalogMaterial
    ) -> None:
        """150000 MPa 를 SI 로 환산하면 1.5e11 이 되어 아무것도 안 걸린다."""
        answer = client.get(
            "/api/catalog/properties/search",
            params={"q": "시험용 점소성 상수", "unit": "MPa", "term": "h0", "near": 150000},
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["total"] == 1
        assert body["hits"][0]["value"] == pytest.approx(150000.0)

    def test_해소가_변수_묶음이라고_말한다(
        self, client: TestClient, admin_headers: dict[str, str], anand: CatalogMaterial
    ) -> None:
        """AI 가 값을 묻기 전에 알아야 한다 — 안 알면 위의 422 를 맞고 나서야 안다."""
        answer = client.get(
            "/api/catalog/properties/resolve",
            params={"q": "시험용 점소성 상수"},
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        found = next(one for one in answer.json()["candidates"] if one["key"] == KEY)
        assert found["parameterized"] is True
        assert "h0" in found["terms"]

    def test_보통_물성은_그대로_환산한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**막는 것이 넘치면 안 된다** — 변수가 하나뿐인 물성은 전과 같아야 한다."""
        db.add(
            CatalogDefinition(
                mt_id=990900,
                key="mechanical.test_plain",
                name="시험용 항복강도",
                domain="mechanical",
                si_unit="Pa",
                value_type="number",
            )
        )
        material = CatalogMaterial(
            mt_id=990901, name=f"평범-{uuid.uuid4().hex[:6]}", category="metal"
        )
        db.add(material)
        db.flush()
        db.add(
            CatalogValue(
                mt_id=990902,
                material_id=material.id,
                property_key="mechanical.test_plain",
                value_num=200e6,
                unit="Pa",
                quality_tier=1,
            )
        )
        db.commit()
        parameters.forget()

        answer = client.get(
            "/api/catalog/properties/search",
            params={"q": "시험용 항복강도", "unit": "MPa", "near": 200},
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["hits"][0]["value"] == pytest.approx(200.0)


SPLIT_KEY = "mechanical.test_mooney"


@pytest.fixture
def aged(db: Session) -> Iterator[CatalogMaterial]:
    """**한 벌 이름 아래 여러 벌.** 노화 3조건에 항 2개씩 6값이 한 `set_id` 에.

    실측(2026-09-10)에서 나온 모양 그대로다 — NBR 씰 고무가 노화 8조건을 한
    이름에 담고 있었다.
    """
    parameters.forget()
    db.add(
        CatalogDefinition(
            mt_id=992001,
            key=SPLIT_KEY,
            name="시험용 초탄성 계수",
            domain="mechanical",
            si_unit="Pa",
            value_type="number",
        )
    )
    item = CatalogMaterial(mt_id=992002, name="시험용 노화고무", category="rubber")
    db.add(item)
    db.flush()
    at = 0
    for hours in (0.0, 10.0, 100.0):
        for term, value in (("C10", 1e5), ("C01", 2e5)):
            db.add(
                CatalogValue(
                    mt_id=992100 + at,
                    material_id=item.id,
                    property_key=SPLIT_KEY,
                    value_num=value + hours,
                    unit="Pa",
                    quality_tier=2,
                    conditions={
                        "term": term,
                        "model": "mooney_rivlin_2",
                        "set_id": "one_paper",
                        "aging_hours": hours,
                    },
                )
            )
            at += 1
    db.commit()
    parameters.forget()
    yield item
    parameters.forget()


class Test한_이름_아래_여러_벌:
    """**안 가르면 같은 항이 여러 번 든 벌이 나간다.**

    그것을 그대로 받아 가면 `C10` 이 3개인 Mooney-Rivlin 이 재료에 담기고,
    카드는 그중 어느 것을 쓸지 모른다.
    """

    def test_조건으로_갈라_낸다(self, db: Session, aged: CatalogMaterial) -> None:
        found = parameters.sets(db, key=SPLIT_KEY, material_id=aged.id)
        assert len(found) == 3, [one.variant for one in found]
        assert {one.variant for one in found} == {
            "aging_hours=0.0",
            "aging_hours=10.0",
            "aging_hours=100.0",
        }
        for one in found:
            assert len(one.terms) == 2
            assert not one.duplicated

    def test_화면에도_갈림이_간다(
        self, client: TestClient, admin_headers: dict[str, str], aged: CatalogMaterial
    ) -> None:
        got = client.get(
            f"/api/catalog/materials/{aged.id}/parameter-sets", headers=admin_headers
        )
        assert got.status_code == 200, got.text
        rows = [one for one in got.json() if one["property_key"] == SPLIT_KEY]
        assert len(rows) == 3
        assert all(one["variant"] for one in rows), rows
        assert all(one["duplicated"] == [] for one in rows)

    def test_채택은_갈린_벌_하나를_집는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        aged: CatalogMaterial,
    ) -> None:
        """`set_id` 만으로는 못 집는다 — 셋 다 같은 이름이다."""
        made = client.post(
            "/api/materials",
            json={"family": "Metal", "category": "Steel", "grade": "PSPLIT"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        material_id = made.json()["id"]

        vague = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={
                "property_key": SPLIT_KEY,
                "catalog_material_id": str(aged.id),
                "set_id": "one_paper",
            },
            headers=admin_headers,
        )
        assert vague.status_code == 422, vague.text
        assert "variant" in vague.json()["error"]["message"]

        picked = client.post(
            f"/api/materials/{material_id}/parameter-sets",
            json={
                "property_key": SPLIT_KEY,
                "catalog_material_id": str(aged.id),
                "set_id": "one_paper",
                "variant": "aging_hours=10.0",
            },
            headers=admin_headers,
        )
        assert picked.status_code == 201, picked.text
        # **그 조건의 값이 담겼다.** 다른 벌 값이 섞이면 여기서 걸린다.
        values = {row["term"]: row["value"] for row in picked.json()["terms"]}
        assert values == {"C10": 1e5 + 10.0, "C01": 2e5 + 10.0}
