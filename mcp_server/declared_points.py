"""선언 물성 **점의 조건**을 다루는 순수 함수 — 되보내기와 문헌 조건 옮기기.

## 왜 따로 있나 (2026-10-01)

선언 물성이 온도 말고 주파수 · 파장도 타게 됐다(유전율 · 유전손실 · 굴절률 — 서버의
`shared/declared_conditions`). 선언 물성 PATCH 는 **통째 교체**라, 기존 줄을 되보낼 때
조건 칸을 하나라도 떨어뜨리면 그 조건은 담기 한 번에 조용히 사라진다. 이 서버의 되보내기
셋이 전부 온도만 옮기고 있었다.

`server.py` 는 mcp SDK 를 부르므로 백엔드 시험이 못 연다 — 판단은 여기 두고
`tests/unit/test_mcp_declared_points.py` 가 문다(`term_gate` · `retry_plan` 과 같은 자리).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

#: 점이 드는 조건 칸 — 서버의 `declared_conditions.POINT_KEYS` 와 같다.
POINT_CONDITION_KEYS = ("temperature_k", "frequency_hz", "wavelength_m")


def resent_points(points: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """저장된 점(응답 모양)을 다시 보낼 모양으로 — **조건 칸을 하나도 안 떨어뜨린다.**"""
    return [
        {**{key: point.get(key) for key in POINT_CONDITION_KEYS}, "value": point.get("value")}
        for point in points
    ]


def catalog_condition(conditions: Mapping[str, Any] | None, key: str) -> float | None:
    """문헌 값의 조건에서 **그 축의 SI 값.** 서버 `declared_conditions.from_catalog` 와 같은 규칙.

    카탈로그는 온도를 `temperature_k` · `temperature_c` 둘로, 파장을 `wavelength_nm` 로 든다 —
    `temperature_k` 만 읽으면 섭씨로 적힌 값의 온도가 빠진다.
    """
    found = conditions or {}

    def number(name: str) -> float | None:
        value = found.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    if key == "temperature_k":
        kelvin, celsius = number("temperature_k"), number("temperature_c")
        if kelvin is not None:
            return kelvin
        return celsius + 273.15 if celsius is not None else None
    if key == "frequency_hz":
        return number("frequency_hz")
    if key == "wavelength_m":
        metre, nano = number("wavelength_m"), number("wavelength_nm")
        if metre is not None:
            return metre
        return nano * 1e-9 if nano is not None else None
    return None


def drop_mixed_temperatures(row: dict[str, Any], axis: str) -> bool:
    """주파수 · 파장 축 줄에서 **측정 온도가 점마다 다르면 비운다.** 비웠으면 참.

    주파수와 온도가 함께 변하면 2차원 표인데 서버는 그것을 안 받는다(422). 비운 사실은
    메모에 남긴다 — 조용히 지우지 않는다.
    """
    if axis == "temperature_k":
        return False
    points = row.get("points") or []
    if len({point.get("temperature_k") for point in points}) <= 1:
        return False
    for point in points:
        point["temperature_k"] = None
    row["note"] = f"{row.get('note') or ''} — 값마다 측정 온도가 달라 비웠다".strip(" —")
    return True
