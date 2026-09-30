"""예제 덱 초안 → **저장할 수 있는 정의**(`scan.as_definition`, 2026-09-30).

화면은 같은 일을 `frontend/src/modules/fitting/deckLines.ts` 의 `fromScan` → `toDefinitionLine`
으로 한다. 두 벌이라 **화면 시험(`deckLines.test.ts`)과 같은 경우**를 여기서도 문다 — 한쪽만
고쳐지면 AI 가 지은 정의와 사람이 지은 정의가 같은 덱에서 다르게 나온다.
"""

from __future__ import annotations

import pytest

from matcore import export
from matcore.export import scan, systems, template
from matcore.export.scan import Cell, Scanned, ScannedLine


def _one(line: ScannedLine) -> dict[str, object]:
    [made] = scan.as_definition(Scanned(lines=[line], notes=[]))["lines"]
    return dict(made)


def test_제안된_이름을_칸에_넣고_없으면_비워_둔다() -> None:
    # 빈칸이 곧 「여기는 네가 정해라」 다 — 짐작으로 채우면 그대로 저장된다.
    made = _one(
        ScannedLine(
            kind="fields",
            cells=[Cell("1", 1.0, suggested="elastic.density"), Cell("2", 2.0)],
            join=", ",
        )
    )
    assert made["fields"] == [
        {"value": "elastic.density", "format": "free"},
        {"value": "", "format": "free"},
    ]


def test_칸_폭과_맞춤을_옮긴다() -> None:
    right = _one(ScannedLine(kind="fields", cells=[Cell("1", 1.0)], width=10, precision=3))
    assert right["fields"] == [{"value": "", "format": ["fixed", 10, 3]}]
    left = _one(
        ScannedLine(kind="fields", cells=[Cell("1", 1.0)], width=8, precision=1, align="left")
    )
    assert left["fields"] == [{"value": "", "format": ["fixed_left", 8, 1]}]
    # 자릿수를 못 읽었으면 화면과 같은 9.
    loose = _one(ScannedLine(kind="fields", cells=[Cell("1", 1.0)], width=10))
    assert loose["fields"] == [{"value": "", "format": ["fixed", 10, 9]}]


def test_비운_칸은_빈_상수로_자리를_지킨다() -> None:
    # Nastran 자유 필드의 `,,` — 값 칸으로 바꾸면 지어낸 값이 덱에 실린다.
    made = _one(
        ScannedLine(
            kind="fields",
            cells=[
                Cell("1", 1.0, suggested="elastic.youngs_modulus"),
                Cell("", 0.0, empty=True),
            ],
        )
    )
    assert made["fields"] == [
        {"value": "elastic.youngs_modulus", "format": "free"},
        {"const": ""},
    ]


def test_표_이름은_비워_두고_키워드는_글자_그대로() -> None:
    assert _one(ScannedLine(kind="rows", cells=[Cell("1", 1.0)]))["rows"] == ""
    assert _one(ScannedLine(kind="text", text="*MATERIAL, NAME=DP600")) == {
        "text": "*MATERIAL, NAME=DP600"
    }


def test_앞글자와_빈_구분자를_지킨다() -> None:
    # 빈 구분자를 안 보내면 서버가 ", " 를 끼워 고정폭 칸이 밀린다.
    made = _one(ScannedLine(kind="fields", cells=[Cell("1", 1.0)], prefix="MAT1    ", join=""))
    assert made["prefix"] == "MAT1    "
    assert made["join"] == ""
    assert "suffix" not in made  # 빈 끝글자는 안 보낸다


def test_빈_칸을_안_채우고_그리면_무엇이_비었는지_말한다() -> None:
    """초안의 빈 `value` 는 채울 자리다. 거절은 맞다 — 다만 **이유가 보여야** 고친다
    (전에는 「'블록.값' 으로 적어야 합니다: 」 로 끝나 무엇이 비었는지 몰랐다)."""
    definition = {
        "key": "draft",
        "label": "초안",
        "extension": "k",
        "describe": "초안",
        "lines": [{"fields": [{"value": "", "format": "free"}]}],
    }
    target = template.renderer_from_definition(definition)
    deck = export.Deck(
        name="DP600",
        solver_id=1,
        blocks={"elastic": {"values": {"youngs_modulus": 200e9}}},
        provenance=(),
    )
    with pytest.raises(export.ExportError, match="값이 비어 있는 칸"):
        export.render(target, deck, systems.SI)


def test_실제_덱을_읽은_초안을_정의로_받아들인다() -> None:
    """**초안이 문법에 맞아야 쓸모가 있다** — 렌더러가 그 정의를 받아야 한다."""
    deck = (
        "*MAT_ELASTIC\n"
        "$#     mid        ro         e        pr\n"
        "         1   7.85E-9  210000.0       0.3\n"
    )
    found = scan.scan(deck, {"elastic.youngs_modulus": 210000.0})
    definition = scan.as_definition(found)
    # 카드 값과 같은 숫자는 그 이름으로 제안된다 — 나머지는 빈 자리.
    suggested = [
        cell.get("value")
        for line in definition["lines"]
        for cell in line.get("fields", [])
        if isinstance(cell, dict)
    ]
    assert "elastic.youngs_modulus" in suggested
    # 확장자 · 설명 · 이름은 덱만 봐서 모른다 — 부르는 쪽(화면 · MCP 도구)이 채운다.
    target = template.renderer_from_definition(
        {"key": "draft", "label": "초안", "extension": "k", "describe": "초안", **definition}
    )
    assert target is not None
