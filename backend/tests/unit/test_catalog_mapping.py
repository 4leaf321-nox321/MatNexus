"""카탈로그 ↔ MatNexus 라벨 매핑 — **어긋나면 여기서 문다.**

매핑 표는 문자열이라 조용히 낡는다: 기준정보 항목을 개명하거나 재료 컬럼을
바꾸면 매핑이 허공을 가리킨다. 그래서 양끝을 실물에 대고 검사한다.
"""

from __future__ import annotations

from app.modules.catalog.mapping import (
    CATEGORY_MAP,
    COLUMN_TARGETS,
    PROPERTY_ITEM_MAP,
    SI_UNIT_EQUIV,
)
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import BUILTIN_PROPERTY_ITEMS
from matcore.units import SI_UNITS


class Test물성_매핑:
    def test_declared_자리는_기본_물성_항목에_실재한다(self) -> None:
        """개명(열전도율→열전도율 등)이 확정되면 기본 목록과 이 표를 **함께**
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


class Test단위_등가:
    """**값은 양쪽 다 SI 다 — 숫자 변환은 0건이어야 한다.**

    카탈로그 단위 표기(`J/(kg*K)`)와 matcore 정본(`J/(kg.K)`)은 철자만 다르다.
    채택은 SI 값을 그대로 보내므로(`input_unit` 비움 = 정본 SI), 이 등가가
    깨지면 — 어느 쪽이 단위를 바꾸면 — **숫자가 조용히 다른 단위로 저장된다.**
    그것을 여기서 막는다.
    """

    def test_declared_자리의_단위가_대상_차원의_정본과_같다(self) -> None:
        dimensions = {value: dimension for value, dimension, *_ in BUILTIN_PROPERTY_ITEMS}
        for key, target in PROPERTY_ITEM_MAP.items():
            if target.place != "declared":
                continue
            matcore_si = SI_UNITS[dimensions[target.label]]
            assert SI_UNIT_EQUIV.get(target.mt_unit) == matcore_si, (
                f"{key}: MT {target.mt_unit!r} 가 {target.label} 차원의 "
                f"정본 {matcore_si!r} 와 등가가 아니다"
            )

    def test_column_자리의_단위도_등가다(self) -> None:
        # density_si 는 kg/m3, poisson_ratio 는 무차원 — 컬럼 이름이 SI 를 못
        # 박으므로 여기서 못 박는다.
        expected = {"밀도": SI_UNITS["density"], "포아송비": "1"}
        for key, target in PROPERTY_ITEM_MAP.items():
            if target.place != "column":
                continue
            assert SI_UNIT_EQUIV.get(target.mt_unit) == expected[target.label], key


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
