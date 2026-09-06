"""선언 물성의 층 — **항목이 아니라 값의 성격이 가른다** (2026-09-06).

ADR 0016 의 표: 문헌·규격(Grade 같으면 같다) → 재료 / 밀시트(로트마다 다르다)
→ 시료. 항복강도라도 문헌의 공칭값은 재료감이다 — 문헌 카탈로그 채택에서
실측으로 걸렸다(강도값 2,837건이 전부 공칭인데 항목 층 때문에 못 담겼다).

    재료 + 항복강도 + literature/standard/estimate   허용 (공칭값)
    재료 + 항복강도 + datasheet                      거부 (밀시트일 수 있다 — 시료로)
    시료 + 탄성계수                                  거부 그대로 (로트마다 다르지 않다)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.materials import declared
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.shared.errors import AppError


@pytest.fixture()
def material(db: Session) -> Material:
    ensure_builtin_property_items(db)
    one = Material(record_name="SUS304_-_-", family="Metal", category="Steel", grade="SUS304")
    db.add(one)
    db.commit()
    return one


def strength_row(source: str) -> dict[str, Any]:
    return {
        "item": "항복강도",
        "points": [{"value": 205}],
        "input_unit": "MPa",
        "source": source,
        "reference": "핸드북 표 3",
    }


class Test재료의_공칭_강도:
    def test_문헌_공칭값은_재료에_담긴다(
        self, client: TestClient, admin_headers: dict[str, str], material: Material
    ) -> None:
        changed = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [strength_row("literature")]},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        rows = changed.json()["declared_properties"]
        assert len(rows) == 1 and rows[0]["item"] == "항복강도"
        # MPa 로 적어도 저장은 정본 SI — 층 우회가 단위 검사를 우회하면 안 된다.
        assert rows[0]["points"][0]["value_si"] == pytest.approx(205e6)

    def test_밀시트_출처면_여전히_시료로_보낸다(
        self, client: TestClient, admin_headers: dict[str, str], material: Material
    ) -> None:
        """로트 증명 문서의 값이 Grade 전체의 값이 되는 것 — 원래 가드레일이다."""
        refused = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [strength_row("datasheet")]},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        message = refused.json()["error"]["message"]
        assert "시료" in message and "로트마다" in message
        # 공칭 시트의 값이 막혔을 때 빠져나갈 길을 말해 준다.
        assert "출처를 문헌·규격으로" in message

    def test_시료에_재료_항목은_그대로_막힌다(self, db: Session, material: Material) -> None:
        """반대 방향은 완화가 아니다 — 탄성계수는 로트마다 다르지 않다."""
        with pytest.raises(AppError) as caught:
            declared.check(
                db,
                [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 206}],
                        "input_unit": "GPa",
                        "source": "literature",
                        "reference": "핸드북",
                    }
                ],
                level="시료",
            )
        assert "재료" in str(caught.value)
