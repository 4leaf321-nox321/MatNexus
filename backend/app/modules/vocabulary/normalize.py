"""문자열 정규화 — **저장값과 비교키를 나눈다.**

하나로 하면 반드시 하나가 망가진다. `'ASTM E8'` 과 `'astm-e8'` 을 같다고
*판정*하는 것과, 저장을 `'astme8'` 로 *바꾸는* 것은 다른 일이다. 후자는 되돌릴
수 없고 화면이 이상해진다 — 대소문자와 괄호는 뜻을 갖는 경우가 있다.

## 층 1 — `clean` (저장할 값)

되돌릴 수 없는 변형은 안 한다. 사람이 보는 값은 그대로 두면서, **눈에 같아
보이는데 DB 가 다르게 보는 것**만 없앤다. 실측한 여섯 가지가 전부 여기서
사라진다:

    맥에서 붙여넣기(NFD 자모 분해)  '포스코' ≠ '포스코'
    전각 영문                       (전각 ASTM) ≠ 'ASTM'
    논브레이킹 스페이스              'ASTM\\xa0E8' ≠ 'ASTM E8'
    끝 공백 · 가운데 두 칸 · 제로폭 문자

## 층 2 — `compare_key` (비교키, 저장하지 않는다)

`clean` 에 casefold 를 더한다. 기준정보 값의 유일성과 별칭 조회가 이 키로 돈다 —
`'포스코'` 와 `'Posco'` 는 같은 값이지만 `'포스코(주)'` 는 **다른 값일 수 있다**
(계열사 구분일 수 있다). 그래서 구두점은 여기서 안 지운다.

구두점까지 지우는 더 강한 정규화는 **병합 후보 탐지**의 몫이다(3단계). 거기서는
`'포스코(주)'` 를 후보로 올려 사람에게 묻지, 말없이 합치지 않는다.
"""

from __future__ import annotations

import re
import unicodedata

#: 눈에 안 보이는데 문자열을 가르는 것들. 웹·PDF 복사에서 딸려 온다.
_INVISIBLE = re.compile("[​-‍﻿]")
_SPACES = re.compile(r"\s+")


def clean(value: str | None) -> str | None:
    """저장할 값. 빈 문자열은 `None` 으로 — `''` 와 `NULL` 이 둘로 갈리면 안 된다."""
    if value is None:
        return None
    # NFKC 가 자모 분해·전각·논브레이킹 스페이스를 한 번에 정리한다.
    text = unicodedata.normalize("NFKC", value)
    text = _INVISIBLE.sub("", text)
    text = _SPACES.sub(" ", text).strip()
    return text or None


def compare_key(value: str | None) -> str:
    """비교키. **저장하지 않는다** — 기준정보 값의 `normalized` 컬럼에만 들어간다."""
    cleaned = clean(value)
    return cleaned.casefold() if cleaned else ""


#: 줄에서 상위와 값을 가르는 문자. **탭이 첫째다** — 엑셀에서 두 열을 복사하면
#: 그대로 붙는다. `>` 는 손으로 칠 때 읽기 좋다(`Steel > SECC`).
PARENT_SEPARATORS = ("\t", ">")


def split_parent(line: str) -> tuple[str | None, str]:
    """`Steel<TAB>SECC` → `("Steel", "SECC")`. 구분자가 없으면 상위는 `None`.

    **부모가 있는 축에서만 부른다.** 제조사 값에 `>` 가 들어 있을 수 있는데,
    부모가 없는 축에서 갈라 버리면 멀쩡한 값이 반토막 난다.
    """
    for separator in PARENT_SEPARATORS:
        if separator in line:
            head, _, tail = line.partition(separator)
            return head.strip() or None, tail.strip()
    return None, line
