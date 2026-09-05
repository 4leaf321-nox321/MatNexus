"""카탈로그 ↔ MatNexus 라벨 매핑 — **어긋나면 여기서 문다.**

매핑 표는 문자열이라 조용히 낡는다: 기준정보 항목을 개명하거나 재료 컬럼을
바꾸면 매핑이 허공을 가리킨다. 그래서 양끝을 실물에 대고 검사한다.
"""

from __future__ import annotations

from app.modules.catalog.mapping import (
    CATEGORY_MAP,
    COLUMN_TARGETS,
    PROPERTY_ITEM_MAP,
)
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import BUILTIN_PROPERTY_ITEMS


class Test물성_매핑:
    def test_declared_자리는_기본_물성_항목에_실재한다(self) -> None:
        """개명(열전도도→열전도율 등)이 확정되면 기본 목록과 이 표를 **함께**
        바꿔야 한다 — 한쪽만 바꾸면 여기서 걸린다."""
        builtin = {value for value, *_ in BUILTIN_PROPERTY_ITEMS}
        declared = {
            target.label for target in PROPERTY_ITEM_MAP.values() if target.place == "declared"
        }
        missing = declared - builtin
        assert not missing, f"기본 물성 항목에 없는 라벨: {sorted(missing)}"

    def test_column_자리는_재료의_실제_컬럼이다(self) -> None:
        for label, column in COLUMN_TARGETS.items():
            assert hasattr(Material, column), (label, column)
        column_labels = {
            target.label for target in PROPERTY_ITEM_MAP.values() if target.place == "column"
        }
        assert column_labels == set(COLUMN_TARGETS), "column 자리와 검증 표가 어긋났다"

    def test_자리는_셋뿐이다(self) -> None:
        places = {target.place for target in PROPERTY_ITEM_MAP.values()}
        assert places <= {"declared", "column", "measured"}


class Test분류_매핑:
    def test_MT_분류_일곱을_전부_덮는다(self) -> None:
        """원본 카탈로그의 category 전수(실측 2026-09-05). 새 스냅샷에서 분류가
        늘면 이관 후 이 목록과 함께 늘린다."""
        assert set(CATEGORY_MAP) == {
            "metal",
            "polymer",
            "ceramic",
            "composite",
            "rubber",
            "foam",
            "molecular",
        }
