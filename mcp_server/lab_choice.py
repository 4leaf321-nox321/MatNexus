"""의뢰의 받는 부서 추천을 AI 에게 옮기는 판단(ADR 0069 C) — `server.py` 와 떼어 시험한다.

`server.py` 는 mcp SDK 를 불러 백엔드 시험이 못 연다(`declared_points` · `term_gate` 와 같은 자리).

**「모름」 과 「없음」 을 섞지 않는다.** TestScope 에 못 물었으면(off · error) 고른 부서가 추천에
있는지는 모른다 — 거짓으로 말하면 AI 는 「그 부서엔 장비가 없다」 고 옮긴다.
"""

from __future__ import annotations

from typing import Any

#: 서버가 받는 항목 수 · 물성 글자 길이(`LabSuggestionRequest`).
MAX_ITEMS = 20
MAX_HINT = 200
LABS_SHOWN = 8
EQUIPMENT_SHOWN = 5


def asked(items: list[Any]) -> dict[str, Any]:
    """의뢰 항목 → 추천 요청 몸. 서버가 막는 길이는 미리 자른다(422 로 추천이 통째 빠지지 않게)."""
    return {
        "items": [
            {
                "test_type_key": one.get("test_type_key"),
                "property_hint": str(one["property_hint"])[:MAX_HINT]
                if one.get("property_hint")
                else None,
            }
            for one in items[:MAX_ITEMS]
            if isinstance(one, dict)
        ]
    }


def shaped(got: Any) -> dict[str, Any]:
    """서버 답 → AI 가 읽을 모양. 못 읽었으면 `error` 상태다(「없음」 이 아니다)."""
    if not isinstance(got, dict) or "error" in got:
        return {"state": "error", "message": "받는 부서 추천을 읽지 못했습니다."}
    return {
        "state": got.get("state"),
        "message": got.get("message"),
        "labs": [
            {
                "slug": one.get("workspace_slug"),
                "name": one.get("workspace_name"),
                "items": one.get("items"),
                "equipment": [eq.get("name") for eq in one.get("equipment") or []][
                    :EQUIPMENT_SHOWN
                ],
            }
            for one in got.get("labs") or []
        ][:LABS_SHOWN],
        "unresolved": [
            {"item": one.get("item"), "text": one.get("text"), "reason": one.get("reason")}
            for one in got.get("unresolved") or []
        ],
    }


def is_suggested(slug: str, suggestions: dict[str, Any]) -> bool | None:
    """고른 부서가 추천에 있나 — TestScope 에 물었을 때만 참 · 거짓, 아니면 None(모름)."""
    if suggestions.get("state") != "ok":
        return None
    return slug in {one.get("slug") for one in suggestions.get("labs") or [] if one.get("slug")}
