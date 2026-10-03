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

from app.shared.representative import annotate, is_term, semantic_conditions


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


class Test변수_값:
    """식의 변수 값(`conditions.term`)은 그 물성의 스칼라와 겨루지 않는다(2026-10-04).

    전에는 property_key 하나로 묶어, 영률 키에 섞인 Prony E0(유리 상태)가 등급에서
    이기면 탄성계수 대표로 섰다 — 덱 · 비교 · Ashby 로 갔다.
    """

    def test_스칼라와_변수_값은_따로_대표가_선다(self) -> None:
        scalar = Value("E", 3, value_num=200e9, mt_id=1)
        glassy = Value(
            "E", 1, value_num=32000.0, conditions={"term": "E0", "unit_of_term": "MPa"}
        )
        marks = annotate([glassy, scalar])
        assert marks[scalar.id].representative, "등급이 나빠도 스칼라 자리는 스칼라의 것"
        assert marks[scalar.id].n_candidates == 1
        assert marks[glassy.id].representative and marks[glassy.id].n_candidates == 1

    def test_다른_항은_종합하지_않는다(self) -> None:
        """Anand 의 a 와 A 는 조건이 같아도 다른 수다 — 그 둘의 중앙값은 아무것도 아니다."""
        same = {"model": "anand", "set_id": "s1"}
        a = Value(
            "anand", 2, value_num=1.72, conditions={**same, "term": "a", "unit_of_term": "1"}
        )
        big_a = Value(
            "anand",
            2,
            value_num=2800.0,
            conditions={**same, "term": "A", "unit_of_term": "1/s"},
        )
        marks = annotate([a, big_a])
        assert marks[a.id].summary is None and marks[big_a.id].summary is None
        assert marks[a.id].representative and marks[big_a.id].representative

    def test_구분으로_쓴_term_은_그_물성의_값이다(self) -> None:
        """최고 사용온도의 `short` · `long` 은 식의 항이 아니다 — 한 벌의 표지가 없다.

        `term` 만으로 가르면 그런 재료 43곳이 비교 · 덱 · 받아 오기에서 빠졌다(2026-10-04
        실측). 전처럼 한 무리에서 겨룬다.
        """
        short = Value("tmax", 2, value_num=422.15, conditions={"term": "short"}, mt_id=1)
        long = Value("tmax", 2, value_num=366.15, conditions={"term": "long"}, mt_id=2)
        marks = annotate([short, long])
        assert not is_term(short) and not is_term(long)
        assert marks[short.id].n_candidates == 2
        assert [marks[one.id].representative for one in (short, long)].count(True) == 1

    def test_같은_항끼리는_겨룬다(self) -> None:
        better = Value(
            "anand", 1, value_num=2800.0, conditions={"term": "A", "unit_of_term": "1/s"}
        )
        worse = Value(
            "anand", 3, value_num=3100.0, conditions={"term": "A", "unit_of_term": "1/s"}
        )
        marks = annotate([worse, better])
        assert marks[better.id].representative
        assert marks[worse.id].separated_by == "등급"
