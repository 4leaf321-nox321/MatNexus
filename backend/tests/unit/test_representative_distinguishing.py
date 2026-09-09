"""후보를 **가르는 조건**만 뽑는다 — 사람이 눈으로 대조하지 않게.

실측(2026-09-09): 값이 둘 이상인 (재료·물성) 조합 6,136개 중 **98%가 조건이 서로
다르다.** 같은 것을 여러 번 잰 것이 아니라 다른 조건의 값이라는 뜻이고, 그래서
「무엇이 다른가」 가 고를 때 가장 중요한 정보다.

전에는 화면이 조건 전체를 그대로 뿌렸다 — 후보가 넷이면 긴 문자열 넷을 눈으로
대조해서 겹치는 것을 지워 가며 차이를 찾아야 했다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.shared import representative


@dataclass
class FakeValue:
    """`annotate` 가 보는 만큼만."""

    property_key: str
    conditions: dict[str, Any] | None
    quality_tier: int = 2
    value_num: float | None = 1.0
    mt_id: int = 1
    id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid.uuid4()


def _cte(**conditions: Any) -> FakeValue:
    return FakeValue(property_key="thermal.expansion_linear", conditions=dict(conditions))


class TestDistinguishing:
    def test_겹치는_조건은_뺀다(self) -> None:
        """`specimen` 이 다 같으면 보여 줘도 지워 가며 읽어야 할 글자만 는다."""
        rows = [
            _cte(specimen="laminate", regime="alpha1 (below Tg)"),
            _cte(specimen="laminate", regime="alpha2 (above Tg)"),
        ]
        marks = representative.annotate(rows)
        for one in rows:
            assert set(marks[one.id].distinguishing) == {"regime"}

    def test_일부에만_있는_키도_가르는_것이다(self) -> None:
        """한쪽에만 `bound` 가 있으면 그것이 둘을 가른다 — 없는 것도 값이다."""
        rows = [
            _cte(regime="alpha1", bound="lower"),
            _cte(regime="alpha1"),
        ]
        marks = representative.annotate(rows)
        assert "bound" in marks[rows[0].id].distinguishing
        assert marks[rows[1].id].distinguishing == {}

    def test_후보가_하나면_가를_것이_없다(self) -> None:
        one = _cte(regime="alpha1", specimen="laminate")
        marks = representative.annotate([one])
        assert marks[one.id].distinguishing == {}

    def test_관리_표지는_안_센다(self) -> None:
        """`verdict_*`·`corrected_by` 는 조건이 아니라 이관 기록이다."""
        rows = [
            _cte(regime="alpha1", corrected_by="pass-2"),
            _cte(regime="alpha1", corrected_by="pass-7"),
        ]
        marks = representative.annotate(rows)
        for one in rows:
            assert marks[one.id].distinguishing == {}

    def test_값의_정체는_조건이_아니다(self) -> None:
        """`term`·`model` 은 「무엇인가」 이지 「어떤 조건인가」 가 아니다(ADR 0029)."""
        rows = [
            FakeValue(
                property_key="mechanical.anand_constant",
                conditions={"term": "A", "model": "anand"},
            ),
            FakeValue(
                property_key="mechanical.anand_constant",
                conditions={"term": "n", "model": "anand"},
            ),
        ]
        marks = representative.annotate(rows)
        for one in rows:
            assert marks[one.id].distinguishing == {}


class TestSummary:
    """**조건이 완전히 같은 중복에만** 종합값을 낸다(실측 1%)."""

    def test_조건이_같으면_중앙값을_낸다(self) -> None:
        rows = [
            _cte(specimen="laminate"),
            _cte(specimen="laminate"),
            _cte(specimen="laminate"),
        ]
        rows[0].value_num, rows[1].value_num, rows[2].value_num = 990.0, 1040.0, 1350.0
        marks = representative.annotate(rows)
        rep = next(one for one in rows if marks[one.id].representative)
        summary = marks[rep.id].summary
        assert summary is not None
        # **평균이 아니라 중앙값이다** — 값이 서넛뿐이라 튄 값 하나가 평균을 끈다.
        assert summary["median"] == 1040.0
        assert (summary["min"], summary["max"], summary["n"]) == (990.0, 1350.0, 3)

    def test_조건이_다르면_안_낸다(self) -> None:
        """**이 시험이 이 기능의 안전장치다.**

        하한과 상한을, Tg 위와 아래를 섞은 중앙값은 아무것도 아닌 수다.
        """
        rows = [_cte(regime="alpha1"), _cte(regime="alpha2")]
        rows[0].value_num, rows[1].value_num = 1.1e-05, 2.7e-04
        marks = representative.annotate(rows)
        assert all(marks[one.id].summary is None for one in rows)

    def test_대표_줄에만_싣는다(self) -> None:
        """줄마다 되풀이하면 「종합이 여럿」 으로 읽힌다."""
        rows = [_cte(specimen="a"), _cte(specimen="a")]
        rows[0].value_num, rows[1].value_num = 10.0, 20.0
        marks = representative.annotate(rows)
        carried = [one for one in rows if marks[one.id].summary is not None]
        assert len(carried) == 1
        assert marks[carried[0].id].representative

    def test_후보가_하나면_안_낸다(self) -> None:
        one = _cte(specimen="a")
        marks = representative.annotate([one])
        assert marks[one.id].summary is None
