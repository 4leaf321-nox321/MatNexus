"""대표값 선택 — **고르되, 진 후보를 숨기지 않는다.**

같은 재료·같은 물성에 값이 여럿일 때(42,209건 중 흔하다) 화면·내보내기가 쓸
하나를 고른다. MaterialTwin 의 `_rep_rank` 를 축약 이식한 것이다 — 순위 축을
늘리지 않는 것까지가 원본의 결론이었다(축을 넣어 보니 개선보다 개악이 많았고,
대신 **밀린 이유를 사람에게 보여 준다**).

순위(앞이 이긴다):

    ① 고체상 먼저      용융·액체 상태 값은 뒤로 (solder 용융 물성이 대표가 되면 안 된다)
    ② 등급(tier) 낮은 것   실측 > 핸드북 > 2차 인용 > 추정
    ③ 수치 있는 것
    ④ 기준 온도 근접    23℃(296.15K) 에 가까운 것. 온도 미기재는 벌점 —
                       「25℃ 실측」 이 「온도 없는 시트값」 을 이긴다
    ⑤ 조건 적은 것      (관리 표지 제외) 조건이 적을수록 일반적인 값
    ⑥ 입력 순서        mt_id — 마지막 동률 깨기
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 조건이 아니라 관리 기록인 키 — 순위·조건 수에 안 센다 (원본 `_NOT_A_CONDITION`).
_BOOKKEEPING_KEYS = frozenset(
    {
        "corrected_by",
        "correction_reason",
        "correction_evidence",
        "moved_from_material",
        "moved_from_source",
        "merge_verdict",
        "direction_verbatim",
    }
)

_NOT_SOLID = ("melt", "molten", "liquid", "용융", "액체")

#: 기준 온도 — 상온 23℃.
_REFERENCE_K = 296.15
#: 온도 미기재 벌점(K 환산 거리). 원본과 같은 5.0 — 이보다 가까운 실측만 이긴다.
_UNKNOWN_TEMPERATURE_PENALTY = 5.0

#: 순위 자리 이름 — `separated_by` 가 이 말로 밀린 이유를 말한다.
_SLOTS = ("상태", "등급", "수치", "온도", "조건 수", "입력 순서")


def is_bookkeeping(key: str) -> bool:
    return (
        key in _BOOKKEEPING_KEYS
        or key.startswith("verdict_")
        or key.endswith("_before_correction")
    )


def semantic_conditions(conditions: dict[str, Any] | None) -> dict[str, Any]:
    """관리 표지를 뺀, 물리적 뜻이 있는 조건만."""
    if not isinstance(conditions, dict):
        return {}
    return {k: v for k, v in conditions.items() if not is_bookkeeping(k)}


def _temperature_distance(conditions: dict[str, Any]) -> float:
    for key, offset in (("temperature_k", 0.0), ("temperature_c", 273.15)):
        raw = conditions.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return abs(float(raw) + offset - _REFERENCE_K)
    return _UNKNOWN_TEMPERATURE_PENALTY


@dataclass(frozen=True)
class Annotation:
    representative: bool
    n_candidates: int
    separated_by: str | None
    """대표에게 **어느 자리에서** 밀렸는가. 대표 자신은 None."""

    distinguishing: dict[str, Any] = field(default_factory=dict)
    """**후보들 사이에서 실제로 값이 갈리는 조건**만. 이 값의 것을 담는다.

    조건은 대개 길다 — `regime`·`below_Tg`·`specimen`·`method` 가 한 줄에 늘어서고,
    후보가 넷이면 사람이 그 넷을 눈으로 대조해서 「무엇이 다른가」 를 찾아야 한다.
    실측(2026-09-09): 값이 둘 이상인 조합 6,136개 중 **98%가 조건이 서로 다르다** —
    같은 것을 여러 번 잰 것이 아니라 **다른 조건의 값**이라는 뜻이다.

    그래서 겹치는 조건은 빼고 **갈리는 것만** 준다. 화면이 대조를 대신한다.
    """


#: 값의 정체를 이루는 키 — 조건이 아니라 「무엇인가」 다(ADR 0029). 갈림 표시에서 뺀다.
_IDENTITY_KEYS = frozenset({"term", "unit_of_term", "model", "set_id"})


def _distinguishing(members: list[Any]) -> dict[Any, dict[str, Any]]:
    """무리 안에서 **값이 갈리는 조건 키**만 뽑는다 → `{값 id: {키: 그 값의 조건}}`.

    모두가 같은 값을 가진 키는 뺀다 — 그것은 이 무리를 가르지 않으므로, 보여 줘도
    사람이 지워 가며 읽어야 할 글자만 는다.
    """
    if len(members) < 2:
        return {one.id: {} for one in members}

    seen: dict[str, set[str]] = {}
    for one in members:
        conditions = semantic_conditions(one.conditions)
        for key, value in conditions.items():
            if key in _IDENTITY_KEYS:
                continue
            seen.setdefault(key, set()).add(repr(value))
    # 값이 하나뿐인 키 = 모두 같다. 없는 값도 「없음」 이라는 값이므로, 일부에만
    # 있는 키는 갈림으로 친다.
    varying = {
        key
        for key, values in seen.items()
        if len(values) > 1
        or any(key not in semantic_conditions(one.conditions) for one in members)
    }
    return {
        one.id: {
            key: value
            for key, value in semantic_conditions(one.conditions).items()
            if key in varying
        }
        for one in members
    }


def _rank(value: Any) -> tuple[float, ...]:
    conditions = semantic_conditions(value.conditions)
    state = str(conditions.get("state", "")).lower()
    return (
        1.0 if any(word in state for word in _NOT_SOLID) else 0.0,
        float(value.quality_tier),
        0.0 if value.value_num is not None else 1.0,
        _temperature_distance(conditions),
        float(len(conditions)),
        float(value.mt_id),
    )


def annotate(values: list[Any]) -> dict[Any, Annotation]:
    """(같은 재료의) 값 목록 → id 별 대표/대안 주석.

    property_key 로 무리 짓고, 무리마다 순위 최상을 대표로 삼는다.
    """
    groups: dict[str, list[Any]] = {}
    for one in values:
        groups.setdefault(one.property_key, []).append(one)

    out: dict[Any, Annotation] = {}
    for members in groups.values():
        ranked = sorted(members, key=_rank)
        winner = ranked[0]
        winner_rank = _rank(winner)
        varying = _distinguishing(members)
        out[winner.id] = Annotation(
            representative=True,
            n_candidates=len(members),
            separated_by=None,
            distinguishing=varying.get(winner.id, {}),
        )
        for loser in ranked[1:]:
            loser_rank = _rank(loser)
            slot = next(
                (_SLOTS[i] for i in range(len(_SLOTS)) if winner_rank[i] != loser_rank[i]),
                _SLOTS[-1],
            )
            out[loser.id] = Annotation(
                representative=False,
                n_candidates=len(members),
                separated_by=slot,
                distinguishing=varying.get(loser.id, {}),
            )
    return out
