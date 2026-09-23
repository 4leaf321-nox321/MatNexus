"""Choose a reviewed or clearly abrupt terminal prefix for tensile models."""

from __future__ import annotations

from numbers import Integral
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_text

AUTO_POLICY = "terminal_loss_auto_v1"
MANUAL_POLICY = "manual_end_v1"
POLICIES = (AUTO_POLICY, MANUAL_POLICY)
DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_TIME = "time"
FIXED_OPTIONS: dict[str, Any] = {
    "profile_version": "1",
    "late_progress_fraction": 0.90,
    "support_window_rows": 5,
    "minimum_support_rows": 3,
    "support_tolerance_fraction": 0.10,
    "adjacent_loss_fraction": 0.20,
    "chain_first_loss_fraction": 0.10,
    "chain_max_rows": 3,
    "recovery_loss_fraction": 0.50,
    "gap_preceding_steps": 20,
    "gap_interval_ratio": 10.0,
    "gap_progress_fraction": 0.01,
    "stable_suffix_remaining_fraction": 0.02,
    "stable_suffix_load_fraction": 0.20,
    "stable_suffix_range_fraction": 0.10,
    "gradual_tail_fraction": 0.10,
    "gradual_tail_drop_fraction": 0.10,
}
OPTION_KEYS = frozenset({"policy", "strain", "stress", "time", "end_index", *FIXED_OPTIONS})


def _resolve_options(
    options: dict[str, Any],
) -> tuple[str, str, str, str, int | None, dict[str, Any]]:
    unknown = sorted((key for key in options if key not in OPTION_KEYS), key=str)
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ProcessingError(f"지원하지 않는 말단 구간 옵션입니다: {names}.")

    for key, expected in FIXED_OPTIONS.items():
        if key in options:
            actual = options[key]
            if type(actual) is not type(expected) or actual != expected:
                raise ProcessingError(
                    f"'{key}' 정책은 {expected!r} 로 고정되어 있습니다. "
                    "다른 정책은 새 버전으로 정의해야 합니다."
                )

    policy = option_text(options, "policy", POLICIES)
    supplied = dict(options)
    supplied.setdefault("strain", DEFAULT_STRAIN)
    supplied.setdefault("stress", DEFAULT_STRESS)
    supplied.setdefault("time", DEFAULT_TIME)
    strain_name = option_text(supplied, "strain", ())
    stress_name = option_text(supplied, "stress", ())
    time_name = option_text(supplied, "time", ())

    end_index: int | None = None
    if policy == MANUAL_POLICY:
        if "end_index" not in options:
            raise ProcessingError("'manual_end_v1' 정책에는 검토한 'end_index' 가 필요합니다.")
        raw_end = options["end_index"]
        if isinstance(raw_end, bool) or not isinstance(raw_end, Integral):
            raise ProcessingError("'end_index' 는 bool 이 아닌 정수여야 합니다.")
        end_index = int(raw_end)
    elif "end_index" in options:
        raise ProcessingError("자동 정책은 'end_index' 를 받을 수 없습니다.")

    effective: dict[str, Any] = {
        "policy": policy,
        "strain": strain_name,
        "stress": stress_name,
        "time": time_name,
        **FIXED_OPTIONS,
    }
    if end_index is not None:
        effective["end_index"] = end_index
    return policy, strain_name, stress_name, time_name, end_index, effective


def _frame_arrays(frame: Frame) -> tuple[int, dict[str, np.ndarray]]:
    if not frame.columns:
        raise ProcessingError("말단 구간을 고를 곡선 열이 없습니다.")
    arrays: dict[str, np.ndarray] = {}
    expected_length: int | None = None
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"프레임 열 '{name}' 을 1차원 열로 읽을 수 없습니다."
            ) from None
        if values.ndim != 1:
            raise ProcessingError(f"프레임의 모든 열은 1차원이어야 합니다: '{name}'.")
        if expected_length is None:
            expected_length = len(values)
        elif len(values) != expected_length:
            raise ProcessingError(
                f"프레임 열의 점 수가 맞지 않습니다: '{name}' 은 {len(values)}점, "
                f"기준 열은 {expected_length}점입니다."
            )
        arrays[name] = values
    assert expected_length is not None
    if expected_length < 2:
        raise ProcessingError("말단 구간을 고르려면 프레임에 2점 이상 있어야 합니다.")
    return expected_length, arrays


