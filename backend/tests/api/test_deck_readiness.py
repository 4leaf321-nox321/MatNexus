"""덱 준비도 — **이 재료로 이 형식이 나오나 · 왜 안 나오나 · 어디서 채우나.**

무는 것이 셋이다. 전부 「낼 수 있다고 해 놓고 못 내는」 부류다.

    판정이 렌더와 같다         준비도가 「나온다」 면 export 도 나와야 한다 — 반대도
    빠진 블록마다 채울 길이 붙는다   시험 종류 · 문헌값 수 · 적어 넣을 수 있나
    지도에 정적 관계가 실린다       형식→블록 · 블록→시험 · 블록→문헌 물성
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_bom_deck import catalog_ids, make_card

from app.modules.catalog.models import CatalogLink
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.tests.models import TestType


def fetch(client: TestClient, headers: dict[str, str], material_id: object) -> dict:  # type: ignore[type-arg]
    got = client.get(f"/api/fitting/materials/{material_id}/deck-readiness", headers=headers)
    assert got.status_code == 200, got.text
    body: dict = got.json()  # type: ignore[type-arg]
    return body


def test_준비도가_나온다면_export_도_나온다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    material, card = make_card(db)
    body = fetch(client, admin_headers, material.id)
    by_key = {one["key"]: one for one in body["formats"]}
    assert "json" not in by_key  # 합칠 수도 해석할 수도 없는 형식은 안 센다
    for key, one in by_key.items():
        got = client.get(
            f"/api/fitting/cards/{card.id}/export",
            params={"format": key, "units": "si"},
            headers=admin_headers,
        )
        assert one["ready"] == (got.status_code == 200), (
            f"{key}: 준비도 {one['ready']} 인데 export 는 {got.status_code} — "
            f"{one['missing']} / {got.text[:200]}"
        )
    # 탄성 + 소성 표 카드는 LS-DYNA 곡선 덱이 나오고, Prony 가 없어 점탄성은 안 나온다.
    assert by_key["dyna"]["ready"] and by_key["dyna"]["card_id"] == str(card.id)
    assert not by_key["dyna_viscoelastic"]["ready"]


def test_빠진_블록마다_채울_길이_붙는다(
    client: TestClient, db: Session, admin_headers: dict[str, str], tmp_path: Path
) -> None:
    material, card = make_card(db)
    # 소성 표를 떼어 탄성만 남긴다 — 곡선 덱이 「소성 표가 없다」 로 막혀야 한다.
    # 탄성계수도 비운다 — 문헌에서 채택할 수 있는 값이 몇인지 보려고.
    card.blocks = {
        "elastic": {"values": {**card.blocks["elastic"]["values"], "youngs_modulus": None}}
    }
    db.add(TestType(key="tensile", label="인장시험", abbr="TEN"))
    ids = catalog_ids(db, tmp_path)
    db.add(CatalogLink(material_id=material.id, catalog_material_id=ids["sus"]))
    db.commit()

    body = fetch(client, admin_headers, material.id)
    dyna = next(one for one in body["formats"] if one["key"] == "dyna")
    assert not dyna["ready"]
    missing = {one["block"]: one for one in dyna["missing"]}
    assert "table" in missing
    # 소성 표는 인장시험이 낸다 — 부서에 등록된 그 시험 종류를 가리킨다.
    tensile = missing["table"]["tests"][0]
    assert tensile["key"] == "tensile" and tensile["label"] == "인장시험"
    assert len(tensile["test_type_ids"]) == 1
    # 표 블록은 적어 넣는 것이 아니다 — 적을 수 있는 값이 없다.
    assert missing["table"]["declarable_values"] == []

    # 탄성계수는 적어 넣을 수도, 이어진 문헌 재료(SUS304 스냅샷)에서 채택할 수도 있다.
    elastic = missing["elastic"]
    assert "mechanical.youngs_modulus" in elastic["declarable_values"]
    assert "mechanical.youngs_modulus" in elastic["catalog"]["property_keys"]
    assert elastic["catalog"]["values_available"] >= 1

    # 열물성 형식은 열 블록이 없다 — 시험이 아니라 사람·문헌이 채운다.
    thermal = next(one for one in body["formats"] if one["key"] == "openradioss_thermal")
    heat = {one["block"]: one for one in thermal["missing"]}["thermal"]
    assert heat["tests"] == []
    assert "thermal.specific_heat" in heat["declarable_values"]
    # 스냅샷에 열물성 값은 없다 — 0 을 0 으로 말한다.
    assert heat["catalog"]["values_available"] == 0


def test_카드가_없어도_형식마다_필요한_것을_말한다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    bare = Material(record_name="빈재료", family="Metal", category="Steel", grade="X")
    db.add(bare)
    db.commit()
    body = fetch(client, admin_headers, bare.id)
    assert body["card_count"] == 0 and "카드가 없습니다" in body["note"]
    dyna = next(one for one in body["formats"] if one["key"] == "dyna")
    assert not dyna["ready"] and dyna["card_id"] is None
    assert {one["block"] for one in dyna["missing"]} >= {"elastic", "table"}


def test_확정_카드를_먼저_대어_본다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """초안이 더 최근이어도 확정된 카드가 나오면 그것을 가리킨다."""
    material, published = make_card(db)
    draft = PropertyCard(
        material_id=material.id, label="초안", status="draft", blocks=published.blocks
    )
    db.add(draft)
    db.commit()
    body = fetch(client, admin_headers, material.id)
    dyna = next(one for one in body["formats"] if one["key"] == "dyna")
    assert dyna["card_id"] == str(published.id)
    assert db.scalar(select(PropertyCard).where(PropertyCard.id == draft.id)) is not None


def test_지도에_정적_관계가_실린다(client: TestClient, admin_headers: dict[str, str]) -> None:
    got = client.get("/api/ontology", headers=admin_headers)
    assert got.status_code == 200, got.text
    req = got.json()["deck_requirements"]
    assert set(req["format_needs"]["dyna"]) >= {"elastic", "table"}
    assert "json" not in req["format_needs"]
    assert req["block_from_tests"]["table"] == ["tensile"]
    assert req["block_from_tests"]["viscoelastic"] == ["dma_sweep"]
    assert "mechanical.youngs_modulus" in req["block_fills"]["elastic"]
    # 열물성은 시험이 아니라 사람·문헌이 채운다.
    assert req["block_from_tests"]["thermal"] == []
