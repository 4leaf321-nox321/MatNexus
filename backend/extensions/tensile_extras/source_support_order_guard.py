"""Guard the source-row support used by the uniform true-plastic candidate.

The source proof is measured on adjacent acquisition rows, while the next
step sorts engineering strain.  This read-only guard makes that boundary
explicit: the rows after the proof crossing and through the prefix peak must
be the same rows selected by the proof-to-peak coordinate window, in the same
order.  Rows before the proof are retained as diagnostics because an early
elastic/search backstep is not by itself a reason to reject the candidate.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

DEFAULT_STRAIN = "strain_engineering"
ORDER_EVIDENCE_COLUMNS = (
    "source_row",
    "prepared_row",
    "source_csv_line",
    "source_excel_row",
)
OPTION_KEYS = frozenset(
    {
        "proof_left_index",
        "proof_right_index",
        "proof_strain",
        "peak_index",
        "peak_strain",
        "order_evidence_code",
        "force_peak_match_code",
        "strain",
    }
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(
            f"원행 support 순서 guard에 알 수 없는 옵션이 있습니다: {names}."
        )
    prepared.setdefault("proof_left_index", "@source_proof_left_index")
    prepared.setdefault("proof_right_index", "@source_proof_right_index")
    prepared.setdefault("proof_strain", "@proof_strain")
    prepared.setdefault("peak_index", "@prepeak_prefix_peak_input_index")
    prepared.setdefault("peak_strain", "@prepeak_prefix_peak_input_strain")
    prepared.setdefault("order_evidence_code", "@prepeak_prefix_order_evidence_code")
    prepared.setdefault("force_peak_match_code", "@prepeak_prefix_force_peak_match_code")
    prepared.setdefault("strain", DEFAULT_STRAIN)
    return prepared


def source_support_order_guard(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Verify the proof-to-peak source support without changing the frame."""

    options = prepare_options(options)
    strain_name = _column_name(options, "strain", DEFAULT_STRAIN)
    _require_unit(frame, strain_name, "1", "변형률")
    strain = _numeric_column(frame, strain_name, "변형률")
    if strain.size < 2:
        raise ProcessingError("원행 support 순서 guard에는 최소 2개 행이 필요합니다.")

    order_code = _code(options.get("order_evidence_code"), "order_evidence_code")
    force_code = _code(options.get("force_peak_match_code"), "force_peak_match_code")
    if order_code != 1:
        raise ProcessingError(
            "원행 support 순서 guard는 취득 순서 증거가 검증된 경우만 사용합니다 "
            "(order_evidence_code=1 필요)."
        )
    if force_code != 1:
        raise ProcessingError(
            "원행 support 순서 guard는 원하중 peak 검증이 끝난 경우만 사용합니다 "
            "(force_peak_match_code=1 필요)."
        )

    evidence_columns = _evidence_columns(frame, strain.size)
    if not evidence_columns:
        raise ProcessingError(
            "취득 순서 증거 열(source_row/prepared_row/source_csv_line/source_excel_row)이 "
            "없어 원행 support 순서를 확인할 수 없습니다."
        )

    left = _row_index(options.get("proof_left_index"), "proof_left_index")
    right = _row_index(options.get("proof_right_index"), "proof_right_index")
    peak = _row_index(options.get("peak_index"), "peak_index")
    proof_strain = _finite(options.get("proof_strain"), "proof_strain")
    peak_strain = _finite(options.get("peak_strain"), "peak_strain")
    if right != left + 1:
        raise ProcessingError(
            f"원행 내력 교점 [{left}, {right}]가 인접 원행 쌍이 아닙니다. "
            "원자료의 교점 경계를 확인하세요."
        )
    if left < 0 or right >= strain.size:
        raise ProcessingError(
            f"원행 내력 교점 [{left}, {right}]가 현재 입력 행 범위를 벗어났습니다 "
            f"(마지막 행 {strain.size - 1})."
        )
    if peak != strain.size - 1:
        raise ProcessingError(
            f"최대공칭응력 peak 원행 {peak}가 prefix 마지막 행 {strain.size - 1}과 "
            "다릅니다. 말단을 임의로 포함하지 않았는지 확인하세요."
        )
    if peak_strain != float(strain[peak]):
        raise ProcessingError(
            "prefix peak 변형률 scalar와 현재 원행 peak가 정확히 일치하지 않습니다. "
            f"scalar={peak_strain:.12g}, 원행={float(strain[peak]):.12g}."
        )
    if peak_strain <= proof_strain:
        raise ProcessingError(
            f"prefix peak 변형률 {peak_strain:.12g}가 proof 변형률 "
            f"{proof_strain:.12g}보다 크지 않습니다."
        )

    left_strain = float(strain[left])
    right_strain = float(strain[right])
    if not left_strain < right_strain:
        raise ProcessingError(
            "원행 내력 교점 쌍의 공학 변형률이 엄격히 증가하지 않습니다: "
            f"원행 {left}->{right}, 변형률 {left_strain:.12g}->{right_strain:.12g}."
        )
    if proof_strain == left_strain:
        proof_mode = 1  # exact left boundary
        first_support = right
    elif proof_strain == right_strain:
        proof_mode = 2  # exact right boundary
        first_support = right + 1
    elif left_strain < proof_strain < right_strain:
        proof_mode = 0  # interpolated crossing pair
        first_support = right
    else:
        raise ProcessingError(
            "원행 내력 proof 변형률이 교점 인접쌍의 닫힌 좌표 범위에 없습니다: "
            f"proof={proof_strain:.12g}, 쌍=[{left_strain:.12g}, {right_strain:.12g}]."
        )
    if first_support > peak:
        raise ProcessingError(
            "proof 교점 뒤에 prefix peak까지의 지원 원행이 없습니다. "
            f"proof pair=[{left}, {right}], peak={peak}."
        )

    time_positions = np.arange(first_support, peak + 1, dtype=np.intp)
    coordinate_positions = np.flatnonzero(
        (strain > proof_strain) & (strain <= peak_strain)
    ).astype(np.intp, copy=False)
    if not np.array_equal(time_positions, coordinate_positions):
        missing = _first_difference(time_positions, coordinate_positions)
        expected = _position_text(frame, strain, missing[0], evidence_columns)
        actual = _position_text(frame, strain, missing[1], evidence_columns)
        raise ProcessingError(
            "proof부터 prefix peak까지 시간상 지원 원행과 좌표창 "
            "(proof < 변형률 <= peak)의 원행 집합이 일치하지 않습니다. "
            f"첫 차이: 시간상={expected}; 좌표상={actual}. "
            "정렬 전에 원자료 행과 proof 경계를 확인하세요."
        )

    support_strain = strain[time_positions]
    bad_support = np.flatnonzero(support_strain[1:] <= support_strain[:-1])
    if bad_support.size:
        offset = int(bad_support[0])
        first = int(time_positions[offset])
        second = int(time_positions[offset + 1])
        raise ProcessingError(
            "proof부터 prefix peak까지의 지원 원행 변형률이 엄격히 증가하지 않습니다. "
            f"첫 문제 {first}->{second}: "
            f"{_position_text(frame, strain, first, evidence_columns)} -> "
            f"{_position_text(frame, strain, second, evidence_columns)}. "
            "이 구간은 curve.sort_unique가 재배열·중복 병합하기 전에 보류합니다."
        )

    _check_sorted_proof_pair(
        frame=frame,
        strain=strain,
        evidence_columns=evidence_columns,
        left=left,
        right=right,
        proof_strain=proof_strain,
        proof_mode=proof_mode,
    )

    prefix_backsteps = int(np.count_nonzero(np.diff(strain[:first_support]) <= 0.0))
    effective_options = {
        "proof_left_index": left,
        "proof_right_index": right,
        "proof_strain": proof_strain,
        "peak_index": peak,
        "peak_strain": peak_strain,
        "order_evidence_code": order_code,
        "force_peak_match_code": force_code,
        "strain": strain_name,
    }
    scalars = (
        Scalar("source_support_order_code", "proof-peak 원행 순서 검증 상태", 1.0, "1"),
        Scalar(
            "source_support_proof_mode_code",
            "proof 경계 형태 (0=보간, 1=왼쪽 정확, 2=오른쪽 정확)",
            float(proof_mode),
            "1",
        ),
        Scalar(
            "source_support_points",
            "proof-peak 원행 지원점 수",
            float(len(time_positions)),
            "1",
        ),
        Scalar(
            "source_support_backstep_count",
            "proof 앞 변형률 후퇴 진단 수",
            float(prefix_backsteps),
            "1",
        ),
        Scalar("source_support_mismatch_count", "proof-peak 좌표 지원 불일치 수", 0.0, "1"),
        Scalar(
            "source_support_first_index",
            "proof-peak 첫 지원 현재행",
            float(first_support),
            "1",
        ),
        Scalar("source_support_peak_index", "지원 검증 prefix peak 현재행", float(peak), "1"),
    )
    if not all(math.isfinite(item.value) for item in scalars):
        raise ProcessingError("원행 support 순서 guard 진단값이 유한하지 않습니다.")
    mode_label = {0: "보간 교점", 1: "왼쪽 정확 경계", 2: "오른쪽 정확 경계"}[proof_mode]
    notes = (
        f"proof {mode_label}부터 prefix peak까지 {len(time_positions)}개 원행의 "
        "시간 순서와 좌표창 지원 집합을 확인했습니다.",
        f"proof 앞 변형률 후퇴 진단 {prefix_backsteps}개는 이 guard의 보류 조건으로 "
        "사용하지 않았습니다. stable 정렬·중복 평균이 proof 경계쌍도 "
        "바꾸지 않는지 확인했습니다.",
    )
    return StepResult(frame, notes=notes, scalars=scalars, effective_options=effective_options)


