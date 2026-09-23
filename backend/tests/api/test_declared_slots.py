"""사람이 적어 둔 값이 **카드의 빈 칸을 채운다** — 이름을 코드에 안 적고.

선언 물성이 카드로 가는 길은 여섯뿐이었다(탄성계수·푸아송비·밀도·비열·선팽창·
열전도율). 코드에 한글 이름이 박혀 있어서, 부서가 기준정보에 항목을 추가하고 값을
적어도 그 값은 카드에 실릴 길이 없었다 — 화면에서 항목란을 만들 수 있게 해 놓고도
(ADR 0033) 그 칸을 선언 물성으로는 못 채웠다는 뜻이다.

이 시험이 지키는 사슬:

    기준정보 항목  ──property_links──▶  물성 키  ◀──property_key──  블록 슬롯

그리고 규칙 둘: **잰 값이 이긴다**(빈 칸만 채운다) · **없던 블록은 안 만든다.**
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.fitting import card_tiers
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import Vocabulary
from app.shared import declared_slots
from matcore import cards
from matcore.cards import BlockSpec
from matcore.registry import Produced

#: 시험이 만들어 쓰는 물성 키. `local.` 은 MatNexus 에서 만든 것이라는 표시다.
KEY = "local.mechanical.barlat_exponent"
ITEM = "Barlat 지수"


@pytest.fixture(autouse=True)
def _block() -> Any:
    """「화면에서 만든 항목란」 을 흉내 낸다 — 슬롯이 물성 키를 든다."""
    cards.load_builtin()
    cards.install(
        BlockSpec(
            key="block_under_test",
            label="시험용 항목란",
            help="",
            produces=(
                Produced(key="exponent", label="지수", si_unit="1", property_key=KEY),
                Produced(key="measured_one", label="잰 값", si_unit="1", property_key=KEY),
            ),
            order=200,
        )
    )
    yield
    for key in cards.installed():
        cards.uninstall(key)


@pytest.fixture
def linked(db: Session) -> str:
    """기준정보 항목 하나를 만들고 **물성 키에 잇는다.** 그 다리가 이 기능의 전부다."""
    db.add(
        CatalogDefinition(
            key=KEY, domain="mechanical", name="Barlat 지수", value_type="numeric", si_unit="1"
        )
    )
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    assert axis is not None
    term = vocabulary_services.resolve_or_create(db, axis, ITEM, created_by_id=None)
    assert term is not None
    term.attributes = {"dimension": "dimensionless"}
    db.add(PropertyLink(property_key=KEY, term_id=term.id, kind="exact"))
    db.commit()
    return ITEM


def _material(client: TestClient, headers: dict[str, str], **over: Any) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"SLOT-{uuid.uuid4().hex[:6]}",
            **over,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _state(
    client: TestClient, headers: dict[str, str], material_id: str, value: float
) -> None:
    """재료 화면의 「선언 물성」 카드에 한 줄 적는 것과 같다."""
    got = client.patch(
        f"/api/materials/{material_id}",
        json={
            "declared_properties": [
                {
                    "item": ITEM,
                    "points": [{"value": value}],
                    "source": "standard",
                    "reference": "KS D 3512",
                }
            ]
        },
        headers=headers,
    )
    assert got.status_code == 200, got.text


def _state_modulus(
    client: TestClient, db: Session, headers: dict[str, str], material_id: str
) -> None:
    """탄성계수도 적어 둔다 — 이 경로가 **저절로** 만드는 블록이 서게."""
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    assert axis is not None
    term = vocabulary_services.resolve_or_create(db, axis, "탄성계수", created_by_id=None)
    assert term is not None
    term.attributes = {"dimension": "stress"}
    db.commit()
    got = client.patch(
        f"/api/materials/{material_id}",
        json={
            "declared_properties": [
                {
                    "item": ITEM,
                    "points": [{"value": 6.0}],
                    "source": "standard",
                    "reference": "KS D 3512",
                },
                {
                    "item": "탄성계수",
                    "points": [{"value": 206.0}],
                    "input_unit": "GPa",
                    "source": "standard",
                    "reference": "KS D 3512",
                },
            ]
        },
        headers=headers,
    )
    assert got.status_code == 200, got.text


def _card(db: Session, material_id: str, values: dict[str, Any]) -> PropertyCard:
    """블록 하나를 든 카드. 저장 경로를 그대로 지나가게 한다."""
    from app.modules.fitting import routes

    item = PropertyCard(
        material_id=uuid.UUID(material_id),
        label="시험용 카드",
        status="draft",
        blocks={"block_under_test": {"values": values}},
    )
    material = db.get(Material, uuid.UUID(material_id))
    stated = declared_slots.fill(db, material, item.blocks)
    assert routes is not None
    db.add(item)
    db.commit()
    db.refresh(item)
    item.source = {"notes": [f"채운 칸: {stated}"]} if stated else {}
    return item


def test_적어_둔_값이_빈_칸을_채운다(
    client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
) -> None:
    """**이름을 코드에 안 적는다.** 기준정보 항목을 물성 키에 이어 두면 그걸로 끝이다."""
    material = _material(client, admin_headers)
    _state(client, admin_headers, material["id"], 6.0)

    item = _card(db, material["id"], {})
    values = item.blocks["block_under_test"]["values"]
    assert values["exponent"] == pytest.approx(6.0)
    # 출처가 함께 붙는다 — 덱을 받은 사람이 「잰 값인가」 를 물을 자리다.
    assert values["exponent_source"] == "declared:standard"
    assert values["exponent_reference"] == "KS D 3512"


def test_잰_값은_안_덮는다(
    client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
) -> None:
    """적은 값으로 덮으면 그 카드가 무엇에서 나왔는지가 뒤집히고, 그 사실은 어디에도
    안 남는다."""
    material = _material(client, admin_headers)
    _state(client, admin_headers, material["id"], 6.0)

    item = _card(db, material["id"], {"measured_one": 8.0, "measured_one_source": "measured"})
    values = item.blocks["block_under_test"]["values"]
    assert values["measured_one"] == pytest.approx(8.0)
    assert values["measured_one_source"] == "measured"
    # 빈 칸이던 쪽은 채워진다 — 같은 물성 키라도 칸마다 따로 본다.
    assert values["exponent"] == pytest.approx(6.0)


def test_등급은_출처가_정한다(
    client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
) -> None:
    """여기서 등급을 계산하지 않는다 — `declared:<출처>` 를 등급 기계가 읽는다.
    규격이면 2, 추정이면 4다."""
    material = _material(client, admin_headers)
    _state(client, admin_headers, material["id"], 6.0)
    item = _card(db, material["id"], {})
    assert card_tiers.value_tiers(item)["block_under_test.exponent"] == 2


def test_안_이어_둔_항목은_안_실린다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """**짐작으로 잇지 않는다.** 이름이 비슷하다고 실으면 비열 자리에 열전도율이
    들어가고, 숫자는 그럴듯하다. 안 실리는 것이 맞는 결과다."""
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    assert axis is not None
    term = vocabulary_services.resolve_or_create(db, axis, ITEM, created_by_id=None)
    assert term is not None
    term.attributes = {"dimension": "dimensionless"}
    db.commit()

    material = _material(client, admin_headers)
    _state(client, admin_headers, material["id"], 6.0)
    item = _card(db, material["id"], {})
    assert "exponent" not in item.blocks["block_under_test"]["values"]


class Test시험_없이_만드는_카드:
    """**고르면 항목란이 카드에 앉는다** — 곡선이 없어도.

    선언 물성은 지금까지 「남의 블록에 얹혀」 만 갈 수 있었다. 블록을 카드에 올리는
    것은 값을 내는 쪽(적합식·묶음)의 일이라, 맞출 곡선이 없는 물성(적층 강성처럼
    사람이 적기만 하는 값)은 항목란을 만들어 두고 값을 적어도 앉을 자리가 없었다.
    """

    def _preview(
        self, client: TestClient, headers: dict[str, str], material_id: str
    ) -> dict[str, Any]:
        got = client.get(
            "/api/fitting/cards/declared/preview",
            params={"material_id": material_id},
            headers=headers,
        )
        assert got.status_code == 200, got.text
        return dict(got.json())

    def _make(
        self,
        client: TestClient,
        headers: dict[str, str],
        material_id: str,
        keys: list[str],
    ) -> Any:
        return client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material_id, "label": "적어 둔 값 카드", "block_keys": keys},
            headers=headers,
        )

    def test_미리보기가_후보를_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
    ) -> None:
        """**누르기 전에 안다.** 만들고 나서 「비었네」 를 보는 것은 늦다."""
        material = _material(client, admin_headers)
        _state(client, admin_headers, material["id"], 6.0)

        found = self._preview(client, admin_headers, material["id"])
        option = next(one for one in found["fillable"] if one["key"] == "block_under_test")
        slot = next(one for one in option["slots"] if one["key"] == "exponent")
        assert slot["value"] == pytest.approx(6.0)
        # 등급이 여기서 갈린다 — 화면이 「규격이라 2등급」 을 미리 말할 수 있다.
        assert slot["source"] == "standard"

    def test_고르면_카드에_앉는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
    ) -> None:
        material = _material(client, admin_headers)
        _state(client, admin_headers, material["id"], 6.0)

        made = self._make(client, admin_headers, material["id"], ["block_under_test"])
        assert made.status_code == 201, made.text
        values = made.json()["blocks"]["block_under_test"]["values"]
        assert values["exponent"] == pytest.approx(6.0)
        assert values["exponent_source"] == "declared:standard"
        # 시험이 하나도 없는 카드다 — 그 사실이 근거에 남아야 한다.
        assert made.json()["source"]["declared_only"] is True

    def test_안_고르면_안_앉는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
    ) -> None:
        """**값이 있다고 다 싣지 않는다.** 고르는 것은 사람이다."""
        material = _material(client, admin_headers, spec_thickness=1.0)
        _state(client, admin_headers, material["id"], 6.0)
        _state_modulus(client, db, admin_headers, material["id"])

        made = self._make(client, admin_headers, material["id"], [])
        assert made.status_code == 201, made.text
        assert "block_under_test" not in made.json()["blocks"]
        assert "elastic" in made.json()["blocks"]

    def test_채울_값이_없는_항목란은_이름을_대고_거절한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
    ) -> None:
        """조용히 빼지 않는다 — 고른 사람은 그것이 실린 줄 안다. 빈 칸만 든 블록이
        앉으면 목록은 「이 물성이 있다」 고 말하는데 값이 없다."""
        material = _material(client, admin_headers)
        _state(client, admin_headers, material["id"], 6.0)

        got = self._make(client, admin_headers, material["id"], ["hardening"])
        assert got.status_code == 422, got.text
        assert "hardening" in got.json()["error"]["message"]

    def test_저절로_실리는_것은_후보가_아니다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
    ) -> None:
        """탄성·열물성은 이 경로가 이미 만든다. 고르게 두면 「켰는데 이미 있다」 와
        「껐는데 실렸다」 가 생긴다."""
        material = _material(client, admin_headers)
        _state(client, admin_headers, material["id"], 6.0)
        _state_modulus(client, db, admin_headers, material["id"])

        found = self._preview(client, admin_headers, material["id"])
        assert {one["key"] for one in found["fillable"]} == {"block_under_test"}


def test_없던_블록은_안_만든다(
    client: TestClient, db: Session, admin_headers: dict[str, str], linked: str
) -> None:
    """이방성 카드를 만들었는데 열물성 블록이 따라 붙으면, 그 카드가 무엇의 카드인지
    흐려진다."""
    material = _material(client, admin_headers)
    _state(client, admin_headers, material["id"], 6.0)

    item = PropertyCard(
        material_id=uuid.UUID(material["id"]),
        label="다른 블록만 든 카드",
        status="draft",
        blocks={"elastic": {"values": {"youngs_modulus": 2.06e11}}},
    )
    declared_slots.fill(db, db.get(Material, uuid.UUID(material["id"])), item.blocks)
    assert set(item.blocks) == {"elastic"}
