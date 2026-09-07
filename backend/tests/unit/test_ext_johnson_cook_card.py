"""`*MAT_098` 렌더러 — **확장이 카드까지 들고 가는가.**

식(`equation.py`)뿐 아니라 그 식이 나가는 솔버 카드(`card.py`)도 확장 폴더 안에
있다. 중심 코드에 두면 `matcore/export/dyna.py` 가 확장의 이름을 알아야 하고,
그러면 확장이 아니다(ADR 0013).

무는 것이 넷이다.

    다른 식의 계수를 안 받는다   Voce 카드로 098 을 내면 계수가 자리를 바꿔 앉는다
    C 와 기준 속도는 한 몸이다    EPSO 를 1 로 굳히면 응력이 조용히 어긋난다
    C 가 없으면 그것을 적는다    준정적 덱인 것은 틀린 게 아니지만 말은 해야 한다
    단위계가 값을 바꾼다        환산 누락은 오류 없이 1000배 틀린 덱이다
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matcore import cards, extensions
from matcore.export import Deck, ExportError, render
from matcore.export.systems import MM_N_TONNE

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"

# 블록의 단위 선언(si_unit)이 있어야 to_system 이 환산한다.
cards.load_builtin()
extensions.load(EXTENSIONS)

KEY = "dyna_johnson_cook"

#: 적합이 낸 A·B·n. 행이 자기 단위를 든다 — 틀이 그것을 보고 환산한다.
JC_ROWS = [
    {"name": "a", "value": 350e6, "si_unit": "Pa"},
    {"name": "b", "value": 600e6, "si_unit": "Pa"},
    {"name": "n", "value": 0.25, "si_unit": "1"},
]

VOCE_ROWS = [
    {"name": "sigma_0", "value": 350e6, "si_unit": "Pa"},
    {"name": "q", "value": 260e6, "si_unit": "Pa"},
    {"name": "b", "value": 12.0, "si_unit": "1"},
]


def deck(rows: list[dict[str, object]] | None = None, **blocks: object) -> Deck:
    base: dict[str, object] = {
        "elastic": {
            "values": {"youngs_modulus": 200e9, "poisson_ratio": 0.3, "density": 7850.0}
        },
        "hardening": {
            "values": {"label": "Johnson-Cook (준정적 항)", "r_squared": 0.998},
            "rows": list(JC_ROWS if rows is None else rows),
        },
    }
    base.update(blocks)
    return Deck(
        name="DP590_MD",
        solver_id=101,
        blocks=base,
        provenance=("시험 6건: 속도 3수준 x 2반복",),
    )


def rate_block(c: float = 0.014, reference: float = 0.002) -> dict[str, object]:
    return {"values": {"model": "johnson_cook", "jc_c": c, "reference_rate": reference}}


class Test덱이_나온다:
    def test_키워드와_계수가_실린다(self) -> None:
        made = render(KEY, deck(rate_table=rate_block()))
        assert "*MAT_SIMPLIFIED_JOHNSON_COOK" in made.text
        assert "*END" in made.text
        card = [line for line in made.text.splitlines() if not line.startswith(("$", "*"))]
        # 카드 두 줄: (mid ro e pr vp) 와 (a b n c psfail sigmax sigsat epso)
        assert len(card) == 2
        assert "3.500E+08" in card[1] and "6.000E+08" in card[1]

    def test_고정_10칸을_지킨다(self) -> None:
        """**칸이 어긋나면 LS-DYNA 는 다른 필드로 읽는다.** 오류는 안 난다."""
        made = render(KEY, deck(rate_table=rate_block()))
        card = [line for line in made.text.splitlines() if not line.startswith(("$", "*"))]
        assert len(card[0]) == 50, "1번 카드는 5필드 x 10칸"
        assert len(card[1]) == 80, "2번 카드는 8필드 x 10칸"

    def test_온도항이_없다는_것을_적는다(self) -> None:
        """098 에는 온도항이 없다. **그것을 모르고 고온 해석에 쓰면 안 된다.**"""
        made = render(KEY, deck(rate_table=rate_block()))
        assert "온도" in made.text and "*MAT_015" in made.text


class Test경화_블록이_덱으로_간다:
    def test_매개변수_모델이라_계수가_그대로_실린다(self) -> None:
        """오래 **「경화식은 덱에 안 실린다」** 였다 — 표로 나가고 식은 주석에만
        남았다(`*MAT_024`·Abaqus `*PLASTIC` 둘 다 표를 받는다).

        `*MAT_098` 은 다르다. 표가 없고 계수 A·B·n·C 를 직접 먹는 **매개변수
        모델**이라 경화 블록 자체가 덱으로 간다. 화면의 `in_deck` 표시가 여기서
        나오므로(`/api/fitting/blocks`), 이 확장이 실리면 그 표시도 바뀐다."""
        from matcore import export

        assert "hardening" in export.blocks_in_decks()


class Test다른_식의_계수를_안_받는다:
    def test_Voce_카드는_거절한다(self) -> None:
        """**계수가 자리를 바꿔 앉으면 덱은 나오고 해석은 조용히 틀린다.**

        Voce 의 `sigma_0·q·b` 를 A·B·n 자리에 넣으면 형식은 멀쩡하다 — b=12 가
        지수 n 자리에 앉아 응력이 천문학적으로 나오는데, 그것을 알아채는 것은
        해석을 돌린 다음이다. 파라미터 **이름**으로 거른다.
        """
        with pytest.raises(ExportError) as raised:
            render(KEY, deck(rows=VOCE_ROWS, rate_table=rate_block()))
        assert "A·B·n" in str(raised.value)
        assert "MAT_024" in str(raised.value), "대신 쓸 것을 알려 줘야 한다"


class TestC_와_기준속도:
    def test_기준_속도가_EPSO_에_실린다(self) -> None:
        """**C 는 기준 속도와 한 몸이다.** 1 로 굳히면 응력이 조용히 어긋난다."""
        made = render(KEY, deck(rate_table=rate_block(c=0.014, reference=0.002)))
        card = [line for line in made.text.splitlines() if not line.startswith(("$", "*"))]
        assert card[1].endswith("2.000E-03"), "EPSO 자리가 기준 속도여야 한다"
        assert "1.400E-02" in card[1], "C 가 실려야 한다"

    def test_C_가_있는데_기준_속도가_없으면_거절한다(self) -> None:
        bare = {"values": {"model": "johnson_cook", "jc_c": 0.014}}
        with pytest.raises(ExportError, match="기준 속도"):
            render(KEY, deck(rate_table=bare))

    def test_속도_묶음이_없으면_C0_이고_그것을_적는다(self) -> None:
        """준정적 덱인 것은 틀린 게 아니다. **말을 안 하는 것이 틀린 것이다.**

        MaterialTwin 은 늘 이 상태였다(속도 자료가 없었다).
        """
        made = render(KEY, deck())
        assert "C=0" in made.text and "준정적" in made.text
        assert any("속도 묶음이 없어" in note for note in made.notes)


class Test단위계:
    def test_mm_N_tonne_로_내면_MPa_숫자가_적힌다(self) -> None:
        """환산 누락은 **오류 없이 1000배 틀린 덱**이다 — 가장 비싼 결함이다.

        A·B 는 행이 든 `si_unit` 을 보고 틀이 환산한다. 렌더러는 이 일을 모른다.
        """
        made = render(KEY, deck(rate_table=rate_block()), MM_N_TONNE)
        card = [line for line in made.text.splitlines() if not line.startswith(("$", "*"))]
        assert "3.500E+02" in card[1], "A 가 350 MPa 로 적혀야 한다"
        assert "6.000E+02" in card[1], "B 가 600 MPa 로 적혀야 한다"
        assert "n" not in card[1]
        # n 은 무차원이라 안 바뀐다.
        assert "2.500E-01" in card[1]
