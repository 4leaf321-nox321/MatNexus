"""검색 대상과 인덱스가 갈리지 않는가.

**`OR` 가지 하나가 색인이 없으면 나머지 인덱스가 전부 무의미해진다.** 실행
계획이 Seq Scan 으로 떨어지기 때문이다. 실측(합성 5만 건):

    6개 컬럼 OR, 그중 2개만 색인  →  118ms  (Seq Scan)
    4개 컬럼 OR, 전부 색인        →  4.6ms  (BitmapOr → Bitmap Index Scan)

처음에 `record_name`·`alias` 둘만 색인하고 "인덱스를 넣었으니 빨라졌겠지" 하고
넘어갈 뻔했다. 실제로는 **208ms → 214ms 로 아무 변화가 없었다.** 숫자를 재지
않았으면 못 봤다.

그래서 이 검사는 성능을 재지 않는다 — 성능이 나오는 **전제**를 지킨다. 검색
컬럼을 하나 늘리면서 인덱스를 잊으면 여기서 걸린다.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Table

from app.modules.materials.models import Material
from app.modules.materials.routes import _SEARCH_COLUMNS


def test_검색하는_컬럼은_전부_trgm_인덱스가_있다() -> None:
    searched = {column.name for column in _SEARCH_COLUMNS}
    # `__table__` 의 선언 타입은 `FromClause` 라 `.indexes` 를 모른다. 실제로는
    # 언제나 `Table` 이다.
    table = cast(Table, Material.__table__)
    indexed = {
        next(iter(index.columns)).name
        for index in table.indexes
        if index.dialect_options["postgresql"].get("using") == "gin"
    }
    assert searched == indexed, (
        f"검색 대상과 trgm 인덱스가 다릅니다. "
        f"색인 없이 검색: {sorted(searched - indexed)} / "
        f"검색 안 하는데 색인: {sorted(indexed - searched)}. "
        f"OR 가지 하나가 색인이 없으면 나머지 인덱스가 통째로 무의미해집니다."
    )
