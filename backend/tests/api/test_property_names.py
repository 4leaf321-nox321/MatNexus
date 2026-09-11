"""물성 이름 해소 — **「항복응력」이 어느 물성인가.**

MCP/AI 가 값을 묻기 전에 거치는 자리다. 여기가 틀리면 그 뒤의 모든 답이 **엉뚱한
물성에 대한 정답**이 되고, 틀렸다는 신호가 어디에도 안 남는다.

무는 것이 다섯이다.

    별칭이 이름을 이긴다        「항복응력」 → 금속 항복강도(유변학 아님)
    갈리면 되묻게 한다          도메인이 다른 후보가 나란히 서면 `ambiguous`
    값 0건을 위로 올리지 않는다  고를 수는 있는데 결과가 없으면 필터를 의심한다
    사내 항목과 이어진 것을 올린다 우리가 실제로 쓰는 물성이 먼저다
    같은 별칭을 두 번 넣어도 된다  이미 있으면 그것을 돌려준다(409 가 아니다)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.catalog.ontology_models import PropertyAlias, PropertyLink
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm

RESOLVE = "/api/catalog/properties/resolve"

#: 실측에서 온 두 물성. **이름이 정확히 「항복응력」인 것이 유변학 물성이다** —
#: 이 시험 전체가 그 함정을 다룬다.
YIELD_STRENGTH = ("mechanical.yield_strength", "항복강도", "mechanical", "Pa")
YIELD_STRESS = ("rheological.yield_stress", "항복응력", "rheological", "Pa")


@pytest.fixture
def definitions(db: Session) -> CatalogMaterial:
    """정의 둘과, 값을 매달 재료 하나. **값은 재료에 붙는다**(FK)."""
    for key, name, domain, unit in (YIELD_STRENGTH, YIELD_STRESS):
        db.add(
            CatalogDefinition(
                mt_id=abs(hash(key)) % 1_000_000,
                key=key,
                name=name,
                domain=domain,
                si_unit=unit,
                value_type="number",
            )
        )
    material = CatalogMaterial(mt_id=1, name="시험용 재료", category="metal")
    db.add(material)
    db.commit()
    return material


def add_values(db: Session, material: CatalogMaterial, key: str, count: int) -> None:
    """값 개수가 순위를 가른다 — 486건과 9건의 차이를 시험이 재현한다."""
    for at in range(count):
        db.add(
            CatalogValue(
                mt_id=abs(hash((key, at))) % 100_000_000,
                material_id=material.id,
                property_key=key,
                value_num=float(at + 1),
                unit="Pa",
                quality_tier=2,
            )
        )
    db.commit()


class Test별칭이_이름을_이긴다:
    def test_항복응력이_금속_항복강도로_간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """**이 시험이 이 기능의 존재 이유다.**

        이름이 정확히 「항복응력」 인 정의는 유변학 물성(페이스트가 흐르는 응력)
        이다. 사람이 「항복응력 200MPa」 를 물으면 금속의 항복강도를 뜻하는데,
        이름만 맞춰 고르면 엉뚱한 물성에 답한다.
        """
        db.add(
            PropertyAlias(
                property_key=YIELD_STRENGTH[0],
                alias="항복응력",
                normalized="항복응력",
                source="seed",
            )
        )
        db.commit()
        add_values(db, definitions, YIELD_STRENGTH[0], 20)
        add_values(db, definitions, YIELD_STRESS[0], 2)

        got = client.get(RESOLVE, params={"q": "항복응력"}, headers=admin_headers).json()
        assert got["candidates"][0]["key"] == YIELD_STRENGTH[0], (
            "별칭이 붙은 금속 항복강도가 1등이어야 합니다 — 이름만 맞는 유변학 "
            "물성이 1등이면 조용히 틀린 답이 나갑니다."
        )
        assert got["candidates"][0]["matched_by"] == "alias"
        # **유변학 물성을 지우지 않는다** — 그것도 답일 수 있고, 사람이 고른다.
        assert YIELD_STRESS[0] in [one["key"] for one in got["candidates"]]

    def test_별칭으로_걸리면_되묻지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """**사람이 이미 답해 둔 것이다.**

        별칭은 「이 말은 이 물성이다」 라고 못 박아 둔 판단이다. 여기서 또 되물으면
        별칭을 넣은 사람을 무시하는 셈이고, AI 는 매번 같은 것을 되묻는다.
        """
        db.add(
            PropertyAlias(
                property_key=YIELD_STRENGTH[0],
                alias="항복응력",
                normalized="항복응력",
                source="seed",
            )
        )
        db.commit()
        add_values(db, definitions, YIELD_STRENGTH[0], 5)
        add_values(db, definitions, YIELD_STRESS[0], 5)

        got = client.get(RESOLVE, params={"q": "항복응력"}, headers=admin_headers).json()
        assert got["ambiguous"] is False
        assert got["candidates"][0]["key"] == YIELD_STRENGTH[0]

    def test_별칭이_없으면_갈린다고_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """**부분 일치로 도메인이 다른 것이 나란히 서면 하나를 고르면 안 된다.**

        「항복」 처럼 사람이 덜 적어 물었을 때가 그 경우다.
        """
        add_values(db, definitions, YIELD_STRENGTH[0], 5)
        add_values(db, definitions, YIELD_STRESS[0], 5)
        got = client.get(RESOLVE, params={"q": "항복"}, headers=admin_headers).json()
        assert got["ambiguous"] is True, "mechanical 과 rheological 이 함께 섰습니다."


class Test순위:
    def test_값이_없는_물성을_1등으로_주지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """**고를 수는 있는데 결과가 0건이면 사람은 필터를 의심한다.**

        기준정보 피커가 개수를 함께 보여 주는 것과 같은 판단이다.
        """
        add_values(db, definitions, YIELD_STRESS[0], 30)
        got = client.get(RESOLVE, params={"q": "항복"}, headers=admin_headers).json()
        keys = [one["key"] for one in got["candidates"]]
        assert keys[0] == YIELD_STRESS[0], "값이 있는 쪽이 먼저다"
        empty = next(one for one in got["candidates"] if one["key"] == YIELD_STRENGTH[0])
        assert empty["value_count"] == 0
        assert any("값이 없습니다" in note for note in empty["notes"]), (
            "값이 없다는 것을 말해 줘야 한다 — 안 그러면 왜 0건인지 모른다"
        )

    def test_사내_항목과_이어진_것이_올라간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """우리가 실제로 쓰는 물성이 먼저다."""
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        term = VocabularyTerm(vocabulary_id=axis.id, value="항복강도", normalized="항복강도")
        db.add(term)
        db.flush()
        db.add(PropertyLink(property_key=YIELD_STRENGTH[0], term_id=term.id, kind="same_as"))
        db.commit()
        add_values(db, definitions, YIELD_STRENGTH[0], 3)
        add_values(db, definitions, YIELD_STRESS[0], 3)

        got = client.get(RESOLVE, params={"q": "항복"}, headers=admin_headers).json()
        first = got["candidates"][0]
        assert first["key"] == YIELD_STRENGTH[0]
        assert first["internal_items"] == ["항복강도"]


class Test못_찾으면:
    def test_지어내지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], definitions: CatalogMaterial
    ) -> None:
        """**빈 목록이 답이다.** 비슷한 것을 아무거나 주면 그것이 정답처럼 보인다."""
        got = client.get(RESOLVE, params={"q": "없는물성이름"}, headers=admin_headers).json()
        assert got["candidates"] == []
        assert got["ambiguous"] is False


class Test별칭_관리:
    def test_같은_별칭을_두_번_넣어도_된다(
        self, client: TestClient, admin_headers: dict[str, str], definitions: CatalogMaterial
    ) -> None:
        """**409 가 아니다.** 실제로 일어난 일은 「이미 있는 것을 또 적었다」 뿐인데
        화면이 멈추면 안 된다(기준정보 값 추가와 같은 판단)."""
        body: dict[str, Any] = {"alias": "YS", "source": "seed"}
        first = client.post(
            f"/api/catalog/properties/{YIELD_STRENGTH[0]}/aliases",
            json=body,
            headers=admin_headers,
        )
        assert first.status_code == 201, first.text
        again = client.post(
            f"/api/catalog/properties/{YIELD_STRENGTH[0]}/aliases",
            json={"alias": "ys", "source": "seed"},
            headers=admin_headers,
        )
        assert again.status_code == 201
        assert again.json()["id"] == first.json()["id"], "정규화가 같으면 같은 별칭이다"

    def test_없는_물성에는_못_붙인다(
        self, client: TestClient, admin_headers: dict[str, str], definitions: CatalogMaterial
    ) -> None:
        bad = client.post(
            "/api/catalog/properties/nope.nothing/aliases",
            json={"alias": "무엇"},
            headers=admin_headers,
        )
        assert bad.status_code == 404
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0021"


class Test매핑:
    def test_사내_항목_이름으로_잇는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        definitions: CatalogMaterial,
    ) -> None:
        """**ADR 0027 이 미뤄 둔 매핑이다.** 사람이 폼에 id 를 적지 않는다."""
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        db.add(VocabularyTerm(vocabulary_id=axis.id, value="항복강도", normalized="항복강도"))
        db.commit()

        made = client.post(
            "/api/catalog/properties/links",
            json={"property_key": YIELD_STRENGTH[0], "item": "항복강도"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert made.json()["item"] == "항복강도"

    def test_없는_항목이면_만들지_않고_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], definitions: CatalogMaterial
    ) -> None:
        """**기준정보와 다르다.** 여기서 물성 항목을 새로 만들면 오타가 축을 늘린다."""
        bad = client.post(
            "/api/catalog/properties/links",
            json={"property_key": YIELD_STRENGTH[0], "item": "없는항목"},
            headers=admin_headers,
        )
        assert bad.status_code == 404
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0025"


SEARCH = "/api/catalog/properties/search"


class Test값으로_찾기:
    """**「항복응력이 200MPa 근처인 재료」** — 이름 해소 + 단위 환산 + 범위."""

    @pytest.fixture
    def values(self, db: Session, definitions: CatalogMaterial) -> CatalogMaterial:
        """**현실을 닮게 만든다** — 실제는 항복강도 486건 대 유변학 9건이라
        갈리지 않는다. 값 개수와 사내 매핑이 순위를 가르는 것이 설계다."""
        # 180 · 200 · 300 MPa. 앞 둘만 200±10% 안이다.
        for at, pa in enumerate((180e6, 200e6, 300e6)):
            db.add(
                CatalogValue(
                    mt_id=900_000 + at,
                    material_id=definitions.id,
                    property_key=YIELD_STRENGTH[0],
                    value_num=pa,
                    unit="Pa",
                    quality_tier=2,
                )
            )
        # 순위를 벌리는 채움값. **범위 밖이라 결과에는 안 낀다.**
        for at in range(40):
            db.add(
                CatalogValue(
                    mt_id=910_000 + at,
                    material_id=definitions.id,
                    property_key=YIELD_STRENGTH[0],
                    value_num=900e6,
                    unit="Pa",
                    quality_tier=2,
                )
            )
        db.add(
            PropertyAlias(
                property_key=YIELD_STRENGTH[0],
                alias="항복응력",
                normalized="항복응력",
                source="seed",
            )
        )
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
        assert axis is not None
        term = VocabularyTerm(vocabulary_id=axis.id, value="항복강도", normalized="항복강도")
        db.add(term)
        db.flush()
        db.add(PropertyLink(property_key=YIELD_STRENGTH[0], term_id=term.id))
        db.commit()
        return definitions

    def test_단위를_환산해_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], values: CatalogMaterial
    ) -> None:
        """**200MPa 는 200,000,000 Pa 다.** 「200」 을 그대로 걸면 8 Pa 가 나온다."""
        got = client.get(
            SEARCH,
            params={"q": "항복응력", "unit": "MPa", "near": 200},
            headers=admin_headers,
        ).json()
        assert got["resolved"]["key"] == YIELD_STRENGTH[0]
        assert got["range_si"] == pytest.approx([180e6, 220e6]), "±10% 로 편다"
        assert [one["value"] for one in got["hits"]] == [180.0, 200.0], (
            "300 MPa 는 범위 밖이다"
        )
        assert got["hits"][0]["unit"] == "MPa", "물어본 단위로 되돌려 준다"

    def test_min_max_로도_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], values: CatalogMaterial
    ) -> None:
        got = client.get(
            SEARCH,
            params={"q": "항복응력", "unit": "MPa", "min": 250, "max": 400},
            headers=admin_headers,
        ).json()
        assert [one["value"] for one in got["hits"]] == [300.0]

    def test_범위를_안_주면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], values: CatalogMaterial
    ) -> None:
        bad = client.get(
            SEARCH, params={"q": "항복응력", "unit": "MPa"}, headers=admin_headers
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0030"

    def test_차원이_다른_단위를_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], values: CatalogMaterial
    ) -> None:
        """**숫자는 나오지만 뜻이 없다.** 조용히 틀리는 쪽이다."""
        bad = client.get(
            SEARCH,
            params={"q": "항복응력", "unit": "K", "near": 200},
            headers=admin_headers,
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0032"

    def test_갈리면_값을_안_찾는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        values: CatalogMaterial,
    ) -> None:
        """**어느 물성인지 모른 채 찾은 값은 엉뚱한 물성의 정답이다.**"""
        # **나란히 서게 만든다.** 금속 쪽은 사내 매핑이 붙어 앞서 있으므로,
        # 유변학 쪽 값이 그만큼 많아야 진짜로 갈린다 — 그것이 이 판정의 뜻이다.
        for at in range(200):
            db.add(
                CatalogValue(
                    mt_id=950_000 + at,
                    material_id=values.id,
                    property_key=YIELD_STRESS[0],
                    value_num=200e6,
                    unit="Pa",
                    quality_tier=2,
                )
            )
        db.commit()

        # **별칭이 안 걸리는 말로 묻는다.** 「항복」 은 별칭 「항복응력」 에
        # 부분으로 걸려 금속 쪽이 앞선다 — 그건 갈린 게 아니다.
        got = client.get(
            SEARCH,
            params={"q": "yield", "unit": "MPa", "near": 200},
            headers=admin_headers,
        ).json()
        assert got["ambiguous"] is True
        assert got["hits"] == [], "갈렸으면 값을 안 찾는다"
        assert len(got["candidates"]) >= 2

    def test_문헌_표기가_달라도_같은_단위면_찾는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**`W/(m*K)` 와 `W/(m.K)` 는 같은 단위다.** 전에는 「차원이 다릅니다」 였다."""
        material = CatalogMaterial(mt_id=2, name="구리", category="metal")
        db.add(material)
        db.add(
            CatalogDefinition(
                mt_id=777_001,
                key="thermal.conductivity",
                name="열전도율",
                domain="thermal",
                si_unit="W/(m*K)",
                value_type="number",
            )
        )
        db.flush()
        db.add(
            CatalogValue(
                mt_id=777_002,
                material_id=material.id,
                property_key="thermal.conductivity",
                value_num=400.0,
                unit="W/(m*K)",
                quality_tier=2,
            )
        )
        db.commit()
        for asked in ("W/(m.K)", "W/(m*K)", "W/(m·K)"):
            got = client.get(
                SEARCH,
                params={"q": "thermal.conductivity", "unit": asked, "near": 400},
                headers=admin_headers,
            )
            assert got.status_code == 200, (asked, got.text)
            assert [one["value"] for one in got.json()["hits"]] == [400.0], asked

    def test_표가_모르는_눈금은_정의의_단위_그대로_견준다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**「HV 200 근처」 는 뜻이 있다.** 환산은 못 해도 저장된 값이 그 눈금이다."""
        material = CatalogMaterial(mt_id=3, name="공구강", category="metal")
        db.add(material)
        db.add(
            CatalogDefinition(
                mt_id=777_003,
                key="mechanical.hardness_vickers",
                name="비커스 경도",
                domain="mechanical",
                si_unit="HV",
                value_type="number",
            )
        )
        db.flush()
        for at, hv in enumerate((190.0, 210.0, 400.0)):
            db.add(
                CatalogValue(
                    mt_id=777_010 + at,
                    material_id=material.id,
                    property_key="mechanical.hardness_vickers",
                    value_num=hv,
                    unit="HV",
                    quality_tier=2,
                )
            )
        db.commit()
        got = client.get(
            SEARCH,
            params={"q": "mechanical.hardness_vickers", "unit": "hv", "near": 200},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        assert [one["value"] for one in got.json()["hits"]] == [190.0, 210.0]
        # 다른 눈금으로 물으면 여전히 모른다고 한다 — HB 200 은 HV 200 이 아니다.
        bad = client.get(
            SEARCH,
            params={"q": "mechanical.hardness_vickers", "unit": "HB", "near": 200},
            headers=admin_headers,
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-CATALOG-0031"

    def test_사내와_안_이어졌으면_그렇다고_말한다(
        self, client: TestClient, admin_headers: dict[str, str], values: CatalogMaterial
    ) -> None:
        """**못 찾은 것과 안 본 것은 다르다.**

        유변학 항복응력은 사내 물성 항목에 없다 — 키로 정확히 물어 갈림을 피한다.
        """
        got = client.get(
            SEARCH,
            params={"q": YIELD_STRESS[0], "unit": "MPa", "near": 200},
            headers=admin_headers,
        ).json()
        assert got["resolved"]["key"] == YIELD_STRESS[0]
        assert any("사내 재료는 안 봤습니다" in note for note in got["notes"])
