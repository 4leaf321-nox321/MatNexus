"""Validate source support through a peak without truncating the input frame.

``source_support_order_guard`` expects a prefix whose peak is its last row.
The versioned route may receive a frame with rows after the peak, so this
adapter validates peak evidence across the full input, delegates the
established proof-to-peak checks to a temporary prefix view, and returns the
original frame unchanged.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore.processing import Frame, ProcessingError, StepResult

from . import source_peak_evidence, source_support_order_guard

DEFAULT_FORCE = source_peak_evidence.DEFAULT_FORCE
DEFAULT_STRAIN = source_peak_evidence.DEFAULT_STRAIN
DEFAULT_STRESS = source_peak_evidence.DEFAULT_STRESS
OPTION_KEYS = frozenset(
    {
        "proof_left_index",
        "proof_right_index",
        "proof_strain",
        "force",
        "strain",
        "stress",
    }
)


def prepare_options(options: dict[str, Any]) -> dict[str, Any]:
    """Keep only proof boundaries and source engineering-column choices."""

    prepared = dict(options)
    unknown = sorted(set(prepared) - OPTION_KEYS, key=str)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ProcessingError(
            f"원행 full support 순서 guard에 알 수 없는 옵션이 있습니다: {names}."
        )
    prepared.setdefault("proof_left_index", "@source_proof_left_index")
    prepared.setdefault("proof_right_index", "@source_proof_right_index")
    prepared.setdefault("proof_strain", "@proof_strain")
    prepared.setdefault("force", DEFAULT_FORCE)
    prepared.setdefault("strain", DEFAULT_STRAIN)
    prepared.setdefault("stress", DEFAULT_STRESS)
    return prepared


def source_support_order_full(frame: Frame, options: dict[str, Any]) -> StepResult:
    """Check full-frame evidence and proof-to-peak support, returning *frame*."""

    options = prepare_options(options)
    force_name = source_peak_evidence._column_name(options, "force", DEFAULT_FORCE)
    strain_name = source_peak_evidence._column_name(options, "strain", DEFAULT_STRAIN)
    stress_name = source_peak_evidence._column_name(options, "stress", DEFAULT_STRESS)

    # Peak evidence is recomputed from the complete input frame.  Caller
    # supplied peak/status scalars are deliberately not accepted or trusted.
    peak_result = source_peak_evidence.source_peak_evidence(
        frame,
        {"force": force_name, "strain": strain_name, "stress": stress_name},
    )
    peak_values = {scalar.key: scalar.value for scalar in peak_result.scalars}
    peak = source_support_order_guard._row_index(
        peak_values["source_peak_index"], "source_peak_index"
    )
    peak_strain = peak_values["source_peak_strain"]
    order_code = peak_values["source_peak_order_evidence_code"]
    force_code = peak_values["source_peak_force_peak_match_code"]
    strain = source_peak_evidence._numeric_column(frame, strain_name, "변형률")

    # The established guard requires its peak to be the final row.  A selected
    # prefix is only a read-only working view; no column from the input frame
    # is replaced or shortened in the returned result.
    prefix = frame.select(np.arange(peak + 1, dtype=np.intp))
    delegated_options = {
        "proof_left_index": options["proof_left_index"],
        "proof_right_index": options["proof_right_index"],
        "proof_strain": options["proof_strain"],
        "peak_index": peak,
        "peak_strain": peak_strain,
        "order_evidence_code": order_code,
        "force_peak_match_code": force_code,
        "strain": strain_name,
    }
    delegated = source_support_order_guard.source_support_order_guard(
        prefix, delegated_options
    )
    evidence_columns = source_support_order_guard._evidence_columns(frame, strain.size)
    assert evidence_columns
    notes = (
        f"현재 입력 원행 전체 {strain.size}개에서 {', '.join(evidence_columns)} "
        "취득 순서 증거를 검증했습니다.",
        "원하중·공칭응력 peak와 양의 비례 관계를 전체 입력에서 다시 검증했습니다.",
        "proof부터 source peak까지는 peak 앞 원행 prefix view로 기존 support 순서 "
        "guard를 적용했으며, peak 뒤 입력 행은 결과 frame에 그대로 보존했습니다.",
        *delegated.notes,
    )
    return StepResult(
        frame,
        notes=notes,
        scalars=delegated.scalars,
        effective_options=options,
    )
