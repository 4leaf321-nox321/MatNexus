"""기본 제공 형식의 **정의판** — 코드판을 템플릿으로 다시 적은 것이 글자까지 같은가.

코드로 만든 형식은 화면에서 못 고친다(ADR 0037). 그래서 템플릿으로 다시 적어 씨앗으로
둔다(`seeds/export-profiles/기본-형식-정의.json`) — 코드판을 사용 중단하고 정의판을 켜면
화면에서 고친다. 처음(2026-09-28 오전)에는 템플릿 문법만으로 19개를 옮겼고 셋만 글자까지
같았다. 문법을 넓힌 뒤(ADR 0038) **중립 JSON 을 뺀 전부**가 글자까지 같다.

같은 카드를 두 길로 내서 견준다(ADR 0023 1단계와 같은 방법) — 덱 글자 · 사람에게 남기는
말 · 거절까지. 카드는 `tests/fixtures/export_twin_cards.json`(속도·온도별 표, 초탄성 네 식,
점도, Johnson-Cook, S-N, 온도별 열 표, 코드판이 거절하는 카드들)이고 단위계 둘로 돈다.

**코드판을 고치면 여기서 멈춘다** — 정의판도 같이 고친다. 사용 중단 → 정의판으로 대신하는
길이 서려면 둘이 늘 같아야 한다.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import replace
from typing import Any

import pytest

from matcore import cards, export, extensions
from matcore.export import (  # noqa: F401  (렌더러 등록)
    ansys,
    bulk,
    dyna,
    electronics,
    optics,
    radioss,
    template,
)

BACKEND = pathlib.Path(__file__).resolve().parents[2]
extensions.load(BACKEND / "extensions")
cards.load_builtin()

SEED = BACKEND / "seeds" / "export-profiles" / "기본-형식-정의.json"
CARDS: dict[str, dict[str, Any]] = json.loads(
    (BACKEND / "tests" / "fixtures" / "export_twin_cards.json").read_text(encoding="utf-8")
)["cards"]

#: 정의로 옮기지 않는 코드판. JSON 은 카드의 블록을 **구조째** 적는 형식이라 줄 문법이
#: 아니고, Zemax AGF 는 잰 점에서 분산식의 계수를 **맞춰** 적는다(`matcore.dispersion`) —
#: ADR 0023 의 「계산이 필요하면 코드로」 자리다(2026-10-02).
#: Anand(확장 `anand`) · Garofalo 크리프(확장 `creep`)는 항마다 다른 단위로 와서 덱 단위계로
#: 옮기는 것이 계산이다
#: (2026-10-08).
CODE_ONLY = {"json", "zemax_agf", "ansys_anand", "ansys_creep"}


def _seed() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(SEED.read_text(encoding="utf-8"))
    return body


PROFILES = {one["key"].removesuffix("_def"): one for one in _seed()["profiles"]}
TWINS = {
    key: template.renderer_from_definition(
        {**one["definition"], "key": one["key"], "label": one["label"]}
    )
    for key, one in PROFILES.items()
}


def _deck(blocks: dict[str, Any]) -> export.Deck:
    return export.Deck(
        name="DP600_MD",
        solver_id=4242,
        blocks=json.loads(json.dumps(blocks)),
        provenance=("재료 DP600 · 시편 3개",),
    )


def _run(target: Any, deck: export.Deck, system: Any) -> export.Rendered | str:
    try:
        return export.render(target, deck, system)
    except export.ExportError as exc:
        return str(exc)


def test_코드판마다_정의판이_있고_같은_자리를_쓴다() -> None:
    """확장자·꼬리·키워드·요구 블록이 코드판과 같다 — 「낼 수 있나」 판정이 갈리면 메뉴가
    어긋난다. **켜진 채로 들어가지 않는다** — 켜면 내보내기 메뉴에 같은 형식이 둘 선다."""
    code = {item.key: item for item in export.list_renderers()}
    assert set(TWINS) == set(code) - CODE_ONLY
    for key, one in PROFILES.items():
        made, source = TWINS[key], code[key]
        assert one["is_active"] is False
        assert one["description"]
        assert (made.extension, made.suffix, made.keywords) == (
            source.extension,
            source.suffix,
            source.keywords,
        ), key
        assert made.needs == source.needs, key
        # **단위를 형식이 정했으면 정의판도 같은 계를 받아야 한다** — 아니면 mm 계에서 정의판만
        # 밀도를 tonne/mm3 로 적는다(`Renderer.fixed_units`).
        assert made.fixed_units == source.fixed_units, key


@pytest.mark.parametrize("key", sorted(TWINS))
def test_글자까지_같다(key: str) -> None:
    code, twin = export.renderer(key), TWINS[key]
    compared = 0
    for name, blocks in CARDS.items():
        deck = _deck(blocks)
        if export.missing_for(deck, code):
            assert export.missing_for(deck, twin), f"{name}: 정의판만 낼 수 있다고 한다"
            continue
        assert not export.missing_for(deck, twin), f"{name}: 코드판만 낼 수 있다고 한다"
        for system in export.SYSTEMS:
            real, made = _run(code, deck, system), _run(twin, deck, system)
            where = f"{key} · {name} · {system.key}"
            if isinstance(real, str):
                # **거절도 같아야 한다.** 코드판이 거절하는 카드(Prony 합 ≥ 1, r ≤ 0 …)를
                # 정의판이 내면 사용 중단 → 정의판으로 바꾼 순간 검사가 빠진다.
                assert isinstance(made, str), f"{where}: 코드판은 거절하는데 정의판은 냈다"
                continue
            assert not isinstance(made, str), f"{where}: 정의판만 거절한다 — {made}"
            assert made.text == real.text, where
            assert made.notes == real.notes, where
            compared += 1
    assert compared, f"{key}: 견줄 카드가 하나도 없다 — 시험 카드를 더한다"


@pytest.mark.parametrize("key", ["dyna", "dyna_rate", "openradioss", "openradioss_rate"])
def test_파단_칸을_켜도_글자까지_같다(key: str) -> None:
    """내보내기 선택(`Deck.options`, ADR 0059 후속, 2026-10-08) — 켜면 추정 파단 변형률이 칸에
    선다. 정의판도 같은 결정을 읽는다(`options.fail_from_elongation`). 연신율이 없는 카드에
    켜면 칸은 비고 그렇다는 말이 남는다 — 그것까지 같아야 한다."""
    code, twin = export.renderer(key), TWINS[key]
    compared = filled = 0
    for name, blocks in CARDS.items():
        deck = replace(_deck(blocks), options={export.FAIL_FROM_ELONGATION: True})
        if export.missing_for(deck, code):
            continue
        for system in export.SYSTEMS:
            real, made = _run(code, deck, system), _run(twin, deck, system)
            where = f"{key} · {name} · {system.key}"
            if isinstance(real, str):
                assert isinstance(made, str), where
                continue
            assert not isinstance(made, str), f"{where}: 정의판만 거절한다 — {made}"
            assert made.text == real.text, where
            assert made.notes == real.notes, where
            compared += 1
            filled += "from elongation at break" in real.text
    assert compared and filled, key


def test_거절하는_카드가_실제로_시험된다() -> None:
    """`거절_` 카드마다 **코드판이 거절하는 형식이 하나는** 있다 — 카드를 잘못 만들면 거절
    검사가 조용히 빈다."""
    for name, blocks in CARDS.items():
        if not name.startswith("거절_"):
            continue
        deck = _deck(blocks)
        refused = [
            key
            for key in TWINS
            if not export.missing_for(deck, export.renderer(key))
            and isinstance(_run(export.renderer(key), deck, export.SYSTEMS[0]), str)
        ]
        assert refused, f"{name}: 거절하는 코드판이 없다"
