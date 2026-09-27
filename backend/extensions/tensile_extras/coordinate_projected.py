"""Apply a bounded coordinate-order correction to a modeled tensile curve.

The stage is deliberately opt-in and runs after ``band_model`` and
``model_anchor``.  It keeps the model's unchanged source rows fixed, delegates
the actual coordinate projection to the extension helper, and accepts the
result only when the model proof point is unchanged.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult
from matcore.processing.tensile import proof_stress

from .coordinate_projection import DEFAULT_METHOD, METHODS, project_model_stress

DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
DEFAULT_SNAPSHOT = "stress_engineering_source_snapshot"
DEFAULT_SOURCE_INDEX = "model_input_index"
DEFAULT_OFFSET_STRAIN = 0.002
PROOF_TOLERANCE = 1.0e-12
METHOD_ALIASES = (
    "upper_envelope",
    "upper_envelope_auto_v1",
    "lower_envelope_auto_v1",
    "isotonic_auto_v1",
    "median_plateau_auto_v1",
    "linear_auto_v1",
    "least_squares_auto_v1",
    "robust_linear_auto_v1",
)
METHOD_CHOICES = (*METHODS, *METHOD_ALIASES)

OPTION_KEYS = frozenset(
    {
        "strain",
        "stress",
        "snapshot",
        "source_index",
        "youngs_modulus",
        "proof_strain",
        "proof_stress",
        "offset_strain",
        "search_start",
        "search_end",
        "method",
        "end_strain",
    }
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill references to the model anchor without mutating recipe options."""

    prepared = dict(options)
    _reject_unknown(prepared)
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    prepared.setdefault("snapshot", DEFAULT_SNAPSHOT)
    prepared.setdefault("source_index", DEFAULT_SOURCE_INDEX)
    prepared.setdefault("youngs_modulus", "@youngs_modulus")
    prepared.setdefault("proof_strain", "@model_proof_strain")
    prepared.setdefault("proof_stress", "@model_proof_stress")
    prepared.setdefault("offset_strain", "@model_proof_offset")
    prepared.setdefault("method", DEFAULT_METHOD)
    return prepared


