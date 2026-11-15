"""표준 시험 조건 — **「어떤 조건에서 잰 값인가」 를 기계가 같은 말로 읽게 한다.**

시험 종류는 부서가 만들고(ADR 0006) 조건 칸도 제 이름으로 짓는다 — 한 부서는 `temp`,
다른 부서는 `temperature`, 문헌은 `temperature_c`·`temperature_k`, 선언 물성은
`temperature_k`. 값은 전부 SI 로 정규화돼 있는데 **키가 다르면 같은 조건이 아니다**
— 「80 °C 에서의 항복강도」 를 물으면 어느 것도 걸리지 않았다(2026-09-16,
[계획] 온톨로지 고도화 §2-D).

그래서 **축을 하나 두고 바인딩한다** — 기준정보가 표에 대해 하는 것(ADR 0010)을
조건에 대해 한다. 시험 종류의 조건 칸은 `canonical_key` 로 이 축의 한 항목을
가리키고, 문헌·선언의 키는 여기 별칭으로 풀린다.

## 왜 DB 표가 아니라 코드인가

관계 레지스트리(ADR 0028)와 같은 판단이다. 항목마다 **SI 단위와 「근처」 의 폭**이
붙어 있고 값 검색이 그것으로 환산·거른다 — 표에 두면 누가 단위를 고친 순간 저장된
값의 뜻이 바뀌는데, 그 사실은 검색 결과가 이상해질 때에야 드러난다. 코드에 두면
`tests/architecture` 가 단위 표(`matcore.units`)와 맞대 보고 CI 에서 잡는다.

조건은 **마디가 아니라 값의 한정자**다 — 그래프는 커지지 않는다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import cache
from typing import Any


@dataclass(frozen=True)
class StandardCondition:
    key: str
    label: str
    si_unit: str
    """저장 단위(SI). 물을 때의 단위는 `matcore.units` 가 이것으로 환산한다."""
    near_tolerance_si: float
    """「근처」 를 물었을 때의 기본 폭(SI, ±). 값 검색의 ±10% 를 그대로 쓰면 온도가
    353 K ±35 K 가 되어 「80 °C」 가 「45~115 °C」 로 읽힌다 — 조건은 좁게 묻는다."""
    aliases: tuple[str, ...] = ()
    """시험 종류·문헌·선언이 이 조건을 부르는 다른 이름들. 소문자로 견준다."""
    help: str = ""


STANDARD: dict[str, StandardCondition] = {
    one.key: one
    for one in (
        StandardCondition(
            key="temperature",
            label="온도",
            si_unit="K",
            near_tolerance_si=5.0,
            aliases=("temp", "t", "temperature_k", "temperature_c", "온도", "시험 온도"),
            help="시험 온도. 문헌의 temperature_c 는 273.15 를 더해 K 로 읽는다.",
        ),
        StandardCondition(
            key="strain_rate",
            label="변형률속도",
            si_unit="1/s",
            near_tolerance_si=0.0,  # 0 이면 ±10% — 속도는 자릿수로 갈린다
            aliases=("rate", "strainrate", "eps_dot", "변형률속도", "변형률 속도"),
        ),
        StandardCondition(
            key="frequency",
            label="주파수",
            si_unit="Hz",
            near_tolerance_si=0.0,
            aliases=("freq", "frequency_hz", "주파수"),
        ),
        StandardCondition(
            key="humidity",
            label="상대습도",
            si_unit="1",
            near_tolerance_si=0.05,
            aliases=("rh", "relative_humidity", "습도", "상대습도"),
            help="분율(0~1). 50 %RH 는 0.5.",
        ),
        StandardCondition(
            key="pressure",
            label="압력",
            si_unit="Pa",
            near_tolerance_si=0.0,
            aliases=("p", "압력"),
        ),
        StandardCondition(
            key="crosshead_speed",
            label="크로스헤드 속도",
            si_unit="m/s",
            near_tolerance_si=0.0,
            aliases=(
                "speed",
                "speed_plastic",
                "speed_elastic",
                "crosshead",
                "속도",
                "시험 속도",
            ),
        ),
        StandardCondition(
            key="preload",
            label="예하중",
            si_unit="N",
            near_tolerance_si=0.0,
            aliases=("pre_load", "예하중"),
        ),
        StandardCondition(
            key="aging_time",
            label="노화 시간",
            si_unit="s",
            near_tolerance_si=0.0,
            aliases=("aging", "age_time", "노화 시간", "노화시간"),
        ),
    )
}


def resolve(key: str | None, *, si_unit: str | None = None) -> str | None:
    """조건 칸의 키(또는 문헌·선언의 키)가 어느 표준 조건인가. 모르면 `None`.

    **단위가 어긋나면 잇지 않는다** — `temperature` 라고 적었는데 저장 단위가 `s` 면
    그것은 이름만 온도다. 이어 두면 검색이 초 단위 값을 켈빈으로 읽는다.
    """
    if not key:
        return None
    wanted = key.strip().lower()
    for one in STANDARD.values():
        if wanted != one.key and wanted not in one.aliases:
            continue
        unit_given = si_unit is not None and bool(si_unit.strip())
        # 문헌의 temperature_c 만 예외 — 읽을 때 K 로 옮긴다(값 검색의 catalog 필터).
        celsius = one.key == "temperature" and wanted == "temperature_c"
        if unit_given and si_unit.strip() != one.si_unit and not celsius:  # type: ignore[union-attr]
            return None
        return one.key
    return None


# --- 문헌의 조건 키 ------------------------------------------------------------

#: 문헌(MaterialTwin) `conditions` 에서 **단위가 키 이름에 박힌** 키 → (양, 배수, 더할 값).
#: SI = 값 * 배수 + 더할 값. 파장은 표준 조건이 아니지만 문헌 반영이 읽는다.
#:
#: **세 길이 따로 읽었다**(2026-10-04 실측). 값 검색은 별칭만, 커버리지는 소문자로 접은
#: 별칭만, 문헌 반영은 `frequency_hz` 하나만 — 같은 값의 조건이 화면마다 있다가 없었다.
#: 주파수는 일곱 가지로 적혀 있어서(`frequency_MHz` 194 · `frequency_ghz` 68 ·
#: `frequency_Hz` 18 …) 반영하면 그 값들의 주파수가 빠졌다. 이제 셋 다 이 표를 읽는다.
#:
#: **글은 읽지 않는다** — 「5 Hz」 · 「room temperature」 를 숫자로 풀면 짐작이 섞인다. 예외
#: 하나: 대표값 순위 · 덱 각주는 「550 degC」 처럼 숫자와 단위로 시작하는 온도 글을 읽는다
#: (`read_catalog(text=True)`).
#: 키는 대소문자를 가린다 — SQL 의 JSON 키가 그렇고, 두 길(SQL · 파이썬)은 같은 답을 내야 한다.
UNIT_KEYS: dict[str, tuple[str, float, float]] = {
    "temperature_k": ("temperature", 1.0, 0.0),
    "temperature_c": ("temperature", 1.0, 273.15),
    "temperature_f": ("temperature", 5 / 9, 459.67 * 5 / 9),
    "frequency_hz": ("frequency", 1.0, 0.0),
    "frequency_Hz": ("frequency", 1.0, 0.0),
    "freq_Hz": ("frequency", 1.0, 0.0),
    "frequency_MHz": ("frequency", 1e6, 0.0),
    "frequency_ghz": ("frequency", 1e9, 0.0),
    "frequency_GHz": ("frequency", 1e9, 0.0),
    # 각주파수(rad/s)와 분당 사이클 — Hz 는 초당 사이클이다.
    "frequency_rad_per_s": ("frequency", 1 / (2 * math.pi), 0.0),
    "frequency_rad_s": ("frequency", 1 / (2 * math.pi), 0.0),
    "frequency_cpm": ("frequency", 1 / 60, 0.0),
    # 변형률 속도 · 습도(2026-10-08 실측: strain_rate_s 2,370 · humidity_pct 998 ·
    # relative_humidity_pct 312 · humidity_rh 272 — 셋 다 0~100 이라 % 다). 별칭이 아니라
    # 이름에 단위가 박힌 키라 여기 둔다. reference_strain_rate_s 는 **시험 조건이 아니라
    # 식의 기준**이라 안 넣는다 — 변형률 속도로 읽으면 JC C 의 기준 속도가 시험 속도
    # 행세를 한다.
    "strain_rate_s": ("strain_rate", 1.0, 0.0),
    "humidity_pct": ("humidity", 0.01, 0.0),
    "relative_humidity_pct": ("humidity", 0.01, 0.0),
    "humidity_rh": ("humidity", 0.01, 0.0),
    "wavelength_m": ("wavelength", 1.0, 0.0),
    "wavelength_um": ("wavelength", 1e-6, 0.0),
    "wavelength_nm": ("wavelength", 1e-9, 0.0),
}


@cache
def catalog_keys(quantity: str) -> tuple[tuple[str, float, float], ...]:
    """문헌 `conditions` 에서 이 양을 읽는 키와 환산 `(키, 배수, 더할 값)` — **앞이 이긴다.**

    단위가 이름에 박힌 키가 먼저, 그다음 표준 조건의 이름 · 별칭이다(SI 로 적었다고 본다).
    표는 모듈 상수라 한 번만 짓는다 — 물성 지도가 문헌 칸마다 · 조건마다 다시 지어, 칸 7천 개인
    재료에서 그것만 0.9 초였다(2026-10-26, 프로파일러 기준).
    """
    named = [
        (key, factor, offset)
        for key, (of, factor, offset) in UNIT_KEYS.items()
        if of == quantity
    ]
    standard = STANDARD.get(quantity)
    plain = [
        (alias, 1.0, 0.0)
        for alias in ((standard.key, *standard.aliases) if standard else ())
        if alias.isascii() and alias not in UNIT_KEYS
    ]
    return tuple(named + plain)


#: **글로 적힌 온도** — 「550 degC」 · 「90 C」 · 「573 K」 · 「25 °C」 ·
#: 「200 degC, held 30 min」. 숫자 하나에 단위 하나가 **바로 붙어 시작하는** 것만 읽는다.
#: 범위(「20-22」 · 「-40 to 200」) · 오차(「23 +/- 2」) · 말(「room temperature」 · 「RT」)은
#: 안 읽는다 — 숫자로 풀면 짐작이 섞인다.
#: 단위의 C · F 는 온도 칸 안에서만 섭씨 · 화씨다(바깥에서는 C 가 쿨롱일 수도 있어 단위표가
#: 안 받는다). 환산은 `UNIT_KEYS` 의 `temperature_c` · `temperature_f` 와 같은 수다.
_TEMPERATURE_TEXT = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?)\s*(°\s*[CF]|℃|deg\s*[CF]|[CFK])(?![A-Za-z0-9])", re.IGNORECASE
)
_TEMPERATURE_TEXT_UNITS: dict[str, tuple[float, float]] = {
    "c": UNIT_KEYS["temperature_c"][1:],
    "f": UNIT_KEYS["temperature_f"][1:],
    "k": UNIT_KEYS["temperature_k"][1:],
}


@cache
def _temperature_text(text: str) -> float | None:
    """글 하나 → K. 못 읽으면 `None`. 같은 글이 순위 비교마다 다시 오므로 기억해 둔다."""
    found = _TEMPERATURE_TEXT.match(text)
    if found is None:
        return None
    letter = found.group(2)[-1].lower()
    factor, offset = _TEMPERATURE_TEXT_UNITS[letter]
    return float(found.group(1)) * factor + offset


def read_catalog(
    conditions: dict[str, Any] | None, quantity: str, *, text: bool = False
) -> float | None:
    """문헌 값의 조건에서 이 양을 SI 로. **숫자로 적힌 것만** — 없으면 `None`.

    `text` 를 켜면 숫자가 하나도 없을 때 **글로 적힌 온도**(「550 degC」)도 읽는다 — 온도만.
    대표값 순위와 덱 각주가 켠다(2026-11-15): 글로 적힌 538 °C 값을 「온도 미기재」 로 쳐서
    벌점 5 K 만 주면 상온 값 대신 대표가 됐다. 값 검색 · 커버리지 · 반영은 끈 채다 — SQL 길과
    같은 답을 내야 한다(머리말의 `UNIT_KEYS`).
    """
    found = conditions or {}
    keys = catalog_keys(quantity)
    for key, factor, offset in keys:
        raw = found.get(key)
        if isinstance(raw, int | float) and not isinstance(raw, bool):
            return float(raw) * factor + offset
    if text and quantity == "temperature":
        for key, _, _ in keys:
            raw = found.get(key)
            if isinstance(raw, str):
                kelvin = _temperature_text(raw)
                if kelvin is not None:
                    return kelvin
    return None


def describe() -> list[dict[str, object]]:
    """온톨로지 지도(`GET /api/ontology`)에 실리는 모양."""
    return [
        {
            "key": one.key,
            "label": one.label,
            "si_unit": one.si_unit,
            "aliases": list(one.aliases),
            "help": one.help,
        }
        for one in STANDARD.values()
    ]
