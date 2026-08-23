"""물성 블록 레지스트리 — **새 물성 1종에 파일 하나.**

여기서 지키는 것은 셋이다.

    선언만으로 화면이 그려진다      이름 없는 블록은 등록이 거절한다
    모르는 블록에 소리를 낸다       조용히 넘기면 덱에 그 물성만 빠진다
    덱에 실리는지는 렌더러가 안다   블록이 스스로 말하면 실제와 어긋날 수 있다

"한 자리를 둘이 채우면 거절한다" 는 시험이 여기 있었다. **구조가 그 문제를
없앴다** — 카드 양식(`export.Card`)이 사라져서 두 블록이 같은 칸을 두고 다툴 일이
없다. 렌더러가 필요한 블록을 이름으로 읽는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import cards, export
from matcore.registry import Produced

cards.load_builtin()


@pytest.fixture
def sandbox() -> Any:
    """레지스트리를 건드리는 시험용. 끝나면 원래대로 돌린다."""
    saved = cards.list_blocks()
    yield
    cards.clear()
    for spec in saved:
        cards.register_block(spec)


class TestDeclaration:
    def test_모든_블록이_뜻을_들고_있다(self) -> None:
        """**화면이 이 선언만으로 그린다** — 비면 키가 그대로 뜬다."""
        for spec in cards.list_blocks():
            assert spec.label.strip(), spec.key
            assert spec.help.strip(), spec.key
            for item in (*spec.produces, *spec.rows):
                assert item.label.strip(), f"{spec.key}.{item.key}"

    def test_이름_없는_선언은_거절한다(self, sandbox: Any) -> None:
        with pytest.raises(ValueError, match="이름이 없습니다"):
            cards.register_block(
                cards.BlockSpec(
                    key="anonymous",
                    label="이름 없는 것",
                    help="시험용",
                    produces=(Produced(key="x", label="  "),),
                )
            )

    def test_같은_key_는_두_번_못_넣는다(self, sandbox: Any) -> None:
        with pytest.raises(ValueError, match="중복"):
            cards.register_block(
                cards.BlockSpec(key="elastic", label="또 탄성", help="시험용")
            )


class TestDeck:
    """**블록이 덱에 어떻게 실리는지는 블록이 모른다.**

    전에는 블록이 `to_card` 로 "나는 솔버 카드의 이 칸에 들어간다" 를 적었다.
    그러면 `export.Card` 라는 정해진 양식이 있어야 하고, 물성이 늘 때마다 그
    양식에 칸을 뚫어야 한다. 지금은 렌더러가 블록을 직접 읽는다.
    """

    def test_모르는_블록을_짚는다(self) -> None:
        """조용히 넘기면 **덱에 그 물성만 빠진 채로 나가고, 덱은 멀쩡히 돈다.**"""
        assert cards.unknown({"elastic": {}, "ogden": {}}) == ("ogden",)

    def test_아는_블록만_있으면_조용하다(self) -> None:
        assert cards.unknown({"elastic": {}, "viscoelastic": {}}) == ()

    def test_덱에_실리는_블록은_렌더러가_정한다(self) -> None:
        """**경화식은 덱에 안 실린다** — 표로 나가고 식은 주석에만 남는다.

        전에는 블록이 스스로 그렇게 선언했는데, 실제로 쓰이는지와 어긋날 수
        있었다. 지금은 등록된 솔버들이 실제로 요구하는 것에서 나온다."""
        in_decks = export.blocks_in_decks()
        assert {"elastic", "table", "viscoelastic", "hyperelastic"} <= in_decks
        assert "hardening" not in in_decks


class TestFormats:
    """**누르기 전에 알아야 한다.** 못 내는 형식을 미리 짚는다."""

    def _deck(self, **blocks: Any) -> export.Deck:
        return export.Deck(name="M", solver_id=1, blocks=blocks)

    def test_표가_없으면_소성_덱은_못_낸다(self) -> None:
        deck = self._deck(elastic={"values": {"youngs_modulus": 2e11, "poisson_ratio": 0.3}})
        # **블록 말로 답한다.** 전에는 카드 양식의 칸 이름으로 답했다.
        assert "소성 표" in export.missing_for(deck, "abaqus")
        assert "abaqus" not in export.available_formats(deck)

    def test_점탄성_카드는_점탄성_형식이_열린다(self) -> None:
        deck = self._deck(
            elastic={"values": {"youngs_modulus": 2e9, "poisson_ratio": 0.45}},
            viscoelastic={
                "values": {"reference_temperature_k": 293.15},
                "rows": [{"relative_modulus": 0.4, "relaxation_time_s": 0.1}],
            },
        )
        assert "abaqus_viscoelastic" in export.available_formats(deck)
        # 같은 카드로 소성 덱은 못 낸다 — 표가 없다.
        assert "abaqus" not in export.available_formats(deck)

    def test_중립_JSON_은_늘_열린다(self) -> None:
        """우리가 만들지 않은 솔버를 쓰는 사람에게 남는 길이다."""
        assert "json" in export.available_formats(self._deck())
