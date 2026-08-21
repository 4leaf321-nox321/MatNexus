"""시험 종류를 가리지 않는 처리 — 정렬·자르기·재샘플·평활.

여기 있는 것은 전부 **인장에도 DMA 에도 쓰인다.** 시험별 계산(`tensile.py`)과
나누는 이유는 물성이 늘 때 무엇을 새로 짜야 하는지가 분명해야 하기 때문이다 —
새 물성 하나가 파일 2~3개로 끝나야 한다(D7).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore import ParamSpec, register
from matcore.processing import (
    Frame,
    ProcessingError,
    StepResult,
    option_float,
    option_int,
    option_text,
    require_increasing,
)


@register(
    id="curve.sort_unique",
    kind="processing",
    label="정렬·중복 정리",
    params=(
        ParamSpec(
            name="x",
            label="기준 열",
            type="str",
            role="column",
            help="이 열을 기준으로 오름차순 정렬합니다.",
        ),
        ParamSpec(
            name="duplicate_policy",
            label="같은 x 가 여럿일 때",
            type="choice",
            default="mean",
            choices=("mean", "first", "last", "reject"),
            choice_labels={
                "mean": "평균으로 합침",
                "first": "첫 점만 남김",
                "last": "마지막 점만 남김",
                "reject": "거절 (직접 정리)",
            },
            help=(
                "장비는 같은 값을 두 번 적기도 하고(샘플링) 되돌아오기도 합니다(제하). "
                "진소성변형률을 0 으로 자른 뒤라면 '마지막 점만 남김'을 쓰세요 — "
                "그 마지막이 항복점입니다."
            ),
        ),
    ),
    order=20,
    version="1",
)
def sort_unique(frame: Frame, options: dict[str, Any]) -> StepResult:
    """기준 열로 정렬하고 중복 x 를 정리한다.

    **거의 모든 계산이 이것을 전제한다.** `np.interp` 도 교점 탐색도 정렬을
    확인하지 않고, 정렬이 깨진 입력에 오류 없이 엉뚱한 값을 낸다. 장비 파일은
    같은 변형률을 두 번 적기도 하고(샘플링), 되돌아오기도 한다(제하).

    중복을 어떻게 다룰지는 **사람이 정한다.** 조용히 평균 내면 제하 구간이
    있는 곡선이 이상한 모양으로 뭉개지고, 조용히 첫 점만 남기면 잡음이 그대로
    남는다. 어느 쪽도 기본으로 옳지 않아서 물어본다.

    `last` 는 **진소성변형률 축에서 필요해졌다.** `tensile.true_plastic` 의
    `clip_zero` 가 탄성 구간을 전부 x=0 에 쌓아 두는데(실측 120점 중 34점),
    그 상태로는 이 축에서 재샘플을 못 해 앙상블이 안 나온다. 쌓인 것 중
    **마지막이 항복점**이다 — 평균을 내면 탄성 구간 응력이 섞여 항복강도가
    낮아지고, 첫 점을 남기면 0 에 가까운 응력을 항복강도로 쓰게 된다.
    """
    x_key = str(options.get("x") or "")
    if not x_key:
        raise ProcessingError("기준 열('x')을 골라야 합니다.")
    policy = option_text(options, "duplicate_policy", ("mean", "first", "last", "reject"))
    x = frame.require(x_key, what="기준 열")

    order = np.argsort(x, kind="stable")
    ordered = frame.select(order)
    x = ordered.columns[x_key]

    unique, starts, counts = np.unique(x, return_index=True, return_counts=True)
    duplicates = int(np.sum(counts - 1))
    if duplicates == 0:
        return StepResult(ordered, notes=(f"'{x_key}' 기준으로 정렬했습니다.",))

    if policy == "reject":
        raise ProcessingError(
            f"'{x_key}' 에 같은 값이 {duplicates}개 있습니다. "
            f"평균·첫 점 중 어떻게 정리할지 고르거나, 앞에서 구간을 잘라내세요."
        )
    if policy == "first":
        return StepResult(
            ordered.select(starts),
            notes=(f"'{x_key}' 정렬 후 중복 {duplicates}점을 첫 값으로 정리했습니다.",),
        )
    if policy == "last":
        return StepResult(
            ordered.select(starts + counts - 1),
            notes=(f"'{x_key}' 정렬 후 중복 {duplicates}점을 마지막 값으로 정리했습니다.",),
        )

    averaged = {
        key: np.asarray(
            [
                float(np.mean(value[start : start + count]))
                for start, count in zip(starts, counts, strict=True)
            ],
            dtype=np.float64,
        )
        for key, value in ordered.columns.items()
    }
    averaged[x_key] = unique.astype(np.float64)
    return StepResult(
        Frame(averaged, dict(ordered.units)),
        notes=(f"'{x_key}' 정렬 후 중복 {duplicates}점을 평균으로 정리했습니다.",),
    )


@register(
    id="curve.crop",
    kind="processing",
    label="구간 자르기",
    params=(
        ParamSpec(name="x", label="기준 열", type="str", role="column"),
        ParamSpec(name="start", label="시작", type="float", help="이 값 미만을 버립니다."),
        ParamSpec(name="end", label="끝", type="float", help="이 값 초과를 버립니다."),
    ),
    order=40,
    version="1",
)
def crop(frame: Frame, options: dict[str, Any]) -> StepResult:
    """기준 열의 [start, end] 밖을 버린다.

    **자른 점 수를 남긴다.** 얼마나 버렸는지가 기록에 없으면, 나중에 곡선이 짧은
    것을 보고 장비가 그렇게 준 것인지 사람이 자른 것인지 알 수 없다.
    """
    x_key = str(options.get("x") or "")
    if not x_key:
        raise ProcessingError("기준 열('x')을 골라야 합니다.")
    x = frame.require(x_key, what="기준 열")
    start = option_float(options, "start", float(np.min(x)))
    end = option_float(options, "end", float(np.max(x)))
    if start >= end:
        raise ProcessingError(f"시작({start})이 끝({end}) 이상입니다.")

    mask = (x >= start) & (x <= end)
    kept = int(np.sum(mask))
    if kept < 2:
        raise ProcessingError(
            f"[{start}, {end}] 안에 {kept}점만 남습니다. 구간을 넓히세요 — "
            f"'{x_key}' 의 실제 범위는 "
            f"[{float(np.min(x)):.6g}, {float(np.max(x)):.6g}] 입니다."
        )
    return StepResult(
        frame.select(mask),
        notes=(f"'{x_key}' [{start:.6g}, {end:.6g}] 밖 {len(x) - kept}점을 잘랐습니다.",),
    )


@register(
    id="curve.resample",
    kind="processing",
    label="균등 격자로 재샘플",
    params=(
        ParamSpec(name="x", label="기준 열", type="str", role="column"),
        ParamSpec(name="count", label="점 수", type="int", default=200),
        ParamSpec(name="start", label="시작", type="float", help="비우면 관측 최솟값"),
        ParamSpec(name="end", label="끝", type="float", help="비우면 관측 최댓값"),
    ),
    # **재샘플은 맨 뒤다.** 앞에 두면 탄성계수·항복강도가 전부 보간된 점으로
    # 계산된다 — 잰 점이 아니라 우리가 만들어 낸 점이다.
    order=95,
    version="1",
)
def resample(frame: Frame, options: dict[str, Any]) -> StepResult:
    """균등 격자 위로 선형 보간한다.

    **여러 시편을 평균 내려면 x 가 같아야 한다.** 장비는 시편마다 다른 점에서
    샘플링하므로, 앙상블 통계(Phase 3 뒤쪽)는 이 단계를 반드시 거친다.

    **외삽하지 않는다.** 요청 구간이 관측 범위를 벗어나면 거절한다 — `np.interp`
    는 범위 밖에서 끝점 값을 그대로 물려 주는데, 그것은 "측정하지 않은 구간에
    측정값이 있는" 그림이 된다.
    """
    x_key = str(options.get("x") or "")
    if not x_key:
        raise ProcessingError("기준 열('x')을 골라야 합니다.")
    x = frame.require(x_key, what="기준 열")
    require_increasing(x, what=f"'{x_key}'")

    count = option_int(options, "count", 200)
    if count < 2:
        raise ProcessingError(f"점 수는 2 이상이어야 합니다: {count}")
    lo, hi = float(np.min(x)), float(np.max(x))
    start = option_float(options, "start", lo)
    end = option_float(options, "end", hi)
    if start < lo or end > hi:
        raise ProcessingError(
            f"[{start:.6g}, {end:.6g}] 는 관측 범위 [{lo:.6g}, {hi:.6g}] 를 벗어납니다. "
            f"측정하지 않은 구간의 값을 만들어 내지 않습니다."
        )
    if start >= end:
        raise ProcessingError(f"시작({start})이 끝({end}) 이상입니다.")

    grid = np.linspace(start, end, count)
    resampled = {
        key: (grid if key == x_key else np.interp(grid, x, value))
        for key, value in frame.columns.items()
    }
    return StepResult(
        Frame(resampled, dict(frame.units)),
        notes=(f"'{x_key}' [{start:.6g}, {end:.6g}] 를 {count}점 균등 격자로 보간했습니다.",),
    )


@register(
    id="curve.smooth",
    kind="processing",
    label="이동평균 평활",
    params=(
        ParamSpec(name="column", label="평활할 열", type="str", role="column"),
        ParamSpec(
            name="window",
            label="창 크기(점)",
            type="int",
            default=5,
            help="홀수. 클수록 부드럽고, 봉우리가 낮아집니다.",
        ),
    ),
    # 원본을 덮지 않고 `<열>_smoothed` 를 더한다 — 무엇을 평활했느냐에 따라
    # 이름이 달라지므로 옵션 값으로 치환한다.
    makes_columns=("{column}_smoothed",),
    order=45,
    version="1",
)
def smooth(frame: Frame, options: dict[str, Any]) -> StepResult:
    """한 열에 이동평균을 건다.

    **평활은 물성을 바꾼다.** 인장 최대하중점의 봉우리가 깎이면 인장강도가
    낮아지고, 그 값은 여전히 그럴듯해 보인다. 그래서 기본으로 넣지 않고, 걸었을
    때는 창 크기를 근거에 남긴다.

    원본 열을 덮어쓰지 않고 `<열>_smoothed` 를 더한다 — 무엇을 평활했는지 원본과
    나란히 볼 수 있어야 사람이 판단한다.
    """
    key = str(options.get("column") or "")
    if not key:
        raise ProcessingError("평활할 열('column')을 골라야 합니다.")
    values = frame.require(key, what="평활할 열")
    window = option_int(options, "window", 5)
    if window < 3 or window % 2 == 0:
        raise ProcessingError(f"창 크기는 3 이상의 홀수여야 합니다: {window}")
    if window > len(values):
        raise ProcessingError(f"창({window})이 점 수({len(values)})보다 큽니다.")

    # 끝을 잘라내지 않으려고 가장자리를 반사한다. `mode="same"` 만 쓰면 양 끝이
    # 0 쪽으로 끌려 내려가 **없던 하강이 생긴다.**
    half = window // 2
    padded = np.pad(values, half, mode="reflect")
    kernel = np.ones(window) / window
    smoothed = np.convolve(padded, kernel, mode="valid")

    return StepResult(
        frame.with_columns(
            {f"{key}_smoothed": smoothed}, {f"{key}_smoothed": frame.units[key]}
        ),
        notes=(f"'{key}' 를 {window}점 이동평균으로 평활해 '{key}_smoothed' 로 더했습니다.",),
    )
