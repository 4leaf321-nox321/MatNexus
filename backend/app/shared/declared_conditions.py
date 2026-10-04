"""선언 물성의 **조건 축** — 값이 무엇에 따라 변하나(온도 · 주파수 · 파장).

## 왜 생겼나 (2026-10-01)

선언 물성은 「항목 한 줄이 온도별 점을 든다」 였다(`materials/declared.py`). 그런데
전기 · 광학 물성은 온도가 아니라 **주파수 · 파장**을 탄다 — 유전율(Dk) · 유전손실(Df)은
1 MHz 와 10 GHz 에서 값이 다르고, 굴절률은 파장마다 다르다. 「1 GHz 의 Dk」 와
「10 GHz 의 Dk」 를 담을 자리가 없어서, 한 값만 적거나 온도 칸에 주파수를 우겨
넣어야 했다 — 뒤엣것은 **숫자는 그럴듯한데 뜻이 다른** 값이다.

문헌 카탈로그는 이미 그 축을 들고 있다(`frequency_hz` 2,399건 · `wavelength_nm` 1,265건,
정의마다 `condition_axes`). 사내 쪽만 온도에 묶여 있었다.

## 규칙

항목마다 **축 하나**(기준정보 「값이 변하는 조건」, 비우면 온도). 점은 그 축의 값을
들고(`frequency_hz` · `wavelength_m`), 점이 둘 이상이면 전부 들어야 하고 서로 달라야
한다 — 온도 축과 같은 규칙이다. 온도가 아닌 축의 항목에도 **측정 온도**는 적을 수 있다
— 점마다 같은 값일 때만(「10 GHz, 23 °C」). 점마다 다르면 2차원 표인데, 그것은 담지
않는다(거절한다): 반쯤 담으면 어느 축이 표의 축인지 덱이 모른다.

`shared` 에 있는 이유: 재료(선언 물성) · 문헌(반영) · 카드(빈 칸 채우기) · 내보내기가
함께 쓴다. 모듈끼리는 `models` 말고 직접 안 부른다(`tests/architecture`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared import standard_conditions


@dataclass(frozen=True)
class Condition:
    """조건 축 하나."""

    label: str
    """기준정보에 적는 이름 — 「온도」 · 「주파수」 · 「파장」."""
    key: str
    """점이 그 값을 드는 칸. **언제나 SI** 다."""
    dimension: str
    """단위 표의 차원."""
    si_unit: str
    units: tuple[str, ...] = ()
    """적을 때 고르는 단위. **단위 표의 차원 목록을 그대로 안 쓴다** — 주파수 차원에는
    `1/s` · `1/min` 이 섞여 있고 MHz · GHz 가 없다(데이터시트는 1 MHz · 10 GHz 로 적는다).
    환산 배수는 서버가 단위 표로 낸다(`matcore.units.to_si`) — 화면은 곱하기만 한다.
    온도는 비어 있다: 화면이 온도 표시 규칙(°C)을 따로 든다."""


TEMPERATURE = Condition("온도", "temperature_k", "temperature", "K")
FREQUENCY = Condition("주파수", "frequency_hz", "frequency", "Hz", ("Hz", "kHz", "MHz", "GHz"))
WAVELENGTH = Condition("파장", "wavelength_m", "length", "m", ("nm", "µm", "m"))

CONDITIONS: dict[str, Condition] = {
    one.label: one for one in (TEMPERATURE, FREQUENCY, WAVELENGTH)
}
DEFAULT = TEMPERATURE
#: 점이 들 수 있는 조건 칸 전부. **다시 보내는 길은 이것을 다 옮긴다** — 온도만 옮기면
#: 주파수가 조용히 빠진다(화면의 문헌 반영 · MCP 가 기존 줄을 되보낼 때).
POINT_KEYS: tuple[str, ...] = tuple(one.key for one in CONDITIONS.values())

AXIS = "property_item"


def of_attributes(attributes: dict[str, Any] | None) -> Condition:
    """항목 속성 → 조건 축. 비거나 모르는 값이면 온도 — 이 칸이 생기기 전의 항목이 그렇다."""
    label = str((attributes or {}).get("condition") or "")
    return CONDITIONS.get(label, DEFAULT)


def of_items(db: Session) -> dict[str, Condition]:
    """사내 물성 항목 이름 → 조건 축. 감춘 항목도 넣는다 — 이미 적힌 값은 읽어야 한다."""
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == AXIS))
    if axis is None:
        return {}
    return {
        term.value: of_attributes(term.attributes)
        for term in db.scalars(
            select(VocabularyTerm).where(VocabularyTerm.vocabulary_id == axis.id)
        )
    }


#: 축 → 문헌 조건을 읽는 양의 이름(`standard_conditions.catalog_keys`).
_QUANTITY = {
    TEMPERATURE.key: "temperature",
    FREQUENCY.key: "frequency",
    WAVELENGTH.key: "wavelength",
}

#: 표준 조건(값 검색 · 커버리지의 조건) → 점이 그 값을 드는 칸. 파장은 아직 표준 조건이 아니다.
POINT_KEY_OF_STANDARD: dict[str, str] = {
    "temperature": TEMPERATURE.key,
    "frequency": FREQUENCY.key,
}


def from_catalog(conditions: dict[str, Any] | None, condition: Condition) -> float | None:
    """문헌 값의 조건에서 **이 축의 SI 값**을 꺼낸다. 없으면 `None`.

    카탈로그의 조건 낱말은 이관 차수마다 달랐다 — 온도는 `temperature_k` 와
    `temperature_c` 가 둘 다 있다(개발 DB 8,458 · 9,597건). 전에는 반영이 `temperature_k`
    만 읽어서 **섭씨로 적힌 문헌 값은 반영하면 온도가 빠졌다**(2026-10-01 실측). 주파수도
    `frequency_hz` 만 읽어 `frequency_MHz` 같은 이름의 값은 빠졌다(2026-10-04) — 이제
    값 검색 · 커버리지와 같은 표(`standard_conditions.UNIT_KEYS`)를 읽는다.
    """
    return standard_conditions.read_catalog(conditions, _QUANTITY[condition.key])


def point_conditions(point: dict[str, Any]) -> dict[str, float | None]:
    """점이 든 조건 칸 전부 — **다시 보낼 때 이것을 그대로 싣는다.**"""
    return {key: point.get(key) for key in POINT_KEYS}
