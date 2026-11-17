"""시험 곡선의 **출처** — 잰 것인가, 다른 데서 옮겨 온 것인가(2026-11-17, ADR 0096).

실측(HWAX 연결): 해석 덱의 소성 표에서 복원한 곡선이 시험으로 올라와 실측처럼 쓰였다. 시험에는
출처를 적는 칸이 없었고, MCP `get_test_run` 은 채택 값마다 `origin: measured` 를 고정으로
붙였다.

**막지 않는다**(사용자 결정: 경고만). 출처가 실측이 아니면 카드 근거 · 덱 머리 · 시험 응답에
그렇다고 적고, 통계 · 카드에는 그대로 들어간다 — 판단은 사람이 한다. 곡선 모양으로 거꾸로
짚는 것은 `matcore.curve_quality` 다(출처 칸이 사람이 적은 답이라면, 그것은 곡선이 말하는
것이다).
"""

from __future__ import annotations

MEASURED = "measured"

#: 출처 코드 → 사람이 읽는 이름. 기본은 실측이다(예전 시험 · 장비 파일).
ORIGINS: dict[str, str] = {
    MEASURED: "실측",
    "digitized": "그림에서 읽음(디지타이즈)",
    "deck_restored": "해석 덱 카드에서 복원",
    "synthetic": "식으로 지음(합성)",
}

#: 카드 근거 경고의 이름표 — 「낡은 결과」 와 나란히 선다.
LABEL = "실측이 아닌 곡선"


def label(code: str | None) -> str:
    return ORIGINS.get(code or MEASURED, code or MEASURED)


def is_measured(code: str | None) -> bool:
    return (code or MEASURED) == MEASURED


def warning(code: str) -> str:
    """카드 근거 · 덱 머리에 실을 한 줄."""
    return (
        f"곡선 출처가 「{label(code)}」 인 시험입니다 — 잰 곡선이 아니라, "
        "이 시험에서 나온 값은 "
        "실측이 아닙니다(통계 · 카드에는 그대로 들어갑니다)."
    )
