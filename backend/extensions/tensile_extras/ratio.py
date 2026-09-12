"""항복비 — 앞 단계가 낸 두 값의 비."""

from __future__ import annotations

import math
from typing import Any

from matcore.processing import Frame, Scalar, StepResult


def yield_ratio(frame: Frame, options: dict[str, Any]) -> StepResult:
    """항복강도 ÷ 인장강도. **값을 못 내면 실패하지 않고 이유를 남긴다** — 내장 단계와
    같은 규율이다. 뒤 단계가 이 값을 가리키면 그 이유가 오류 문구에 실린다."""
    proof = options.get("proof_stress")
    tensile = options.get("tensile_strength")
    numbers = all(
        isinstance(one, int | float) and math.isfinite(float(one)) for one in (proof, tensile)
    )
    if not numbers:
        return StepResult(
            frame=frame,
            notes=("항복강도나 인장강도가 없어 항복비를 내지 않았습니다.",),
        )
    if float(tensile) <= 0.0:
        return StepResult(
            frame=frame,
            notes=(f"인장강도가 0 이하({float(tensile):.4g} Pa)라 항복비를 내지 않았습니다.",),
        )
    ratio = float(proof) / float(tensile)
    return StepResult(
        frame=frame,
        scalars=(Scalar("yield_ratio", "항복비", ratio, "1"),),
        notes=(
            f"항복비 {ratio:.3f} = {float(proof) / 1e6:.4g} MPa ÷ "
            f"{float(tensile) / 1e6:.4g} MPa.",
        ),
    )
