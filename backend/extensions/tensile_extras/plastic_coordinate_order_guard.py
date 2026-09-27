"""Guard source order and positive true-plastic coordinates before sorting."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

DEFAULT_X = "strain_true_plastic"
DEFAULT_SOURCE_INDEX = "source_row"
SOURCE_EVIDENCE_COLUMNS = (
    "source_row",
    "prepared_row",
    "source_csv_line",
    "source_excel_row",
    "source_data_row",
    "source_physical_line",
)
SOURCE_ROW_PAIR = ("source_data_row", "source_physical_line")
MAX_EXACT_INTEGER = float(1 << 53)
OPTION_KEYS = frozenset({"x", "source_index"})


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"진소성 좌표 순서 guard에 알 수 없는 옵션이 있습니다: {names}.")
    source_option = prepared.get("source_index")
    if source_option is not None and (
        not isinstance(source_option, str)
        or (source_option != "auto" and source_option not in SOURCE_EVIDENCE_COLUMNS)
    ):
        names = ", ".join(repr(name) for name in SOURCE_EVIDENCE_COLUMNS)
        raise ProcessingError(
            f"지원하지 않는 source_index '{source_option}'입니다. 허용 값: 'auto', {names}."
        )
    return prepared


def plastic_coordinate_order_guard(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Check source-order evidence and positive-epsilon order without changing values.

    The first row is the logical proof anchor.  Its source-row value can be an
    interpolated value produced by ``plastic_domain`` and is therefore excluded
    from the measured source-order check.  Only the contiguous zero-valued
    prefix after that anchor is allowed; a zero that reappears after a positive
    plastic strain would be moved by sorting and is held here.
    """

    options = prepare_options(options)
    if "x" not in options:
        raise ProcessingError(
            "진소성 좌표 순서 guard에는 'x' 진소성변형률 열을 명시해야 합니다."
        )
    x_name = _column_name(options, "x", "")
    source_option = options.get("source_index")
    explicit_source_index = source_option not in (None, "auto")
    if explicit_source_index:
        source_name = _column_name(options, "source_index", DEFAULT_SOURCE_INDEX)
    else:
        source_name = ""
    if x_name == source_name:
        raise ProcessingError(
            "진소성 좌표 순서 guard의 좌표 열과 원행 열은 서로 달라야 합니다."
        )
    _require_unit(frame, x_name, "1", "진소성변형률")
    x = _numeric_column(frame, x_name, "진소성변형률")
    _validate_source_row_pair(frame, x.size)
    if explicit_source_index:
        source = _validated_source_column(frame, source_name, x.size)
    else:
        source_name, source = _select_source_evidence(frame, x.size)
    if x_name == source_name:
        raise ProcessingError(
            "진소성 좌표 순서 guard의 좌표 열과 원행 열은 서로 달라야 합니다."
        )
    if x.size < 2:
        raise ProcessingError("진소성 좌표 순서 guard에는 최소 2개 행이 필요합니다.")
    if x[0] != 0.0:
        raise ProcessingError(
            f"진소성 proof anchor의 첫 좌표가 0이 아닙니다: {x[0]:.12g}. "
            "proof anchor를 첫 행으로 만드는 레시피를 확인하세요."
        )

    measured_source = source[1:]
    noninteger_source = np.flatnonzero(measured_source != np.floor(measured_source))
    if noninteger_source.size:
        position = int(noninteger_source[0]) + 1
        raise ProcessingError(
            "첫 proof anchor 뒤 원행 증거에 정수가 아닌 파생 행이 있습니다. "
            "실측 원행으로 확인할 수 없는 경계점은 자동 카드 후보에 포함하지 않습니다. "
            f"현재행 {position}, {source_name}={source[position]:.9g}, εp={x[position]:.9g}."
        )

    negative_positions = np.flatnonzero(x < 0.0).astype(np.intp, copy=False)
    if negative_positions.size:
        position = int(negative_positions[0])
        raise ProcessingError(
            "진소성변형률에 음수 εp가 있습니다. 이 균일 진소성 후보는 "
            f"clip_zero 계약을 전제로 하므로 첫 문제 현재행 {position}, "
            f"원행 증거 {source[position]:.9g}, εp={x[position]:.9g}를 보류합니다."
        )

    positive_positions = np.flatnonzero(x > 0.0).astype(np.intp, copy=False)
    if positive_positions.size:
        first_positive = int(positive_positions[0])
        zero_after_positive = np.flatnonzero((x == 0.0) & (np.arange(x.size) > first_positive))
        if zero_after_positive.size:
            position = int(zero_after_positive[0])
            previous = position - 1
            raise ProcessingError(
                "양의 εp 뒤에 εp=0 행이 다시 나타납니다. εp=0 중복은 proof anchor "
                "직후의 연속 구간만 허용합니다. "
                f"첫 문제 {previous}->{position}: εp {x[previous]:.9g}->{x[position]:.9g}, "
                f"{source_name} {source[previous]:.9g}->{source[position]:.9g}."
            )

    zero_duplicates = int(np.count_nonzero(x == 0.0) - 1)
    if zero_duplicates < 0:
        zero_duplicates = 0
    source_bad = np.flatnonzero(measured_source[1:] <= measured_source[:-1])
    if source_bad.size:
        offset = int(source_bad[0]) + 1
        first = offset
        second = offset + 1
        raise ProcessingError(
            "proof anchor를 제외한 진소성 지원 원행 순서가 엄격히 증가하지 않습니다. "
            f"첫 문제 {first}->{second}: "
            f"{source_name} {source[first]:.9g}->{source[second]:.9g}, "
            f"εp {x[first]:.9g}->{x[second]:.9g}. "
            "진소성변형률 정렬 전에 원자료 순서를 검토합니다."
        )

    if positive_positions.size < 2:
        raise ProcessingError(
            "진소성 좌표 순서 guard에서 양의 εp 지원점이 2개 미만입니다. "
            f"현재 {positive_positions.size}개라 카드 후보를 만들지 않습니다."
        )
    positive_bad = np.flatnonzero(x[positive_positions[1:]] <= x[positive_positions[:-1]])
    if positive_bad.size:
        offset = int(positive_bad[0])
        first = int(positive_positions[offset])
        second = int(positive_positions[offset + 1])
        relation = "같거나" if x[first] == x[second] else "감소하여"
        raise ProcessingError(
            f"양의 εp 지원 좌표가 엄격히 증가하지 않습니다({relation}). "
            f"첫 문제 {first}->{second}: εp {x[first]:.9g}->{x[second]:.9g}, "
            f"{source_name} {source[first]:.9g}->{source[second]:.9g}. "
            "curve.sort_unique가 역행·중복을 숨기기 전에 보류합니다."
        )

    effective_options = {"x": x_name, "source_index": source_name}
    scalars = (
        Scalar("plastic_coord_order_code", "진소성 좌표 순서 검증 상태", 1.0, "1"),
        Scalar("plastic_coord_source_order_code", "진소성 원행 순서 상태", 1.0, "1"),
        Scalar("plastic_coord_positive_order_code", "양의 εp 순서 상태", 1.0, "1"),
        Scalar(
            "plastic_coord_positive_points",
            "양의 εp 지원점 수",
            float(len(positive_positions)),
            "1",
        ),
        Scalar(
            "plastic_coord_zero_duplicate_count",
            "εp=0 의도된 중복 진단 수",
            float(zero_duplicates),
            "1",
        ),
        Scalar(
            "plastic_coord_derived_first_code",
            "첫 proof 행 파생 원행 허용 상태",
            1.0,
            "1",
        ),
        Scalar(
            "plastic_coord_source_rows_checked",
            "proof 뒤 원행 순서 검사 행 수",
            float(len(measured_source)),
            "1",
        ),
    )
    if not all(math.isfinite(item.value) for item in scalars):
        raise ProcessingError("진소성 좌표 순서 guard 진단값이 유한하지 않습니다.")
    notes = (
        f"proof 첫 행을 제외한 {len(measured_source)}개 원행과 양의 εp "
        f"{len(positive_positions)}개가 각각 엄격히 증가합니다.",
        f"취득 순서 증거 열 '{source_name}'을 사용했습니다.",
        f"εp=0 중복 {zero_duplicates}개는 의도된 초기 중복으로 진단만 남겼습니다. "
        "후속 first 정리와 proof_anchor_guard가 통과해야 후보를 채택할 수 있습니다.",
    )
    return StepResult(frame, notes=notes, scalars=scalars, effective_options=effective_options)