def _check_sorted_proof_pair(
    *,
    frame: Frame,
    strain: np.ndarray,
    evidence_columns: tuple[str, ...],
    left: int,
    right: int,
    proof_strain: float,
    proof_mode: int,
) -> None:
    """Simulate only x sorting/grouping used by the following mean step.

    The full ``Frame`` is deliberately untouched.  Stable coordinate ordering
    and exact-equality groups are enough to determine which observed rows would
    bracket ``proof_strain`` after ``curve.sort_unique(..., mean)``.
    """

    order = np.argsort(strain, kind="stable")
    sorted_strain = strain[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_strain) != 0.0) + 1]
    ends = np.r_[starts[1:], sorted_strain.size]
    unique_strain = sorted_strain[starts]

    if proof_mode in (1, 2):
        exact_group_index = np.flatnonzero(unique_strain == proof_strain)
        expected = left if proof_mode == 1 else right
        if exact_group_index.size != 1:
            raise ProcessingError(
                "stable 정렬 후 proof 정확 경계를 찾지 못했습니다. "
                f"proof={proof_strain:.12g}, source proof 원행={expected}."
            )
        group_index = int(exact_group_index[0])
        group = order[starts[group_index] : ends[group_index]]
        if group.size != 1 or int(group[0]) != expected:
            offender = _first_group_offender(group, expected)
            raise ProcessingError(
                "첫 curve.sort_unique의 duplicate_policy=mean이 정확 proof 원행을 "
                "동률 병합하거나 다른 원행을 끼워 넣습니다. "
                f"예상={_position_text(frame, strain, expected, evidence_columns)}; "
                f"첫 문제={_position_text(frame, strain, offender, evidence_columns)}. "
                "원행 proof 경계를 자동 카드 후보에 사용하지 않습니다."
            )
        return

    right_group_index = int(np.searchsorted(unique_strain, proof_strain, side="right"))
    if right_group_index <= 0 or right_group_index >= len(unique_strain):
        raise ProcessingError(
            "stable 정렬 후 proof 변형률을 끼우는 양쪽 관측 원행을 찾지 못했습니다. "
            f"proof={proof_strain:.12g}."
        )
    left_group = order[starts[right_group_index - 1] : ends[right_group_index - 1]]
    right_group = order[starts[right_group_index] : ends[right_group_index]]
    left_ok = left_group.size == 1 and int(left_group[0]) == left
    right_ok = right_group.size == 1 and int(right_group[0]) == right
    if left_ok and right_ok:
        return

    if not left_ok:
        expected = left
        group = left_group
        side = "왼쪽"
    else:
        expected = right
        group = right_group
        side = "오른쪽"
    offender = _first_group_offender(group, expected)
    actual_coordinate = float(strain[int(group[0])]) if group.size else float("nan")
    raise ProcessingError(
        "첫 curve.sort_unique 후 proof 보간쌍이 source_proof 원행쌍과 달라집니다. "
        f"{side} 가장 가까운 좌표={actual_coordinate:.12g}, "
        f"예상 원행={_position_text(frame, strain, expected, evidence_columns)}, "
        f"첫 문제 원행={_position_text(frame, strain, offender, evidence_columns)}. "
        "다른 원행 유입·동률 병합을 자동으로 평균내지 않고 보류합니다."
    )


