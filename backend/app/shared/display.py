"""사람이 보고 적는 단위 — **저장은 SI, 화면은 CAE 단위계(mm·N·tonne).**

## 왜 여기에 있는가

「밀도를 무엇으로 보여 주는가」를 재료 모듈과 적합 모듈이 각자 적고 있었다.
둘 다 `kg/m³` 를 문장에 손으로 박아 넣었고, 표시 단위를 바꾸는 순간 한쪽만
바뀔 수 있었다 — 그러면 **같은 값이 화면 두 곳에서 10¹² 배 다르게 적힌다.**

모듈끼리 부르지 않는 것이 이 저장소의 규칙이라, 공유는 `shared` 를 거친다.

## 저장은 바뀌지 않았다

`matcore/units.py` 첫 문단이 적어 둔 그대로다 — 이전 앱이 밀도를 `tonne/mm³`
로 **저장**해서, 다른 솔버를 붙일 때 어디서 변환이 일어났는지 추적할 수 없었다.
그 판단은 유효하고, 여기서 정하는 것은 **사람이 보는 숫자**뿐이다.
"""

from __future__ import annotations

from matcore import units

#: 길이. 도면·규격이 mm 로 적힌다.
LENGTH_UNIT = "mm"

#: 밀도. CAE 단위계(mm·N·tonne)의 밀도다 — 강이 `7.85e-9`.
#:
#: **위첨자 없는 표기다.** `matcore/units` 표가 아는 기호가 `tonne/mm3` 이고,
#: 값과 함께 이 문자열이 그대로 API 를 오간다.
DENSITY_UNIT = "tonne/mm3"


def quantity(value: float, symbol: str, *, digits: int = 4) -> str:
    """SI 값 하나를 **사람이 읽는 문장 조각**으로. `7850` → `7.85e-09 tonne/mm3`.

    서버가 문장을 만드는 자리가 있다(「시료마다 밀도가 다릅니다(…)」). 그 문장
    안의 숫자만 SI 로 남으면, 화면의 다른 칸과 단위가 달라져 사람이 둘을
    비교하다 틀린다.
    """
    return f"{units.from_si(value, symbol):.{digits}g} {symbol}"


def density_text(value: float, *, digits: int = 4) -> str:
    """SI 밀도(kg/m³)를 화면 단위로 적은 문자열."""
    return quantity(value, DENSITY_UNIT, digits=digits)
