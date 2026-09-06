"""선언 카드의 합성 소성 표 — **카드에 실려도 「합성」 이 따라다닌다** (5단계 ①-2).

문헌 값을 채택해 둔(또는 손으로 적은) 사내 재료도 시험 곡선이 없으면 소성
덱을 못 냈다 — 선언 스칼라로 표를 지어 싣되, 카드는 재사용되는 물건이라
표기가 데이터에 박혀야 한다: `source.synthetic_plastic` + 근거 줄 + 덱 각주.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.materials.models import Material


def make_material(db: Session, *, with_strength: bool = True) -> Material:
    rows: list[dict[str, Any]] = [
        {
            "item": "탄성계수",
            "points": [{"temperature_k": None, "value_si": 200e9}],
            "input_unit": "GPa",
            "source": "literature",
            "reference": "핸드북 7판",
        }
    ]
    if with_strength:
        rows += [
            {
                "item": "항복강도",
                "points": [{"temperature_k": None, "value_si": 300e6}],
                "input_unit": "MPa",
                "source": "literature",
                "reference": "핸드북 7판 표 2",
            },
            {
                "item": "인장강도",
                "points": [{"temperature_k": None, "value_si": 450e6}],
                "input_unit": "MPa",
                "source": "standard",
                "reference": "KS D 3512",
            },
            {
                "item": "연신율",
                "points": [{"temperature_k": None, "value_si": 0.25}],
                "input_unit": "1",
                "source": "literature",
                "reference": "핸드북 7판 표 2",
            },
        ]
    material = Material(
        record_name=f"SYN_{'FULL' if with_strength else 'E'}_1.0",
        family="Metal",
        category="Steel",
        grade="SYN",
        poisson_ratio=0.3,
        density_si=7850.0,
        declared_properties=rows,
    )
    db.add(material)
    db.commit()
    return material


class Test미리보기:
    def test_켜기_전에_무엇이_지어지는지_안다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = make_material(db)
        body = client.get(
            f"/api/fitting/cards/declared/preview?material_id={material.id}"
            "&synthesize_plastic=true",
            headers=admin_headers,
        ).json()
        assert body["synthetic"]["ok"] is True
        assert "Hollomon" in body["synthetic"]["model"]
        assert body["synthetic"]["points"] >= 2
        assert "table" in body["blocks"]

    def test_근거가_없으면_이유를_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = make_material(db, with_strength=False)
        body = client.get(
            f"/api/fitting/cards/declared/preview?material_id={material.id}",
            headers=admin_headers,
        ).json()
        assert body["synthetic"]["ok"] is False
        assert "근거가 없습니다" in body["synthetic"]["why"]


class Test만들기:
    def test_합성_표가_실리고_표기가_데이터에_박힌다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = make_material(db)
        made = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": str(material.id),
                "label": "선언+합성",
                "synthesize_plastic": True,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = made.json()
        rows = card["blocks"]["table"]["rows"]
        assert len(rows) >= 2 and rows[0]["plastic_strain"] == 0.0
        # 표기가 데이터에 박힌다 — 화면 배지·덱 각주의 근거.
        assert card["source"]["synthetic_plastic"]["points"] == len(rows)
        assert any("합성 소성 표" in note for note in card["source"]["notes"])
        assert any("합성 입력 항복강도" in note for note in card["source"]["notes"])
        # 소성 표가 생겼으니 곡선 덱 형식이 열린다.
        assert "dyna" in card["available_formats"]

        # 덱까지 따라간다 — BOM 혼합 덱에 실어 각주를 실측.
        deck = client.post(
            "/api/fitting/decks/bom",
            json={"rows": [{"mid": 3, "name": "SYN", "card_id": card["id"]}]},
            headers=admin_headers,
        ).json()
        assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in deck["text"]
        assert "합성 소성 표 — 실측이 아니다" in deck["text"]

    def test_켰는데_못_지으면_카드를_만들지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """조용히 빼면 「소성까지 있는 카드」 인 줄 알고 쓰게 된다."""
        material = make_material(db, with_strength=False)
        refused = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": str(material.id),
                "label": "안 될 카드",
                "synthesize_plastic": True,
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert "합성할 수 없습니다" in refused.json()["error"]["message"]

    def test_안_켜면_전과_같다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = make_material(db)
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": str(material.id), "label": "선언만"},
            headers=admin_headers,
        ).json()
        assert "table" not in card["blocks"]
        assert "synthetic_plastic" not in card["source"]
