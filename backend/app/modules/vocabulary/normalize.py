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


#: 별칭 열 안에서 여러 표기를 가르는 문자. 엑셀 한 칸에 여러 개를 적는다.
ALIAS_SEPARATORS = (";", ",")


def split_row(line: str, *, has_parent: bool) -> tuple[str | None, str, list[str]]:
    """엑셀에서 복사한 한 줄을 상위·값·별칭으로 가른다.

    **엑셀에서 범위를 복사하면 열이 탭으로 붙는다.** 그래서 파일을 올릴 필요도,
    `.xlsx` 를 읽을 코드도 없다 — 붙여넣기가 곧 흡수 경로다.

        부모 있는 축   Steel <TAB> SECC <TAB> SECC-1;SECC(주)
        부모 없는 축   포스코 <TAB> POSCO;포스코(주)

    ## 왜 고쳤나

    전에는 `partition` 으로 **한 번만** 갈랐다. 그래서 세 열을 붙이면
    `Steel<TAB>SECC<TAB>SECC-1` 이 값 `'SECC<TAB>SECC-1'` 로 조용히 들어갔다 —
    오류도 안 나고 목록에 이상한 값 하나가 남는다.

    **별칭을 함께 받는 이유:** 별칭은 사후 병합보다 싸다. 등록해 두면 값을 만들
    때 게이트가 별칭까지 뒤져서 애초에 중복이 안 생긴다. 그런데 지금은 값을 넣고
    나서 하나씩 달아야 해서, 엑셀에 이미 적혀 있어도 옮길 길이 없었다.
    """
    columns = [part.strip() for part in line.split("	")] if "	" in line else None
    if columns is None:
        # 손으로 친 줄. `>` 는 상위 표기로만 쓰고 별칭은 없다.
        parent, body = split_parent(line) if has_parent else (None, line)
        return parent, body, []

    parent = None
    if has_parent:
        parent = columns.pop(0) or None if columns else None
    value = columns.pop(0) if columns else ""
    aliases: list[str] = []
    for column in columns:
        for separator in ALIAS_SEPARATORS:
            column = column.replace(separator, ALIAS_SEPARATORS[0])
        aliases.extend(
            part.strip() for part in column.split(ALIAS_SEPARATORS[0]) if part.strip()
        )
    return parent, value, aliases