def _first_group_offender(group: np.ndarray, expected: int) -> int:
    for position in group:
        if int(position) != expected:
            return int(position)
    return int(group[0]) if group.size else -1


def _evidence_columns(frame: Frame, size: int) -> tuple[str, ...]:
    present: list[str] = []
    for name in ORDER_EVIDENCE_COLUMNS:
        if name not in frame.columns:
            continue
        _require_unit(frame, name, "1", "원행 증거")
        values = _numeric_column(frame, name, "원행 증거")
        if values.size != size:
            raise ProcessingError(f"원행 증거 열 '{name}'의 길이가 변형률과 다릅니다.")
        if np.any(values != np.floor(values)):
            raise ProcessingError(f"원행 증거 열 '{name}'에 정수가 아닌 값이 있습니다.")
        if values.size >= 2 and np.any(np.diff(values) <= 0.0):
            raise ProcessingError(
                f"원행 증거 열 '{name}'이 엄격히 증가하지 않습니다. 취득 순서를 확인하세요."
            )
        present.append(name)
    return tuple(present)


def _first_difference(expected: np.ndarray, actual: np.ndarray) -> tuple[int, int]:
    limit = min(len(expected), len(actual))
    for index in range(limit):
        if int(expected[index]) != int(actual[index]):
            return int(expected[index]), int(actual[index])
    if len(expected) > limit:
        return int(expected[limit]), -1
    if len(actual) > limit:
        return -1, int(actual[limit])
    return -1, -1


