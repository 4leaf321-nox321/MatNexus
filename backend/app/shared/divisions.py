"""사업부 표시 순서 — **한 군데서 정한다.**

사업부는 기준정보 축(ADR 0010)이지만 `VocabularyTerm` 에는 순서 칸이 없다. 그래서
정렬을 각자 하면 화면마다 다른 차례로 선다 — 실제로 그랬다: 홈의 표는 여기 순서,
시험 데이터의 거르기는 그룹핑이 준 순서(사실상 무작위), 그래프의 툴팁은 누적
순서였다. 같은 다섯 값이 세 가지 차례로 서면 사람은 그것을 다른 목록으로 읽는다.

**모르는 값은 뒤에 이름순, 「미지정」 은 맨 뒤.** 새 사업부가 생겨도 목록에서
사라지지 않고, 채울 일이 남은 것이 마지막에 눈에 띈다.

순서를 코드에 두는 것이 임시라는 것은 안다 — 사업부가 바뀌면 배포가 필요하다.
기준정보에 순서 칸이 생기면 이 파일이 그것을 읽는 자리가 된다.
"""

from __future__ import annotations

#: 실사용이 정한 차례(2026-08-29).
DIVISION_ORDER: tuple[str, ...] = ("MX", "VD", "DA", "NW", "의료기기")

#: 사업부를 안 적은 시험. 숨기지 않는다 — 채울 일이 남았다는 뜻이다.
UNSET = "미지정"


def rank(division: str | None) -> tuple[int, str]:
    """정렬 열쇠. `sorted(..., key=lambda x: rank(x.division))` 로 쓴다."""
    if not division or division == UNSET:
        return (len(DIVISION_ORDER) + 1, "")
    try:
        return (DIVISION_ORDER.index(division), "")
    except ValueError:
        return (len(DIVISION_ORDER), division)
