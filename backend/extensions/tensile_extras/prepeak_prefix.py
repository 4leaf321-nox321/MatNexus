"""Retain the acquisition prefix through the first maximum engineering stress.

This is an opt-in boundary for a uniform-deformation true-plastic card path.
It deliberately runs on the acquisition-order engineering frame: the maximum
load is a useful bound candidate, but this step does not claim that the row is
the physical onset of necking or fracture.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
FORCE_COLUMN = "force"
ORDER_EVIDENCE_COLUMNS = (
    "source_row",
    "prepared_row",
    "source_csv_line",
    "source_excel_row",
)
OPTION_KEYS = frozenset({"strain", "stress"})
MIN_INPUT_POINTS = 2


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill the explicit engineering-column defaults and reject typos."""
    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"지원하지 않는 prepeak prefix 옵션입니다: {names}.")
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    return prepared


def prepeak_prefix(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Keep rows from acquisition start through the earliest global stress peak.

    The operation applies one identical prefix mask to every column.  It does
    not require monotone strain because acquisition backsteps are precisely
    what this boundary is intended to exclude after the peak.  It also does
    not smooth, sort, interpolate, or change any retained value.
    """
    options = prepare_options(options)
    strain_name = _column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = _column_name(options, "stress", DEFAULT_STRESS)
    if strain_name == stress_name:
        raise ProcessingError("prepeak prefix의 변형률 열과 응력 열은 서로 달라야 합니다.")
    _require_unit(frame, strain_name, "1", "변형률")
    _require_unit(frame, stress_name, "Pa", "응력")

    n, columns = _numeric_columns(frame)
    order_columns = _validate_order_evidence(columns)
    if n < MIN_INPUT_POINTS:
        raise ProcessingError(
            "prepeak prefix를 적용하려면 동일 길이의 유한한 입력 행이 최소 2개 필요합니다."
        )
    strain = columns[strain_name]
    stress = columns[stress_name]
    peak_index = int(np.argmax(stress))
    peak_stress = float(stress[peak_index])
    if peak_index == 0:
        raise ProcessingError(
            "prepeak prefix를 적용할 수 없습니다: 최대응력이 첫 원행에 있어 "
            "균일변형 구간 지지점이 부족합니다."
        )
    if peak_index + 1 < MIN_INPUT_POINTS:
        raise ProcessingError(
            "prepeak prefix를 적용할 수 없습니다: 최대응력 앞의 원행 지지가 부족합니다."
        )
    if peak_stress <= 0.0:
        raise ProcessingError(
            "prepeak prefix를 적용할 수 없습니다: 최대응력이 양수가 아닙니다 "
            f"({peak_stress:.9g} Pa)."
        )

    force_peak_index, force_evidence = _validate_force_evidence(
        frame, columns, stress, peak_index
    )

    kept = peak_index + 1
    removed = n - kept
    selected = frame.select(np.arange(kept, dtype=np.intp))
    order_note = (
        f"순서 증거: {', '.join(order_columns)} 열이 유한한 정수·엄격 증가인지 확인되었습니다."
        if order_columns
        else "순서 증거 없음: 매핑 원행 열이 없어 현재 열 순서를 취득 순서로 가정했습니다."
    )
    if force_evidence:
        peak_note = (
            f"원하중과 공칭응력의 peak가 원행 {peak_index}에서 일치하고 양의 일정 비례를 "
            "확인했습니다."
        )
        peak_label = "최대하중 후보"
    else:
        peak_note = (
            "원하중 peak와의 일치·비례를 검증할 수 없어 최대공칭응력 후보로만 기록했습니다."
        )
        peak_label = "최대공칭응력 후보"
    notes = (
        f"취득 순서 원행 0~{peak_index}을 유지하고 뒤의 {removed}개 행을 제외했습니다. "
        f"{peak_label}는 원행 {peak_index}, 변형률 {strain[peak_index]:.9g}, "
        f"응력 {peak_stress / 1e6:.9g} MPa 입니다.",
        order_note,
        peak_note,
        "최대하중점은 균일변형 구간 상한 후보일 뿐이며, 네킹이나 파단을 입증하는 "
        "판정이 아닙니다.",
    )
    scalars = (
        Scalar("prepeak_prefix_input_points", "입력 원행 수", float(n), "1"),
        Scalar(
            "prepeak_prefix_peak_input_index",
            "최대공칭응력 입력 원행 위치",
            float(peak_index),
            "1",
        ),
        Scalar(
            "prepeak_prefix_peak_input_strain",
            "최대공칭응력 입력 원행 변형률",
            float(strain[peak_index]),
            "1",
            "strain",
        ),
        Scalar(
            "prepeak_prefix_peak_input_stress",
            "최대공칭응력 입력 원행 응력",
            peak_stress,
            "Pa",
        ),
        Scalar("prepeak_prefix_removed_points", "제외한 말단 원행 수", float(removed), "1"),
        Scalar(
            "prepeak_prefix_order_evidence_code",
            "취득 순서 증거 상태 (0=없음, 1=검증)",
            float(bool(order_columns)),
            "1",
        ),
        Scalar(
            "prepeak_prefix_force_peak_index",
            "원하중 최댓값 원행 위치 (-1=비교 불가)",
            float(force_peak_index),
            "1",
        ),
        Scalar(
            "prepeak_prefix_force_peak_match_code",
            "원하중 peak 검증 상태 (0=비교 불가, 1=검증)",
            float(force_evidence),
            "1",
        ),
    )
    return StepResult(selected, notes=notes, scalars=scalars, effective_options=options)


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"prepeak prefix의 '{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다."
        )
    return value


def _require_unit(frame: Frame, name: str, expected: str, what: str) -> None:
    frame.require(name, what=what)
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"prepeak prefix의 {what} 열 '{name}' 단위는 '{expected}' 이어야 합니다. "
            f"현재: {shown}."
        )


def _numeric_columns(frame: Frame) -> tuple[int, dict[str, np.ndarray]]:
    if not frame.columns:
        raise ProcessingError("prepeak prefix를 적용할 입력 열이 없습니다.")
    columns: dict[str, np.ndarray] = {}
    expected: int | None = None
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"입력 열 '{name}' 을 숫자 배열로 읽을 수 없습니다."
            ) from None
        if (
            values.ndim != 1
            or np.iscomplexobj(values)
            or not np.issubdtype(values.dtype, np.number)
        ):
            raise ProcessingError(f"입력 열 '{name}' 은 1차원 실수형 숫자여야 합니다.")
        if expected is None:
            expected = len(values)
        elif len(values) != expected:
            raise ProcessingError(
                f"입력 열 '{name}' 의 점 수가 맞지 않습니다: {len(values)}점, "
                f"기준 {expected}점."
            )
        try:
            numeric = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"입력 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
            ) from None
        if not np.all(np.isfinite(numeric)):
            raise ProcessingError(f"입력 열 '{name}' 에 유한하지 않은 값이 있습니다.")
        columns[name] = numeric
    assert expected is not None
    return expected, columns


def _validate_order_evidence(columns: dict[str, np.ndarray]) -> tuple[str, ...]:
    present = tuple(name for name in ORDER_EVIDENCE_COLUMNS if name in columns)
    for name in present:
        values = columns[name]
        if np.any(values != np.floor(values)):
            raise ProcessingError(
                f"순서 증거 열 '{name}' 에 정수가 아닌 원행 값이 있어 처리하지 않습니다."
            )
        if values.size >= 2 and np.any(np.diff(values) <= 0.0):
            raise ProcessingError(
                f"순서 증거 열 '{name}' 이 엄격히 증가하지 않아 처리하지 않습니다. "
                "취득 순서가 정렬·중복 제거로 바뀌었는지 확인하세요."
            )
    return present


def _validate_force_evidence(
    frame: Frame,
    columns: dict[str, np.ndarray],
    stress: np.ndarray,
    stress_peak_index: int,
) -> tuple[int, bool]:
    force = columns.get(FORCE_COLUMN)
    if force is None:
        return -1, False
    if frame.units.get(FORCE_COLUMN) != "N":
        return -1, False

    force_peak_index = int(np.argmax(force))
    if force_peak_index != stress_peak_index:
        raise ProcessingError(
            "원하중과 공칭응력의 최대 위치가 일치하지 않아 최대하중 후보로 "
            "처리하지 않습니다. 응력·하중 채널과 단위를 확인하세요."
        )
    force_peak = float(force[force_peak_index])
    if force_peak <= 0.0:
        raise ProcessingError(
            f"원하중의 최대값이 양수가 아니어서 최대하중 후보로 처리하지 않습니다: "
            f"{force_peak:.9g} N."
        )

    nonzero = force != 0.0
    if np.any((~nonzero) & (stress != 0.0)):
        raise ProcessingError(
            "원하중이 0인 행에 0이 아닌 공칭응력이 있어 하중·응력 비례를 검증하지 못했습니다."
        )
    ratios = stress[nonzero] / force[nonzero]
    if ratios.size == 0 or not np.all(np.isfinite(ratios)):
        raise ProcessingError("원하중·공칭응력의 비례 검증값이 유한하지 않습니다.")
    reference = float(np.median(ratios))
    if reference <= 0.0 or not np.allclose(ratios, reference, rtol=1e-9, atol=0.0):
        raise ProcessingError(
            "원하중과 공칭응력이 양의 일정 비례가 아니어서 최대하중 후보로 "
            "처리하지 않습니다. 변환·단위를 확인하세요."
        )
    return force_peak_index, True
