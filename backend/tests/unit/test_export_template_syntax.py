"""정의 문법을 넓혔다(ADR 0038) — 자리표 · 조건 · 표 함수 · 표 정의 · each · pack · fail.

기본 제공 형식 50개를 글자까지 옮기는 데 **실제로 쓰인 것만** 넣었다. 그것이 모두 되는지는
`test_export_twins.py` 가 코드판과 견주어 보고, 여기서는 조각마다의 뜻과 막는 자리를 본다.
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import export
from matcore.export import template


def _deck(**blocks: Any) -> export.Deck:
    return export.Deck(
        name="DP600_MD", solver_id=4242, blocks=blocks, provenance=("근거 한 줄",)
    )


STEEL = {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}}


def _text(lines: list[dict[str, Any]], deck: export.Deck, **tables: Any) -> str:
    return template.render({"lines": lines, "tables": tables}, deck).text


class Test자리표:
    def test_재료_번호와_이름과_식(self) -> None:
        got = _text(
            [
                {"text": "/MAT/LAW1/{id}/1 {name:.5}"},
                {"text": "E={elastic.youngs_modulus / 1e9:.1f} GPa · {{그대로}}"},
            ],
            _deck(elastic=STEEL),
        )
        assert got == "/MAT/LAW1/4242/1 DP600\nE=210.0 GPa · {그대로}\n"

    def test_글자_값과_빠진_값의_대신(self) -> None:
        deck = _deck(thermal={"values": {"specific_heat": 460.0}})
        got = _text([{"text": 'source={thermal.specific_heat_source or "unknown"}'}], deck)
        assert got == "source=unknown\n"

    def test_units_는_그_단위계의_기호다(self) -> None:
        """응력 단위를 이름으로 적는 형식(OptiStruct MATFAT 의 UNIT)이 쓴다 — 계마다 다르다."""
        lines = [{"text": '{units.Pa} {units.m} {"MPA" if units.Pa == "MPa" else "PA"}'}]
        deck = _deck(elastic=STEEL)
        assert template.render({"lines": lines}, deck).text == "Pa m PA\n"
        mm = export.to_system(deck, export.systems.MM_N_TONNE)
        assert template.render({"lines": lines}, mm).text == "MPa mm MPA\n"
        with pytest.raises(export.ExportError, match=r"units\.furlong"):
            _text([{"text": "{units.furlong}"}], deck)

    def test_빠진_값은_when_으로_거르라고_말한다(self) -> None:
        with pytest.raises(export.ExportError) as caught:
            _text([{"text": "{elastic.density:.3g}"}], _deck(elastic={"values": {}}))
        assert "elastic.density" in str(caught.value)
        assert "when" in str(caught.value)

    def test_느낌표는_저장_전에_막는다(self) -> None:
        """`{a != b}` 는 파이썬 형식 문법에서 변환(!r)으로 읽힌다 — 조용히 다르게 돌지 않게."""
        with pytest.raises(export.ExportError, match="not"):
            template.renderer_from_definition(
                {
                    "key": "x",
                    "label": "x",
                    "extension": "k",
                    "describe": "x",
                    "lines": [{"text": "{elastic.density != 1}"}],
                }
            )


class Test조건:
    def test_식_조건과_예전_조건(self) -> None:
        deck = _deck(elastic=STEEL, hyperelastic={"values": {"family": "ogden_1"}})
        lines = [
            {"text": "a", "when": "has(elastic.density) and elastic.poisson_ratio < 0.5"},
            {"text": "b", "when": 'hyperelastic.family == "ogden_1"'},
            # 빠진 값은 거짓 — 멈추지 않는다.
            {"text": "c", "when": "thermal.specific_heat > 0"},
            {"text": "d", "when": "not has(thermal.specific_heat)"},
            # **예전 조건은 예전 뜻** — 숫자가 있는가. 글자 값은 늘 「없다」 였다.
            {"text": "e", "when": "hyperelastic.family"},
            {"text": "f", "when": "missing:hyperelastic.family"},
        ]
        assert _text(lines, deck) == "a\nb\nd\nf\n"


class Test표:
    def test_첫_점_합_개수_이름으로_고르기(self) -> None:
        deck = _deck(
            table={
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 300e6},
                    {"plastic_strain": 0.0, "true_stress": 350e6},  # 탄성 구간 자국
                    {"plastic_strain": 0.1, "true_stress": 500e6},
                ]
            },
            hyperelastic={
                "rows": [{"name": "c10", "value": 1.0}, {"name": "c10", "value": 2.0}]
            },
        )
        got = _text(
            [
                {"text": "{first(curve, true_stress):.4g} {count(curve)} {count(table)}"},
                {"text": '{last(hyperelastic, value, name == "c10"):g}'},
                {"text": '{joined(curve, fmt(plastic_strain, ".2f"), "/")}'},
            ],
            deck,
            curve={"of": "table", "x": "plastic_strain", "y": "true_stress"},
        )
        # 정리된 곡선은 두 점이고 첫 점이 항복(350) — 원래 표는 세 줄이다.
        assert got == "3.5e+08 2 3\n2\n0.00/0.10\n"

    def test_거르고_정렬하고_번호를_매긴다(self) -> None:
        deck = _deck(
            thermal={
                "rows": [
                    {"temperature": 473.15, "specific_heat": 500.0},
                    {"temperature": 293.15, "specific_heat": 460.0},
                    {"temperature": 373.15},
                ]
            }
        )
        got = _text(
            [
                {
                    "rows": "cp",
                    "prefix": "MPTEMP,",
                    "fields": [
                        {"expr": "_index", "format": ["spec", "d"]},
                        {"value": "temperature", "format": ["spec", ".2f"]},
                    ],
                    "join": ",",
                }
            ],
            deck,
            cp={"of": "thermal", "where": "has(specific_heat)", "sort": "temperature"},
        )
        assert got == "MPTEMP,1,293.15\nMPTEMP,2,473.15\n"

    def test_묶고_짧은_끝에서_자르고_교차를_안다(self) -> None:
        rows = [
            {"rate": 1.0, "x": 0.0, "y": 100.0},
            {"rate": 1.0, "x": 0.2, "y": 200.0},
            {"rate": 10.0, "x": 0.0, "y": 90.0},
            {"rate": 10.0, "x": 0.1, "y": 140.0},  # x=0.1 에서 앞 곡선(150)보다 낮다
        ]
        deck = _deck(rate_table={"rows": rows})
        made = template.render(
            {
                "tables": {
                    "curves": {
                        "of": "rate_table",
                        "by": "rate",
                        "x": "x",
                        "y": "y",
                        "clip": "shortest",
                        "note": "속도 {_key:g}: ",
                    }
                },
                "lines": [
                    {
                        "each": "curves",
                        "as": "curve",
                        "lines": [
                            {"text": "{_key:g} {_clipped} {_below_prev} {last(curve, y):g}"},
                        ],
                    }
                ],
            },
            deck,
        )
        # 첫 곡선을 0.1 에서 잘라 그 자리의 값(150)을 읽는다 — 늘리지 않는다. 둘째 곡선은
        # 거기서 140 이라 앞 곡선 아래로 내려간다(LS-DYNA 표에서 교차).
        assert made.text == "1 1 0 150\n10 0 1 140\n"


class Test줄:
    def test_큰칸_카드를_묶는다(self) -> None:
        """Nastran 큰칸 — 논리 줄 여덟 칸이 물리 줄 넷씩, 빈 칸 16칸, 끝 공백 없이."""
        blank = " " * 16
        got = _text(
            [
                {
                    "pack": [
                        {"expr": "_id", "format": ["spec", "<16d"]},
                        {"value": "elastic.youngs_modulus", "format": ["fixed_left", 16, 8]},
                        {"const": blank},
                        {"value": "elastic.poisson_ratio", "format": ["fixed_left", 16, 8]},
                        {"value": "elastic.density", "format": ["fixed_left", 16, 8]},
                    ],
                    "per_line": 4,
                    "first": "MAT1*   ",
                    "next": "*       ",
                    "pad_to": 8,
                    "pad": blank,
                    "rstrip": True,
                }
            ],
            _deck(elastic=STEEL),
        )
        assert got == (
            "MAT1*   4242            2.10000000E+11                  3.00000000E-01\n"
            "*       7.85000000E+03\n"
        )

    def test_줄_번호로_머리를_단다(self) -> None:
        deck = _deck(viscoelastic={"rows": [{"g": float(one)} for one in range(1, 5)]})
        got = _text(
            [
                {
                    "pack": [
                        {
                            "rows": "viscoelastic",
                            "fields": [
                                {"value": "g", "format": ["spec", "g"]},
                            ],
                        }
                    ],
                    "per_line": 3,
                    "first": "TBDATA,{3 * _line + 1},",
                    "next": "TBDATA,{3 * _line + 1},",
                    "join": ",",
                }
            ],
            deck,
        )
        assert got == "TBDATA,1,1,2,3\nTBDATA,4,4\n"

    def test_fail_은_그_말로_멈추고_note_는_덱에_안_적는다(self) -> None:
        deck = _deck(
            viscoelastic={"rows": [{"relative_modulus": 0.7}, {"relative_modulus": 0.4}]}
        )
        lines = [
            {"note": "합 {sum(viscoelastic, relative_modulus):.2f}"},
            {
                "fail": "합이 {sum(viscoelastic, relative_modulus):.2f} 입니다",
                "when": "sum(viscoelastic, relative_modulus) >= 1",
            },
        ]
        with pytest.raises(export.ExportError, match=r"합이 1\.10 입니다"):
            template.render({"lines": lines}, deck)
        made = template.render({"lines": lines[:1]}, deck)
        assert made.text == "\n" and made.notes == ("합 1.10",)

    def test_칸의_조건과_대신할_글자(self) -> None:
        deck = _deck(elastic={"values": {"youngs_modulus": 1.0}})
        got = _text(
            [
                {
                    "fields": [
                        {"value": "elastic.youngs_modulus", "format": ["spec", "g"]},
                        {"value": "elastic.density", "format": ["spec", "g"], "default": "-"},
                        {"const": "x", "when": "has(elastic.density)"},
                    ],
                    "join": "|",
                }
            ],
            deck,
        )
        assert got == "1|-\n"

    def test_머리_묶음이_주석_기호를_받는다(self) -> None:
        got = _text([{"block": "header", "comment": "$"}], _deck())
        assert got == "$ MatNexus 물성 카드\n$ 근거 한 줄\n"
        with pytest.raises(export.ExportError, match="모르는 칸"):
            _text([{"block": "header", "nope": 1}], _deck())


class Test막는_자리:
    def test_정수_형식은_정수만(self) -> None:
        """3.5 를 `d` 로 적으려 하면 반올림하지 않고 멈춘다 — 재료 번호가 조용히 바뀌면
        안 된다."""
        with pytest.raises(export.ExportError, match="정수"):
            _text([{"fields": [{"expr": "3.5", "format": ["spec", "d"]}]}], _deck())

    def test_큰_거듭제곱은_멈추지_않고_거절한다(self) -> None:
        """정수로 계산하면 `10 ^ 10 ^ 10` 이 서버를 멈춘다 — 실수로 바꿔 넘침으로 거절한다."""
        with pytest.raises(export.ExportError, match="너무 큽니다"):
            _text([{"fields": [{"expr": "10 ^ 10 ^ 10"}]}], _deck())

    @pytest.mark.parametrize(
        "line",
        [
            {"fields": [{"value": "a.b", "format": ["spec", ">99999d"]}]},  # 끝없는 폭
            {"text": "{open('x')}"},
            {"each": "t", "lines": [{"text": "{__import__('os')}"}]},  # each 안까지 읽는다
            {"pack": [{"expr": "a.b +"}], "per_line": 2},
            {"pack": [], "per_line": 0},
            {"text": "x", "when": "a.b ||| c"},
        ],
    )
    def test_저장_전에_읽어_본다(self, line: dict[str, Any]) -> None:
        with pytest.raises(export.ExportError):
            template.renderer_from_definition(
                {"key": "x", "label": "x", "extension": "k", "describe": "x", "lines": [line]}
            )

    def test_표_정의도_저장_전에_읽어_본다(self) -> None:
        for tables in (
            {"t": {"of": "table", "where": "lambda: 1"}},
            {"t": {"of": "table", "x": "a"}},  # y 없이
            {"t": {"of": "table", "notes": "somewhere"}},
            {"t": {"of": "table", "clip": "longest"}},
        ):
            with pytest.raises(export.ExportError):
                template.renderer_from_definition(
                    {
                        "key": "x",
                        "label": "x",
                        "extension": "k",
                        "describe": "x",
                        "lines": [{"text": "x"}],
                        "tables": tables,
                    }
                )

    def test_needs_의_최솟값(self) -> None:
        made = template.renderer_from_definition(
            {
                "key": "x",
                "label": "x",
                "extension": "k",
                "describe": "x",
                "lines": [{"text": "x"}],
                "needs": [
                    {
                        "block": "rate_table",
                        "values": ["rate_count"],
                        "at_least": {"rate_count": 2},
                    }
                ],
            }
        )
        one = _deck(rate_table={"values": {"rate_count": 1}})
        two = _deck(rate_table={"values": {"rate_count": 2}})
        assert export.missing_for(one, made) and not export.missing_for(two, made)
