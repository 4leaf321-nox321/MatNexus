"""검색 대상과 인덱스가 갈리지 않는가.

**`OR` 가지 하나가 색인이 없으면 나머지 인덱스가 전부 무의미해진다.** 실행
계획이 Seq Scan 으로 떨어지기 때문이다. 실측(합성 5만 건):

    6개 컬럼 OR, 그중 2개만 색인  →  118ms  (Seq Scan)
    4개 컬럼 OR, 전부 색인        →  4.6ms  (BitmapOr → Bitmap Index Scan)

처음에 `record_name`·`alias` 둘만 색인하고 "인덱스를 넣었으니 빨라졌겠지" 하고
넘어갈 뻔했다. 실제로는 **208ms → 214ms 로 아무 변화가 없었다.** 숫자를 재지
않았으면 못 봤다.

**같은 함정에 세 번 빠졌다.** 두 번째는 피커의 값+별칭 `OR`(97ms 대 0.4ms,
`UNION` 으로 고쳤다), 세 번째는 Contract 다 — `family_term_id IN (SELECT ...)`
로 쓰면 그 가지는 인덱스 조건이 아니라 **필터로 강등돼서 BitmapOr 에 못 낀다.**
좁은 검색(4건 일치)이 0.08ms 에서 90ms 로 갔다. 값이 박힌 `IN (id, ...)` 만 낀다.

그래서 이 검사는 성능을 재지 않는다 — 성능이 나오는 **전제**를 지킨다.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase

from app.modules.materials.models import Material
from app.modules.materials.routes import _SEARCH_AXES, _SEARCH_TEXT
from app.modules.vocabulary.models import VocabularyTerm

#: 문자열 컬럼에 남아 있지만 이제 검색이 안 보는 것. Contract 2단계에서 컬럼과
#: 함께 지운다 — 지금 지우면 읽기 전환을 되돌릴 데가 없다.
VESTIGIAL = {"family", "category"}


def _gin(model: type[DeclarativeBase]) -> set[str]:
    # `__table__` 의 선언 타입은 `FromClause` 라 `.indexes` 를 모른다. 실제로는
    # 언제나 `Table` 이다.
    table = cast(Table, model.__table__)
    return {
        next(iter(index.columns)).name
        for index in table.indexes
        if index.dialect_options["postgresql"].get("using") == "gin"
    }


def test_문자열로_훑는_컬럼은_trgm_인덱스가_있다() -> None:
    searched = {column.name for column in _SEARCH_TEXT}
    indexed = _gin(Material)
    assert searched == indexed - VESTIGIAL, (
        f"검색 대상과 trgm 인덱스가 다릅니다. "
        f"색인 없이 검색: {sorted(searched - indexed)} / "
        f"검색 안 하는데 색인: {sorted(indexed - searched - VESTIGIAL)}. "
        f"OR 가지 하나가 색인이 없으면 나머지 인덱스가 통째로 무의미해집니다."
    )


def test_어휘로_거르는_컬럼은_인덱스가_있다() -> None:
    """`family_term_id IN (id, ...)` 가 인덱스를 타야 BitmapOr 에 낀다."""
    table = cast(Table, Material.__table__)
    indexed = {next(iter(index.columns)).name for index in table.indexes}
    for slug, column in _SEARCH_AXES:
        assert column.name in indexed, f"{slug} 의 {column.name} 에 인덱스가 없습니다."


def test_어휘_찾기가_trgm_인덱스를_탄다() -> None:
    """축으로 좁혀도 `normalized ILIKE '%낱말%'` 은 여전히 색인이 필요하다 —
    강종처럼 값이 수만 개인 축이 검색 축이 되는 날이 온다."""
    assert "normalized" in _gin(VocabularyTerm)
