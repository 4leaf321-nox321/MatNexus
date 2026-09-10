"""한 벌 이름 아래 **여러 벌**이 들어 있을 때 갈라 내는 규칙.

## 왜 갈라야 하나 (실측 2026-09-10)

출처 하나가 한 `set_id` 아래 온도별·계열별·노화 시간별로 여러 벌을 담는 일이
흔하다. 안 가르면 **한 벌 안에 같은 항이 여러 번** 들어간다 — 카탈로그 전수로
재료 25종·벌 61개·값 435건이 그랬다. NBR 씰 고무는 노화 8조건이 한 벌로 뭉쳐
`C01` 이 8번이었고, 그것을 그대로 받아 가면 **`C01` 이 8개인 Mooney-Rivlin** 이
재료에 담긴다 — 카드는 그중 어느 것을 쓸지 모른다.

## 규칙이 조용히 틀릴 수 있는 자리

    가장 성긴 축을 고른다      항마다 달라지는 칸으로 가르면 «항 하나에 벌 하나» 가 된다
    없는 것도 값이다          어떤 벌에만 붙은 칸은 그 있고 없음이 곧 축이다
    이관 기록은 축이 아니다    「고친 이력이 다르다」 로 벌이 갈리면 안 된다
    못 가르면 말한다          겹친 항을 들고 다녀야 채택이 막힌다
"""

from __future__ import annotations

from typing import Any

from app.modules.catalog.parameters import _axis_candidates, _split_axes


def _rows(*items: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"term": term, "conditions": {"term": term, **rest}} for term, rest in items]


class Test축_고르기:
    def test_값이_갈리는_칸만_후보다(self) -> None:
        rows = _rows(
            ("A", {"model": "anand", "temperature_c": 20, "lab": "K"}),
            ("B", {"model": "anand", "temperature_c": 80, "lab": "K"}),
        )
        # `model` 은 이름표라 제외, `lab` 은 값이 하나뿐이라 제외.
        assert _axis_candidates(rows) == ["temperature_c"]

    def test_이관_기록은_축이_아니다(self) -> None:
        """**「고친 이력이 다르다」 는 물성과 아무 상관이 없다.**"""
        rows = _rows(
            ("A", {"corrected_by": "52차", "verdict_tie_axis": "x", "n_before_correction": 1}),
            ("A", {"corrected_by": "53차", "verdict_tie_axis": "y", "n_before_correction": 2}),
        )
        assert _axis_candidates(rows) == []

    def test_없는_것도_값이다(self) -> None:
        """실측: Ogden 벌 넷이 이것 때문에 안 갈렸다.

        `mode` 가 절반에만 붙어 있으면, 있는 행끼리만 보면 값이 한 가지라 축이
        아닌 줄 안다 — 그런데 그 있고 없음이 곧 두 벌을 가른다.
        """
        rows = _rows(
            ("mu1", {}),
            ("mu1", {"mode": "inverse_fe"}),
        )
        assert _axis_candidates(rows) == ["mode"]
        assert _split_axes(rows) == ("mode",)

    def test_안_적힌_것과_null_로_적힌_것은_다르다(self) -> None:
        """**「없다」 와 「없다고 적었다」 는 다른 말이다.**

        표 하나로 뭉뚱그리면 그 둘이 한 벌로 묶인다 — 조건을 적어 둔 쪽은
        「재지 않았다」 를 밝힌 것이고, 안 적힌 쪽은 아무 말도 안 한 것이다.
        """
        rows = _rows(
            ("A", {"mode": None}),
            ("A", {}),
        )
        assert _split_axes(rows) == ("mode",)


class Test가르기:
    def test_안_겹치면_안_가른다(self) -> None:
        """**늘 가르면 멀쩡한 벌이 조각난다.**"""
        rows = _rows(("A", {"temperature_c": 20}), ("B", {"temperature_c": 80}))
        assert _split_axes(rows) == ()

    def test_온도로_가른다(self) -> None:
        rows = _rows(
            ("A", {"temperature_c": 20}),
            ("B", {"temperature_c": 20}),
            ("A", {"temperature_c": 80}),
            ("B", {"temperature_c": 80}),
        )
        assert _split_axes(rows) == ("temperature_c",)

    def test_항마다_달라지는_칸으로는_안_가른다(self) -> None:
        """**가장 성긴 축을 고른다.**

        `term_index` 로 가르면 항 하나에 벌 하나가 되어 버린다 — 갈린 것이 아니라
        흩어진 것이다. 실제로 가르는 축은 항을 한 벌씩 통째로 되풀이시킨다.
        """
        rows = _rows(
            ("w1", {"series": "E", "term_index": 1}),
            ("w2", {"series": "E", "term_index": 2}),
            ("w1", {"series": "G", "term_index": 1}),
            ("w2", {"series": "G", "term_index": 2}),
        )
        assert _split_axes(rows) == ("series",)

    def test_네모반듯한_쪽을_고른다(self) -> None:
        """묶음 수가 같으면 **묶음마다 값 수가 같은** 축이 진짜다."""
        rows = _rows(
            ("A", {"temperature_c": 20, "ragged": "p"}),
            ("B", {"temperature_c": 20, "ragged": "q"}),
            ("A", {"temperature_c": 80, "ragged": "q"}),
            ("B", {"temperature_c": 80, "ragged": "q"}),
        )
        assert _split_axes(rows) == ("temperature_c",)

    def test_축이_없으면_못_가른다(self) -> None:
        """가를 자료가 없으면 억지로 가르지 않는다 — 겹친 채로 두고 말한다."""
        rows = _rows(("A", {}), ("A", {}))
        assert _split_axes(rows) == ()

    def test_축_둘까지_겹쳐_본다(self) -> None:
        """온도와 계열이 함께 걸린 벌은 하나로는 안 갈린다."""
        rows = _rows(
            ("A", {"temperature_c": 20, "series": "E"}),
            ("A", {"temperature_c": 20, "series": "G"}),
            ("A", {"temperature_c": 80, "series": "E"}),
            ("A", {"temperature_c": 80, "series": "G"}),
        )
        assert set(_split_axes(rows)) == {"temperature_c", "series"}
