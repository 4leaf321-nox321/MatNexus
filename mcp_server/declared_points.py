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

import math
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


#: 점의 조건 칸 → 문헌 `conditions` 에서 그 축을 읽는 키와 환산 `(키, 배수, 더할 값)` — **앞이
#: 이긴다.** SI = 값 * 배수 + 더할 값. 서버 `standard_conditions.catalog_keys` 와 같은 표다 —
#: 단위가 이름에 박힌 키(`UNIT_KEYS`)가 먼저, 그다음 표준 조건의 이름 · 별칭.
#: `tests/unit/test_mcp_declared_points.py` 가 서버 표와 맞대 본다.
#:
#: **주파수는 일곱 가지로 적혀 있다**(2026-11-15). 전에는 `frequency_hz` 만 읽어 씨앗의
#: `frequency_MHz` · `frequency_ghz` 같은 값 약 300건이 반영하면 주파수 없는 유전율이 됐다 —
#: 그런데도 문헌 등급을 달고 카드로 갔다.
CATALOG_KEYS: dict[str, tuple[tuple[str, float, float], ...]] = {
    "temperature_k": (
        ("temperature_k", 1.0, 0.0),
        ("temperature_c", 1.0, 273.15),
        ("temperature_f", 5 / 9, 459.67 * 5 / 9),
        ("temperature", 1.0, 0.0),
        ("temp", 1.0, 0.0),
        ("t", 1.0, 0.0),
    ),
    "frequency_hz": (
        ("frequency_hz", 1.0, 0.0),
        ("frequency_Hz", 1.0, 0.0),
        ("freq_Hz", 1.0, 0.0),
        ("frequency_MHz", 1e6, 0.0),
        ("frequency_ghz", 1e9, 0.0),
        ("frequency_GHz", 1e9, 0.0),
        # 각주파수(rad/s)와 분당 사이클 — Hz 는 초당 사이클이다.
        ("frequency_rad_per_s", 1 / (2 * math.pi), 0.0),
        ("frequency_rad_s", 1 / (2 * math.pi), 0.0),
        ("frequency_cpm", 1 / 60, 0.0),
        ("frequency", 1.0, 0.0),
        ("freq", 1.0, 0.0),
    ),
    "wavelength_m": (
        ("wavelength_m", 1.0, 0.0),
        ("wavelength_um", 1e-6, 0.0),
        ("wavelength_nm", 1e-9, 0.0),
    ),
}


def catalog_condition(conditions: Mapping[str, Any] | None, key: str) -> float | None:
    """문헌 값의 조건에서 **그 축의 SI 값.** 서버 `declared_conditions.from_catalog` 와 같은 규칙.

    카탈로그는 온도를 `temperature_k` · `temperature_c` 둘로, 주파수를 `frequency_MHz` ·
    `frequency_ghz` …로, 파장을 `wavelength_nm` 로 든다(`CATALOG_KEYS`) — 한 이름만 읽으면 다른
    이름으로 적힌 값의 조건이 빠진다. 숫자로 적힌 것만 읽는다(글은 짐작이 섞인다).
    """
    found = conditions or {}
    for name, factor, offset in CATALOG_KEYS.get(key, ()):
        value = found.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        return float(value) * factor + offset
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


def approval_warning(row: Mapping[str, Any] | None) -> str | None:
    """덮어쓸 줄이 **자료 관리자가 승인한 값**이면 미리보기에 실을 말(ADR 0049, 2026-10-02).

    승인은 그때의 값에 묶여 있어 값이 바뀌면 풀리고 등급이 한 단계 내려간다. 서버가 막지는
    않는다(고칠 권한은 그대로다) — 그래서 덮어쓰기 전에 사람이 알게 미리보기에서 말한다.
    """
    approval = (row or {}).get("approval")
    if not isinstance(approval, Mapping):
        return None
    who = approval.get("by") or "자료 관리자"
    return (
        f"{who} 님이 승인한 값이다 — 값이 바뀌면 승인이 풀리고 등급이 한 단계 내려간다. "
        "덮어쓰기 전에 사용자에게 알려라."
    )