def _position_text(
    frame: Frame, strain: np.ndarray, position: int, evidence_columns: tuple[str, ...]
) -> str:
    if position < 0 or position >= len(strain):
        return f"현재행 {position} (지원 없음)"
    evidence = ", ".join(
        f"{name}={float(np.asarray(frame.columns[name])[position]):.9g}"
        for name in evidence_columns
    )
    return f"현재행 {position}, 변형률={float(strain[position]):.9g}, {evidence}"


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"원행 support 순서 guard의 '{key}' 열 이름은 비어 있지 않아야 합니다."
        )
    return value


def _require_unit(frame: Frame, name: str, expected: str, what: str) -> None:
    frame.require(name, what=what)
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"원행 support 순서 guard의 {what} 열 '{name}' 단위는 '{expected}'이어야 합니다. "
            f"현재: {shown}."
        )


def _numeric_column(frame: Frame, name: str, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(name, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}' {what} 열을 숫자 배열로 읽을 수 없습니다.") from None
    if raw.ndim != 1 or np.iscomplexobj(raw) or not np.issubdtype(raw.dtype, np.number):
        raise ProcessingError(f"'{name}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        numeric = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"'{name}' {what} 열을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if not np.all(np.isfinite(numeric)):
        raise ProcessingError(f"'{name}' {what} 열에 유한하지 않은 값이 있습니다.")
    return numeric


def _finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.") from None
    if not math.isfinite(number):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    return number


def _code(value: Any, name: str) -> int:
    number = _finite(value, name)
    if number not in (0.0, 1.0):
        raise ProcessingError(f"'{name}'은 0 또는 1이어야 합니다.")
    return int(number)


def _row_index(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ProcessingError(f"'{name}'은 유한한 정수 행 위치여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 유한한 정수 행 위치여야 합니다.") from None
    if not math.isfinite(number) or not number.is_integer() or number < 0.0:
        raise ProcessingError(f"'{name}'은 0 이상의 유한한 정수 행 위치여야 합니다.")
    return int(number)
