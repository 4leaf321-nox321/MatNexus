"""Build a bounded engineering domain for paired-proof true-plastic conversion."""

from __future__ import annotations

from numbers import Real
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_text

DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"
OPTION_KEYS = frozenset(
    {"proof_strain", "proof_stress", "end_strain", "necking_limit", "strain", "stress"}
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Pair the model proof point and necking bound unless the recipe overrides them."""
    prepared = dict(options)
    prepared.setdefault("proof_strain", "@model_proof_strain")
    prepared.setdefault("proof_stress", "@model_proof_stress")
    prepared.setdefault("end_strain", "@necking_candidate_strain")
    prepared.setdefault("necking_limit", "@necking_candidate_strain")
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    return prepared


def _number(options: dict[str, Any], key: str) -> float:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ProcessingError(f"'{key}' 는 유한한 실수여야 합니다.")
    result = float(value)
    if not np.isfinite(result):
        raise ProcessingError(f"'{key}' 는 유한한 실수여야 합니다.")
    return result


def _arrays(frame: Frame) -> tuple[int, dict[str, np.ndarray]]:
    if not frame.columns:
        raise ProcessingError("소성 구간을 고를 곡선 열이 없습니다.")
    columns: dict[str, np.ndarray] = {}
    expected_length: int | None = None
    for name, raw in frame.columns.items():
        try:
            values = np.asarray(raw)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"프레임 열 '{name}' 을 숫자 열로 읽을 수 없습니다."
            ) from None
        if values.ndim != 1:
            raise ProcessingError(f"프레임 열 '{name}' 은 1차원이어야 합니다.")
        if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
            raise ProcessingError(f"프레임 열 '{name}' 은 실수형 숫자여야 합니다.")
        if expected_length is None:
            expected_length = len(values)
        elif len(values) != expected_length:
            raise ProcessingError(
                f"프레임 열 '{name}' 의 점 수가 맞지 않습니다: {len(values)}점, "
                f"기준 {expected_length}점."
            )
        try:
            numeric = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            raise ProcessingError(
                f"프레임 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
            ) from None
        if not np.all(np.isfinite(numeric)):
            raise ProcessingError(f"프레임 열 '{name}' 에 유한하지 않은 값이 있습니다.")
        columns[name] = numeric
    assert expected_length is not None
    if expected_length < 2:
        raise ProcessingError("소성 구간을 고르려면 입력 곡선에 2점 이상 있어야 합니다.")
    return expected_length, columns


def _interpolated_row(
    arrays: dict[str, np.ndarray], x: np.ndarray, target: float, exact_index: int | None
) -> dict[str, float]:
    if exact_index is not None:
        return {name: float(values[exact_index]) for name, values in arrays.items()}

    right = int(np.searchsorted(x, target, side="right"))
    left = right - 1
    if left < 0 or right >= len(x):
        raise ProcessingError(
            f"경계 변형률 {target:.12g} 을 현재 입력 관측행 사이에서 보간할 수 없습니다."
        )
    fraction = (target - x[left]) / (x[right] - x[left])
    if not np.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ProcessingError(
            f"경계 변형률 {target:.12g} 을 현재 입력 관측행 사이에서 보간할 수 없습니다."
        )
    row = {
        name: float((1.0 - fraction) * values[left] + fraction * values[right])
        for name, values in arrays.items()
    }
    if not all(np.isfinite(value) for value in row.values()):
        raise ProcessingError(f"경계 변형률 {target:.12g} 의 보간 결과가 유한하지 않습니다.")
    return row


def plastic_domain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Retain observed rows and add only missing paired-proof/end boundary rows."""
    unknown = sorted(set(options) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"지원하지 않는 소성 구간 옵션입니다: {names}.")

    strain_name = option_text(options, "strain", ())
    stress_name = option_text(options, "stress", ())
    if strain_name == stress_name:
        raise ProcessingError("변형률 열과 응력 열은 서로 달라야 합니다.")
    frame.require(strain_name, what="변형률")
    frame.require(stress_name, what="응력")
    if frame.units.get(strain_name) != "1":
        actual = frame.units.get(strain_name)
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"변형률 열 '{strain_name}' 의 단위는 '1' 이어야 합니다. 현재 단위: {shown}."
        )
    if frame.units.get(stress_name) != "Pa":
        actual = frame.units.get(stress_name)
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"응력 열 '{stress_name}' 의 단위는 'Pa' 이어야 합니다. 현재 단위: {shown}."
        )

    n, arrays = _arrays(frame)
    x = arrays[strain_name]
    if not np.all(x[1:] > x[:-1]):
        raise ProcessingError(
            f"변형률 열 '{strain_name}' 이 현재 입력 행 순서에서 엄격히 증가하지 않습니다. "
            "행을 자동 정렬하지 않았습니다."
        )

    proof_strain = _number(options, "proof_strain")
    proof_stress = _number(options, "proof_stress")
    end_strain = _number(options, "end_strain")
    necking_limit = _number(options, "necking_limit")
    if proof_stress <= 0.0:
        raise ProcessingError(f"모델 proof 응력은 양수여야 합니다: {proof_stress:.12g} Pa.")
    if not (x[0] <= proof_strain < end_strain <= x[-1]):
        raise ProcessingError(
            "모델 구간은 현재 입력 변형률 범위 안이어야 하며 proof_strain < end_strain 이어야 "
            f"합니다: 입력 [{x[0]:.12g}, {x[-1]:.12g}], 요청 "
            f"[{proof_strain:.12g}, {end_strain:.12g}]. 외삽하지 않았습니다."
        )
    if end_strain > necking_limit:
        raise ProcessingError(
            f"end_strain {end_strain:.12g} 이 necking_limit {necking_limit:.12g} 보다 큽니다."
        )

    support = np.flatnonzero((x > proof_strain) & (x <= end_strain))
    if len(support) < 2:
        raise ProcessingError(
            "현재 입력 프레임에서 proof_strain < 변형률 <= end_strain 인 관측 모델행이 "
            f"{len(support)}개뿐입니다. 경계점을 추가하기 전에 최소 2개가 필요합니다."
        )

    proof_index: int | None = int(np.searchsorted(x, proof_strain, side="left"))
    if proof_index == n or x[proof_index] != proof_strain:
        proof_index = None
    end_index: int | None = int(np.searchsorted(x, end_strain, side="left"))
    if end_index == n or x[end_index] != end_strain:
        end_index = None

    proof_row = _interpolated_row(arrays, x, proof_strain, proof_index)
    measured_proof_stress = proof_row[stress_name]
    if not np.isclose(measured_proof_stress, proof_stress, rtol=1e-9, atol=1.0):
        raise ProcessingError(
            f"model_proof_stress {proof_stress:.12g} Pa 는 proof_strain "
            f"{proof_strain:.12g} 의 현재 입력 보간 응력 {measured_proof_stress:.12g} Pa 와 "
            "일치하지 않습니다 (rtol=1e-9, atol=1 Pa)."
        )
    end_row = _interpolated_row(arrays, x, end_strain, end_index)

    interior = np.flatnonzero((x > proof_strain) & (x < end_strain))
    inserted_proof = proof_index is None
    inserted_end = end_index is None
    if inserted_proof or inserted_end:
        output: dict[str, np.ndarray] = {}
        for name, values in arrays.items():
            joined = np.concatenate(
                (
                    np.asarray([proof_row[name]], dtype=np.float64),
                    values[interior],
                    np.asarray([end_row[name]], dtype=np.float64),
                )
            )
            output[name] = joined
        output[strain_name][0] = proof_strain
        output[strain_name][-1] = end_strain
    else:
        indices = np.concatenate(
            (
                np.asarray([proof_index], dtype=np.intp),
                interior,
                np.asarray([end_index], dtype=np.intp),
            )
        )
        selected = frame.select(indices)
        output = dict(selected.columns)
        if output[stress_name][0] != proof_stress:
            # Use the paired model proof value after validating the observed endpoint.
            output[stress_name] = output[stress_name].astype(np.float64, copy=True)
            output[stress_name][0] = proof_stress

    output[stress_name][0] = proof_stress
    selected = Frame(output, dict(frame.units))
    output_x = np.asarray(output[strain_name], dtype=np.float64)
    output_stress = np.asarray(output[stress_name], dtype=np.float64)
    if np.any(output_x <= -1.0):
        raise ProcessingError(
            "선택한 모델 구간에 변형률 -1 이하가 있어 true-plastic 로그 변환을 할 수 없습니다."
        )
    if np.any(output_stress < 0.0):
        raise ProcessingError("선택한 모델 구간에 음의 공칭응력이 있습니다.")

    inserted_count = int(inserted_proof) + int(inserted_end)
    scalars = (
        Scalar("plastic_domain_input_points", "입력 관측점 수", float(n), "1"),
        Scalar(
            "plastic_domain_support_points", "입력 모델 관측점 수", float(len(support)), "1"
        ),
        Scalar("plastic_domain_output_points", "출력 구간 점 수", float(len(output_x)), "1"),
        Scalar("plastic_domain_inserted_points", "삽입 경계점 수", float(inserted_count), "1"),
        Scalar(
            "plastic_domain_proof_inserted", "proof 경계 삽입 여부", float(inserted_proof), "1"
        ),
        Scalar("plastic_domain_end_inserted", "끝 경계 삽입 여부", float(inserted_end), "1"),
        Scalar(
            "plastic_domain_proof_strain", "모델 proof 변형률", proof_strain, "1", "strain"
        ),
        Scalar("plastic_domain_proof_stress", "모델 proof 응력", proof_stress, "Pa"),
        Scalar("plastic_domain_end_strain", "소성 구간 끝 변형률", end_strain, "1", "strain"),
        Scalar(
            "plastic_domain_necking_limit", "네킹 상한 변형률", necking_limit, "1", "strain"
        ),
    )
    if not all(np.isfinite(scalar.value) for scalar in scalars):
        raise ProcessingError("소성 구간 진단값이 유한하지 않습니다.")

    notes = [
        (
            f"현재 입력 {n}개 관측점 중 {len(support)}개를 proof 뒤, 끝 경계까지의 "
            "지원점으로 사용했습니다."
        ),
        (
            f"proof/end 경계 삽입 여부 {int(inserted_proof)}/{int(inserted_end)}; "
            f"출력 {len(output_x)}점."
        ),
        (
            "proof 경계 응력은 관측 보간값과 허용오차 내에서 확인한 뒤 짝지은 "
            "model_proof_stress를 사용합니다."
        ),
        (
            "빠진 경계만 모든 숫자 열에서 선형 보간했습니다. 삽입점의 행 식별자는 "
            "파생값이며 원래 취득행으로 보지 않습니다."
        ),
    ]
    effective_options = {
        "proof_strain": proof_strain,
        "proof_stress": proof_stress,
        "end_strain": end_strain,
        "necking_limit": necking_limit,
        "strain": strain_name,
        "stress": stress_name,
    }
    return StepResult(
        frame=selected,
        notes=tuple(notes),
        scalars=scalars,
        effective_options=effective_options,
    )
