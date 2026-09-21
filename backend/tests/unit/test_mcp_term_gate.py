"""AI 가 **새 기준정보 값을 세우지 못하게** 하는 문 (ADR 0032).

화면에서는 「새로 추가」 를 안 보여 주고 서버는 403 으로 막는다. MCP 는 그 사이에
하나 더 둔다 — **아무것도 안 만든 채로 멈추기 위해서**다: 재료를 만들다 Grade 에서
막히면 그 앞의 Family·Category 는 이미 생겨 있고, 그것은 아무도 쓰지 않는 용어로
남는다.

지키는 것 셋:

    통제되는 축만 본다      로트·메모까지 막으면 아무 일도 못 한다
    같은 표기가 있으면 통과  `secc` 와 `SECC` 를 가르는 것이 이 문의 목적이다
    모르면 안 막는다        축 목록을 못 받은 것이 쓰기 전체를 세우면 안 된다
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import term_gate  # noqa: E402

POLICY = {
    "family": "managed",
    "category": "managed",
    "grade": "managed",
    "manufacturer": "managed",
    "vendor": "managed",
    "sales_type": "open",
    "specimen_standard": "open",
}


def _terms(*values: str) -> list[dict[str, str]]:
    return [{"value": one} for one in values]


class Test검사할_것:
    def test_통제되는_축만_본다(self) -> None:
        got = term_gate.to_check(
            {"grade": "SECC", "sales_type": "직거래", "lot_no": "L-1"}, POLICY
        )
        # `sales_type` 은 open 이라, `lot_no` 는 용어가 아니라 안 본다.
        assert got == [("grade", "grade", "SECC")]

    def test_빈_값은_안_본다(self) -> None:
        assert term_gate.to_check({"grade": None, "manufacturer": "  "}, POLICY) == []

    def test_유통사와_주_벤더는_한_축이다(self) -> None:
        """같은 회사가 로트에 따라 둘 중 어느 쪽도 된다 — 백엔드 바인딩과 같다."""
        got = term_gate.to_check(
            {"distributor": "삼성물산", "primary_vendor": "포스코"}, POLICY
        )
        assert [axis for _, axis, _ in got] == ["vendor", "vendor"]

    def test_정책을_모르는_축은_안_막는다(self) -> None:
        """축 목록을 못 받아 왔을 때 전부 막으면, 읽기 한 번 실패가 쓰기를 세운다.
        판정은 어차피 서버가 한다."""
        assert term_gate.to_check({"grade": "SECC"}, {}) == []


class Test새_낱말인가:
    def test_같은_표기가_있으면_통과한다(self) -> None:
        assert term_gate.is_new("SECC", _terms("SECC", "SECD")) is False

    def test_대소문자와_공백은_무시한다(self) -> None:
        """**`secc` 와 `SECC` 를 가르는 것이 이 문의 목적이다** — 여기서 둘을 다른
        것으로 보면 문이 그 갈림을 스스로 만든다."""
        assert term_gate.is_new(" secc ", _terms("SECC")) is False

    def test_비슷하기만_하면_새것이다(self) -> None:
        # `SECC강판` 은 `SECC` 가 아니다. 후보로 보여 주고 사람이 고르게 한다.
        assert term_gate.is_new("SECC강판", _terms("SECC", "SECCN5")) is True
        assert term_gate.candidates(_terms("SECC", "SECCN5")) == ["SECC", "SECCN5"]

    def test_아무것도_없으면_새것이다(self) -> None:
        assert term_gate.is_new("DP980", []) is True


def test_거절은_다음에_할_일을_준다() -> None:
    """「권한이 없습니다」 로 끝내면 AI 는 그 말만 옮기고 끝난다. 갈림은 대개
    오타에서 나므로 후보가 있으면 그 자리에서 해결된다."""
    got = term_gate.refusal(
        [{"field": "grade", "axis": "grade", "value": "SECC강판", "candidates": ["SECC"]}]
    )
    assert "만들지 않았습니다" in got["error"]
    assert got["blocked"][0]["candidates"] == ["SECC"]
    assert "부서 관리자" in got["hint"]
