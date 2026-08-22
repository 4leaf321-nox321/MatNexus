"""시편 비율 조건 — **규격이 치수를 안 주고 비만 주는 일이 흔하다.**

DMA 규격표를 보면 숫자를 실제로 주는 파트가 ISO 6721-2·-3·-10 셋뿐이고 나머지는
전부 비율이다.

    ISO 6721-3   L/h >= 50      저장탄성률 ±5 % 정확도 확보
    ISO 6721-4   La/b > 6       클램프의 횡수축 구속 영향 배제
    ISO 6721-6   h/L > 4        굽힘 성분 기여를 무시할 수준으로
    ISO 6721-12  h/D 1~2        프리로드 하 좌굴·배럴링 방지
    ISO 6721-10  D/d 10~50
    ASTM D7028   스팬/두께 > 10 전단 변형 기여 억제
    ISO 4664-1   변/두께 >= 4   단순 전단 상태·균일 가황

**어겼다고 막지는 않는다.** 규격이 권장값을 주는데 장비가 못 맞추는 일이 실제로
있다 — ISO 6721-4 는 클램프 간 50~100 mm 를 권하지만 Netzsch 는 15 mm,
Mettler 는 20 mm, TA 는 30 mm 가 한계다. **어느 장비도 그 권장값을 만족하지
못한다.** 막으면 실제로 잰 데이터를 시스템에 못 넣게 되고, 그러면 사람은
시스템 밖에서 일한다.

대신 **어긴 채로 쟀다는 것이 기록에 남아야 한다.** 규격 이름만 적힌 보고서는
재현이 안 된다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    """비율 조건 하나 — `분자 / 분모` 가 `[최소, 최대]` 안에 있어야 한다."""

    numerator: str
    denominator: str
    minimum: float | None = None
    maximum: float | None = None
    help: str | None = None

    def label(self, names: Mapping[str, str] | None = None) -> str:
        """사람이 읽는 조건. `게이지 길이 / 두께 >= 50`"""
        show = names or {}
        left = f"{show.get(self.numerator, self.numerator)} / "
        left += show.get(self.denominator, self.denominator)
        if self.minimum is not None and self.maximum is not None:
            return f"{left} = {_num(self.minimum)} ~ {_num(self.maximum)}"
        if self.minimum is not None:
            return f"{left} >= {_num(self.minimum)}"
        if self.maximum is not None:
            return f"{left} <= {_num(self.maximum)}"
        return left


@dataclass(frozen=True)
class Violation:
    """어긴 조건 하나와 **실제 값.** 값이 없으면 사람이 무엇을 고쳐야 할지 모른다."""

    check: Check
    actual: float


def _num(value: float) -> str:
    return f"{value:g}"


def ratio(check: Check, values: Mapping[str, float]) -> float | None:
    """비. 둘 중 하나라도 없거나 분모가 0 이면 `None`.

    **못 잰 것과 어긴 것은 다르다.** 값이 없으면 조건을 판정하지 않는다 — 0 으로
    치면 모든 조건이 어긴 것으로 보이고, 그러면 경고가 소음이 된다.
    """
    top = values.get(check.numerator)
    bottom = values.get(check.denominator)
    if not top or not bottom:
        return None
    return float(top) / float(bottom)


def violations(checks: Sequence[Check], values: Mapping[str, float]) -> list[Violation]:
    """어긴 조건들. 잴 수 없는 조건은 조용히 건너뛴다."""
    found: list[Violation] = []
    for check in checks:
        value = ratio(check, values)
        if value is None:
            continue
        if (check.minimum is not None and value < check.minimum) or (
            check.maximum is not None and value > check.maximum
        ):
            found.append(Violation(check, value))
    return found
