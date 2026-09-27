"""Atomic, bounded correction of isolated acquisition strain notches."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

from . import (
    source_peak_evidence,
    source_proof,
    source_support_order_full,
    source_support_order_guard,
)

DEFAULT_FORCE = source_peak_evidence.DEFAULT_FORCE
DEFAULT_STRAIN = source_peak_evidence.DEFAULT_STRAIN
DEFAULT_STRESS = source_peak_evidence.DEFAULT_STRESS
OPTION_KEYS = frozenset(
    {
        "proof_left_index",
        "proof_right_index",
        "proof_strain",
        "proof_stress",
        "youngs_modulus",
        "source_elastic_end_index",
        "elastic_window_end",
        "offset_strain",
        "force",
        "strain",
        "stress",
        "time",
        "displacement",
    }
)
SOURCE_ROW_PAIR = ("source_data_row", "source_physical_line")
ORIGINAL_PAIR = ("source_data_row_original", "source_physical_line_original")
REMOVED_POINTS_KEY = "acquisition_frontier_removed_points"
MAX_NOTCH_DEPTH_KEY = "acquisition_frontier_max_notch_depth"
FIRST_CURRENT_ROW_KEY = "acquisition_frontier_first_current_row"
LAST_CURRENT_ROW_KEY = "acquisition_frontier_last_current_row"
FIRST_SOURCE_ROW_KEY = "acquisition_frontier_first_source_row"
LAST_SOURCE_ROW_KEY = "acquisition_frontier_last_source_row"


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        raise ProcessingError(
            "원행 acquisition frontier에 알 수 없는 옵션이 있습니다: "
            + ", ".join(repr(name) for name in unknown)
            + ". peak·status scalar는 옵션으로 받지 않습니다."
        )
    defaults = {
        "proof_left_index": "@source_proof_left_index",
        "proof_right_index": "@source_proof_right_index",
        "proof_strain": "@proof_strain",
        "proof_stress": "@proof_stress",
        "youngs_modulus": "@youngs_modulus",
        "source_elastic_end_index": "@source_elastic_end_index",
        "elastic_window_end": "@elastic_window_end",
        "offset_strain": source_proof.DEFAULT_OFFSET,
        "force": DEFAULT_FORCE,
        "strain": DEFAULT_STRAIN,
        "stress": DEFAULT_STRESS,
        "time": "time",
        "displacement": "displacement",
    }
    for key, value in defaults.items():
        prepared.setdefault(key, value)
    return prepared


def acquisition_frontier(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Select all columns once, after every raw and proposed-frame check passes."""
    options = prepare_options(options)
    if any(name in frame.columns or name in frame.units for name in ORIGINAL_PAIR):
        raise ProcessingError(
            "원행 original pair 예약 열이 이미 있어 frontier를 재적용할 수 없습니다."
        )
    force_name = source_peak_evidence._column_name(options, "force", DEFAULT_FORCE)
    strain_name = source_peak_evidence._column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = source_peak_evidence._column_name(options, "stress", DEFAULT_STRESS)
    time_name = source_peak_evidence._column_name(options, "time", "time")
    displacement_name = source_peak_evidence._column_name(
        options, "displacement", "displacement"
    )
    if len({force_name, strain_name, stress_name, time_name, displacement_name}) != 5:
        raise ProcessingError("frontier 하중·변형률·응력·시간·변위 열은 서로 달라야 합니다.")

    peak_result = source_peak_evidence.source_peak_evidence(
        frame, {"force": force_name, "strain": strain_name, "stress": stress_name}
    )
    peak_values = {item.key: item.value for item in peak_result.scalars}
    peak = _row_index(peak_values["source_peak_index"], "source_peak_index")
    left = _row_index(options["proof_left_index"], "proof_left_index")
    right = _row_index(options["proof_right_index"], "proof_right_index")
    if right != left + 1 or right >= peak:
        raise ProcessingError("proof pair가 인접하지 않거나 raw peak 이전에 있지 않습니다.")
    strain = source_peak_evidence._numeric_column(frame, strain_name, "변형률")
    stress = source_peak_evidence._numeric_column(frame, stress_name, "응력")
    force = source_peak_evidence._numeric_column(frame, force_name, "하중")
    proof_options = {
        "youngs_modulus": options["youngs_modulus"],
        "start_index": options["source_elastic_end_index"],
        "end_index": peak,
        "search_start": options["elastic_window_end"],
        "offset_strain": options["offset_strain"],
        "strain": strain_name,
        "stress": stress_name,
    }
    proof_result = source_proof.source_proof_stress(frame, proof_options)
    proof_values = {item.key: item.value for item in proof_result.scalars}
    if left != _row_index(proof_values["source_proof_left_index"], "source_proof_left_index"):
        raise ProcessingError(
            "원행 proof 재계산 결과 proof_left_index가 전달된 값과 다릅니다."
        )
    if right != _row_index(
        proof_values["source_proof_right_index"], "source_proof_right_index"
    ):
        raise ProcessingError(
            "원행 proof 재계산 결과 proof_right_index가 전달된 값과 다릅니다."
        )
    for key, actual in (
        ("proof_strain", proof_values["proof_strain"]),
        ("proof_stress", proof_values["proof_stress"]),
    ):
        expected = source_proof._finite_number(options[key], key)
        if not math.isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-15):
            raise ProcessingError(f"원행 proof 재계산 결과 {key}가 전달된 값과 다릅니다.")

    present = source_support_order_guard._evidence_columns(frame, strain.size)
    evidence = _source_evidence(frame, present)
    if evidence is None:
        raise ProcessingError("frontier에는 source_row 또는 원행 pair 취득 증거가 필요합니다.")
    evidence_name, evidence_values = evidence
    pair_present = all(name in present for name in SOURCE_ROW_PAIR)
    if (
        pair_present
        and "source_row" in present
        and not np.array_equal(
            np.asarray(frame.columns["source_row"]),
            np.asarray(frame.columns["source_data_row"]),
        )
    ):
        raise ProcessingError("source_row와 source_data_row 원행 식별자가 일치하지 않습니다.")
    if "source_row" in present and np.any(
        np.diff(np.asarray(frame.columns["source_row"])[right : peak + 1]) != 1
    ):
        raise ProcessingError("proof-peak 원행 source_row에 기존 행 누락 간격이 있습니다.")

    resolved_proof = proof_result.effective_options
    assert resolved_proof is not None
    effective_options = {
        "proof_left_index": left,
        "proof_right_index": right,
        "proof_strain": proof_values["proof_strain"],
        "proof_stress": proof_values["proof_stress"],
        "youngs_modulus": resolved_proof["youngs_modulus"],
        "source_elastic_end_index": resolved_proof["start_index"],
        "elastic_window_end": resolved_proof["search_start"],
        "offset_strain": resolved_proof["offset_strain"],
        "force": force_name,
        "strain": strain_name,
        "stress": stress_name,
        "time": time_name,
        "displacement": displacement_name,
    }
    bad = np.flatnonzero(np.diff(strain[right : peak + 1]) <= 0.0) + right
    if bad.size == 0:
        return _no_op(frame, effective_options)

    if time_name not in frame.columns or frame.units.get(time_name) not in ("s", "1"):
        raise ProcessingError("frontier 시간 열에는 숫자 값과 단위 s 또는 1이 필요합니다.")
    if displacement_name not in frame.columns or frame.units.get(displacement_name) != "m":
        raise ProcessingError("frontier 변위 열에는 숫자 값과 단위 m가 필요합니다.")
    time = source_peak_evidence._numeric_column(frame, time_name, "시간")
    displacement = source_peak_evidence._numeric_column(frame, displacement_name, "변위")
    if np.any(np.diff(time[right : peak + 1]) <= 0.0):
        raise ProcessingError("proof-peak 전체 취득 시간·순번이 엄격히 증가하지 않습니다.")
    dependent_displacement = _derived_from_strain(strain, displacement)
    removed: list[int] = []
    depths: list[float] = []
    for boundary in bad:
        start = int(boundary)
        middle = start + 1
        end = middle + 1
        if (
            middle <= right
            or end > peak
            or (removed and start <= removed[-1] + 1)
            or not strain[middle] < strain[start] < strain[end]
            or not stress[start] < stress[middle] < stress[end]
            or not force[start] < force[middle] < force[end]
            or not _consecutive(evidence_values, start, middle, end)
        ):
            raise ProcessingError(
                f"원행 {start}->{middle} 역전은 고립된 3행 notch가 아닙니다."
            )
        step = _local_positive_median(np.diff(strain), start, right, peak)
        depth = float(strain[start] - strain[middle])
        if depth > step:
            raise ProcessingError(
                f"원행 {middle} notch 깊이가 국소 양의 변형률 간격보다 큽니다."
            )
        local_time = _local_positive_median(np.diff(time), start, right, peak)
        increments = np.diff(time[start : end + 1])
        if np.any(increments < 0.5 * local_time) or np.any(increments > 2.0 * local_time):
            raise ProcessingError(f"원행 {middle} 시간 취득 간격이 국소 cadence를 벗어납니다.")
        if not dependent_displacement:
            local_displacement = _local_positive_median(
                np.diff(displacement), start, right, peak
            )
            displacement_steps = np.diff(displacement[start : end + 1])
            if np.any(displacement_steps < 0.5 * local_displacement) or np.any(
                displacement_steps > 2.0 * local_displacement
            ):
                raise ProcessingError(
                    f"원행 {middle} 독립 변위 간격이 양의 국소 cadence를 벗어납니다."
                )
        removed.append(middle)
        depths.append(depth)

    if len(removed) > 10 or len(removed) / (peak - right) > 0.01:
        raise ProcessingError("frontier 삭제 상한 10행 또는 proof-peak 간격의 1%를 넘습니다.")
    keep = np.ones(strain.size, dtype=bool)
    keep[np.asarray(removed, dtype=np.intp)] = False
    retained = np.flatnonzero(keep).astype(np.intp, copy=False)
    if np.any(np.diff(strain[retained[(retained >= right) & (retained <= peak)]]) <= 0.0):
        raise ProcessingError(
            "frontier 선택 후 proof-peak 전체 지원이 엄격히 증가하지 않습니다."
        )
    if not keep[left] or not keep[right] or not keep[peak]:
        raise ProcessingError("frontier가 proof pair 또는 raw peak를 제거할 수 없습니다.")

    selected = frame.select(retained)
    if pair_present:
        columns = dict(selected.columns)
        units = dict(selected.units)
        for old, new in zip(SOURCE_ROW_PAIR, ORIGINAL_PAIR, strict=True):
            columns[new] = columns.pop(old)
            units[new] = units.pop(old)
        if "source_row" not in columns:
            columns["source_row"] = columns[ORIGINAL_PAIR[0]].copy()
            units["source_row"] = "1"
        selected = Frame(columns, units)
    source_support_order_full.source_support_order_full(
        selected,
        {
            "proof_left_index": left,
            "proof_right_index": right,
            "proof_strain": proof_values["proof_strain"],
            "force": force_name,
            "strain": strain_name,
            "stress": stress_name,
        },
    )
    notes = (
        f"frontier가 원행 {len(removed)}개를 제거했습니다. "
        + _removed_source_note(evidence_name, evidence_values, removed),
        f"시간 단위 {frame.units[time_name]!r}의 국소 취득 cadence를 검사했습니다"
        + (
            " (단위 1은 초가 아닌 순번 cadence입니다); "
            if frame.units[time_name] == "1"
            else "; "
        )
        + (
            "변위는 변형률에서 거의 정확히 유도되어 독립 증거가 아닙니다."
            if dependent_displacement
            else "독립 변위의 국소 양의 간격을 확인했습니다."
        ),
        "모든 열을 같은 순서로 선택하고 proof pair·raw peak·전체 지원을 재검증했습니다.",
        *(
            (
                "원행 pair 열 source_data_row→source_data_row_original, "
                "source_physical_line→source_physical_line_original로 옮기고 "
                "source_row에 원래 data row 값을 보존했습니다.",
            )
            if pair_present
            else ()
        ),
    )
    return StepResult(
        selected,
        notes=notes,
        scalars=_diagnostics(removed, depths, evidence_values),
        effective_options=effective_options,
    )


