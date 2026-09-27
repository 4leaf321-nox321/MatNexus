"""Preserve the engineering stress seen immediately before model editing.

The coordinate-projected model needs an immutable reference to the values that
entered the model stage.  This small stage deliberately adds one column and
does not select, sort, or otherwise alter any existing source row.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, StepResult

DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_SNAPSHOT = "stress_engineering_source_snapshot"
SNAPSHOT_UNIT = "Pa"

_OPTION_KEYS = frozenset({"strain", "stress", "snapshot"})


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill the stable source-channel defaults without mutating *options*."""

    prepared = dict(options)
    unknown = sorted(set(prepared) - _OPTION_KEYS)
    if unknown:
        raise ProcessingError(
            "source_stress_snapshot 이 지원하지 않는 옵션입니다: " + ", ".join(unknown)
        )
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    prepared.setdefault("snapshot", DEFAULT_SNAPSHOT)
    return prepared


def source_stress_snapshot(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Add a copy of the current engineering stress as a source snapshot.

    The copy is intentionally made before any model stage.  Existing arrays are
    left untouched and remain aligned with the snapshot's current-row order.
    """

    _reject_unknown(options)
    strain_key = _column_name(options, "strain", DEFAULT_STRAIN)
    stress_key = _column_name(options, "stress", DEFAULT_STRESS)
    snapshot_key = _column_name(options, "snapshot", DEFAULT_SNAPSHOT)
    if snapshot_key in frame.columns:
        raise ProcessingError(
            f"원응력 snapshot 열 '{snapshot_key}'이 이미 있습니다. "
            "기존 열을 덮어쓰지 않습니다."
        )
    if frame.units.get(strain_key) != "1":
        raise ProcessingError(f"변형률 열 '{strain_key}'의 단위는 '1'이어야 합니다.")
    if frame.units.get(stress_key) != SNAPSHOT_UNIT:
        raise ProcessingError(
            f"응력 열 '{stress_key}'의 단위는 '{SNAPSHOT_UNIT}'이어야 합니다."
        )

    strain = _numeric_column(frame, strain_key, what="변형률")
    stress = _numeric_column(frame, stress_key, what="응력")
    if strain.size == 0:
        raise ProcessingError("원응력 snapshot을 만들 현재 행이 없습니다.")
    if strain.size != stress.size:
        raise ProcessingError("변형률과 응력 snapshot 열의 행 수가 서로 다릅니다.")
    if not np.all(np.isfinite(strain)):
        raise ProcessingError("원응력 snapshot의 변형률에는 유한하지 않은 값이 있습니다.")
    if not np.all(np.isfinite(stress)):
        raise ProcessingError("원응력 snapshot의 응력에는 유한하지 않은 값이 있습니다.")
    if strain.size > 1 and np.any(np.diff(strain) <= 0.0):
        raise ProcessingError("원응력 snapshot의 변형률은 엄격히 증가해야 합니다.")

    snapshot = np.array(stress, dtype=np.float64, copy=True)
    result_frame = frame.with_columns({snapshot_key: snapshot}, {snapshot_key: SNAPSHOT_UNIT})
    return StepResult(
        result_frame,
        notes=(
            f"현재 모델 입력 원행의 '{stress_key}'를 '{snapshot_key}'로 보존했습니다. "
            "행 선택·정렬·응력 변경은 하지 않았습니다.",
        ),
        effective_options={
            "strain": strain_key,
            "stress": stress_key,
            "snapshot": snapshot_key,
        },
    )


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = sorted(set(options) - _OPTION_KEYS)
    if unknown:
        raise ProcessingError(
            "source_stress_snapshot 이 지원하지 않는 옵션입니다: " + ", ".join(unknown)
        )


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(f"'{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _numeric_column(frame: Frame, key: str, *, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(key, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 읽을 수 없습니다.") from None
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ProcessingError(f"'{key}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        values = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 실수형 숫자로 읽을 수 없습니다.") from None
    return values
