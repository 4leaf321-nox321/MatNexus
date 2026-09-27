"""Atomically validate source evidence and select a tensile terminal domain.

The ordinary terminal-domain stage receives only terminal-policy options.  This
wrapper computes the source peak from the complete input before delegating to
that stage, then verifies that the selected frame is an exact all-column
prefix.  Keeping those operations together prevents a caller from replacing a
source peak or terminal decision with unrelated scalar options.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult

from . import source_peak_evidence, terminal_domain

DEFAULT_STRAIN = terminal_domain.DEFAULT_STRAIN
DEFAULT_STRESS = terminal_domain.DEFAULT_STRESS
DEFAULT_TIME = terminal_domain.DEFAULT_TIME
DEFAULT_FORCE = source_peak_evidence.DEFAULT_FORCE
DEFAULT_POLICY = terminal_domain.AUTO_POLICY
OPTION_KEYS = terminal_domain.PROGRESSIVE_OPTION_KEYS | {"force"}
GUARD_SCALAR_KEYS = (
    "source_terminal_guard_code",
    "source_terminal_guard_peak_index",
    "source_terminal_guard_end_index",
    "source_terminal_guard_decision_code",
    "source_terminal_guard_gradual_unresolved",
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Prepare only terminal-domain options; source values are never inputs."""

    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(
            f"원행 말단 domain에 알 수 없는 옵션이 있습니다: {names}. "
            "source peak·terminal 결과 scalar는 입력으로 받지 않습니다."
        )
    prepared.setdefault("policy", DEFAULT_POLICY)
    prepared.setdefault("force", DEFAULT_FORCE)
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    prepared.setdefault("time", DEFAULT_TIME)
    return prepared


