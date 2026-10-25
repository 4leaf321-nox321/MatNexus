"""MCP 가 문헌 값의 조건을 AI 에게 옮기는 규칙 — `server.py` 와 떼어 시험한다.

`server.py` 는 mcp SDK 를 불러 백엔드 시험이 못 연다(`declared_points` · `lab_choice` 와 같은 자리).

**관리 표지는 조건이 아니다.** 원본(MaterialTwin)이 고친 내력(`corrected_by` · `verdict_tie_note` …)을 조건 칸에
남겨 두는데, 화면은 숨기고 대표값 순위도 세지 않는다(`app.shared.representative.is_bookkeeping`). MCP 만 그대로
실어, SAC305 한 재료의 `get_catalog_material` 이 값 40개에 69 KB — 그 가운데 조건이 47 KB 였다(2026-10-26 AI 검증).
판정은 백엔드와 같아야 한다 — `tests/unit/test_mcp_catalog_rows.py` 가 대 본다.
"""

from __future__ import annotations

from typing import Any

BOOKKEEPING_KEYS = frozenset(
    {
        "corrected_by",
        "correction_reason",
        "correction_evidence",
        "moved_from_material",
        "moved_from_source",
        "merge_verdict",
        "direction_verbatim",
    }
)


def is_bookkeeping(key: str) -> bool:
    return (
        key in BOOKKEEPING_KEYS or key.startswith("verdict_") or key.endswith("_before_correction")
    )


def semantic_conditions(conditions: Any) -> dict[str, Any] | None:
    """관리 표지를 뺀 조건 — 남는 것이 없으면 None."""
    if not isinstance(conditions, dict):
        return None
    kept = {key: value for key, value in conditions.items() if not is_bookkeeping(str(key))}
    return kept or None
