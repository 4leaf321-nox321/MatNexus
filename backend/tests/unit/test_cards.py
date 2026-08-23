"""물성 블록 레지스트리 — **새 물성 1종에 파일 하나.**

여기서 지키는 것은 셋이다.

    선언만으로 화면이 그려진다      이름 없는 블록은 등록이 거절한다
    모르는 블록에 소리를 낸다       조용히 넘기면 덱에 그 물성만 빠진다
    한 자리는 한 블록이 채운다      둘이 채우면 어느 값이 실릴지 모른다
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


class TestToCard:
    def test_탄성은_있는_값만_싣는다(self) -> None:
        """**없는 값은 넣지 않는다.** 0.3 으로 채우면 덱만 봐서는 못 가른다."""
        got = cards.card_kwargs({"elastic": {"values": {"youngs_modulus": 2.0e11}}})
        assert got == {"youngs_modulus": 2.0e11}

    def test_경화식은_덱에_안_실린다(self) -> None:
        """실리지 않는다고 쓸모없는 것이 아니라 **실리는 자리가 다르다.**"""
        got = cards.card_kwargs({"hardening": {"values": {"label": "Voce"}}})
        assert got == {}

    def test_점탄성은_상대_탄성률과_기준_온도를_낸다(self) -> None:
        got = cards.card_kwargs(
            {
                "viscoelastic": {
                    "values": {"reference_temperature_k": 293.15},
                    "rows": [
                        {
                            "relaxation_time_s": 0.1,
                            "modulus_pa": 1e8,
                            "relative_modulus": 0.4,
                        },
                        {
                            "relaxation_time_s": 10.0,
                            "modulus_pa": 5e7,
                            "relative_modulus": 0.2,
                        },
                    ],
                }
            }
        )
        assert got["prony"] == ((0.4, 0.1), (0.2, 10.0))
        assert got["prony_reference_temperature"] == 293.15

    def test_빈_블록은_안_싣는다(self) -> None:
        assert cards.card_kwargs({"elastic": {}, "table": {"rows": []}}) == {}

    def test_모르는_블록에_소리를_낸다(self) -> None:
        """조용히 넘기면 **덱에 그 물성만 빠진 채로 나가고, 덱은 멀쩡히 돈다.**"""
        with pytest.raises(cards.CardError, match="모르는 물성 블록"):
            cards.card_kwargs({"ogden": {"values": {"mu_1": 1.0}}})

    def test_한_자리를_둘이_채우면_거절한다(self, sandbox: Any) -> None:
        """점탄성 덱의 `*ELASTIC` 은 순간 탄성률이어야 한다. 평형 탄성률이
        실리면 재료가 무르게 계산되는데 **덱은 돌고 결과도 그럴듯하다.**"""
        cards.register_block(
            cards.BlockSpec(
                key="rival",
                label="겹치는 것",
                help="시험용",
                produces=(Produced(key="youngs_modulus", label="탄성계수", si_unit="Pa"),),
                to_card=lambda payload: {"youngs_modulus": 1.0},
            )
        )
        with pytest.raises(cards.CardError, match="같은 자리"):
            cards.card_kwargs(
                {
                    "elastic": {"values": {"youngs_modulus": 2.0e11}},
                    "rival": {"values": {"youngs_modulus": 1.0}},
                }
            )


class TestFormats:
    """**누르기 전에 알아야 한다.** 못 내는 형식을 미리 짚는다."""

    def _card(self, **kwargs: Any) -> export.Card:
        return export.Card(name="M", solver_id=1, **kwargs)

    def test_표가_없으면_소성_덱은_못_낸다(self) -> None:
        card = self._card(youngs_modulus=2e11, poisson_ratio=0.3)
        assert "소성 표" in export.missing_for(card, "abaqus")
        assert "abaqus" not in export.available_formats(card)

    def test_점탄성_카드는_점탄성_형식이_열린다(self) -> None:
        card = self._card(
            youngs_modulus=2e9,
            poisson_ratio=0.45,
            prony=((0.4, 0.1),),
            prony_reference_temperature=293.15,
        )
        assert "abaqus_viscoelastic" in export.available_formats(card)
        # 같은 카드로 소성 덱은 못 낸다 — 표가 없다.
        assert "abaqus" not in export.available_formats(card)

    def test_중립_JSON_은_늘_열린다(self) -> None:
        """우리가 만들지 않은 솔버를 쓰는 사람에게 남는 길이다."""
        assert "json" in export.available_formats(self._card())
