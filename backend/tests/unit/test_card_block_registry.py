"""표에서 온 항목란이 **내장을 덮지 못한다** (ADR 0033 D2).

## 왜 둘째 방어선이 필요한가

저장할 때도 막는다(`blocks.validate`). 그런데 그 검사는 **저장 시점의 내장 목록**을
본다 — 오늘 `anisotropy` 라는 항목란을 만들어 두고, 반년 뒤 릴리스가 같은 이름의
내장 블록을 더하면 그 행은 **이미 표에 있다.** 그때 기동이 조용히 내장을 덮으면
그 물성을 내는 계산이 다른 칸을 보게 되고, 그 사실은 덱을 열어 보기 전까지 안
드러난다.

그래서 얹는 자리에서 한 번 더 본다. 여기가 그 검사가 살아 있는지 재는 곳이다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from matcore import cards
from matcore.registry import Produced


def _spec(key: str, label: str = "이방성") -> cards.BlockSpec:
    return cards.BlockSpec(
        key=key,
        label=label,
        help="세 방향 인장에서 나오는 r값들.",
        produces=(Produced(key="r_bar", label="평균 이방성", si_unit="1"),),
        order=200,
    )


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    cards.load_builtin()
    yield
    for key in cards.installed():
        cards.uninstall(key)


def test_내장_키는_못_얹는다() -> None:
    cards.load_builtin()
    with pytest.raises(cards.CardError) as failed:
        cards.install(_spec("elastic"))
    assert "내장" in str(failed.value)
    # **내장이 그대로 살아 있다.** 막았는데 값이 바뀌어 있으면 막은 것이 아니다.
    assert cards.block("elastic").label == "탄성"


def test_자기_것은_새_판으로_바꾼다() -> None:
    cards.install(_spec("anisotropy"))
    cards.install(_spec("anisotropy", label="이방성(판재)"))
    assert cards.block("anisotropy").label == "이방성(판재)"
    assert cards.installed() == ["anisotropy"]


def test_내장은_못_뺀다() -> None:
    cards.load_builtin()
    with pytest.raises(cards.CardError):
        cards.uninstall("elastic")
    assert cards.block("elastic") is not None


def test_이름_없는_슬롯은_안_얹는다() -> None:
    """비면 화면에 키가 그대로 뜨고, 그것이 무엇인지는 만든 사람만 안다."""
    empty = cards.BlockSpec(
        key="anisotropy",
        label="이방성",
        help="",
        produces=(Produced(key="r_bar", label="  ", si_unit="1"),),
    )
    with pytest.raises(cards.CardError):
        cards.install(empty)
    assert cards.installed() == []


def test_목록에_섞여_나오되_순서는_order_가_정한다() -> None:
    cards.install(_spec("anisotropy"))
    keys = [spec.key for spec in cards.list_blocks()]
    assert "anisotropy" in keys and "elastic" in keys
    # 기본 200 — **내장들 뒤다.**
    assert keys.index("anisotropy") > keys.index("elastic")