def _real_values(values: np.ndarray, name: str, *, what: str) -> np.ndarray:
    if values.ndim != 1:
        raise ProcessingError(f"{what} 열 '{name}' 은 1차원이어야 합니다.")
    if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
        raise ProcessingError(f"{what} 열 '{name}' 은 실수형 숫자여야 합니다.")
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"{what} 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if not np.all(np.isfinite(result)):
        raise ProcessingError(f"{what} 열 '{name}' 에 유한하지 않은 값이 있습니다.")
    return result


def _require_unit(frame: Frame, name: str, expected: str, *, what: str) -> None:
    actual = frame.units.get(name)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"{what} 열 '{name}' 의 단위는 '{expected}' 이어야 합니다. 현재 단위: {shown}."
        )


def _strictly_increasing(values: np.ndarray) -> bool:
    return bool(np.all(values[1:] > values[:-1]))


def _normalized(values: np.ndarray) -> np.ndarray | None:
    scale = max(abs(float(values[0])), abs(float(values[-1])))
    if scale == 0.0:
        return None
    scaled = values / scale
    span = float(scaled[-1] - scaled[0])
    if not np.isfinite(span) or span <= 0.0:
        return None
    progress: np.ndarray = (scaled - scaled[0]) / span
    if not np.all(np.isfinite(progress)) or not _strictly_increasing(progress):
        return None
    return progress


def _progress(
    arrays: dict[str, np.ndarray],
    frame: Frame,
    strain: np.ndarray,
    strain_name: str,
    time_name: str,
) -> tuple[np.ndarray, str, str | None]:
    time_reason: str | None = None
    if time_name not in arrays:
        time_reason = f"시간 열 '{time_name}' 이 없어 시간 진행축을 쓰지 않았습니다."
    elif frame.units.get(time_name) != "s":
        unit = frame.units.get(time_name)
        shown = "누락" if unit is None else repr(unit)
        time_reason = f"시간 열 '{time_name}' 의 단위가 {shown} 이므로 초로 읽지 않았습니다."
    else:
        try:
            time = _real_values(arrays[time_name], time_name, what="시간")
        except ProcessingError as exc:
            time_reason = str(exc)
        else:
            if not _strictly_increasing(time):
                time_reason = (
                    f"시간 열 '{time_name}' 이 원래 행 순서에서 엄격히 증가하지 않습니다."
                )
            else:
                normalized_time = _normalized(time)
                if normalized_time is not None:
                    return normalized_time, "time", None
                time_reason = f"시간 열 '{time_name}' 을 0~1 진행축으로 정규화할 수 없습니다."

    if _strictly_increasing(strain):
        normalized_strain = _normalized(strain)
        if normalized_strain is not None:
            return normalized_strain, "strain", time_reason
        strain_reason = f"변형률 열 '{strain_name}' 을 0~1 진행축으로 정규화할 수 없습니다."
    else:
        strain_reason = (
            f"변형률 열 '{strain_name}' 이 원래 행 순서에서 엄격히 증가하지 않습니다."
        )
    ordinal = np.arange(len(strain), dtype=float) / (len(strain) - 1)
    reason = f"{time_reason} {strain_reason} 행 순서를 진행축으로 사용했습니다."
    return ordinal, "ordinal", reason