def source_terminal_domain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Verify raw source evidence and return the terminal-domain result atomically."""

    options = prepare_options(options)
    force_name = _column_name(options, "force", DEFAULT_FORCE)
    strain_name = _column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = _column_name(options, "stress", DEFAULT_STRESS)
    _column_name(options, "time", DEFAULT_TIME)

    before_columns = _copy_columns(frame)
    before_units = dict(frame.units)
    peak_result = source_peak_evidence.source_peak_evidence(
        frame,
        {
            "force": force_name,
            "strain": strain_name,
            "stress": stress_name,
        },
    )
    peak_values = {item.key: item.value for item in peak_result.scalars}
    raw_peak_index = _row_index(peak_values.get("source_peak_index"), "source_peak_index")
    raw_peak_stress = _finite_number(
        peak_values.get("source_peak_stress"), "source_peak_stress"
    )

    terminal_options = {key: value for key, value in options.items() if key != "force"}
    delegated = terminal_domain.terminal_domain(frame, terminal_options)
    _verify_input_unchanged(frame, before_columns, before_units)

    terminal_values = {item.key: item.value for item in delegated.scalars}
    end_index = _row_index(
        terminal_values.get("terminal_domain_end_index"),
        "terminal_domain_end_index",
    )
    decision_code = _decision_code(
        terminal_values.get("terminal_domain_decision_code"),
        "terminal_domain_decision_code",
    )
    _verify_selected_prefix(
        source_frame=frame,
        selected_frame=delegated.frame,
        source_columns=before_columns,
        source_units=before_units,
        end_index=end_index,
        decision_code=decision_code,
    )
    if end_index < raw_peak_index:
        raise ProcessingError(
            "원행 말단 domain이 source peak를 보존하지 않았습니다: "
            f"terminal_domain_end_index={end_index}, source_peak_index={raw_peak_index}."
        )
    _verify_selected_peak(
        delegated.frame,
        stress_name=stress_name,
        raw_peak_index=raw_peak_index,
        raw_peak_stress=raw_peak_stress,
    )

    gradual_unresolved = False
    progress_basis = "not_checked"
    if decision_code == 0:
        arrays = {name: np.asarray(values) for name, values in before_columns.items()}
        strain = terminal_domain._real_values(arrays[strain_name], strain_name, what="변형률")
        stress = terminal_domain._real_values(arrays[stress_name], stress_name, what="응력")
        progress, progress_basis, _ = terminal_domain._progress(
            arrays,
            frame,
            strain,
            strain_name,
            options["time"],
        )
        gradual_unresolved = terminal_domain._gradual_unresolved(stress, progress)
        if gradual_unresolved:
            raise ProcessingError(
                "gradual_tail_unresolved: terminal_domain code 0이 전체 원행을 보존했지만 "
                "원래 입력의 마지막 진행 구간에 완만한 응력 감소가 남아 있어 원행 "
                "말단 후보를 보류합니다."
            )

    guard_scalars = (
        Scalar("source_terminal_guard_code", "원행 말단 보존 검증 상태 (1=검증)", 1.0, "1"),
        Scalar(
            "source_terminal_guard_peak_index",
            "검증한 원행 최대하중 위치",
            float(raw_peak_index),
            "1",
        ),
        Scalar(
            "source_terminal_guard_end_index",
            "검증한 말단 끝 원행",
            float(end_index),
            "1",
        ),
        Scalar(
            "source_terminal_guard_decision_code",
            "검증한 말단 결정 코드",
            float(decision_code),
            "1",
        ),
        Scalar(
            "source_terminal_guard_gradual_unresolved",
            "검증한 완만한 말단 하강 미해결 상태",
            float(gradual_unresolved),
            "1",
        ),
    )
    if not all(math.isfinite(item.value) for item in guard_scalars):
        raise ProcessingError("원행 말단 domain guard 진단값이 유한하지 않습니다.")

    basis_labels = {"time": "시간(s)", "strain": "변형률", "ordinal": "원래 행 순서"}
    notes = (
        *delegated.notes,
        f"전체 원행에서 source peak {raw_peak_index} ({raw_peak_stress:.9g} Pa)를 "
        "다시 확인하고 terminal-domain 결과의 peak 보존을 검증했습니다.",
        "terminal-domain 결과가 모든 열에서 원래 입력의 동일한 포함 prefix임을 "
        "확인했습니다. 입력 Frame과 선택값은 이 단계에서 변경하지 않았습니다.",
        *(
            (
                "자동 무절단(code 0)의 진행축을 원래 입력에서 다시 계산했습니다: "
                f"{basis_labels[progress_basis]}. gradual_tail_unresolved가 아닙니다.",
            )
            if decision_code == 0
            else ()
        ),
    )
    effective_options = dict(delegated.effective_options or terminal_options)
    effective_options["force"] = force_name
    return StepResult(
        frame=delegated.frame,
        notes=notes,
        scalars=(*delegated.scalars, *guard_scalars),
        effective_options=effective_options,
    )


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"원행 말단 domain의 '{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다."
        )
    return value


def _copy_columns(frame: Frame) -> dict[str, np.ndarray]:
    if not frame.columns:
        raise ProcessingError("원행 말단 domain을 적용할 입력 열이 없습니다.")
    copied: dict[str, np.ndarray] = {}
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"원행 말단 domain 입력 열 '{name}'을 배열로 읽을 수 없습니다."
            ) from None
        copied[name] = np.array(values, copy=True)
    return copied


def _verify_input_unchanged(
    frame: Frame, before_columns: dict[str, np.ndarray], before_units: dict[str, str]
) -> None:
    if frame.units != before_units or set(frame.columns) != set(before_columns):
        raise ProcessingError(
            "terminal-domain이 원래 입력 Frame의 열 또는 단위를 변경했습니다."
        )
    for name, before in before_columns.items():
        current = np.asarray(frame.columns[name])
        if not np.array_equal(current, before):
            raise ProcessingError(
                f"terminal-domain이 원래 입력 열 '{name}'의 값을 변경했습니다."
            )


def _verify_selected_prefix(
    *,
    source_frame: Frame,
    selected_frame: Frame,
    source_columns: dict[str, np.ndarray],
    source_units: dict[str, str],
    end_index: int,
    decision_code: int,
) -> None:
    source_length = _frame_length(source_columns)
    selected_columns = _copy_columns(selected_frame)
    selected_length = _frame_length(selected_columns)
    if end_index >= source_length:
        raise ProcessingError(
            "terminal_domain_end_index가 원래 입력 범위를 벗어났습니다: "
            f"{end_index}, 마지막 행 {source_length - 1}."
        )
    if selected_length != end_index + 1:
        raise ProcessingError(
            "terminal-domain 결과 길이가 terminal_domain_end_index와 맞지 않습니다: "
            f"현재 {selected_length}개, 끝 행 {end_index}."
        )
    if set(selected_columns) != set(source_columns) or selected_frame.units != source_units:
        raise ProcessingError(
            "terminal-domain 결과가 모든 입력 열과 단위를 보존하지 않았습니다."
        )
    for name, source in source_columns.items():
        expected = source[: end_index + 1]
        actual = selected_columns[name]
        if not np.array_equal(actual, expected):
            raise ProcessingError(
                f"terminal-domain 결과가 입력 열 '{name}'의 동일한 prefix가 아닙니다."
            )

    if end_index == source_length - 1:
        if selected_frame is not source_frame:
            raise ProcessingError(
                "terminal-domain이 선택할 행이 없는 결과에서 입력 Frame identity를 "
                "보존하지 않았습니다."
            )
    elif selected_frame is source_frame:
        raise ProcessingError(
            "terminal-domain이 일부 행을 제외해야 하는데 입력 Frame identity를 "
            "그대로 반환했습니다."
        )
    if decision_code == 0 and end_index != source_length - 1:
        raise ProcessingError(
            "terminal-domain decision code 0인데 입력 전체를 보존하지 않았습니다."
        )


def _verify_selected_peak(
    frame: Frame, *, stress_name: str, raw_peak_index: int, raw_peak_stress: float
) -> None:
    try:
        stress_raw = np.asarray(frame.require(stress_name, what="응력"))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"선택 결과 응력 열 '{stress_name}'을 읽을 수 없습니다."
        ) from None
    stress = terminal_domain._real_values(stress_raw, stress_name, what="응력")
    current_peak = int(np.argmax(stress))
    if current_peak != raw_peak_index:
        raise ProcessingError(
            "terminal-domain 선택 결과에서 source peak의 첫 최대 위치가 달라졌습니다: "
            f"원행={raw_peak_index}, 선택 결과={current_peak}."
        )
    if float(stress[raw_peak_index]) != raw_peak_stress:
        raise ProcessingError(
            "terminal-domain 선택 결과의 source peak 응력이 원행 값과 정확히 다릅니다: "
            f"원행={raw_peak_stress:.12g}, 선택 결과={float(stress[raw_peak_index]):.12g}."
        )


def _frame_length(columns: dict[str, np.ndarray]) -> int:
    if not columns:
        raise ProcessingError("원행 말단 domain 결과에 입력 열이 없습니다.")
    lengths = {len(values) for values in columns.values()}
    if len(lengths) != 1:
        raise ProcessingError("원행 말단 domain 결과 열의 점 수가 서로 다릅니다.")
    return next(iter(lengths))


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.") from None
    if not math.isfinite(number):
        raise ProcessingError(f"'{name}'은 유한한 숫자여야 합니다.")
    return number


def _row_index(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ProcessingError(f"'{name}'은 0 이상의 유한한 정수 행 위치여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{name}'은 0 이상의 유한한 정수 행 위치여야 합니다.") from None
    if not math.isfinite(number) or not number.is_integer() or number < 0.0:
        raise ProcessingError(f"'{name}'은 0 이상의 유한한 정수 행 위치여야 합니다.")
    return int(number)


def _decision_code(value: Any, name: str) -> int:
    number = _finite_number(value, name)
    if number not in (0.0, 1.0, 2.0, 3.0):
        raise ProcessingError(f"'{name}'은 0, 1, 2, 3 중 하나여야 합니다.")
    return int(number)
