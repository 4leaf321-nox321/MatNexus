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

import pytest

from app.shared import standard_conditions
from app.shared.representative import annotate, is_term, off_room, semantic_conditions


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


class Test온도_읽기:
    """순위의 온도는 `standard_conditions.read_catalog` 로 읽는다(2026-11-15).

    전에는 `temperature_k` · `temperature_c` 둘만 읽어 °F 칸과 글로 적힌 온도(「550 degC」
    135건)가 「미기재」 가 됐다 — 벌점 5 K 만 받아 550 °C 값이 상온 값과 거의 같은 자리에 섰다.
    아래 둘은 전에는 온도 쪽 값이 **조건 수로 이겼다**(둘 다 벌점 5 K, 조건 1개 < 2개).
    """

    def test_글로_적힌_550_도는_미기재가_아니다(self) -> None:
        hot = Value("k", 2, conditions={"temperature": "550 degC"}, mt_id=1)
        bare = Value("k", 2, conditions={"specimen": "bar", "method_detail": "x"}, mt_id=2)
        marks = annotate([hot, bare])
        assert marks[bare.id].representative
        assert marks[hot.id].separated_by == "온도"

    def test_화씨_칸도_읽는다(self) -> None:
        hot = Value("k", 2, conditions={"temperature_f": 1000}, mt_id=1)
        bare = Value("k", 2, conditions={"specimen": "bar", "method_detail": "x"}, mt_id=2)
        marks = annotate([hot, bare])
        assert marks[bare.id].representative
        assert marks[hot.id].separated_by == "온도"

    def test_등급은_여전히_온도보다_앞이다(self) -> None:
        """의도다(사용자 결정) — 상온이 아닌 대표는 덱이 그 온도를 적는다(`off_room`)."""
        hot = Value("k", 1, conditions={"temperature_c": 538}, mt_id=1)
        room = Value("k", 2, conditions={"temperature_k": 296.15}, mt_id=2)
        marks = annotate([hot, room])
        assert marks[hot.id].representative
        assert off_room(hot.conditions) == pytest.approx(811.15)
        assert off_room(room.conditions) is None
        assert off_room({"temperature_c": 27}) is None, "23 ± 5 °C 는 상온이다"
        assert off_room({"temperature": "room temperature"}) is None
        assert off_room(None) is None

    @pytest.mark.parametrize(
        ("text", "kelvin"),
        [
            ("550 degC", 823.15),
            ("90 C", 363.15),
            ("573 K", 573.0),
            ("25 °C", 298.15),
            ("50C", 323.15),
            ("200 degC, held 30 min", 473.15),
            ("23 C / 50 %RH", 296.15),
            ("212 F", 373.15),
        ],
    )
    def test_숫자와_단위로_시작하는_글만_읽는다(self, text: str, kelvin: float) -> None:
        read = standard_conditions.read_catalog
        assert read({"temperature": text}, "temperature", text=True) == pytest.approx(kelvin)
        # 끄면(값 검색 · 커버리지 · 반영) 전처럼 글을 안 읽는다 — SQL 길과 같은 답.
        assert read({"temperature": text}, "temperature") is None

    @pytest.mark.parametrize(
        "text",
        ["room temperature", "RT", "20-22", "-40 to 200", "23 +/- 2", "not printed", "180"],
    )
    def test_범위_오차_말은_안_읽는다(self, text: str) -> None:
        read = standard_conditions.read_catalog
        assert read({"temperature": text}, "temperature", text=True) is None

    def test_숫자가_글보다_앞이다(self) -> None:
        read = standard_conditions.read_catalog
        both = {"temperature": "550 degC", "temperature_c": 25}
        assert read(both, "temperature", text=True) == pytest.approx(298.15)


class Test범위의_끝:
    """하한 · 상한 줄은 범위 가운데 값 뒤로(2026-11-17, `value_bounds`).

    개발 DB: 하한 · 상한 줄만 있는 재료 · 물성 748쌍(영률 63 · 선팽창계수 214)에서 대표가 곧 그
    끝이었고 표지가 없었다. 등급이 좋은 하한은 「typical」 도 이겼다.
    """

    def test_등급이_좋은_하한도_가운데_값에_진다(self) -> None:
        lower = Value("k", 1, conditions={"bound": "lower"}, mt_id=1)
        typical = Value("k", 3, conditions={"value_type": "typical"}, mt_id=2)
        marks = annotate([lower, typical])
        assert marks[typical.id].representative
        assert marks[lower.id].separated_by == "범위의 끝"
        assert marks[lower.id].bound == "lower"
        assert marks[typical.id].bound is None

    def test_끝만_있으면_끝이_대표로_서되_그렇다고_말한다(self) -> None:
        lower = Value(
            "k", 1, conditions={"bound": "lower — 원문은 `400 to 700` 구간이다"}, mt_id=1
        )
        upper = Value("k", 1, conditions={"bound": "upper"}, mt_id=2)
        marks = annotate([lower, upper])
        winner = next(one for one in (lower, upper) if marks[one.id].representative)
        assert marks[winner.id].bound in ("lower", "upper")


class Test범위의_끝_읽기:
    @pytest.mark.parametrize(
        ("conditions", "side"),
        [
            ({"bound": "lower"}, "lower"),
            ({"bound": "min"}, "lower"),
            ({"bound": "range_lower"}, "lower"),
            ({"bound": "lower_limit"}, "lower"),
            ({"bound": "lower bound of printed range"}, "lower"),
            ({"bound": "upper — LONGEST-life boundary of the scatter band"}, "upper"),
            ({"bound": "max"}, "upper"),
            ({"value_type": "minimum (guaranteed spec floor)"}, "lower"),
            ({"value_type": "guaranteed minimum (원문 '>=' 표기)"}, "lower"),
            ({"value_type": "maximum (spec ceiling)"}, "upper"),
            ({"statistic": "minimum of 8 measurements"}, "lower"),
            ({"statistic": "maximum of the printed pair"}, "upper"),
            ({"statistic": "maximum"}, "upper"),
        ],
    )
    def test_끝(self, conditions: dict[str, Any], side: str) -> None:
        from app.shared import value_bounds

        assert value_bounds.side(conditions) == side

    @pytest.mark.parametrize(
        "conditions",
        [
            {"value_type": "typical"},
            {"statistic": "mean of 5 specimens"},
            # 곡선의 극값 · 분포의 모수는 측정값들의 최소가 아니다.
            {"statistic": "minimum of the alpha_i vs T curve"},
            {"statistic": "3P-Weibull minimum (safe) life parameter alpha"},
            {"bound": "midpoint"},
            None,
        ],
    )
    def test_끝이_아니다(self, conditions: dict[str, Any] | None) -> None:
        from app.shared import value_bounds

        assert value_bounds.side(conditions) is None