def _source_evidence(
    frame: Frame, present: tuple[str, ...]
) -> tuple[str, tuple[np.ndarray, ...]] | None:
    if all(name in present for name in SOURCE_ROW_PAIR):
        return "source_data_row/source_physical_line", tuple(
            np.asarray(frame.columns[name], dtype=np.float64) for name in SOURCE_ROW_PAIR
        )
    for name in ("source_row", "source_csv_line", "source_excel_row"):
        if name in present:
            return name, (np.asarray(frame.columns[name], dtype=np.float64),)
    return None


def _consecutive(values: tuple[np.ndarray, ...], left: int, middle: int, right: int) -> bool:
    return all(v[middle] - v[left] == 1 and v[right] - v[middle] == 1 for v in values)


def _local_positive_median(steps: np.ndarray, boundary: int, lower: int, upper: int) -> float:
    local = steps[max(lower, boundary - 20) : min(upper, boundary + 21)]
    positive = local[local > 0.0]
    if positive.size == 0:
        raise ProcessingError("frontier 국소 양의 취득 간격이 없습니다.")
    median = float(np.median(positive))
    if not math.isfinite(median) or median <= 0.0:
        raise ProcessingError("frontier 국소 취득 간격이 유한한 양수가 아닙니다.")
    return median


def _derived_from_strain(strain: np.ndarray, displacement: np.ndarray) -> bool:
    span = float(np.ptp(strain))
    if span <= 0.0:
        return False
    slope = float(
        np.dot(strain - np.mean(strain), displacement - np.mean(displacement))
        / np.dot(strain - np.mean(strain), strain - np.mean(strain))
    )
    intercept = float(np.mean(displacement) - slope * np.mean(strain))
    if not math.isfinite(slope) or not math.isfinite(intercept):
        return False
    tolerance = max(1e-12, abs(slope) * span * 1e-8)
    return bool(np.all(np.abs(displacement - (slope * strain + intercept)) <= tolerance))


