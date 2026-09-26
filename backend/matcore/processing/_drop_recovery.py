"""순수한 공칭 응력 강하·회복 사건 검출과 곡선 근사 보조 함수.

이 모듈은 ``Frame`` 이나 처리 레지스트리를 알지 않는다. 호출자가 선택한 관측
구간의 원행 순서 그대로 받은 배열만 읽고, 결과 배열도 새로 만든다. 따라서
``tensile.yield_drop`` 의 진단을 실제 자료 검증에서 그대로 재사용할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

EventKind = Literal["full_recovery", "partial_recovery", "terminal_unrecovered"]


@dataclass(frozen=True)
class DropEvent:
    """한 번의 유의한 하강과 그 뒤의 회복 상태.

    모든 index 는 함수에 건네진 배열의 **원행 index** 다. 호출자가 도메인 배열을
    잘랐다면 원래 Frame index 를 더하는 책임은 호출자에게 있다.
    ``recovery_index`` 는 trough 뒤 의미 있는 반등이 시작된 첫 행이고,
    ``end_index`` 는 full recovery일 때 원래 peak로 처음 돌아온 행이다. 그 사이의
    작은 재하강은 별도 사건으로 나누지 않는다.
    """

    peak_index: int
    drop_start: int
    trough_index: int
    recovery_index: int | None
    end_index: int
    kind: EventKind
    end_at_observation_boundary: bool


def _validate_options(
    values: np.ndarray,
    threshold: float,
    recovery_threshold: float,
    min_reference_fraction: float,
) -> None:
    if values.ndim != 1:
        raise ValueError("stress 는 1차원 배열이어야 합니다")
    if values.size == 0:
        return
    if not np.all(np.isfinite(values)):
        raise ValueError("stress 에 유한하지 않은 값이 있습니다")
    if not np.isfinite(threshold) or not 0 <= threshold < 1:
        raise ValueError(f"threshold 는 0 이상 1 미만이어야 합니다: {threshold}")
    if not np.isfinite(recovery_threshold) or not 0 <= recovery_threshold < 1:
        raise ValueError(
            f"recovery_threshold 는 0 이상 1 미만이어야 합니다: {recovery_threshold}"
        )
    if not np.isfinite(min_reference_fraction) or not 0 <= min_reference_fraction <= 1:
        raise ValueError(
            f"min_reference_fraction 은 0 이상 1 이하이어야 합니다: {min_reference_fraction}"
        )


def detect_events(
    stress: np.ndarray,
    threshold: float,
    recovery_threshold: float | None = None,
    min_reference_fraction: float = 0.05,
) -> list[DropEvent]:
    """원행 순서에서 유의한 하강→회복 사건을 찾는다.

    양의 관측 응력의 ``min_reference_fraction`` 미만인 봉우리는 기준점으로 쓰지
    않는다. 그 밖의 하강은 선행 봉우리에서 ``threshold`` 를 넘는 첫 행을
    ``drop_start`` 로 삼고, 최저점과 회복을 추적한다. ``recovery_threshold`` 를
    넘게 오르되 봉우리 높이에 이르지 못하면 partial 이며, 다음 유의한 하강이
    시작되면 그 전의 회복 봉우리에서 사건을 닫고 다음 사건을 이어 찾는다.

    이 함수는 변형률을 읽지 않으므로 중복·역전된 변형률도 원행 시간 순서로
    진단할 수 있다. 입력은 복사해 검증하며 호출자의 배열을 바꾸지 않는다.
    """

    values = np.asarray(stress, dtype=np.float64)
    if recovery_threshold is None:
        recovery_threshold = threshold
    _validate_options(
        values, float(threshold), float(recovery_threshold), float(min_reference_fraction)
    )
    n = int(values.size)
    if n < 2:
        return []

    positive = values[values > 0]
    if positive.size == 0:
        return []
    reference_floor = float(np.max(positive)) * float(min_reference_fraction)

    events: list[DropEvent] = []
    scan = 0
    while scan < n - 1:
        found = _next_drop(
            values,
            scan,
            float(threshold),
            reference_floor,
        )
        if found is None:
            break
        peak_index, drop_start = found
        peak_value = float(values[peak_index])
        traced = _trace_drop(
            values,
            peak_index,
            drop_start,
            peak_value,
            float(threshold),
            float(recovery_threshold),
        )
        events.append(traced[0])
        # A full recovery is itself a possible reference peak for the next row. A
        # partial event closed by the next drop likewise starts the next search at
        # the rebound peak, so the second event cannot be skipped.
        scan = traced[1]

    return events


def _next_drop(
    values: np.ndarray,
    start: int,
    threshold: float,
    reference_floor: float,
) -> tuple[int, int] | None:
    peak_index: int | None = None
    peak_value = -np.inf
    for index in range(max(0, start), len(values) - 1):
        value = float(values[index])
        # >= deliberately selects the last row of a flat maximum before a drop.
        # That avoids attributing a later drop to the beginning of a long plateau.
        if value > 0 and value >= reference_floor and value >= peak_value:
            peak_index = index
            peak_value = value
        if peak_index is None:
            continue
        following = float(values[index + 1])
        if peak_value - following > threshold * peak_value:
            return peak_index, index + 1
    return None


def _trace_drop(
    values: np.ndarray,
    peak_index: int,
    drop_start: int,
    peak_value: float,
    threshold: float,
    recovery_threshold: float,
) -> tuple[DropEvent, int]:
    # First look for the first return to the original peak. If it exists, the whole
    # outer episode is one full event even when it contains smaller internal falls.
    # This is what keeps a 906 -> 911 -> 1637 episode together at the default
    # threshold instead of treating the 911 rebound as a new episode.
    full_hits = np.flatnonzero(values[drop_start + 1 :] >= peak_value)
    if full_hits.size:
        full_end = int(drop_start + 1 + full_hits[0])
        trough_index = drop_start
        for index in range(drop_start + 1, full_end + 1):
            if float(values[index]) < float(values[trough_index]):
                trough_index = index
        trough_value = float(values[trough_index])
        recovery_index: int | None = None
        for index in range(trough_index + 1, full_end + 1):
            value = float(values[index])
            if value >= peak_value or value - trough_value > recovery_threshold * peak_value:
                recovery_index = index
                break
        return (
            DropEvent(
                peak_index,
                drop_start,
                trough_index,
                recovery_index,
                full_end,
                "full_recovery",
                False,
            ),
            full_end,
        )

    trough_index = drop_start
    recovery_index = None
    rebound_peak_index: int | None = None

    for index in range(drop_start + 1, len(values)):
        value = float(values[index])

        if recovery_index is None:
            # The first trough wins a tie. Once a meaningful rebound has begun,
            # later drops belong to the next event and cannot rewrite this one.
            if value < float(values[trough_index]):
                trough_index = index
            if value >= peak_value:
                return (
                    DropEvent(
                        peak_index,
                        drop_start,
                        trough_index,
                        index,
                        index,
                        "full_recovery",
                        False,
                    ),
                    index,
                )
            if value - float(values[trough_index]) > recovery_threshold * peak_value:
                recovery_index = index
                rebound_peak_index = index
            continue

        assert rebound_peak_index is not None
        rebound_value = float(values[rebound_peak_index])
        if value >= peak_value:
            return (
                DropEvent(
                    peak_index,
                    drop_start,
                    trough_index,
                    recovery_index,
                    index,
                    "full_recovery",
                    False,
                ),
                index,
            )
        if value > rebound_value:
            rebound_peak_index = index
            continue
        # A new significant fall closes the partial event just before that fall.
        # Start the next search at the rebound peak so it becomes its peak.
        if rebound_value - value > threshold * peak_value:
            return (
                DropEvent(
                    peak_index,
                    drop_start,
                    trough_index,
                    recovery_index,
                    rebound_peak_index,
                    "partial_recovery",
                    False,
                ),
                rebound_peak_index,
            )

    if recovery_index is None:
        return (
            DropEvent(
                peak_index,
                drop_start,
                trough_index,
                None,
                len(values) - 1,
                "terminal_unrecovered",
                True,
            ),
            len(values),
        )
    assert rebound_peak_index is not None
    return (
        DropEvent(
            peak_index,
            drop_start,
            trough_index,
            recovery_index,
            rebound_peak_index,
            "partial_recovery",
            True,
        ),
        len(values),
    )


__all__ = ["DropEvent", "EventKind", "detect_events"]
