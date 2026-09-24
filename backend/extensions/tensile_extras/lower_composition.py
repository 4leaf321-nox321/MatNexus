"""Bounded source-event closure and lower-envelope composition helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from matcore.processing._drop_recovery import DropEvent


@dataclass(frozen=True, slots=True)
class LowerComponentClosure:
    """Whole modeled components and eligible source events in one closure."""

    component_indices: tuple[int, ...]
    event_indices: tuple[int, ...]


def validated_source_rows(source_rows: ArrayLike) -> NDArray[np.int64] | None:
    """Return safe source-row evidence, or ``None`` for unusable metadata."""
    try:
        raw = np.asarray(source_rows)
        if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
            return None
        numeric = np.asarray(raw, dtype=np.float64)
        if (
            not np.all(np.isfinite(numeric))
            or np.any(numeric < 0.0)
            or np.any(numeric >= float(1 << 63))
            or np.any(numeric != np.floor(numeric))
            or np.any(np.diff(numeric) <= 0.0)
        ):
            return None
        return numeric.astype(np.int64)
    except (TypeError, ValueError, OverflowError):
        return None


def _eligible_connector(event: DropEvent) -> bool:
    return event.kind == "full_recovery" or (
        event.kind == "partial_recovery"
        and event.recovery_index is not None
        and not event.end_at_observation_boundary
    )


def _touches(left_a: int, right_a: int, left_b: int, right_b: int) -> bool:
    """Inclusive interval touch: overlap or one shared original row."""
    return left_a <= right_b and left_b <= right_a


def connected_lower_closure(
    events: tuple[DropEvent, ...],
    component_intervals: tuple[tuple[int, int], ...],
    component_event_indices: tuple[tuple[int, ...], ...],
    *,
    root_component: int,
    failed_event: int,
) -> LowerComponentClosure | None:
    """Close original eligible event intervals from one blocking component.

    The graph uses only original event intervals and whole prior model-component
    intervals. Observation-boundary partials and terminal events never connect
    nodes. A candidate component that extends past the failed event's observed
    end makes the closure infeasible rather than being partially consumed.
    """
    if len(component_intervals) != len(component_event_indices):
        raise ValueError("component intervals and event memberships must align")
    if not 0 <= root_component < len(component_intervals):
        raise ValueError("root component index is outside the component list")
    if not 0 <= failed_event < len(events):
        raise ValueError("failed event index is outside the event list")
    failed = events[failed_event]
    if not _eligible_connector(failed):
        return None
    bound = failed.end_index
    if component_intervals[root_component][1] > bound:
        return None

    eligible_indices = {
        index
        for index, event in enumerate(events)
        if _eligible_connector(event) and event.end_index <= bound
    }
    if failed_event not in eligible_indices:
        return None

    # Source events alone establish reachability. Component membership is a
    # qualification for whole-component consumption, never an edge that can
    # connect otherwise disconnected source-event intervals.
    event_set = {failed_event}
    changed = True
    while changed:
        changed = False
        for event_index in tuple(event_set):
            event = events[event_index]
            for candidate_index in eligible_indices:
                if candidate_index in event_set:
                    continue
                candidate = events[candidate_index]
                if _touches(
                    event.peak_index,
                    event.end_index,
                    candidate.peak_index,
                    candidate.end_index,
                ):
                    event_set.add(candidate_index)
                    changed = True

    component_set: set[int] = set()
    for component_index, (left, right) in enumerate(component_intervals):
        members = set(component_event_indices[component_index])
        touched_members = {
            event_index
            for event_index in event_set
            if event_index in members
            and _touches(
                events[event_index].peak_index,
                events[event_index].end_index,
                left,
                right,
            )
        }
        if touched_members:
            required_members = {
                event_index
                for event_index in members
                if _eligible_connector(events[event_index])
                and _touches(
                    events[event_index].peak_index,
                    events[event_index].end_index,
                    left,
                    right,
                )
            }
            if any(events[index].end_index > bound for index in required_members):
                return None
            if not required_members.issubset(event_set):
                return None
            if right > bound:
                return None
            component_set.add(component_index)

    if failed_event not in event_set or root_component not in component_set:
        return None
    return LowerComponentClosure(
        component_indices=tuple(sorted(component_set)),
        event_indices=tuple(sorted(event_set)),
    )


def lower_closure_failure_diagnostic(
    events: tuple[DropEvent, ...],
    component_intervals: tuple[tuple[int, int], ...],
    component_event_indices: tuple[tuple[int, ...], ...],
    *,
    root_component: int,
    failed_event: int,
    stress: ArrayLike | None = None,
    source_rows: ArrayLike | None = None,
) -> str:
    """Describe a failed closure using only bounded observed evidence."""

    def token(value: object) -> str:
        if isinstance(value, (bool, np.bool_)):
            return "true" if value else "false"
        return "unavailable" if value is None else str(value)

    failed = events[failed_event]
    root_left, root_right = component_intervals[root_component]
    prior_candidates = [
        index
        for index in component_event_indices[root_component]
        if index != failed_event
        and _eligible_connector(events[index])
        and events[index].end_index <= failed.peak_index
    ]
    prior_index = (
        max(prior_candidates, key=lambda index: (events[index].end_index, index))
        if prior_candidates
        else None
    )
    fields = [
        "closure_diagnostic_scope=observed_root_prior_event_boundary",
        f"root_component={root_component}",
        f"root_component_interval={root_left}~{root_right}",
        f"failed_event={failed_event}",
        f"failed_event_kind={failed.kind}",
        f"failed_event_peak={failed.peak_index}",
        f"failed_event_end={failed.end_index}",
        f"failed_event_closed={token(_eligible_connector(failed))}",
    ]
    if prior_index is None:
        fields.extend(
            (
                "prior_event=unavailable",
                "boundary_relation=unavailable",
                "observed_index_gap=unavailable",
                "observed_boundary_tie=not_evaluated",
                "observed_between_all_equal=not_evaluated",
                "source_row_evidence=unavailable",
            )
        )
        return " ".join(fields)

    prior = events[prior_index]
    index_delta = failed.peak_index - prior.end_index
    relation = (
        "overlap"
        if index_delta < 0
        else "shared_row"
        if index_delta == 0
        else "adjacent"
        if index_delta == 1
        else "gap"
    )
    fields.extend(
        (
            f"prior_event={prior_index}",
            f"prior_event_kind={prior.kind}",
            f"prior_event_interval={prior.peak_index}~{prior.end_index}",
            f"boundary_relation={relation}",
            f"observed_index_gap={max(index_delta - 1, 0)}",
        )
    )
    stress_values = None if stress is None else np.asarray(stress, dtype=np.float64)
    if (
        stress_values is None
        or stress_values.ndim != 1
        or not np.all(np.isfinite(stress_values))
        or max(prior.end_index, failed.peak_index) >= stress_values.size
    ):
        fields.append("observed_boundary_tie=not_evaluated")
    else:
        tie = stress_values[prior.end_index] == stress_values[failed.peak_index]
        observed_boundary = stress_values[prior.end_index : failed.peak_index + 1]
        fields.append(f"observed_boundary_tie={token(tie)}")
        fields.append(
            "observed_between_all_equal="
            + token(
                bool(
                    observed_boundary.size
                    and np.all(observed_boundary == observed_boundary[0])
                )
            )
        )

    source_values = None if source_rows is None else validated_source_rows(source_rows)
    if source_values is not None and (
        stress_values is None or source_values.size != stress_values.size
    ):
        source_values = None
    if (
        source_values is None
        or source_values.ndim != 1
        or max(prior.end_index, failed.peak_index) >= source_values.size
    ):
        fields.append("source_row_evidence=unavailable")
    else:
        left = int(source_values[prior.end_index])
        right = int(source_values[failed.peak_index])
        fields.extend(
            (
                "source_row_evidence=available",
                f"source_row_interval={left}~{right}",
                f"source_row_gap={max(right - left - 1, 0)}",
                f"source_row_gap_exceeds_observed={token(right - left > index_delta)}",
            )
        )
    return " ".join(fields)


def lower_suffix_minorant(source: ArrayLike, *, left: int, right: int) -> NDArray[np.float64]:
    """Return the original-source lower suffix envelope between exact anchors."""
    raw = np.asarray(source)
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ValueError("source stress must be a one-dimensional real numeric array")
    values = np.asarray(raw, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("source stress must be finite")
    if not 0 <= left < right < values.size:
        raise ValueError("lower-envelope anchors must be ordered source rows")
    support = values[left : right + 1]
    if np.any(support <= 0.0):
        raise ValueError("lower-envelope source support must stay positive")
    if values[left] > float(np.min(support[1:])):
        raise ValueError("left anchor exceeds the original-source suffix minimum")

    result = values.copy()
    suffix = np.minimum.accumulate(support[::-1])[::-1]
    result[left + 1 : right] = suffix[1:-1]
    return result
