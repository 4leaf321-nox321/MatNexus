"""자동 재시도가 **무엇을 넓히고 무엇을 못 넓히는가**.

AI 가 처리를 돌리다 실패하면 레시피를 조금씩 바꿔 가며 될 때까지 다시 시도하려
든다. 그 자체를 막을 수는 없지만(사람도 그렇게 한다), **방어선까지 내리면 안 된다.**

    실측(2026-08-29): 18점짜리 곡선에서 탄성계수가 1.83 GPa 로 나왔다 — 강판이면
    200 GPa 다. 그 뒤로 못 믿을 값은 아예 안 내고, 그 임계값은 **코드 상수**로 뒀다.

이 시험이 지키는 것: 넓히는 것은 「어디를 볼까」(구간·창)뿐이고, 「얼마나 믿을까」
(최소 점 수·R² 문턱)는 애초에 옵션에 없어 손댈 수 없다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server"))

import retry_plan  # noqa: E402


def _steps(**options: Any) -> list[dict[str, Any]]:
    return [{"plugin": "tensile.elastic_modulus", "options": dict(options)}]


class TestWiden:
    def test_구간을_넓힌다(self) -> None:
        made = retry_plan.widen(_steps(maximum_strain=0.01))
        assert [one[0]["options"]["maximum_strain"] for one in made] == [0.02, 0.04]

    def test_넓힐_것이_없으면_빈_목록이다(self) -> None:
        """**「여러 번 시도했다」 는 인상만 남기지 않는다** — 같은 실패를 두 번 겪는다."""
        assert retry_plan.widen(_steps(strain="strain", stress="stress")) == []
        assert retry_plan.widen([]) == []

    def test_켬끔_옵션은_안_건드린다(self) -> None:
        """`bool` 은 `int` 의 하위형이다 — 참을 2배 하면 2가 된다."""
        made = retry_plan.widen(_steps(maximum_strain=0.01, window=True))
        for one in made:
            assert one[0]["options"]["window"] is True

    def test_모르는_옵션은_안_건드린다(self) -> None:
        """무슨 뜻인지 모르는 값을 곱하면 무엇이 바뀌는지 아무도 모른다."""
        made = retry_plan.widen(_steps(maximum_strain=0.01, mystery=5))
        for one in made:
            assert one[0]["options"]["mystery"] == 5

    def test_원본을_안_바꾼다(self) -> None:
        """첫 시도의 기록이 남아야 「무엇을 바꿔 봤나」 를 말할 수 있다."""
        original = _steps(maximum_strain=0.01)
        retry_plan.widen(original)
        assert original[0]["options"]["maximum_strain"] == 0.01

    def test_임계값은_넓힐_목록에_없다(self) -> None:
        """**이 시험이 이 파일의 이유다.**

        최소 점 수·R² 문턱은 레시피 옵션이 아니라 코드 상수다. 넓힐 수 있는 이름
        목록에 그것들이 들어오는 순간 방어선이 API 로 열린다.
        """
        forbidden = {
            "min_points",
            "minimum_points",
            "min_r_squared",
            "r_squared_threshold",
            "tolerance",
        }
        assert not (set(retry_plan.WIDENABLE) & forbidden)
