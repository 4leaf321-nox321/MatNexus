"""항목란의 칸과 기준정보 항목이 **물성 키로** 만난다.

전에는 카드 라우터가 한글 항목 이름을 직접 들고 있었다(`THERMAL_ITEMS`,
`_declared(material, "탄성계수")`). 그 표가 기준정보 씨앗과 따로 놀았으므로,
항목 이름을 고치면 카드가 **오류 없이 비었다** — 값만 사라지는 종류다.

지금은 칸이 자기 물성 키를 들고(`Produced.property_key`), 키 ↔ 이름의 정본은
기준정보 씨앗 하나다. 이 시험은 그 다리가 실제로 이어져 있는지 본다 — 어느 쪽을
고쳐도 여기서 걸린다.
"""

from __future__ import annotations

from app.modules.fitting.routes import FROM_RECORD, _declared_items
from app.modules.vocabulary.definitions import BUILTIN_ITEM_OF_KEY, BUILTIN_PROPERTY_ITEMS
from app.shared import property_names
from matcore import cards


def test_기본_항목란의_칸이_전부_이름을_찾는다() -> None:
    """탄성·열물성의 칸은 **하나도 빠짐없이** 기준정보 항목으로 풀려야 한다.

    하나라도 못 풀면 그 칸은 조용히 비고, 그 재료의 덱에서 값 하나가 없어진다.
    """
    cards.load_builtin()
    for block in ("elastic", "thermal"):
        spec = cards.block(block)
        wanted = [
            slot.key
            for slot in spec.produces
            if slot.property_key and slot.key not in FROM_RECORD
        ]
        found = _declared_items(block)
        assert set(found) == set(wanted), (
            f"{block}: {sorted(set(wanted) - set(found))} 이(가) 안 풀린다"
        )


def test_탄성계수와_열물성이_옛_이름_그대로_풀린다() -> None:
    """**행동이 안 바뀌었다는 증거다.** 정리 전 코드가 들고 있던 이름 그대로여야
    이미 쌓인 선언 물성이 계속 카드로 간다."""
    assert _declared_items("elastic") == {"youngs_modulus": "탄성계수"}
    assert _declared_items("thermal") == {
        "thermal_expansion": "선팽창계수(CTE)",
        "specific_heat": "비열",
        "thermal_conductivity": "열전도율",
    }


def test_물성_키는_기본_항목마다_하나씩이다() -> None:
    """키가 겹치면 뒤엣것이 이긴다 — 이름을 찾을 때 엉뚱한 항목이 나온다."""
    keys = [row[6] for row in BUILTIN_PROPERTY_ITEMS]
    assert len(keys) == len(set(keys))
    assert len(BUILTIN_ITEM_OF_KEY) == len(BUILTIN_PROPERTY_ITEMS)


def test_모르는_키는_이름이_없다() -> None:
    """확장이 선언한 키는 여기서 안 풀린다 — 그쪽은 「사내 항목 연결」 이 잇는다."""
    assert property_names.builtin_item("local.mechanical.barlat_exponent") is None
    assert property_names.builtin_item(None) is None


def test_폭인_물성은_표시가_붙는다() -> None:
    """**단위는 같은데 뜻이 다른 자리다.** WLF C₂ 는 K 로 적히지만 온도가 아니라
    온도 폭이다 — 섭씨로 바꿀 때 영점을 빼면 안 된다.

    지금은 환산하는 곳이 없어 아무 일도 안 나지만, 그 표시를 잃어버리면 「℃ 로
    보기」 를 붙이는 날 51.6 K 가 -221.55 °C 로 뜬다.
    """
    from app.modules.catalog import spans

    assert spans.is_span("mechanical.wlf_c2")
    # 나머지 온도 물성은 절대온도다 — 개발 DB 의 K 단위 정의 12종 중 폭은 하나뿐이다.
    assert not spans.is_span("thermal.glass_transition")
    assert not spans.is_span("thermal.melting_point")
    assert not spans.is_span(None)
