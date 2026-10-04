"""덱의 어느 자리에 카드의 어느 값이 가나 — **흔들어 짚는다**(2026-10-04).

짚은 자리를 숫자로 읽으면 그 값이다       고정폭(LS-DYNA) · 자유 형식(Abaqus) 둘 다
여러 값에서 셈한 칸은 그 값들이 함께 짚는다   LS-DYNA SIGY 는 표의 첫 응력에서 온다
안 쓰는 값은 안 쓴다고 · 흔들면 안 나오는 값은 못 짚었다고 말한다
"""

from __future__ import annotations

import pytest

import matcore.export.dyna  # noqa: F401  (LS-DYNA 렌더러 등록)
from matcore import cards, export
from matcore.export import Deck, ExportError, Rendered, layout
from matcore.export.systems import SI


@pytest.fixture(autouse=True)
def _blocks() -> None:
    cards.load_builtin()


def _deck(**extra: object) -> Deck:
    return Deck(
        name="SECC_MD",
        solver_id=7,
        blocks={
            "elastic": {
                "values": {
                    "youngs_modulus": 2.05e11,
                    "poisson_ratio": 0.3,
                    "density": 7850.0,
                    "youngs_modulus_source": "measured",
                }
            },
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 3.0e8},
                    {"plastic_strain": 0.05, "true_stress": 3.6e8},
                    {"plastic_strain": 0.1, "true_stress": 4.0e8},
                ]
            },
            **extra,
        },
    )


def _locate(format_key: str, deck: Deck) -> tuple[list[str], layout.Layout]:
    target = export.renderer(format_key)
    lines = export.render(target, deck, SI).text.splitlines()
    return lines, layout.locate(lambda one: export.render(target, one, SI), deck)


@pytest.mark.parametrize("format_key", ["abaqus", "dyna"])
def test_짚은_자리를_숫자로_읽으면_그_값이다(format_key: str) -> None:
    lines, found = _locate(format_key, _deck())
    placed = {(one.block, one.key): one for one in found.placed}
    for key, value in (
        ("youngs_modulus", 2.05e11),
        ("poisson_ratio", 0.3),
        ("density", 7850.0),
    ):
        span = placed[("elastic", key)].spans[0]
        text = lines[span.line][span.start : span.end]
        assert float(text) == pytest.approx(value), (key, text)
    # 열은 행마다 짚힌다 — 0 인 첫 소성 변형률은 흔들어도 0 이라 빠진다(머리말의 한계).
    assert len(placed[("table", "plastic_strain")].spans) == 2
    # 글자 값(`_source`)은 흔들지 않는다.
    assert all(one.key != "youngs_modulus_source" for one in found.placed)


def test_셈한_칸은_그_값을_흔들어도_짚힌다() -> None:
    """LS-DYNA *MAT_024 의 SIGY(항복응력)는 표의 첫 응력에서 온다 — 표의 열을 흔들면 그 칸도
    바뀌어야 한다. 정의만 읽어서는 안 보이는 자리다."""
    lines, found = _locate("dyna", _deck())
    stress = next(one for one in found.placed if one.key == "true_stress")
    material_line = next(
        span.line for span in stress.spans if lines[span.line].lstrip().startswith("7 ")
    )
    assert "3.0E+8" in lines[material_line]


def test_안_쓰는_값과_못_짚은_값을_가른다() -> None:
    deck = _deck(hardening={"values": {"q": 1.0e8}})
    target = export.renderer("abaqus")

    def render(one: Deck) -> Rendered:
        # 흔든 푸아송비를 범위 검사가 거절한다고 친다.
        if one.number("elastic", "poisson_ratio") != 0.3:
            raise ExportError("푸아송비가 범위 밖입니다.")
        return export.render(target, one, SI)

    found = layout.locate(render, deck)

    # 경화식 블록은 Abaqus 표 덱에 안 실린다.
    assert ("hardening", "q", False) in found.unused
    assert [(one[0], one[1]) for one in found.failed] == [("elastic", "poisson_ratio")]
    assert "범위" in found.failed[0][3]


def test_값이_넓어져도_앞_빈칸을_자리로_잡지_않는다() -> None:
    """오른쪽 맞춤 칸에서 `4.7E+8` 이 `4.23E+8` 이 되면 앞 빈칸 하나가 「지워진 것」 으로
    잡힌다 — 개발 DB 의 LS-DYNA 열 덱에서 실측(2026-10-04). 자리는 숫자만이다."""
    spans = layout.changed(["    4.7E+8      50.0"], ["   4.23E+8      50.0"])
    assert [("    4.7E+8      50.0"[one.start : one.end]) for one in spans] == ["4.7E+8"]
