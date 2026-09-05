"""대표값 선택 — **고르되, 진 후보를 숨기지 않는다.**

무는 것이 넷이다.

    실측이 추정을 이긴다        tier 낮은 쪽이 대표
    온도 적은 실측이 이긴다      「25℃」 가 「온도 미기재」 를 이긴다
    용융값은 대표가 못 된다      solder 의 용융 물성이 카드에 실리면 안 된다
    관리 표지는 조건이 아니다    정정 이력이 조건 수를 부풀리면 안 된다
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.modules.catalog.representative import annotate, semantic_conditions


@dataclass
class Value:
    property_key: str
    quality_tier: int
    value_num: float | None = 1.0
    conditions: dict[str, Any] | None = None
    mt_id: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class Test순위:
    def test_실측이_추정을_이긴다(self) -> None:
        measured = Value("k", 1, mt_id=2)
        assumed = Value("k", 4, conditions={"assumption": True}, mt_id=1)
        marks = annotate([assumed, measured])
        assert marks[measured.id].representative
        assert not marks[assumed.id].representative
        assert marks[assumed.id].separated_by == "등급"
        assert marks[assumed.id].n_candidates == 2

    def test_온도_적은_실측이_미기재를_이긴다(self) -> None:
        with_temp = Value("k", 1, conditions={"temperature_k": 298.15}, mt_id=2)
        without = Value("k", 1, mt_id=1)
        marks = annotate([without, with_temp])
        assert marks[with_temp.id].representative
        assert marks[without.id].separated_by == "온도"

    def test_용융값은_대표가_못_된다(self) -> None:
        solid = Value("k", 3, mt_id=2)
        molten = Value("k", 1, conditions={"state": "molten"}, mt_id=1)
        marks = annotate([molten, solid])
        assert marks[solid.id].representative, "등급이 좋아도 용융이면 진다"
        assert marks[molten.id].separated_by == "상태"

    def test_후보가_하나면_그냥_대표다(self) -> None:
        only = Value("k", 4)
        marks = annotate([only])
        assert marks[only.id].representative and marks[only.id].n_candidates == 1

    def test_물성이_다르면_무리가_다르다(self) -> None:
        first = Value("a", 1)
        second = Value("b", 4)
        marks = annotate([first, second])
        assert marks[first.id].representative and marks[second.id].representative


class Test관리_표지:
    def test_정정_이력은_조건_수에_안_센다(self) -> None:
        # 정정 표지 셋이 붙어도 「조건 없는 값」 과 같은 급이어야 한다.
        corrected = Value(
            "k",
            1,
            conditions={
                "corrected_by": "54차 PA",
                "correction_reason": "표 오독",
                "verdict_tie_axis": "temperature",
                "value_before_correction": 1.0,
            },
            mt_id=2,
        )
        plain = Value("k", 1, conditions={"grade_scope": "class"}, mt_id=1)
        assert semantic_conditions(corrected.conditions) == {}
        marks = annotate([plain, corrected])
        # 관리 표지만 있는 쪽이 조건 0개라 「조건 수」 에서 이긴다.
        assert marks[corrected.id].representative
        assert marks[plain.id].separated_by == "조건 수"
