"""짝 카드와 합쳐 내보낸다 — 이방성(r값) 카드 + MD 경화 카드 → Hill48 덱(ADR 0037).

이방성 카드에는 방향이 없고 r 셋만 있다(ADR 0034). Hill 재료는 기준 방향의 경화 곡선과 탄성이
한 재료에 함께 들어가야 해서, **내보낼 때만** 두 카드를 합친다. 지키는 것 넷:

    혼자서는 못 낸다          카드 목록의 `available_formats` 에 Hill 형식이 없다
    짝과 합치면 낸다          `paired-formats` 가 미리 말하고, 내려받기가 실제로 낸다
    이 카드의 블록이 이긴다    짝은 빈자리만 채운다
    같은 재료만              다른 재료의 곡선에 이 재료의 r 을 얹지 않는다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.fitting.models import PropertyCard

CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]
PLASTIC = {
    "elastic": {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}},
    "table": {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]},
}
ANISOTROPY = {"anisotropy": {"values": {"r_0": 1.8, "r_45": 1.4, "r_90": 2.1}}}


def _material(client: TestClient, headers: dict[str, str]) -> str:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"PAIR-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
        },
        headers=headers,
    )
    assert made.status_code in (200, 201), made.text
    return str(made.json()["id"])


def _card(
    db: Session, material_id: str, label: str, blocks: dict[str, Any], **extra: Any
) -> str:
    item = PropertyCard(
        material_id=uuid.UUID(material_id), label=label, status="draft", blocks=blocks, **extra
    )
    db.add(item)
    db.commit()
    return str(item.id)


@pytest.fixture
def pair(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, str]:
    material = _material(client, admin_headers)
    return {
        "material": material,
        "aniso": _card(db, material, "이방성 r", ANISOTROPY),
        "md": _card(db, material, "인장 MD", PLASTIC, orientation="MD"),
    }


def test_혼자서는_못_내고_짝과_합치면_낸다(
    client: TestClient, admin_headers: dict[str, str], pair: dict[str, str]
) -> None:
    alone = client.get(f"/api/fitting/cards/{pair['aniso']}", headers=admin_headers).json()
    assert "dyna_hill" not in alone["available_formats"]

    paired = client.get(
        f"/api/fitting/cards/{pair['aniso']}/paired-formats",
        params={"with_card": pair["md"]},
        headers=admin_headers,
    )
    assert paired.status_code == 200, paired.text
    body = paired.json()
    for key in ("abaqus_hill", "ansys_hill", "dyna_hill", "openradioss_hill", "nastran_hill"):
        assert key in body["available_formats"], key
    assert set(body["borrowed_blocks"]) == {"elastic", "table"}

    deck = client.get(
        f"/api/fitting/cards/{pair['aniso']}/export",
        params={"format": "dyna_hill", "units": "mm_n_tonne", "with_card": pair["md"]},
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert "*MAT_3-PARAMETER_BARLAT" in deck.text
    # 짝의 경화 곡선이 실렸다 — MPa 로.
    assert f"{455.0:>20.9E}" in deck.text
    # 짝이 어디서 왔는지 덱에 남는다.
    assert "짝 카드 인장 MD (MD)" in deck.text


def test_짝_없이_내려받으면_못_낸다고_말한다(
    client: TestClient, admin_headers: dict[str, str], pair: dict[str, str]
) -> None:
    deck = client.get(
        f"/api/fitting/cards/{pair['aniso']}/export",
        params={"format": "dyna_hill"},
        headers=admin_headers,
    )
    assert deck.status_code == 422


def test_이_카드의_블록이_이긴다(
    client: TestClient, db: Session, admin_headers: dict[str, str], pair: dict[str, str]
) -> None:
    """짝이 같은 블록을 들고 있어도 이 카드의 것이 실린다 — 짝은 빈자리만 채운다."""
    other = _card(
        db,
        pair["material"],
        "다른 r",
        {**PLASTIC, "anisotropy": {"values": {"r_0": 0.5, "r_45": 0.5, "r_90": 0.5}}},
    )
    deck = client.get(
        f"/api/fitting/cards/{pair['aniso']}/export",
        params={"format": "openradioss_hill", "units": "mm_n_tonne", "with_card": other},
        headers=admin_headers,
    )
    assert deck.status_code == 200, deck.text
    assert f"{1.8:>20.9E}{1.4:>20.9E}{2.1:>20.9E}" in deck.text


def test_다른_재료의_카드는_짝이_못_된다(
    client: TestClient, db: Session, admin_headers: dict[str, str], pair: dict[str, str]
) -> None:
    stranger = _card(
        db, _material(client, admin_headers), "남의 MD", PLASTIC, orientation="MD"
    )
    for path, params in (
        ("paired-formats", {"with_card": stranger}),
        ("export", {"format": "dyna_hill", "with_card": stranger}),
    ):
        answer = client.get(
            f"/api/fitting/cards/{pair['aniso']}/{path}", params=params, headers=admin_headers
        )
        assert answer.status_code == 422, answer.text
        assert "같은 재료" in answer.text
