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

from dataclasses import dataclass


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
