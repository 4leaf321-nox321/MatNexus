"""덱 정의의 식 — 값·열을 계산해서 적는다(2026-09-05).

**`eval` 이 아니다.** 정의는 부서 관리자가 적는 데이터라, 그 글자가 코드로 돌면
원격 실행이다. 사칙연산·거듭제곱·괄호·몇 개의 함수만 지나가고 나머지는 이름을
대며 거절한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import export
from matcore.export import expr, template


def test_사칙연산과_거듭제곱_괄호_함수() -> None:
    values = {
        "a": 8.0,
        "b": 2.0,
        "elastic.youngs_modulus": 210e9,
        "elastic.poisson_ratio": 0.3,
    }
    got = expr.evaluate("a / b + 1", values.get)
    assert got == 5.0
    assert expr.evaluate("a ^ 2", values.get) == 64.0  # ^ 는 거듭제곱이다 — XOR 가 아니다
    assert expr.evaluate("-a * (b + 1)", values.get) == -24.0
    assert expr.evaluate("sqrt(a * b)", values.get) == 4.0
    assert expr.evaluate("max(a, b, 3)", values.get) == 8.0
    shear = expr.evaluate(
        "elastic.youngs_modulus / (2 * (1 + elastic.poisson_ratio))", values.get
    )
    assert shear == pytest.approx(210e9 / 2.6)
    assert expr.names("true_stress / elastic.youngs_modulus + sqrt(2)") == [
        "elastic.youngs_modulus",
        "true_stress",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "__import__('os')",
        "a.b.c",
        "a if b else c",
        "a[0]",
        "lambda: 1",
        "a and b",
        "a << 2",
        "'x'",
        "open('f')",
        "a +",
    ],
)
def test_허용_밖은_거절한다(text: str) -> None:
    with pytest.raises(expr.BadExpression):
        expr.parse(text)


def test_없는_이름은_이름을_댄다() -> None:
    with pytest.raises(expr.MissingName) as caught:
        expr.evaluate("a / 2", lambda _name: None)
    assert caught.value.name == "a"


def _deck() -> export.Deck:
    return export.Deck(
        name="X",
        solver_id=1,
        blocks={
            "elastic": {"values": {"youngs_modulus": 200e9, "poisson_ratio": 0.25}},
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 250e6},
                    {"plastic_strain": 0.1, "true_stress": 300e6},
                ]
            },
        },
        provenance=(),
    )


class Test정의에서:
    def test_표의_열에_상수를_나눈다(self) -> None:
        spec: dict[str, Any] = {
            "lines": [
                {
                    "rows": "table",
                    "fields": [{"expr": "true_stress / 1000"}, {"value": "plastic_strain"}],
                }
            ]
        }
        made = template.render(spec, _deck())
        first = made.text.splitlines()[0].split(", ")
        assert float(first[0]) == pytest.approx(250e3)

    def test_열과_카드_값을_섞는다(self) -> None:
        """열 / 블록.값 — 정규화한 응력 같은 것."""
        spec: dict[str, Any] = {
            "lines": [
                {"rows": "table", "fields": [{"expr": "true_stress / elastic.youngs_modulus"}]}
            ]
        }
        made = template.render(spec, _deck())
        assert float(made.text.splitlines()[1]) == pytest.approx(300e6 / 200e9)

    def test_값_줄에서_전단탄성률을_만든다(self) -> None:
        spec: dict[str, Any] = {
            "lines": [
                {
                    "prefix": "G = ",
                    "fields": [
                        {"expr": "elastic.youngs_modulus / (2 * (1 + elastic.poisson_ratio))"}
                    ],
                }
            ]
        }
        made = template.render(spec, _deck())
        assert made.text.startswith("G = ")
        assert float(made.text[4:]) == pytest.approx(80e9)

    def test_없는_값은_값_칸과_같은_말로_멈춘다(self) -> None:
        spec: dict[str, Any] = {"lines": [{"fields": [{"expr": "elastic.density / 2"}]}]}
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, _deck())
        assert "elastic.density" in str(caught.value)
        assert "when" in str(caught.value)

    def test_값_줄에서_맨_이름은_거절한다(self) -> None:
        spec: dict[str, Any] = {"lines": [{"fields": [{"expr": "youngs_modulus / 2"}]}]}
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, _deck())
        assert "블록.값" in str(caught.value)

    def test_저장_전에_식을_읽어_본다(self) -> None:
        """내려받을 때 터지면 그 자리에 고칠 사람이 없다."""
        definition = {
            "key": "x",
            "label": "x",
            "extension": "k",
            "describe": "x",
            "lines": [{"text": "*A"}, {"fields": [{"expr": "open('f')"}]}],
        }
        with pytest.raises(export.ExportError) as caught:
            template.renderer_from_definition(definition)
        assert "2번 줄" in str(caught.value)

    def test_글자_줄은_카드_값_없이_그대로_나간다(self) -> None:
        """옵션 숫자·주석 줄. `plain` 은 편집기가 묶음으로 접을 때만 쓴다."""
        spec: dict[str, Any] = {
            "lines": [{"text": "*MAT, {name}"}, {"text": "1, 0, 0", "plain": True}]
        }
        made = template.render(spec, _deck())
        assert made.text == "*MAT, X\n1, 0, 0\n"

    def test_모르는_자리표는_이름을_대며_멈춘다(self) -> None:
        spec: dict[str, Any] = {"lines": [{"text": "{id}"}]}
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, _deck())
        assert "{id}" in str(caught.value)
        assert "{{" in str(caught.value)