def _select_source_evidence(frame: Frame, size: int) -> tuple[str, np.ndarray]:
    present = [name for name in SOURCE_EVIDENCE_COLUMNS if name in frame.columns]
    if not present:
        names = ", ".join(SOURCE_EVIDENCE_COLUMNS)
        raise ProcessingError(
            "자동 source_index를 정할 취득 순서 증거 열이 없습니다. "
            f"지원 열({names}) 중 하나를 입력에 남겨 주세요."
        )
    failures: list[str] = []
    for name in present:
        try:
            values = _validated_source_column(frame, name, size)
        except ProcessingError as exc:
            failures.append(f"{name}: {exc}")
            continue
        return name, values
    detail = "; ".join(failures)
    raise ProcessingError(
        f"자동 source_index로 사용할 취득 순서 증거 열이 모두 검증에 실패했습니다. {detail}"
    )


def _validated_source_column(frame: Frame, name: str, size: int) -> np.ndarray:
    _require_unit(frame, name, "1", "원행 증거")
    values = _numeric_column(frame, name, "원행 증거")
    if values.size != size:
        raise ProcessingError(
            f"원행 증거 열 '{name}'의 길이가 진소성변형률과 다릅니다 "
            f"({values.size} 대 {size})."
        )
    measured = values[1:]
    if np.any(np.abs(measured) > MAX_EXACT_INTEGER):
        raise ProcessingError(f"원행 증거 열 '{name}'에 정확히 표현할 수 없는 값이 있습니다.")
    if np.any(measured != np.floor(measured)):
        raise ProcessingError(
            f"원행 증거 열 '{name}'의 proof 뒤에 정수가 아닌 파생 행이 포함되어 있습니다."
        )
    if measured.size >= 2 and np.any(np.diff(measured) <= 0.0):
        raise ProcessingError(f"원행 순서 증거 열 '{name}'이 엄격히 증가하지 않습니다.")
    return values