def coordinate_projected(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Project only changed model rows while preserving the model proof point."""

    _reject_unknown(options)
    strain_name = _column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = _column_name(options, "stress", DEFAULT_STRESS)
    snapshot_name = _column_name(options, "snapshot", DEFAULT_SNAPSHOT)
    source_index_name = _column_name(options, "source_index", DEFAULT_SOURCE_INDEX)
    if strain_name == stress_name:
        raise ProcessingError("좌표 투영의 변형률 열과 응력 열은 서로 달라야 합니다.")
    if strain_name == snapshot_name or stress_name == snapshot_name:
        raise ProcessingError(
            "좌표 투영의 원응력 snapshot 열은 모델 응력·변형률 열과 달라야 합니다."
        )

    _require_unit(frame, strain_name, "1", "변형률")
    _require_unit(frame, stress_name, "Pa", "모델 응력")
    _require_unit(frame, snapshot_name, "Pa", "원응력 snapshot")
    _require_unit(frame, source_index_name, "1", "원행 대응")

    strain = _numeric_column(frame, strain_name, "변형률")
    modeled = _numeric_column(frame, stress_name, "모델 응력")
    raw = _numeric_column(frame, snapshot_name, "원응력 snapshot")
    source_rows = _source_rows(frame, source_index_name)
    _validate_curve_lengths(strain, raw, modeled, source_rows)
    _validate_strain(strain)
    if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(modeled)):
        raise ProcessingError("좌표 투영의 원응력과 모델 응력에는 유한한 값만 허용됩니다.")

    modulus = _finite_number(options, "youngs_modulus")
    if modulus <= 0.0:
        raise ProcessingError("좌표 투영의 Young's modulus는 양수여야 합니다.")
    proof_strain_value = _finite_number(options, "proof_strain")
    proof_stress_value = _finite_number(options, "proof_stress")
    offset = _finite_number(
        options if "offset_strain" in options else {"offset_strain": DEFAULT_OFFSET_STRAIN},
        "offset_strain",
    )
    if offset < 0.0:
        raise ProcessingError("좌표 투영의 오프셋은 음수일 수 없습니다.")
    method = options.get("method", DEFAULT_METHOD)
    if not isinstance(method, str) or method not in METHOD_CHOICES:
        names = ", ".join(METHOD_CHOICES)
        raise ProcessingError(f"좌표 투영 방법은 {names} 중 하나여야 합니다: {method!r}.")

    end_strain = _optional_number(options, "end_strain")
    if end_strain is not None:
        if not strain[0] <= end_strain <= strain[-1]:
            raise ProcessingError(
                "좌표 투영 end_strain은 현재 모델 변형률 범위 안이어야 합니다: "
                f"[{strain[0]:.12g}, {strain[-1]:.12g}] 밖의 {end_strain:.12g}."
            )
        if end_strain < proof_strain_value:
            raise ProcessingError(
                "좌표 투영 end_strain은 model proof 변형률 이상이어야 합니다: "
                f"{end_strain:.12g} < {proof_strain_value:.12g}."
            )

    allowed_length = _projection_length(strain, end_strain)
    changed = modeled != raw
    changed_in_scope = changed[:allowed_length]
    corrected = modeled.copy()
    helper_diagnostics = None
    if np.any(changed_in_scope):
        try:
            projected, helper_diagnostics = project_model_stress(
                strain,
                raw,
                modeled,
                modulus,
                proof_strain_value,
                method,
                end_strain=end_strain,
            )
        except ProcessingError as exc:
            raise ProcessingError(f"좌표 투영을 보류합니다: {exc}") from None
        except (TypeError, ValueError, OverflowError, FloatingPointError) as exc:
            raise ProcessingError(f"좌표 투영 입력을 보류합니다: {exc}") from None
        projected = np.asarray(projected, dtype=np.float64)
        if projected.shape != modeled.shape:
            raise ProcessingError(
                "좌표 투영이 모델 응력과 같은 행 수의 결과를 내지 않았습니다."
            )
        corrected = projected.copy()

    _validate_projection_result(
        raw=raw,
        modeled=modeled,
        corrected=corrected,
        changed=changed_in_scope,
        allowed_length=allowed_length,
    )

    # The proof anchor is a contract of the incoming model stage.  Recompute
    # it through the core implementation, including the same offset and any
    # explicitly supplied search bounds, before accepting a correction.
    corrected_frame = (
        frame
        if np.array_equal(corrected, modeled)
        else frame.with_columns({stress_name: corrected}, {})
    )
    recomputed = _recompute_model_proof(
        corrected_frame,
        strain_name=strain_name,
        stress_name=stress_name,
        modulus=modulus,
        offset=offset,
        options=options,
    )
    actual_proof_stress = _scalar_value(recomputed, "proof_stress")
    actual_proof_strain = _scalar_value(recomputed, "proof_strain")
    if not _within_tolerance(actual_proof_stress, proof_stress_value) or not _within_tolerance(
        actual_proof_strain, proof_strain_value
    ):
        raise ProcessingError(
            "좌표 투영을 보류합니다: 모델 proof anchor가 이동했습니다 "
            f"(expected strain={proof_strain_value:.12g}, stress={proof_stress_value:.12g}; "
            f"actual strain={actual_proof_strain:.12g}, stress={actual_proof_stress:.12g}; "
            f"tolerance={PROOF_TOLERANCE:.3g})."
        )

    changed_after = corrected != modeled
    changed_rows = np.flatnonzero(changed_after)
    correction_count = int(changed_rows.size)
    if helper_diagnostics is not None and helper_diagnostics.changed_count != correction_count:
        raise ProcessingError(
            "좌표 투영 진단의 보정 점 수가 실제 응력 결과와 일치하지 않습니다."
        )
    maximum_change = (
        float(np.max(np.abs(corrected[changed_rows] - modeled[changed_rows])))
        if correction_count
        else 0.0
    )
    first_source = int(source_rows[changed_rows[0]]) if correction_count else -1
    last_source = int(source_rows[changed_rows[-1]]) if correction_count else -1
    scalars = (
        Scalar(
            "coordinate_projected_correction_count",
            "좌표 투영 응력 보정 점 수",
            float(correction_count),
            "1",
        ),
        Scalar(
            "coordinate_projected_max_abs_change",
            "좌표 투영 최대 응력 보정 폭",
            maximum_change,
            "Pa",
        ),
        Scalar(
            "coordinate_projected_first_source_row",
            "좌표 투영 첫 원행",
            float(first_source),
            "1",
        ),
        Scalar(
            "coordinate_projected_last_source_row",
            "좌표 투영 마지막 원행",
            float(last_source),
            "1",
        ),
    )

    effective_options = {
        "strain": strain_name,
        "stress": stress_name,
        "snapshot": snapshot_name,
        "source_index": source_index_name,
        "youngs_modulus": modulus,
        "proof_strain": proof_strain_value,
        "proof_stress": proof_stress_value,
        "offset_strain": offset,
        "method": method,
    }
    for name in ("search_start", "search_end"):
        if name in options and options[name] is not None:
            effective_options[name] = _finite_number(options, name)
    if end_strain is not None:
        effective_options["end_strain"] = end_strain

    if correction_count:
        scope_note = f" (변형률 상한 {end_strain:.12g})" if end_strain is not None else ""
        notes = (
            f"coordinate_projected_v1이 모델 변경행 {correction_count}개{scope_note}를 "
            f"좌표 투영했습니다. 최대 응력 보정 폭은 {maximum_change:.12g} Pa, "
            f"원행 범위는 {first_source}~{last_source}입니다.",
            "model proof stress·strain을 core proof_stress로 재계산해 기존 anchor와 "
            f"{PROOF_TOLERANCE:.3g} tolerance 안에서 확인했습니다.",
            "이 결과는 coordinate-projected model이라는 별도 모델이며 원 band method의 "
            "shape 보존을 주장하지 않습니다.",
        )
    else:
        notes = (
            "coordinate_projected_v1은 보정할 모델 변경행이 없어 no-op으로 유지했습니다. "
            "모델 응력 배열을 byte-identical하게 보존했습니다.",
            "model proof stress·strain을 core proof_stress로 재계산해 기존 anchor와 "
            f"{PROOF_TOLERANCE:.3g} tolerance 안에서 확인했습니다.",
        )
    return StepResult(
        corrected_frame,
        notes=notes,
        scalars=scalars,
        effective_options=effective_options,
    )


def _recompute_model_proof(
    frame: Frame,
    *,
    strain_name: str,
    stress_name: str,
    modulus: float,
    offset: float,
    options: dict[str, Any],
) -> StepResult:
    proof_options: dict[str, Any] = {
        "strain": strain_name,
        "stress": stress_name,
        "youngs_modulus": modulus,
        "offset_strain": offset,
    }
    for name in ("search_start", "search_end"):
        if name in options and options[name] is not None:
            proof_options[name] = _finite_number(options, name)
    try:
        return proof_stress(frame, proof_options)
    except ProcessingError as exc:
        raise ProcessingError(f"좌표 투영 proof 재계산을 보류합니다: {exc}") from None


def _validate_projection_result(
    *,
    raw: np.ndarray,
    modeled: np.ndarray,
    corrected: np.ndarray,
    changed: np.ndarray,
    allowed_length: int,
) -> None:
    if corrected.shape != modeled.shape or not np.all(np.isfinite(corrected)):
        raise ProcessingError("좌표 투영 결과의 행 수 또는 유한성 검증에 실패했습니다.")
    if not np.array_equal(corrected[allowed_length:], modeled[allowed_length:]):
        raise ProcessingError("좌표 투영이 범위 밖의 고정 모델 행을 변경했습니다.")
    fixed = ~changed
    if not np.array_equal(corrected[:allowed_length][fixed], modeled[:allowed_length][fixed]):
        raise ProcessingError("좌표 투영이 원응력과 같은 고정 모델 행을 변경했습니다.")
    lower = np.minimum(raw, modeled)
    upper = np.maximum(raw, modeled)
    values = corrected
    if np.any(values < lower) or np.any(values > upper):
        row = int(np.flatnonzero((values < lower) | (values > upper))[0])
        raise ProcessingError(
            f"좌표 투영 행 {row}의 응력이 raw/model 닫힌 구간을 벗어났습니다."
        )


def _projection_length(strain: np.ndarray, end_strain: float | None) -> int:
    if end_strain is None:
        return int(strain.size)
    length = int(np.searchsorted(strain, end_strain, side="right"))
    return max(1, min(length, int(strain.size)))


def _source_rows(frame: Frame, name: str) -> np.ndarray:
    values = _numeric_column(frame, name, "원행 대응")
    if values.size == 0:
        raise ProcessingError("좌표 투영의 원행 대응 열이 비어 있습니다.")
    if (
        np.any(~np.isfinite(values))
        or np.any(values < 0.0)
        or np.any(values >= float(1 << 63))
        or np.any(values != np.floor(values))
    ):
        raise ProcessingError("좌표 투영의 원행 대응 열은 0 이상 정수여야 합니다.")
    if values.size > 1 and np.any(np.diff(values) <= 0.0):
        raise ProcessingError("좌표 투영의 원행 대응 열은 엄격히 증가해야 합니다.")
    return values.astype(np.int64, copy=False)


def _validate_curve_lengths(
    strain: np.ndarray,
    raw: np.ndarray,
    modeled: np.ndarray,
    source_rows: np.ndarray,
) -> None:
    length = strain.size
    if length == 0:
        raise ProcessingError("좌표 투영에 현재 모델 입력 행이 없습니다.")
    if raw.size != length or modeled.size != length or source_rows.size != length:
        raise ProcessingError("좌표 투영 입력 열의 행 수가 서로 다릅니다.")


def _validate_strain(strain: np.ndarray) -> None:
    if not np.all(np.isfinite(strain)):
        raise ProcessingError("좌표 투영 변형률에는 유한한 값만 허용됩니다.")
    if np.any(np.diff(strain) <= 0.0):
        raise ProcessingError("좌표 투영 변형률은 엄격히 증가해야 합니다.")
    if np.any(strain <= -1.0):
        raise ProcessingError("좌표 투영 변형률은 -1보다 커야 합니다.")


def _within_tolerance(actual: float, expected: float) -> bool:
    return bool(np.isclose(actual, expected, rtol=PROOF_TOLERANCE, atol=PROOF_TOLERANCE))


def _scalar_value(result: StepResult, key: str) -> float:
    for scalar in result.scalars:
        if scalar.key == key:
            return float(scalar.value)
    raise ProcessingError(f"core proof_stress 결과에 '{key}'가 없습니다.")


def _finite_number(options: dict[str, Any], name: str) -> float:
    value = options.get(name)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ProcessingError(f"좌표 투영 '{name}'은 유한한 실수여야 합니다.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"좌표 투영 '{name}'은 유한한 실수여야 합니다.") from None
    if not np.isfinite(result):
        raise ProcessingError(f"좌표 투영 '{name}'은 유한한 실수여야 합니다.")
    return result


def _optional_number(options: dict[str, Any], name: str) -> float | None:
    if name not in options or options[name] is None:
        return None
    return _finite_number(options, name)


def _numeric_column(frame: Frame, key: str, what: str) -> np.ndarray:
    try:
        raw = np.asarray(frame.require(key, what=what))
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 읽을 수 없습니다.") from None
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.number) or np.iscomplexobj(raw):
        raise ProcessingError(f"'{key}' {what} 열은 1차원 실수형 숫자여야 합니다.")
    try:
        return np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(f"'{key}' {what} 열을 실수형 숫자로 읽을 수 없습니다.") from None


def _column_name(options: dict[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProcessingError(
            f"좌표 투영 '{key}' 열 이름은 비어 있지 않은 문자열이어야 합니다."
        )
    return value


def _require_unit(frame: Frame, key: str, expected: str, what: str) -> None:
    actual = frame.units.get(key)
    if actual != expected:
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"좌표 투영 {what} 열 '{key}' 단위가 {expected!r}이 아닙니다: {shown}."
        )


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = sorted(set(options) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"coordinate_projected_v1이 지원하지 않는 옵션입니다: {names}.")


__all__ = [
    "METHOD_ALIASES",
    "METHOD_CHOICES",
    "coordinate_projected",
    "prepare_options",
]
