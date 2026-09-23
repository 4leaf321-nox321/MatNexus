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