def _validate_source_row_pair(frame: Frame, size: int) -> None:
    data_name, physical_name = SOURCE_ROW_PAIR
    present = tuple(name for name in SOURCE_ROW_PAIR if name in frame.columns)
    for name in present:
        _require_unit(frame, name, "1", "원행 증거")
    if not present:
        return
    if len(present) != len(SOURCE_ROW_PAIR):
        raise ProcessingError(
            "source_data_row와 source_physical_line은 원행 pair 증거라서 두 열을 함께 "
            "제공해야 합니다. 한 열만 있는 입력은 처리하지 않습니다."
        )
    data = _validated_source_column(frame, data_name, size)
    physical = _validated_source_column(frame, physical_name, size)
    if data.size != physical.size:
        raise ProcessingError("source_data_row와 source_physical_line의 길이가 서로 다릅니다.")
    if data.size == 0:
        return
    if np.any(data < 1.0) or np.any(physical < 1.0):
        raise ProcessingError(
            "source_data_row와 source_physical_line은 1기반 원행 증거라서 모든 값이 "
            "1 이상이어야 합니다. proof anchor의 fractional 값도 1 이상이어야 합니다."
        )
    if np.any(physical <= data):
        raise ProcessingError(
            "source_physical_line은 헤더를 포함한 물리 파일 행이므로 "
            "source_data_row보다 커야 합니다."
        )
    measured_data = data[1:]
    measured_physical = physical[1:]
    if measured_data.size >= 2 and (
        np.any(np.diff(measured_data) != 1.0) or np.any(np.diff(measured_physical) != 1.0)
    ):
        raise ProcessingError(
            "source_data_row와 source_physical_line의 proof 뒤 측정행이 연속한 "
            "정수행이 아닙니다."
        )
    if np.any(np.diff(data) <= 0.0) or np.any(np.diff(physical) <= 0.0):
        raise ProcessingError(
            "source_data_row와 source_physical_line이 엄격히 증가하지 않아 처리하지 않습니다."
        )
    offset = physical - data
    measured_offset = offset[1:]
    if np.any(measured_offset < 1.0) or np.any(measured_offset != np.floor(measured_offset)):
        raise ProcessingError(
            "source_physical_line-source_data_row의 측정행 offset은 1 이상의 정수여야 합니다."
        )
    if measured_offset.size == 0:
        return
    expected_offset = float(measured_offset[0])
    if (
        not np.all(np.isfinite(offset))
        or not np.isclose(offset[0], expected_offset, rtol=0.0, atol=1e-9)
        or not np.allclose(measured_offset, expected_offset, rtol=0.0, atol=1e-9)
    ):
        raise ProcessingError(
            "source_data_row와 source_physical_line의 행별 대응 차이가 일정하지 않아 "
            "처리하지 않습니다. 원자료의 빈 줄로 offset이 달라지는 경우도 후보를 "
            "보류합니다."
        )


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"진소성 좌표 순서 guard의 '{key}' 열 이름은 비어 있지 않아야 합니다."
        )
    return value


def _require_unit(frame: Frame, name: str, expected: str, what: str) -> None:
    try:
        frame.require(name, what=what)
    except ProcessingError:
        available = ", ".join(sorted(frame.columns)) or "(없음)"
        raise ProcessingError(
            f"{what} 열 '{name}'이 없습니다. 이 곡선에 있는 열: {available}"
        ) from None
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"진소성 좌표 순서 guard의 {what} 열 '{name}' 단위는 '{expected}'이어야 합니다. "
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
