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


def test_단위가_이름에_박힌_주파수_키도_Hz_로() -> None:
    """2026-11-15: `frequency_hz` 만 읽어, 씨앗의 `frequency_MHz` · `frequency_ghz` 값 약
    300건이 주파수 없는 유전율로 담겼다 — 그런데도 문헌 등급을 달고 카드로 갔다."""
    read = declared_points.catalog_condition
    assert read({"frequency_MHz": 1}, "frequency_hz") == pytest.approx(1e6)
    assert read({"frequency_ghz": 10}, "frequency_hz") == pytest.approx(1e10)
    assert read({"frequency_GHz": 2.4}, "frequency_hz") == pytest.approx(2.4e9)
    assert read({"temperature_f": 212}, "temperature_k") == pytest.approx(373.15)
    assert read({"wavelength_um": 1.55}, "wavelength_m") == pytest.approx(1.55e-6)
    assert read({"frequency_MHz": "1 MHz"}, "frequency_hz") is None, "글은 안 읽는다"


def test_조건_키_표가_서버와_같다() -> None:
    """MCP 는 서버를 import 하지 않는다(HTTP 로만 붙는다) — 표가 두 벌이라 여기서 맞대 본다."""
    from app.shared import declared_conditions, standard_conditions

    for point_key, quantity in (
        (declared_conditions.TEMPERATURE.key, "temperature"),
        (declared_conditions.FREQUENCY.key, "frequency"),
        (declared_conditions.WAVELENGTH.key, "wavelength"),
    ):
        server = standard_conditions.catalog_keys(quantity)
        mine = declared_points.CATALOG_KEYS[point_key]
        assert [one[0] for one in mine] == [one[0] for one in server], point_key
        for (_, factor, offset), (_, want_factor, want_offset) in zip(
            mine, server, strict=True
        ):
            assert factor == pytest.approx(want_factor) and offset == pytest.approx(
                want_offset
            )


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


def test_승인된_값을_덮어쓰면_미리보기가_말한다() -> None:
    """승인은 값에 묶여 있어 덮어쓰면 풀린다(ADR 0049) — 서버는 막지 않으니 사람이
    먼저 알아야 한다."""
    approved = {"item": "탄성계수", "approval": {"by": "김관리", "at": "2026-10-02T01:00:00Z"}}

    warning = declared_points.approval_warning(approved)

    assert warning is not None
    assert "김관리" in warning and "승인이 풀리고" in warning
    assert declared_points.approval_warning({"item": "탄성계수", "approval": None}) is None
    assert declared_points.approval_warning(None) is None
