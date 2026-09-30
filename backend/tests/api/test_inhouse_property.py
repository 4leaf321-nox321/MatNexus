"""사내 물성을 들여 **카드와 덱까지** — 해석 프로그램 전용 물성 한 줄기(2026-09-30).

사용자 물음: 「eCAE 물성을 선언 물성으로 정의해 넣고, 거기 맞는 내보내기를 AI 로
만들 수 있나」.
사슬은 여섯 걸음이고, 전부 AI(MCP) 경유로 된다 — 여기서 `X-Client: mcp` 로 끝까지 밟는다:

    물성 키 → 사내 물성 항목 → 물성 연결 → 카드 항목란 → 선언 값 → 카드(항목란 골라 싣기) → 덱

무는 것:

    항목 차원은 만들 때 적는다        전에는 숫자 속성만 받아서, 관리자가 따로 붙여야 했다
    항목란 칸의 물성 키는 실재한다     없는 키면 아무것도 안 채워진다
    칸 단위와 키의 차원이 같다         다르면 단위계를 바꿔 내보낼 때 환산이 조용히 어긋난다
    AI 가 한 세 걸음은 감사에 남는다   항목 · 연결 · 항목란 — 셋 다 전 부서에 먹는다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.modules.vocabulary.definitions import (
    ensure_builtin_axis_fields,
    ensure_builtin_vocabularies,
)

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "ECAE",
    "spec_thickness": 1.0,
    "spec_thickness_unit": "mm",
}


@pytest.fixture(autouse=True)
def _axes(db: Session) -> None:
    """사내 물성 항목 축과 그 칸(차원 · 기호 · 붙는 곳) — 운영은 배포가 심는다
    (`scripts/refresh_builtins.py`)."""
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    db.commit()


def _ok(response: Any, status: int = 201) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def test_eCAE_전용_물성이_선언_값에서_카드와_덱까지_간다(
    client: TestClient, admin_headers: dict[str, str], db: Session
) -> None:
    ai = {**admin_headers, "X-Client": "mcp"}

    # ① 물성 키(문헌 물성) — 없으면 만든다.
    key = _ok(
        client.post(
            "/api/catalog/properties",
            json={
                "name": "eCAE 마찰계수",
                "domain": "mechanical",
                "slug": "ecae_friction",
                "si_unit": "1",
            },
            headers=ai,
        )
    )["key"]
    # ② 사내 물성 항목 — **차원 · 기호 · 붙는 곳을 만들 때 함께**(전에는 숫자 속성만 받았다).
    term = _ok(
        client.post(
            "/api/vocabularies/property_item/terms",
            json={
                "value": "eCAE 마찰계수",
                "attributes": {"dimension": "dimensionless", "symbol": "mu", "level": "재료"},
            },
            headers=ai,
        )
    )
    assert term["attributes"]["symbol"] == "mu"
    # ③ 물성 연결.
    _ok(
        client.post(
            "/api/catalog/properties/links",
            json={"item": "eCAE 마찰계수", "property_key": key},
            headers=ai,
        )
    )
    # ④ 카드 항목란 — 칸이 그 물성 키를 가리킨다.
    _ok(
        client.post(
            "/api/fitting/block-definitions",
            json={
                "key": "ecae",
                "label": "eCAE 전용",
                "produces": [
                    {
                        "key": "friction",
                        "label": "마찰계수",
                        "si_unit": "1",
                        "property_key": key,
                    }
                ],
            },
            headers=ai,
        )
    )
    # ⑤ 재료에 선언 값.
    material = _ok(client.post("/api/materials", json=SECC, headers=admin_headers))
    _ok(
        client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "eCAE 마찰계수",
                        "points": [{"value": 0.15}],
                        "source": "standard",
                        "reference": "eCAE 사내 기준 v3",
                    }
                ]
            },
            headers=ai,
        ),
        200,
    )
    # ⑥ 카드 — 고를 수 있는 항목란에 서고, 고르면 실린다.
    preview = _ok(
        client.get(
            "/api/fitting/cards/declared/preview",
            params={"material_id": material["id"]},
            headers=admin_headers,
        ),
        200,
    )
    assert "ecae" in {one["key"] for one in preview["fillable"]}
    card = _ok(
        client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "eCAE 카드", "block_keys": ["ecae"]},
            headers=ai,
        )
    )
    assert card["blocks"]["ecae"]["values"]["friction"] == 0.15
    # ⑦ 덱 — 정의가 `ecae.friction` 을 가리키면 그 값이 나간다.
    drawn = _ok(
        client.post(
            "/api/fitting/export-profiles/preview",
            json={
                "definition": {
                    "label": "eCAE",
                    "extension": "ecae",
                    "describe": "eCAE 재료 카드",
                    "lines": [
                        {"text": "MATERIAL {id}"},
                        {"fields": [{"value": "ecae.friction", "format": ["spec", ".3f"]}]},
                    ],
                },
                "card_id": card["id"],
                "units": "si",
            },
            headers=admin_headers,
        ),
        200,
    )
    assert drawn["error"] is None, drawn
    assert "0.150" in drawn["text"]

    # **AI 가 한 세 걸음은 감사에 남는다** — 셋 다 전 부서에 먹는다.
    actions = {
        row.action
        for row in db.scalars(select(AuditEntry).where(AuditEntry.action.like("%by_client")))
    }
    assert {
        "vocabulary.term_created_by_client",
        "property_link.created_by_client",
        "card_block.saved_by_client",
    } <= actions


def test_항목란_칸의_물성_키는_실재하고_차원이_같아야_한다(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    def block(slot: dict[str, Any]) -> Any:
        return client.post(
            "/api/fitting/block-definitions",
            json={"key": "probe_block", "label": "검사", "produces": [slot]},
            headers=admin_headers,
        )

    missing = block(
        {"key": "friction", "label": "마찰계수", "si_unit": "1", "property_key": "local.none"}
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["code"] == "MNX-CARDBLOCK-0009"

    key = _ok(
        client.post(
            "/api/catalog/properties",
            json={
                "name": "검사 강성",
                "domain": "mechanical",
                "slug": "probe_stiff",
                "si_unit": "Pa",
            },
            headers=admin_headers,
        )
    )["key"]
    # 칸은 무차원인데 키는 응력 — 단위계를 바꿔 내보낼 때 환산이 조용히 어긋난다.
    crossed = block({"key": "stiff", "label": "강성", "si_unit": "1", "property_key": key})
    assert crossed.status_code == 422, crossed.text
    assert crossed.json()["error"]["code"] == "MNX-CARDBLOCK-0010"
    # 같은 차원이면 된다(MPa 도 응력이다).
    assert (
        block(
            {"key": "stiff", "label": "강성", "si_unit": "Pa", "property_key": key}
        ).status_code
        == 201
    )


def test_사내_물성_항목의_차원은_고를_수_있는_것만(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    bad = client.post(
        "/api/vocabularies/property_item/terms",
        json={"value": "검사 물성", "attributes": {"dimension": "furlong"}},
        headers=admin_headers,
    )
    assert bad.status_code == 422, bad.text
    # 고를 수 있는 것 전부를 알려 준다 — AI 가 그것을 보고 고친다.
    assert "dimensionless" in bad.json()["error"]["message"]
