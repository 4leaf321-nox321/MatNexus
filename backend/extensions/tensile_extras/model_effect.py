"""Observed extent of a model edit, separate from measured material properties."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from matcore.processing import Scalar


def effect_scalars(
    strain: NDArray[np.float64],
    source: NDArray[np.float64],
    modeled: NDArray[np.float64],
    *,
    supports: Sequence[tuple[int, int]] = (),
    selected_end: int | None = None,
) -> tuple[Scalar, ...]:
    """Include selected support and closure of every actually changed region.

    A fallback closure is the next observed row after the last change. It is
    deliberately not called an internal regression anchor: legacy steps do not
    expose their fitting intervals as typed data. Declared extension supports
    take precedence when they extend farther. This function changes no array.
    """
    changed = np.flatnonzero(modeled != source)
    last_changed = int(changed[-1]) if changed.size else -1
    closure = min(last_changed + 1, len(source) - 1) if changed.size else -1
    declared = [
        end
        for start, end in supports
        if np.any(modeled[start : end + 1] != source[start : end + 1])
    ]
    if selected_end is not None:
        declared.append(selected_end)
    effect_end = max([closure, *declared])
    support_kind = 2 if declared else 1 if changed.size else 0
    values = (
        ("model_card_input_points", "모델 단계 입력 관측점 수", float(len(source)), None),
        ("model_card_changed_points", "모델 단계 변경 관측점 수", float(changed.size), None),
        ("model_card_last_changed_index", "마지막 변경 모델 행", float(last_changed), None),
        ("model_card_effect_end_index", "카드용 모델 영향 끝 관측행", float(effect_end), None),
        (
            "model_card_effect_end_strain",
            "카드용 모델 영향 끝 공칭 변형률 (영향 없음은 0)",
            float(strain[effect_end]) if effect_end >= 0 else 0.0,
            "strain",
        ),
        (
            "model_card_support_kind",
            "모델 지지 종류 (0 없음, 1 변경곡선 접합, 2 선언 지지 포함)",
            float(support_kind),
            None,
        ),
    )
    return tuple(
        Scalar(key, label, value, "1", dimension) for key, label, value, dimension in values
    )
