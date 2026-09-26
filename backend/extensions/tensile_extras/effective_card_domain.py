"""Choose a bounded engineering domain for a saved plastic-card recipe."""

from __future__ import annotations

from numbers import Real
from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_text

from .plastic_domain import plastic_domain

DEFAULT_STRAIN = "strain_engineering"
DEFAULT_STRESS = "stress_engineering"

UNIFORM_MEASURED_POLICY = "uniform_measured_v1"
EFFECTIVE_MODEL_POLICY = "effective_engineering_model_auto_v1"
MANUAL_POLICY = "manual_observed_end_v1"
POLICIES = (UNIFORM_MEASURED_POLICY, EFFECTIVE_MODEL_POLICY, MANUAL_POLICY)
DEFAULT_POLICY = UNIFORM_MEASURED_POLICY

COORDINATE_ASSUMPTION = "effective_engineering_to_true_uniform_v1"

EFFECT_OPTIONS = ("effect_end_index", "effect_end_strain", "model_input_points")
OPTION_KEYS = frozenset(
    {
        "policy",
        "coordinate_assumption",
        "proof_strain",
        "proof_stress",
        "source_necking_strain",
        *EFFECT_OPTIONS,
        "end_index",
        "strain",
        "stress",
    }
)


def _reject_unknown(options: dict[str, Any]) -> None:
    unknown = sorted(set(options) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(f"지원하지 않는 유효 카드 구간 옵션입니다: {names}.")


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Add paired model references and effect metadata for effect-based modes."""
    prepared = dict(options)
    policy = prepared.get("policy", DEFAULT_POLICY)
    prepared.setdefault("policy", DEFAULT_POLICY)
    prepared.setdefault("coordinate_assumption", COORDINATE_ASSUMPTION)
    prepared.setdefault("proof_strain", "@model_proof_strain")
    prepared.setdefault("proof_stress", "@model_proof_stress")
    prepared.setdefault("source_necking_strain", "@necking_candidate_strain")
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)

    supplied_effect_options = sum(name in prepared for name in EFFECT_OPTIONS)
    if policy in (EFFECTIVE_MODEL_POLICY, MANUAL_POLICY) and supplied_effect_options == 0:
        prepared.update(
            {
                "effect_end_index": "@model_card_effect_end_index",
                "effect_end_strain": "@model_card_effect_end_strain",
                "model_input_points": "@model_card_input_points",
            }
        )
    _reject_unknown(prepared)
    return prepared


def _number(options: dict[str, Any], name: str) -> float:
    value = options.get(name)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.") from None
    if not np.isfinite(result):
        raise ProcessingError(f"'{name}' 는 유한한 실수여야 합니다.")
    return result


def _integer(options: dict[str, Any], name: str) -> int:
    value = _number(options, name)
    if not value.is_integer():
        raise ProcessingError(f"'{name}' 는 정수여야 합니다.")
    return int(value)


def _strain_values(frame: Frame, name: str) -> np.ndarray:
    raw = frame.require(name, what="변형률")
    if frame.units.get(name) != "1":
        actual = frame.units.get(name)
        shown = "누락" if actual is None else repr(actual)
        raise ProcessingError(
            f"변형률 열 '{name}' 의 단위는 '1' 이어야 합니다. 현재 단위: {shown}."
        )
    try:
        values = np.asarray(raw)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"변형률 열 '{name}' 은 실수형 숫자 배열이어야 합니다."
        ) from None
    if values.ndim != 1:
        raise ProcessingError(f"변형률 열 '{name}' 은 1차원이어야 합니다.")
    if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
        raise ProcessingError(f"변형률 열 '{name}' 은 실수형 숫자여야 합니다.")
    try:
        numeric = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        raise ProcessingError(
            f"변형률 열 '{name}' 을 실수형 숫자로 읽을 수 없습니다."
        ) from None
    if len(numeric) < 2:
        raise ProcessingError("소성 구간을 고르려면 입력 곡선에 2점 이상 있어야 합니다.")
    if not np.all(np.isfinite(numeric)):
        raise ProcessingError(f"변형률 열 '{name}' 에 유한하지 않은 값이 있습니다.")
    if not np.all(numeric[1:] > numeric[:-1]):
        raise ProcessingError(
            f"변형률 열 '{name}' 이 현재 입력 행 순서에서 엄격히 증가하지 않습니다. "
            "행을 자동 정렬하지 않았습니다."
        )
    return numeric


def _effect_metadata(
    options: dict[str, Any], strain: np.ndarray
) -> tuple[int, float, int] | None:
    supplied = [name in options for name in EFFECT_OPTIONS]
    if not any(supplied):
        return None
    if not all(supplied):
        raise ProcessingError("모델 영향 메타데이터 세 항목을 함께 지정해야 합니다.")

    effect_index = _integer(options, "effect_end_index")
    effect_strain = _number(options, "effect_end_strain")
    input_points = _integer(options, "model_input_points")
    if input_points != len(strain):
        raise ProcessingError(
            "model_input_points 가 현재 모델 입력 행 수와 다릅니다: "
            f"{input_points} 대 {len(strain)}."
        )
    if effect_index == -1:
        if effect_strain != 0.0:
            raise ProcessingError(
                "effect_end_index -1 no-effect 표식에는 effect_end_strain 0 이 필요합니다."
            )
    elif not 0 <= effect_index < len(strain):
        raise ProcessingError(
            f"effect_end_index {effect_index} 는 현재 모델 입력 프레임 범위 밖입니다."
        )
    elif effect_strain != float(strain[effect_index]):
        raise ProcessingError(
            "effect_end_strain 이 현재 모델 입력의 effect_end_index 관측 변형률과 "
            "일치하지 않습니다."
        )
    return effect_index, effect_strain, input_points


def effective_card_domain(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Select a replayable card end while retaining the source neck separately."""
    _reject_unknown(options)
    policy = option_text(options, "policy", POLICIES)
    coordinate_assumption = option_text(
        options, "coordinate_assumption", (COORDINATE_ASSUMPTION,)
    )
    strain_name = option_text(options, "strain", ())
    stress_name = option_text(options, "stress", ())
    if strain_name == stress_name:
        raise ProcessingError("변형률 열과 응력 열은 서로 달라야 합니다.")

    strain = _strain_values(frame, strain_name)
    proof_strain = _number(options, "proof_strain")
    proof_stress = _number(options, "proof_stress")
    source_necking_strain = _number(options, "source_necking_strain")
    if not strain[0] <= source_necking_strain <= strain[-1]:
        raise ProcessingError(
            "source_necking_strain 은 현재 모델 입력 변형률 범위 안이어야 하며 "
            "자동으로 자르지 않습니다: "
            f"입력 [{strain[0]:.12g}, {strain[-1]:.12g}], "
            f"요청 {source_necking_strain:.12g}."
        )

    effect = _effect_metadata(options, strain)
    if policy in (EFFECTIVE_MODEL_POLICY, MANUAL_POLICY) and effect is None:
        raise ProcessingError("이 정책에는 완전한 모델 영향 메타데이터 세 항목이 필요합니다.")

    if policy == MANUAL_POLICY:
        if "end_index" not in options:
            raise ProcessingError("manual_observed_end_v1 에는 end_index 가 필요합니다.")
        end_index = _integer(options, "end_index")
        if not 0 <= end_index < len(strain):
            raise ProcessingError(
                f"end_index {end_index} 는 현재 모델 입력 프레임 범위 밖입니다."
            )
        end_strain = float(strain[end_index])
        if end_strain <= proof_strain:
            raise ProcessingError("수동 end_index 는 모델 proof 변형률 뒤에 있어야 합니다.")
    else:
        if "end_index" in options:
            raise ProcessingError("end_index 는 manual_observed_end_v1 에서만 쓸 수 있습니다.")
        if policy == EFFECTIVE_MODEL_POLICY and effect is not None and effect[0] >= 0:
            end_strain = max(source_necking_strain, effect[1])
        else:
            # The default policy is exactly the previous source-necking boundary.
            end_strain = source_necking_strain
        end_index = -1

    delegate_options = {
        "proof_strain": proof_strain,
        "proof_stress": proof_stress,
        "end_strain": end_strain,
        "necking_limit": end_strain,
        "strain": strain_name,
        "stress": stress_name,
    }
    result = plastic_domain(frame, delegate_options)

    if end_index < 0:
        observed_end = int(np.searchsorted(strain, end_strain, side="left"))
        if observed_end == len(strain) or strain[observed_end] != end_strain:
            observed_end = -1
        end_index = observed_end

    effect_index = -1 if effect is None else effect[0]
    effect_strain = 0.0 if effect is None else effect[1]
    effect_info_known = effect is not None
    effect_truncated = bool(
        effect_info_known and effect_index >= 0 and end_strain < effect_strain
    )
    deliberate_effect_truncation = bool(effect_truncated and policy == MANUAL_POLICY)
    end_stress = float(result.frame.columns[stress_name][-1])
    input_points = len(strain)
    scalars = (
        Scalar(
            "card_domain_source_necking_strain",
            "원자료 네킹 후보 변형률 (카드 끝과 별도 보존)",
            source_necking_strain,
            "1",
            "strain",
        ),
        Scalar(
            "card_domain_end_index",
            "카드 끝 관측 모델 행 (보간 경계는 -1)",
            float(end_index),
            "1",
        ),
        Scalar("card_domain_end_strain", "카드 끝 공학 변형률", end_strain, "1", "strain"),
        Scalar("card_domain_end_stress", "카드 끝 공학 응력", end_stress, "Pa"),
        Scalar(
            "card_domain_effect_end_index",
            "모델 영향 끝 관측 모델 행 (없음은 -1)",
            float(effect_index),
            "1",
        ),
        Scalar(
            "card_domain_effect_end_strain",
            "모델 영향 끝 공학 변형률 (없음은 0)",
            effect_strain,
            "1",
            "strain",
        ),
        Scalar(
            "card_domain_effect_info_known",
            "모델 영향 메타데이터 제공 여부",
            float(effect_info_known),
            "1",
        ),
        Scalar(
            "card_domain_beyond_source_neck",
            "카드 끝이 원자료 네킹 후보 뒤인지 여부",
            float(end_strain > source_necking_strain),
            "1",
        ),
        Scalar(
            "card_domain_effect_truncated",
            "카드 끝이 모델 영향 지지 끝보다 앞인지 여부",
            float(effect_truncated),
            "1",
        ),
        Scalar(
            "card_domain_effect_truncation_deliberate",
            "수동 선택으로 모델 영향이 실제 잘렸는지 여부",
            float(deliberate_effect_truncation),
            "1",
        ),
        Scalar(
            "card_domain_model_input_points",
            "모델 단계 입력 관측점 수",
            float(input_points),
            "1",
        ),
        Scalar(
            "card_domain_last_input_strain",
            "마지막으로 남은 모델 입력 변형률",
            float(strain[-1]),
            "1",
            "strain",
        ),
    )

    notes = list(result.notes)
    notes.append(
        f"원자료 네킹 후보 변형률 {source_necking_strain:.12g} 는 별도로 보존했습니다. "
        f"카드 계산 경계 {end_strain:.12g} 는 입력 프레임 행 위치 {end_index} 이며, "
        "계산용 necking_limit 은 이 카드 경계입니다."
    )
    if end_strain > source_necking_strain:
        notes.append(
            "원자료 네킹 후보 뒤의 유효 공학 변형률을 진변형률로 옮기는 것은 "
            "저장한 simulation approximation 입니다. 측정된 국부 응력이나 "
            "완전소성 일정 진응력을 뜻하지 않습니다."
        )
    if effect_truncated:
        intent = "수동 끝 행에서 의도적으로" if deliberate_effect_truncation else ""
        notes.append(
            f"{intent}모델 영향 지지 끝 {effect_strain:.12g} 전에 카드 구간이 끝납니다."
        )
    if effect is None:
        notes.append(
            "모델 영향 메타데이터가 제공되지 않았습니다. 모델 영향 지지의 포함 여부를 "
            "이 단계에서 확인할 수 없습니다."
        )
    if end_index < 0:
        notes.append(
            "카드 끝은 입력 관측행 사이의 보간 경계입니다. 그 경계에 취득행 식별자를 "
            "부여하지 않았습니다."
        )

    effective_options = {
        "policy": policy,
        "coordinate_assumption": coordinate_assumption,
        "proof_strain": proof_strain,
        "proof_stress": proof_stress,
        "source_necking_strain": source_necking_strain,
        "strain": strain_name,
        "stress": stress_name,
    }
    if effect is not None:
        effective_options.update(
            {
                "effect_end_index": effect_index,
                "effect_end_strain": effect_strain,
                "model_input_points": input_points,
            }
        )
    if policy == MANUAL_POLICY:
        effective_options["end_index"] = int(options["end_index"])

    delegated_scalars = tuple(
        Scalar(
            scalar.key,
            "카드 계산 상한 변형률",
            scalar.value,
            scalar.si_unit,
            scalar.dimension,
        )
        if scalar.key == "plastic_domain_necking_limit"
        else scalar
        for scalar in result.scalars
    )

    return StepResult(
        frame=result.frame,
        notes=tuple(notes),
        scalars=(*delegated_scalars, *scalars),
        effective_options=effective_options,
    )
