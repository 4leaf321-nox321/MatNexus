"""장비 파일 파서 — 바이트를 받아 채널과 요약값을 낸다.

**파일시스템을 모른다.** 파서는 `bytes` 를 받는다. 경로를 받으면 서버·배치·장비
파이프라인이 각자 다르게 열게 되고, 테스트도 임시 파일을 만들어야 한다. 읽는 것은
호출부가 하고, 파서는 해석만 한다.

**모르는 형식은 명시적으로 실패한다.** 조용히 잘못 읽는 쪽이 훨씬 나쁘다 —
잘못 읽힌 곡선은 그럴듯해 보여서 나중에 찾아낼 수 없고, 그 곡선으로 적합한 물성이
해석에 들어간다. `ParseError` 는 `TestRun.parse_error` 에 그대로 남아 사람이 본다.

단위는 파서가 SI 로 바꿔서 낸다(`matcore.units`). 원본 단위는 `source_unit` 에
남겨, 나중에 "장비가 뭐라고 적어 보냈나"를 답할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ParseError(Exception):
    """이 파일을 이 파서로는 읽을 수 없다.

    메시지는 사용자가 읽는다. "무엇을 기대했는데 무엇이 왔는지"를 적는다 —
    '파싱 실패' 만 남기면 다음 사람이 파일을 직접 열어 봐야 한다.
    """


@dataclass(frozen=True)
class Channel:
    """곡선의 열 하나. 값은 이미 SI 다."""

    key: str
    label: str
    si_unit: str
    values: tuple[float | None, ...]
    source_unit: str | None = None
    """장비가 적어 보낸 단위. 변환 근거를 남긴다."""


@dataclass(frozen=True)
class SummaryValue:
    """장비가 계산해 준 값 하나.

    `value` 와 `text` 를 나눠 두는 이유: 장비가 숫자 자리에 `"Unknown"` 을 보낸다.
    그것을 숫자 칸에 억지로 넣으면 집계에서 하나의 값으로 잡혀 통계가 오염되고,
    버리면 "장비가 못 구했다"는 사실 자체가 사라진다.
    """

    key: str
    label: str
    value: float | None = None
    text: str | None = None
    si_unit: str | None = None
    source_unit: str | None = None


@dataclass(frozen=True)
class CurveData:
    """곡선 한 벌. **한 파일이 곡선을 여럿 낼 수 있다.**

    실측: TA DMA850 의 주파수-온도 스윕 파일에는 `[step]` 블록이 8개 있고, 측정
    구간 6개와 처리 결과(TTS 마스터 곡선) 2개가 한 파일에 섞여 있다. 하나로 뭉치면
    서로 다른 온도의 측정이 한 곡선으로 이어져 버린다.
    """

    key: str
    """`Curve.key` 가 된다. 시험 안에서 유일해야 한다."""
    label: str | None = None
    channels: tuple[Channel, ...] = ()
    kind: str = "measured"
    """`measured`(측정) | `derived`(장비가 계산해 준 것).

    버리지도 섞지도 않는다. 버리면 장비가 계산해 준 결과를 잃고, 섞으면 Phase 3
    의 처리가 마스터 곡선을 원본으로 착각한다."""


@dataclass(frozen=True)
class ParsedTest:
    """파서 하나의 산출물."""

    channels: tuple[Channel, ...] = ()
    summary: tuple[SummaryValue, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    """시험자·장비·시험일 등 원문 그대로. 해석은 호출부가 한다."""
    curves: tuple[CurveData, ...] = ()
    """곡선이 여럿일 때. 비어 있으면 `channels` 하나를 `raw` 로 본다."""
    warnings: tuple[str, ...] = ()
    """읽기는 했지만 이상한 것. 실패시키기에는 과하고 묻기에는 아까운 것들."""
    record: dict[str, str] = field(default_factory=dict)
    """시험 기록의 **칸에 채울 값들.** 키는 앱이 정한 칸 이름.

    `metadata` 와 무엇이 다른가: `metadata` 는 파일에 적힌 그대로의 보관이고,
    이쪽은 "이 값을 시험의 어느 칸에 넣어라" 는 **지시**다. 프로파일이 그
    연결을 선언하고, 여기는 그 결과만 담는다.

    **여기서도 DB 는 모른다.** `operator` 가 무슨 컬럼인지 이 층은 모른다 —
    `summary` 의 `tensile_strength` 가 무엇인지 모르는 것과 같다."""
    identity: dict[str, str] = field(default_factory=dict)
    """이 파일이 **어느 재료·시료·시편의 것인지** 가리키는 값들.

    파싱 때는 못 쓴다 — 시험은 이미 시편에 매달려 있다. **짚어 주기만 한다.**
    일괄 등록과 이관 스크립트가 이것을 읽어 사람에게 보여 주거나 짝을 찾는다.

    채우는 것과 갈라 둔 이유는 되돌릴 수 있는 실수와 없는 실수의 차이다.
    시험자를 잘못 채우면 고치면 되지만, 곡선이 남의 재료에 붙으면 그 시험은
    생성 시점에 그 시편 id 에 묶여 있어 칸을 고쳐 되돌릴 수 없다."""

    @property
    def all_curves(self) -> tuple[CurveData, ...]:
        """저장할 곡선들. 단일 곡선 파서와 다중 곡선 파서를 같은 모양으로 본다."""
        if self.curves:
            return self.curves
        if self.channels:
            return (CurveData(key="raw", label=None, channels=self.channels),)
        return ()

    @property
    def row_count(self) -> int:
        return len(self.channels[0].values) if self.channels else 0

    def channel(self, key: str) -> Channel | None:
        return next((c for c in self.channels if c.key == key), None)


def load_builtin() -> None:
    """내장 파서를 레지스트리에 등록한다.

    import 부작용에 기대지 않고 명시적으로 부른다 — `app.jobs.handlers.load_all`
    과 같은 이유다. 워커와 테스트가 같은 함수를 부르면 "테스트에서는 되는데
    워커에서는 파서가 없다"는 어긋남이 생기지 않는다.
    """
    from matcore.parsers import zwick_tra  # noqa: F401
