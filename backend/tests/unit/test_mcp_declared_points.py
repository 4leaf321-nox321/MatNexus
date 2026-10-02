"""MCP 가 선언 물성을 **되보낼 때 조건을 안 떨어뜨린다**(2026-10-01).

선언 물성 PATCH 는 통째 교체다. MCP 의 되보내기 셋(문헌 반영 · 선언 값 적기)이 온도만
옮기고 있었는데, 유전율이 주파수를 타게 되면서 그대로 두면 **담기 한 번에 주파수가 조용히
사라진다.** 판단은 `mcp_server/declared_points.py` 에 있다 — `server.py` 는 mcp SDK 를 불러
이 스위트가 못 연다(`term_gate` · `retry_plan` 과 같은 자리).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import declared_points  # noqa: E402


def test_되보낼_때_주파수와_파장이_남는다() -> None:
    saved = [
        {
            "temperature_k": None,
            "frequency_hz": 1e9,
            "wavelength_m": None,
            "value": 3.6,
            "value_si": 3.6,
        },
        {
            "temperature_k": 296.15,
            "frequency_hz": None,
            "wavelength_m": 5.876e-7,
            "value": 1.5,
        },
    ]

    sent = declared_points.resent_points(saved)

    assert sent[0] == {
        "temperature_k": None,
        "frequency_hz": 1e9,
        "wavelength_m": None,
        "value": 3.6,
    }
    assert sent[1]["wavelength_m"] == pytest.approx(5.876e-7)
    assert sent[1]["temperature_k"] == pytest.approx(296.15)


def test_문헌_조건을_축의_SI_로() -> None:
    """서버 `declared_conditions.from_catalog` 와 같은 규칙 — 섭씨 온도도 읽는다."""
    read = declared_points.catalog_condition
    assert read({"temperature_c": 25}, "temperature_k") == pytest.approx(298.15)
    assert read({"temperature_k": 300, "temperature_c": 25}, "temperature_k") == pytest.approx(
        300
    )
    assert read({"frequency_hz": 1e6}, "frequency_hz") == pytest.approx(1e6)
    assert read({"wavelength_nm": 589}, "wavelength_m") == pytest.approx(589e-9)
    assert read(None, "frequency_hz") is None


def test_측정_온도가_점마다_다르면_비우고_적는다() -> None:
    row: dict[str, Any] = {
        "item": "비유전율",
        "points": [
            {"value": 3.6, "frequency_hz": 1e9, "temperature_k": 296.15},
            {"value": 3.8, "frequency_hz": 1e6, "temperature_k": 298.15},
        ],
        "note": "문헌 물성 카탈로그에서 채택 (스냅샷)",
    }

    assert declared_points.drop_mixed_temperatures(row, "frequency_hz") is True
    assert all(point["temperature_k"] is None for point in row["points"])
    assert "측정 온도가 달라" in row["note"]


def test_온도_축이나_같은_온도면_그대로_둔다() -> None:
    same: dict[str, Any] = {
        "points": [
            {"value": 3.6, "frequency_hz": 1e9, "temperature_k": 296.15},
            {"value": 3.8, "frequency_hz": 1e6, "temperature_k": 296.15},
        ],
        "note": None,
    }
    assert declared_points.drop_mixed_temperatures(same, "frequency_hz") is False
    assert same["points"][0]["temperature_k"] == pytest.approx(296.15)

    table: dict[str, Any] = {
        "points": [{"temperature_k": 293.15}, {"temperature_k": 373.15}],
        "note": None,
    }
    assert declared_points.drop_mixed_temperatures(table, "temperature_k") is False