def _removed_source_note(name: str, values: tuple[np.ndarray, ...], removed: list[int]) -> str:
    identities = []
    for index in removed:
        if len(values) == 2:
            identity = (
                f"source_data_row={values[0][index]:.0f}, "
                f"source_physical_line={values[1][index]:.0f}"
            )
        else:
            identity = f"{name}={values[0][index]:.0f}"
        identities.append(f"현재행 {index} ({identity})")
    return "제거한 source row: " + "; ".join(identities) + "."


def _diagnostics(
    removed: list[int], depths: list[float], values: tuple[np.ndarray, ...]
) -> tuple[Scalar, ...]:
    first = removed[0] if removed else -1
    last = removed[-1] if removed else -1
    return (
        Scalar(REMOVED_POINTS_KEY, "제거한 고립 역전 원행 수", float(len(removed)), "1"),
        Scalar(
            MAX_NOTCH_DEPTH_KEY,
            "제거한 최대 역전 깊이",
            max(depths, default=0.0),
            "1",
            "strain",
        ),
        Scalar(FIRST_CURRENT_ROW_KEY, "첫 제거 현재행", float(first), "1"),
        Scalar(LAST_CURRENT_ROW_KEY, "마지막 제거 현재행", float(last), "1"),
        Scalar(
            FIRST_SOURCE_ROW_KEY,
            "첫 제거 원행",
            float(values[0][first]) if removed else -1.0,
            "1",
        ),
        Scalar(
            LAST_SOURCE_ROW_KEY,
            "마지막 제거 원행",
            float(values[0][last]) if removed else -1.0,
            "1",
        ),
    )


def _no_op(frame: Frame, options: dict[str, Any]) -> StepResult:
    return StepResult(
        frame,
        notes=("frontier 제거 대상이 없어 입력 원행을 그대로 보존했습니다.",),
        scalars=_diagnostics([], [], (np.empty(0),)),
        effective_options=options,
    )


def _row_index(value: Any, name: str) -> int:
    return source_proof._row_index(value, name)
