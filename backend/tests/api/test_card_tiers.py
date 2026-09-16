"""덱 각주의 값 등급 — **덱만 받은 사람이 「이 값 믿을 만한가」 를 파일 안에서 본다.**

시험에서 온 값은 표본 수로       표본 3 → 1
적어 둔 값은 출처로              데이터시트 1 · 사람이 직접 넣은 값 4
등급 줄이 덱 각주에 실린다        솔버 형식이 달라도 같은 줄
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.fitting import card_tiers
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material


def _card(db: Session, *, sample_count: int) -> PropertyCard:
    name = f"TIER{sample_count}"
    material = Material(record_name=name, family="Metal", category="Steel", grade=name)
    db.add(material)
    db.flush()
    card = PropertyCard(
        material_id=material.id,
        label="등급 시험",
        status="published",
        source={"sample_count": sample_count},
        blocks={
            "elastic": {
                "values": {
                    "youngs_modulus": 205e9,
                    "youngs_modulus_source": "measured",
                    "poisson_ratio": 0.29,
                    "poisson_ratio_source": "manual",
                    "density": 7850.0,
                    "density_source": "declared:datasheet",
                    "density_reference": "포스코 카탈로그 2024",
                }
            },
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 440e6},
                    {"plastic_strain": 0.05, "true_stress": 520e6},
                ]
            },
        },
    )
    db.add(card)
    db.commit()
    return card


def test_값마다_근거에서_등급이_나온다(db: Session) -> None:
    card = _card(db, sample_count=3)
    graded = card_tiers.value_tiers(card)
    assert graded["elastic.youngs_modulus"] == 1  # 시험 · 표본 3
    assert graded["elastic.density"] == 1  # 데이터시트에서 옮겨 적음 — 그 제품의 문서
    assert graded["elastic.poisson_ratio"] == 4  # 근거 없이 직접 넣은 값
    assert graded["table"] == 1

    two = _card(db, sample_count=2)
    assert card_tiers.value_tiers(two)["elastic.youngs_modulus"] == 2
    assert card_tiers.worst_tier(two) == 4


def test_등급_줄이_덱_각주에_실린다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    card = _card(db, sample_count=3)
    for fmt in ("dyna", "abaqus"):
        got = client.get(
            f"/api/fitting/cards/{card.id}/export",
            params={"format": fmt, "units": "si"},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        assert "값 등급(1 좋음 ~ 4 계산·추정" in got.text, fmt
        assert "등급 1 — " in got.text and "탄성계수" in got.text
        assert "등급 4 — " in got.text and "푸아송비" in got.text
