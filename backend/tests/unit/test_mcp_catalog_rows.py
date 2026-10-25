"""MCP 가 문헌 값의 조건에서 **관리 표지를 백엔드와 같은 규칙으로 뺀다**(2026-10-26).

판단은 `mcp_server/catalog_rows.py` 에 있다 — `server.py` 는 mcp SDK 를 불러 이 스위트가
못 연다. 두 벌이라 어긋나면 AI 에게는 화면이 숨긴 고친 내력이 조건처럼 보이고, 거꾸로 진짜
조건이 빠진다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import catalog_rows  # noqa: E402

from app.shared import representative  # noqa: E402


def test_관리_표지_판정이_백엔드와_같다() -> None:
    assert catalog_rows.BOOKKEEPING_KEYS == representative._BOOKKEEPING_KEYS
    samples = [
        *representative._BOOKKEEPING_KEYS,
        "verdict_tie_note",
        "verdict_tie_axis",
        "temperature_k_before_correction",
        "temperature_k",
        "model",
        "term",
        "set_id",
        "specimen",
        "aging_hours",
    ]
    for key in samples:
        assert catalog_rows.is_bookkeeping(key) == representative.is_bookkeeping(key), key


def test_조건에서_관리_표지만_빠지고_비면_None() -> None:
    conditions = {
        "temperature_k": 296.15,
        "corrected_by": "54차 PA",
        "verdict_tie_note": "길다" * 100,
        "specimen": "dog-bone",
    }
    assert catalog_rows.semantic_conditions(conditions) == {
        "temperature_k": 296.15,
        "specimen": "dog-bone",
    }
    assert catalog_rows.semantic_conditions({"corrected_by": "x"}) is None
    assert catalog_rows.semantic_conditions(None) is None
