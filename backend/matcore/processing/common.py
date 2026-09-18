"""시험 종류를 가리지 않는 처리 — 정렬·자르기·재샘플·평활.

여기 있는 것은 전부 **인장에도 DMA 에도 쓰인다.** 시험별 계산(`tensile.py`)과
나누는 이유는 물성이 늘 때 무엇을 새로 짜야 하는지가 분명해야 하기 때문이다 —
새 물성 하나가 파일 2~3개로 끝나야 한다(D7).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from matcore import ParamSpec, Produced, register
from matcore.processing import (
    Frame,
    ProcessingError,
    Scalar,
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
        ParamSpec(
            name="start",
            label="시작",
            type="float",
            unit_from="x",
            help="이 값 미만을 버립니다.",
        ),
        ParamSpec(
            name="end",
            label="끝",
            type="float",
            unit_from="x",
            help="이 값 초과를 버립니다.",
        ),
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


#: 요청 구간이 관측 범위를 벗어나도 봐 주는 폭. **관측 폭에 대한 비율이다.**
#:
#: 절대값으로 두면 변형률(0~0.4)과 응력(0~5e8)에서 뜻이 전혀 달라진다.
#:
#: 실측(2026-08-27): `.tra` 의 첫 변형률이 `2.92968e-09`, 관측 폭이 `0.400074` 라
#: 비율이 `7.3e-9` 다. 1e-6 은 그보다 두 자릿수 넉넉하면서, 변형률로 치면
#: `4e-7`(0.00004%)이라 어떤 장비의 분해능보다도 작다. 사람이 다른 구간을 적은
#: 경우(예: 0 을 요청했는데 데이터가 0.05 부터)는 비율이 0.1 대라 한참 걸린다.
RANGE_SLACK = 1e-6


@register(
    id="curve.resample",
    kind="processing",
    label="균등 격자로 재샘플",
    params=(
        ParamSpec(name="x", label="기준 열", type="str", role="column"),
        ParamSpec(name="count", label="점 수", type="int", default=200),
        ParamSpec(
            name="start",
            label="시작",
            type="float",
            unit_from="x",
            help="비우면 관측 최솟값",
        ),
        ParamSpec(
            name="end",
            label="끝",
            type="float",
            unit_from="x",
            help="비우면 관측 최댓값",
        ),
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

    ## 다만 끝자락의 잡음까지 거절하지는 않는다

    실측으로 걸렸다(2026-08-27, 전체 흐름 점검). 화면이 채워 주는 표준 레시피는
    `start: 0` 을 적는다 — 「0 부터」 라는 뜻이다. 그런데 실제 `.tra` 의 첫
    변형률은 `2.92968e-09` 이지 정확히 0 이 아니다. 그래서 **화면이 권하는 그
    구성이 실파일에서 422 로 막혔다.**

    3e-9 는 외삽이 아니라 **0 의 반올림**이다. 그것까지 거절하면 사람은 관측
    최솟값을 손으로 옮겨 적게 되는데, 그 값은 시편마다 다르므로 결국 **시편마다
    다른 레시피**가 만들어진다 — 그러면 통계가 격자를 못 맞춘다.

    그래서 **관측 폭에 견주어 잡음 수준일 때만** 요청한 구간을 그대로 받는다.
    구간을 관측 안으로 **당기지는 않는다** — 당기면 시편마다 시작점이 달라져
    격자가 어긋난다. 봐 줬다는 사실은 노트에 적는다. 잡음 수준을 넘으면 전과
    같이 거절한다.
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

    # **관측 폭에 견준다.** 절대값으로 두면 변형률(0~0.4)과 응력(0~5e8)에서 뜻이
    # 전혀 달라진다.
    span = hi - lo
    slack = abs(span) * RANGE_SLACK
    if start < lo - slack or end > hi + slack:
        raise ProcessingError(
            f"[{start:.6g}, {end:.6g}] 는 관측 범위 [{lo:.6g}, {hi:.6g}] 를 벗어납니다. "
            f"측정하지 않은 구간의 값을 만들어 내지 않습니다."
        )

    # **당기지 않는다.** 관측 범위 안으로 당기면 시편마다 시작점이 달라지고,
    # 그러면 여러 시편의 격자가 어긋나 통계가 대표 곡선을 못 낸다 — `start: 0`
    # 을 못 박는 이유가 바로 **모든 시편이 같은 격자를 쓰게** 하려는 것이다.
    #
    # 요청한 격자를 그대로 쓴다. 끝자락 한 점의 값은 `np.interp` 가 관측
    # 끝값으로 채우는데, 벗어난 폭이 잡음 수준일 때만 여기까지 오므로 그
    # 값은 실제로 잰 값과 구별되지 않는다.
    said: list[str] = []
    if start < lo or end > hi:
        # **조용히 넘어가지 않는다.** 봐 준 사실이 어딘가에 남아야 한다.
        said.append(
            f"요청한 [{start:.6g}, {end:.6g}] 가 관측 범위 [{lo:.6g}, {hi:.6g}] 를 "
            f"아주 조금(관측 폭의 {max(lo - start, end - hi) / abs(span or 1):.1e}) "
            f"벗어나지만 끝자락의 반올림이라 그대로 씁니다."
        )

    if start >= end:
        raise ProcessingError(f"시작({start})이 끝({end}) 이상입니다.")

    grid = np.linspace(start, end, count)
    resampled = {
        key: (grid if key == x_key else np.interp(grid, x, value))
        for key, value in frame.columns.items()
    }
    said.append(f"'{x_key}' [{start:.6g}, {end:.6g}] 를 {count}점 균등 격자로 보간했습니다.")
    return StepResult(Frame(resampled, dict(frame.units)), notes=tuple(said))


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
    makes_columns=(
        Produced(
            key="{column}_smoothed",
            label="평활한 열",
            help="원본 열을 덮지 않고 옆에 더합니다 — 무엇을 평활했는지 나란히 봅니다.",
        ),
    ),
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


# ── 단조 증가 보정 ────────────────────────────────────────────────────────────

#: 엄격히 올리기 — 점마다 최소 이만큼(y 최댓값의 비율)은 앞 점보다 커야 한다.
MONOTONE_STEP_RATIO = 1e-6

MONOTONE_METHODS = ("envelope", "isotonic")


def monotone_isotonic(values: np.ndarray) -> np.ndarray:
    """단조 비감소 최소제곱 회귀(PAVA). `tensile.yield_drop` 과 같은 알고리즘이다."""
    level: list[float] = []
    weight: list[int] = []
    for value in values.tolist():
        level.append(float(value))
        weight.append(1)
        while len(level) > 1 and level[-2] > level[-1]:
            total = weight[-2] + weight[-1]
            merged = (level[-2] * weight[-2] + level[-1] * weight[-1]) / total
            level[-2:] = [merged]
            weight[-2:] = [total]
    out = np.empty(len(values), dtype=np.float64)
    at = 0
    for value, count in zip(level, weight, strict=True):
        out[at : at + count] = value
        at += count
    return out


def strictly_increasing(
    x: np.ndarray, y: np.ndarray, *, step_ratio: float, min_slope: float
) -> np.ndarray:
    """평탄한 자리에도 오름을 준다 — 앞 점보다 `max(step, min_slope·Δx)` 만큼은 크게.

    `step` 은 y 최댓값의 `step_ratio` 배라 단위가 없다(1e-6 이면 400 MPa 곡선에서 400 Pa —
    솔버에는 0 과 구별되는 값이고 물성으로는 없는 값이다). 앞에서부터 한 번 훑는다.
    """
    out = y.astype(np.float64).copy()
    step = float(np.max(np.abs(out))) * step_ratio if len(out) else 0.0
    for index in range(1, len(out)):
        floor = out[index - 1] + max(step, min_slope * float(x[index] - x[index - 1]))
        if out[index] < floor:
            out[index] = floor
    return out


@register(
    id="curve.monotone",
    kind="processing",
    label="단조 증가 보정",
    params=(
        ParamSpec(name="column", label="보정할 열", type="str", role="column"),
        ParamSpec(
            name="x",
            label="기준 열",
            type="str",
            role="column",
            help="이 열이 늘 때 보정할 열이 늘어야 합니다(변형률). 최소 기울기의 기준입니다.",
        ),
        ParamSpec(
            name="method",
            label="내려가는 곳은",
            type="choice",
            default="envelope",
            choices=MONOTONE_METHODS,
            choice_labels={
                "envelope": "직전 최댓값으로 덮기",
                "isotonic": "이웃과 평균으로 펴기",
            },
            choice_help={
                "envelope": "running max — 내려간 점을 앞의 최댓값으로 올립니다. 봉우리 "
                "쪽으로 치우칩니다.",
                "isotonic": "단조 비감소 최소제곱 회귀(PAVA) — 위아래로 고른 잡음에 원곡선과 "
                "가깝습니다.",
            },
        ),
        ParamSpec(
            name="strict",
            label="엄격히 증가",
            type="bool",
            default=True,
            help="켜면 평탄부(기울기 0)도 아주 조금씩 오르게 합니다 — 접선계수 0 을 거부하는 "
            "솔버용. 끄면 평탄부를 둡니다(단조 비감소).",
        ),
        ParamSpec(
            name="step_ratio",
            label="최소 오름(최댓값 비율)",
            type="float",
            default=MONOTONE_STEP_RATIO,
            unit="1",
            help="엄격히 증가일 때 점마다 최소 이만큼(열 최댓값의 비율) 앞 점보다 커야 "
            "합니다. 1e-6 이면 400 MPa 곡선에서 400 Pa — 물성으로는 없는 값입니다.",
        ),
        ParamSpec(
            name="min_slope",
            label="최소 기울기",
            type="float",
            default=0.0,
            help="기준 열 단위당 최소 오름(열의 단위 / 기준 열 단위). 0 이면 최소 오름만 "
            "씁니다. 예: 응력에 1e7 이면 10 MPa/1.0 변형률.",
        ),
    ),
    makes_values=(
        Produced(
            key="monotone_points",
            label="단조 보정한 점 수",
            si_unit="1",
            help="이 단계가 값을 올린 점의 수. 0 이면 이미 단조 증가였습니다.",
        ),
        Produced(
            key="monotone_max_lift",
            label="최대 올린 폭",
            help="한 점을 가장 많이 올린 폭(열의 단위). 크면 곡선이 실제로 내려갔던 것입니다.",
        ),
    ),
    order=46,
    version="1",
)
def monotone(frame: Frame, options: dict[str, Any]) -> StepResult:
    """한 열을 기준 열에 대해 **단조 증가**로 만든다 — 평탄부까지.

    `tensile.yield_drop` 은 「내려가는」 곡선을 고치고, 내려간 데가 없으면 손대지 않는다.
    그런데 솔버가 거부하는 것은 하강만이 아니다 — **변형률이 늘어도 응력이 그대로인
    평탄부**(접선계수 0)도 거부하거나 발산한다(2026-09-18 요청). 이 단계는 시험 종류와
    무관하게 아무 열에나 걸 수 있고, 하강은 고른 방법으로, 평탄부는 아주 조금씩 올려
    엄격히 증가로 만든다.

    **무엇을 얼마나 올렸는지 남긴다** — 올린 점 수와 최대 폭. 최대 폭이 크면 곡선이
    실제로 내려갔던 것이고, 그것은 이 단계가 아니라 `tensile.yield_drop` 으로 이유를
    갈라 다뤄야 한다.
    """
    key = str(options.get("column") or "")
    x_key = str(options.get("x") or "")
    if not key or not x_key:
        raise ProcessingError("보정할 열('column')과 기준 열('x')을 골라야 합니다.")
    if key == x_key:
        raise ProcessingError("보정할 열과 기준 열이 같습니다.")
    x = frame.require(x_key, what="기준 열")
    y = frame.require(key, what="보정할 열")
    require_increasing(x, what=f"'{x_key}'")
    method = option_text(options, "method", MONOTONE_METHODS)
    strict = bool(options.get("strict", True))
    step_ratio = option_float(options, "step_ratio", MONOTONE_STEP_RATIO)
    min_slope = option_float(options, "min_slope", 0.0)
    if step_ratio < 0 or min_slope < 0:
        raise ProcessingError("최소 오름과 최소 기울기는 0 이상이어야 합니다.")

    original = np.asarray(y, dtype=np.float64)
    fixed = (
        np.maximum.accumulate(original)
        if method == "envelope"
        else monotone_isotonic(original)
    )
    if strict:
        fixed = strictly_increasing(x, fixed, step_ratio=step_ratio, min_slope=min_slope)

    lifted = fixed - original
    changed = int(np.count_nonzero(lifted != 0))
    max_lift = float(np.max(np.abs(lifted))) if len(lifted) else 0.0
    unit = frame.units.get(key, "1")
    if changed == 0:
        note = f"'{key}' 는 이미 '{x_key}' 에 대해 엄격히 증가합니다 — 손대지 않았습니다."
    else:
        how = "직전 최댓값으로 덮고" if method == "envelope" else "이웃과 평균으로 펴고"
        note = (
            f"'{key}' 를 '{x_key}' 에 대해 단조 증가로 만들었습니다 — 내려간 곳은 {how}"
            + (", 평탄부는 아주 조금씩 올려 엄격히 증가" if strict else "")
            + f". {changed}점을 바꿨고 가장 많이 올린 폭은 {max_lift:.4g} {unit} 입니다."
            + (
                " 폭이 크면 곡선이 실제로 내려갔던 것입니다 — 이유는 'tensile.yield_drop' 으로"
                " 가르세요."
                if len(original) and max_lift > 0.01 * float(np.max(np.abs(original)))
                else ""
            )
        )
    return StepResult(
        frame.with_columns({key: fixed}, {}),
        notes=(note,),
        scalars=(
            Scalar("monotone_points", "단조 보정한 점 수", float(changed), "1"),
            Scalar("monotone_max_lift", "최대 올린 폭", max_lift, unit),
        ),
    )