def _median(values: np.ndarray) -> float:
    ordered = np.sort(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float(ordered[middle - 1] / 2.0 + ordered[middle] / 2.0)


def _drop_chain(stress: np.ndarray, index: int, local_load: float) -> tuple[int, str] | None:
    adjacent_limit = stress[index] - FIXED_OPTIONS["adjacent_loss_fraction"] * local_load
    if stress[index + 1] <= adjacent_limit:
        return index + 1, "adjacent"

    first_limit = stress[index] - FIXED_OPTIONS["chain_first_loss_fraction"] * local_load
    if stress[index + 1] > first_limit:
        return None
    for rows in (2, 3):
        end = index + rows
        if end >= len(stress):
            continue
        chain = stress[index + 1 : end + 1]
        if np.any(chain[1:] > chain[:-1]):
            continue
        if stress[end] <= adjacent_limit:
            return end, f"chain_{rows}"
    return None


def _gap_error(
    progress: np.ndarray, basis: str, index: int, end: int
) -> ProcessingError | None:
    if basis == "ordinal":
        return None
    increments = np.diff(progress)
    for row in range(index + 1, end + 1):
        step_index = row - 1
        prior = increments[
            max(0, step_index - FIXED_OPTIONS["gap_preceding_steps"]) : step_index
        ]
        positive = prior[prior > 0.0]
        if not len(positive):
            continue
        local = _median(positive)
        step = float(increments[step_index])
        if (
            step > FIXED_OPTIONS["gap_interval_ratio"] * local
            and step > FIXED_OPTIONS["gap_progress_fraction"]
        ):
            return ProcessingError(
                "ambiguous_sampling_gap: "
                f"후보 유지 행 {index} 의 손실 연결에서 입력 행 {row - 1}→{row} 진행 간격 "
                f"{step:.6g} 이 직전 간격 중앙값 {local:.6g} 의 10배 초과이며 "
                "전체 진행 폭의 1%보다 큽니다. 급락이 이 간격 안의 어느 위치에서 시작했는지 "
                "관측만으로 정할 수 없어 자동 자르기를 보류합니다."
            )
    return None


def _automatic_end(
    stress: np.ndarray, progress: np.ndarray, basis: str
) -> tuple[int | None, list[str], bool]:
    notes: list[str] = []
    n = len(stress)
    min_index = FIXED_OPTIONS["minimum_support_rows"] - 1
    for index in range(min_index, n - 1):
        if progress[index] < FIXED_OPTIONS["late_progress_fraction"]:
            continue
        local = _median(
            stress[max(0, index - FIXED_OPTIONS["support_window_rows"] + 1) : index + 1]
        )
        if local <= 0.0 or stress[index] <= 0.0:
            continue
        if abs(stress[index] - local) > FIXED_OPTIONS["support_tolerance_fraction"] * local:
            continue
        chain = _drop_chain(stress, index, local)
        if chain is None:
            continue
        end, kind = chain
        # Recovery after the shortest qualifying low row makes this an internal event.
        midpoint = stress[index] * 0.5 + stress[end] * 0.5
        if np.any(stress[end:] > midpoint):
            continue

        gap_error = _gap_error(progress, basis, index, end)
        if gap_error is not None:
            raise gap_error

        suffix = stress[index + 1 :]
        remaining = 1.0 - progress[index]
        stable_loaded = (
            remaining > FIXED_OPTIONS["stable_suffix_remaining_fraction"]
            and _median(suffix) >= FIXED_OPTIONS["stable_suffix_load_fraction"] * local
            and np.min(suffix)
            >= np.max(suffix) - FIXED_OPTIONS["stable_suffix_range_fraction"] * local
        )
        if stable_loaded:
            raise ProcessingError(
                "ambiguous_stable_low_suffix: "
                f"후보 유지 행 {index} 뒤에 진행 폭 {remaining:.6g} 의 안정된 "
                "하중 구간이 남습니다. "
                "의도된 하측 모델 구간일 수 있어 자동 자르기를 보류합니다."
            )

        first_loss_fraction = float((stress[index] - stress[index + 1]) / local)
        total_loss_fraction = float((stress[index] - stress[end]) / local)
        notes.extend(
            (
                f"결정 applied ({kind}); 후보 유지 행 {index}, 첫 제외 행 {index + 1}, "
                f"마지막 연결 행 {end}.",
                f"후보 행 응력 {stress[index]:.6g} Pa, 첫 제외 응력 "
                f"{stress[index + 1]:.6g} Pa, 끝 연결 응력 {stress[end]:.6g} Pa, "
                f"국소 기준 L={local:.6g} Pa, 첫 손실/L={first_loss_fraction:.6g}, "
                f"총 손실/L={total_loss_fraction:.6g}.",
            )
        )
        return index, notes, False
    return None, notes, _gradual_unresolved(stress, progress)


def _gradual_unresolved(stress: np.ndarray, progress: np.ndarray) -> bool:
    source_max = max(0.0, float(np.max(stress)))
    if source_max <= 0.0:
        return False
    first_late = int(
        np.searchsorted(progress, FIXED_OPTIONS["late_progress_fraction"], side="left")
    )
    threshold = FIXED_OPTIONS["gradual_tail_drop_fraction"] * source_max
    with np.errstate(over="ignore", invalid="ignore"):
        return bool(stress[-1] <= stress[first_late] - threshold)


def _progress_notes(basis: str, reason: str | None, strain_strict: bool) -> tuple[str, ...]:
    descriptions = {"time": "시간(s)", "strain": "변형률", "ordinal": "원래 행 순서"}
    notes = [f"진행축 {descriptions[basis]} 을 사용해 0~1 로 정규화했습니다."]
    if reason:
        notes.append(f"진행축 대체 이유: {reason}")
    if basis == "ordinal":
        notes.append("행 순서 진행축은 실제 시간·변형률 간격을 증명하지 않습니다.")
    if not strain_strict:
        notes.append(
            "변형률은 원래 행 순서에서 엄격히 증가하지 않습니다. "
            "뒤의 모델 단계는 자체 순서 검사를 합니다."
        )
    return tuple(notes)


def terminal_domain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Retain a manual or supported abrupt-loss prefix for model methods."""
    policy, strain_name, stress_name, time_name, manual_end, effective = _resolve_options(
        options
    )
    n, arrays = _frame_arrays(frame)
    frame.require(strain_name, what="변형률")
    frame.require(stress_name, what="응력")
    _require_unit(frame, strain_name, "1", what="변형률")
    _require_unit(frame, stress_name, "Pa", what="응력")
    strain = _real_values(arrays[strain_name], strain_name, what="변형률")
    stress = _real_values(arrays[stress_name], stress_name, what="응력")
    strain_strict = _strictly_increasing(strain)
    progress, basis, fallback_reason = _progress(arrays, frame, strain, strain_name, time_name)

    progress_notes = _progress_notes(basis, fallback_reason, strain_strict)
    decision_code: float
    unresolved = False
    candidate_notes: tuple[str, ...] = ()
    end_index: int | None
    if policy == MANUAL_POLICY:
        assert manual_end is not None
        if manual_end < 1 or manual_end >= n:
            raise ProcessingError(
                f"'end_index' 는 현재 입력 프레임에서 1~{n - 1} 사이의 정수여야 합니다: "
                f"{manual_end}."
            )
        end_index = manual_end
        decision_code = 2.0
        if end_index == n - 1:
            candidate_notes = (
                f"결정 applied (manual_end_v1); 현재 입력 행 0~{end_index} 를 "
                "모두 유지했습니다.",
            )
        else:
            candidate_notes = (
                f"결정 applied (manual_end_v1); 현재 입력 행 0~{end_index} 를 유지하고 "
                f"{end_index + 1}~{n - 1} 을 제외합니다.",
            )
    else:
        end_index, automatic_notes, unresolved = _automatic_end(stress, progress, basis)
        if end_index is None:
            end_index = n - 1
            decision_code = 0.0
            candidate_notes = (
                f"결정 no_abrupt_terminal_loss; 현재 입력 행 0~{n - 1} 을 모두 유지했습니다.",
            )
        else:
            decision_code = 1.0
            candidate_notes = tuple(automatic_notes)

    if policy == MANUAL_POLICY:
        selected = frame if end_index == n - 1 else frame.select(np.arange(end_index + 1))
    elif decision_code == 1.0:
        selected = frame.select(np.arange(end_index + 1))
    else:
        selected = frame

    notes = [f"정책 {policy}.", *progress_notes, *candidate_notes]
    if unresolved and policy == AUTO_POLICY:
        first_late = int(
            np.searchsorted(progress, FIXED_OPTIONS["late_progress_fraction"], side="left")
        )
        notes.append(
            "결정 gradual_tail_unresolved; 마지막 진행축 10% 구간 첫 응력 "
            f"{stress[first_late]:.6g} Pa 에서 끝 응력 {stress[-1]:.6g} Pa 까지 "
            "양의 원응력 최댓값의 10% 이상 감소했지만 이 급락 정책은 완만한 끝 감소를 "
            "자르지 않습니다. 말단이 물리적으로 유효하다고 판정한 것은 아닙니다."
        )
    notes.append("말단 구간 선택은 모델용 기록 범위이며 네킹이나 파단을 판정하지 않습니다.")

    scalar_values = (
        Scalar(
            "terminal_domain_end_index", "모델 구간 끝 행 위치 (0부터)", float(end_index), "1"
        ),
        Scalar(
            "terminal_domain_end_strain",
            "모델 구간 끝 변형률",
            float(strain[end_index]),
            "1",
            "strain",
        ),
        Scalar(
            "terminal_domain_removed_points",
            "제외한 말단 점 수",
            float(n - end_index - 1),
            "1",
        ),
        Scalar("terminal_domain_input_points", "입력 점 수", float(n), "1"),
        Scalar("terminal_domain_input_end_load", "입력 끝 응력", float(stress[-1]), "Pa"),
        Scalar("terminal_domain_decision_code", "말단 결정 코드", decision_code, "1"),
        Scalar(
            "terminal_domain_strain_strict",
            "입력 변형률 엄격 증가 여부",
            float(strain_strict),
            "1",
        ),
        Scalar(
            "terminal_domain_progress_basis_code",
            "진행축 코드",
            {"ordinal": 0.0, "strain": 1.0, "time": 2.0}[basis],
            "1",
        ),
    )
    if not all(np.isfinite(scalar.value) for scalar in scalar_values):
        raise ProcessingError("말단 구간 진단값이 유한하지 않습니다.")
    return StepResult(
        frame=selected,
        notes=tuple(notes),
        scalars=scalar_values,
        effective_options=effective,
    )
