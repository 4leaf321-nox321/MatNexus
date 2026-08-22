"""DMA 처리 단계 — **장비가 준 것과 우리가 낼 것을 가른다.**

DMA 는 인장과 사정이 정반대다. 인장은 하중·변위라는 날것을 받아 우리가 응력·
변형률을 만들지만, DMA 장비는 저장·손실 탄성률을 **이미 계산해서** 준다. 그래서
여기 있는 단계들은 새로 만드는 것이 아니라 **채우고 바꾸는** 일을 한다.

    파생 열     tan δ · |E*| · 위상각. 파일이 주면 그대로 쓰고, 안 주면 만든다
    주파수      ω = 2πf. 파일마다 한쪽만 있다
    Tg          정의마다 값이 다르다 — 무엇으로 쟀는지가 값과 함께 남아야 한다
    E → G       Prony 카드가 전단 기준이라, 인장·굽힘으로 쟀으면 바꿔야 한다

## 왜 파일이 주는 값을 다시 계산하는가

`tan_delta`·`complex_modulus`·`phase_angle` 은 DMA 시험 종류에서 **선택 채널**
이다 — 장비·표에 따라 있기도 없기도 하다(실측: 마스터커브 표에만 있는 것이
있었다). 없으면 뒤 단계가 통째로 막히므로, 정의대로 채워 두는 자리가 필요하다.

파일이 이미 준 열을 덮을 때는 **덮었다고 적는다.** 조용히 바꾸면 "장비 값인가
우리 값인가" 를 나중에 답할 수 없다.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from matcore.processing import (
    Frame,
    ProcessingError,
    Scalar,
    StepResult,
    option_float,
    option_text,
)
from matcore.registry import ParamSpec, Produced, register

#: DMA 시험 종류의 채널 키. **저장된 계약이라 코드가 이 이름으로 건다.**
STORAGE = "storage_modulus"
LOSS = "loss_modulus"
TEMPERATURE = "temperature"
FREQUENCY = "frequency"
ANGULAR = "angular_frequency"

TAN_DELTA = "tan_delta"
COMPLEX = "complex_modulus"
PHASE = "phase_angle"


def _moduli(frame: Frame, options: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    storage_key = str(options.get("storage") or STORAGE)
    loss_key = str(options.get("loss") or LOSS)
    storage = frame.require(storage_key, what="저장 탄성률")
    loss = frame.require(loss_key, what="손실 탄성률")
    if np.any(storage <= 0):
        raise ProcessingError(
            "저장 탄성률에 0 이하가 있습니다. tan δ 는 저장 탄성률로 나누므로 "
            "그 점에서 무한대가 됩니다 — 먼저 그 구간을 잘라내세요."
        )
    return storage, loss


@register(
    id="dma.derived",
    kind="processing",
    label="tan δ · 복소 탄성률",
    params=(
        ParamSpec(
            name="storage", label="저장 탄성률 열", type="str", role="column", default=STORAGE
        ),
        ParamSpec(
            name="loss", label="손실 탄성률 열", type="str", role="column", default=LOSS
        ),
    ),
    applies_to=("dma_sweep",),
    makes_columns=(
        Produced(
            key=TAN_DELTA,
            label="손실계수",
            si_unit="1",
            help="E″/E′. 피크 온도를 Tg 로 읽는 정의가 이 열을 씁니다.",
        ),
        Produced(
            key=COMPLEX,
            label="복소 탄성률",
            si_unit="Pa",
            help="√(E′² + E″²). 크기만 보는 자리에서 씁니다.",
        ),
        Produced(
            key=PHASE,
            label="위상각",
            si_unit="rad",
            help="atan(E″/E′). tan δ 와 같은 것을 각도로 본 값입니다.",
        ),
    ),
    order=10,
    version="1",
)
def derived(frame: Frame, options: dict[str, Any]) -> StepResult:
    """저장·손실 탄성률에서 tan δ·|E*|·위상각을 낸다.

    **정의 그대로다.** 그런데도 단계로 두는 이유는, 이 열들이 선택 채널이라 파일
    에 따라 없기 때문이다 — 없으면 Tg 판정이 통째로 막힌다.
    """
    storage, loss = _moduli(frame, options)
    tan_delta = loss / storage

    overwritten = [key for key in (TAN_DELTA, COMPLEX, PHASE) if key in frame.columns]
    notes: list[str] = []
    if overwritten:
        # **조용히 덮으면 "장비 값인가 우리 값인가" 를 못 답한다.**
        notes.append(
            f"파일이 준 열을 계산값으로 덮었습니다: {', '.join(overwritten)}. "
            f"정의(E″/E′)대로 다시 냈습니다."
        )

    return StepResult(
        frame.with_columns(
            {
                TAN_DELTA: tan_delta,
                COMPLEX: np.hypot(storage, loss),
                PHASE: np.arctan2(loss, storage),
            },
            {TAN_DELTA: "1", COMPLEX: "Pa", PHASE: "rad"},
        ),
        notes=tuple(notes),
    )


@register(
    id="dma.frequency",
    kind="processing",
    label="주파수 ↔ 각주파수",
    params=(
        ParamSpec(
            name="direction",
            label="방향",
            type="choice",
            default="to_angular",
            choices=("to_angular", "to_frequency"),
            choice_labels={
                "to_angular": "주파수 → 각주파수 (ω = 2πf)",
                "to_frequency": "각주파수 → 주파수 (f = ω/2π)",
            },
            help="파일마다 한쪽만 있습니다. 마스터커브는 주파수축을 씁니다.",
        ),
    ),
    applies_to=("dma_sweep",),
    makes_columns=(
        Produced(key=ANGULAR, label="각주파수", si_unit="rad/s"),
        Produced(key=FREQUENCY, label="주파수", si_unit="Hz"),
    ),
    order=20,
    version="1",
)
def frequency(frame: Frame, options: dict[str, Any]) -> StepResult:
    """없는 쪽을 만든다.

    **한쪽만 오는 파일이 있다.** 실측: 첫 스윕 표에만 `Frequency` 가 있고 나머지
    여섯에는 없었다. 그 상태로는 마스터커브가 못 돈다.
    """
    direction = option_text(options, "direction", ("to_angular", "to_frequency"))
    if direction == "to_angular":
        source = frame.require(FREQUENCY, what="주파수")
        return StepResult(
            frame.with_columns({ANGULAR: 2.0 * math.pi * source}, {ANGULAR: "rad/s"})
        )
    source = frame.require(ANGULAR, what="각주파수")
    return StepResult(
        frame.with_columns({FREQUENCY: source / (2.0 * math.pi)}, {FREQUENCY: "Hz"})
    )


@register(
    id="dma.glass_transition",
    kind="processing",
    label="유리전이온도",
    params=(
        ParamSpec(
            name="method",
            label="정의",
            type="choice",
            default="tan_delta_peak",
            choices=("tan_delta_peak", "loss_peak", "storage_onset"),
            choice_labels={
                "tan_delta_peak": "tan δ 피크",
                "loss_peak": "손실 탄성률 피크",
                "storage_onset": "저장 탄성률 온셋 (접선 교점)",
            },
            help=(
                "셋은 보통 몇 °C 씩 다릅니다. 어느 것으로 쟀는지를 안 적으면 "
                "다른 정의로 보고된 값과 비교할 수 없습니다."
            ),
        ),
        ParamSpec(
            name="drop",
            label="온셋 판정 낙폭",
            type="float",
            unit="1",
            default=0.5,
            when={"method": ("storage_onset",)},
            help="저장 탄성률이 이 비율만큼 떨어지는 지점을 씁니다(0.5 = 절반).",
        ),
        ParamSpec(
            name="temperature", label="온도 열", type="str", role="column", default=TEMPERATURE
        ),
    ),
    applies_to=("dma_sweep",),
    makes_values=(
        Produced(
            key="glass_transition",
            label="유리전이온도",
            si_unit="K",
            help="정의에 따라 값이 다릅니다. 무엇으로 쟀는지가 단계 설정에 남습니다.",
        ),
        Produced(
            key="glass_transition_peak",
            label="피크에서의 값",
            si_unit="1",
            help="tan δ 피크면 그 tan δ 값. 피크가 뚜렷한지 보는 근거입니다.",
        ),
    ),
    order=60,
    version="1",
)
def glass_transition(frame: Frame, options: dict[str, Any]) -> StepResult:
    """온도 스윕에서 Tg 를 잡는다. 곡선은 안 바뀐다.

    **정의마다 값이 다르다.** tan δ 피크가 가장 높고 저장 탄성률 온셋이 가장
    낮은 것이 보통이며, 그 차이는 몇 °C 에서 십수 °C 까지 간다. 하나로 박아 두면
    다른 정의로 보고된 값과 비교가 안 되고, 조용히 바꾸면 예전 값과 어긋난다 —
    탄성계수 단계와 같은 판단이다.

    그리고 tan δ 피크 온도는 **모드와 주파수에 의존한다.** 규격 번호만 적힌
    보고서로는 재현이 안 된다는 것이 DMA 규격 문헌의 결론이다.
    """
    method = option_text(options, "method", ("tan_delta_peak", "loss_peak", "storage_onset"))
    temperature_key = str(options.get("temperature") or TEMPERATURE)
    temperature = frame.require(temperature_key, what="온도")
    if len(temperature) < 3:
        raise ProcessingError("온도 점이 3개 미만입니다. 스윕이 아닙니다.")

    if method == "tan_delta_peak":
        series = frame.require(TAN_DELTA, what="tan δ")
    elif method == "loss_peak":
        series = frame.require(LOSS, what="손실 탄성률")
    else:
        series = frame.require(STORAGE, what="저장 탄성률")

    notes: list[str] = []
    if method == "storage_onset":
        drop = option_float(options, "drop", 0.5)
        if not 0 < drop < 1:
            raise ProcessingError(f"낙폭은 0 과 1 사이여야 합니다: {drop}")
        # 유리 영역(가장 높은 저장 탄성률)에서 그 비율만큼 떨어진 첫 점.
        target = float(np.max(series)) * (1.0 - drop)
        below = np.flatnonzero(series <= target)
        if below.size == 0:
            raise ProcessingError(
                f"저장 탄성률이 {drop:.0%} 만큼 떨어지는 지점이 없습니다. "
                f"스윕이 전이를 다 지나지 않았을 수 있습니다."
            )
        index = int(below[0])
        value = float(series[index])
    else:
        index = int(np.argmax(series))
        value = float(series[index])
        if index in (0, len(series) - 1):
            # **끝에서 잡힌 피크는 피크가 아니다.** 스윕이 전이를 안 지났거나
            # 구간을 잘못 잘랐다는 뜻인데, 값 자체는 그럴듯하게 나온다.
            notes.append(
                "피크가 스윕의 끝에서 잡혔습니다 — 전이가 구간 밖에 있을 수 "
                "있습니다. 온도 범위를 넓혀 다시 보세요."
            )

    return StepResult(
        frame,
        notes=tuple(notes),
        scalars=(
            Scalar(
                key="glass_transition",
                label="유리전이온도",
                value=float(temperature[index]),
                si_unit="K",
                dimension="temperature",
            ),
            Scalar(
                key="glass_transition_peak",
                label="피크에서의 값",
                value=value,
                si_unit="1" if method == "tan_delta_peak" else "Pa",
            ),
        ),
    )


@register(
    id="dma.to_shear",
    kind="processing",
    label="인장 → 전단 (E → G)",
    params=(
        ParamSpec(
            name="poisson_ratio",
            label="포아송비",
            type="float",
            unit="1",
            required=True,
            help=(
                "G = E / 2(1+ν). 고무는 0.5 에 가깝고 유리질 고분자는 0.35 안팎입니다. "
                "기본값을 안 두는 이유는 이 값이 결과를 그대로 바꾸기 때문입니다."
            ),
        ),
        ParamSpec(
            name="storage", label="저장 탄성률 열", type="str", role="column", default=STORAGE
        ),
        ParamSpec(
            name="loss", label="손실 탄성률 열", type="str", role="column", default=LOSS
        ),
    ),
    applies_to=("dma_sweep",),
    makes_columns=(
        Produced(
            key="storage_modulus_shear",
            label="전단 저장 탄성률",
            si_unit="Pa",
            help="G′ = E′ / 2(1+ν). Prony 카드가 이 값을 씁니다.",
        ),
        Produced(
            key="loss_modulus_shear",
            label="전단 손실 탄성률",
            si_unit="Pa",
            help="G″ = E″ / 2(1+ν).",
        ),
    ),
    order=30,
    version="1",
)
def to_shear(frame: Frame, options: dict[str, Any]) -> StepResult:
    """인장·굽힘으로 잰 E 를 전단 G 로 바꾼다.

    **Prony 카드는 전단 기준이다.** 고무를 전단 샌드위치로 쟀다면 변환 없이 바로
    이어지지만, 인장이나 굽힘으로 쟀다면 여기를 거쳐야 한다.

    **등방·선형 탄성을 가정한 변환이다.** 이방성 재료(복합재)나 큰 변형에서는
    성립하지 않는다. 그리고 ν 는 온도에 따라 변하는데 여기서는 상수로 둔다 —
    그 사실을 결과에 적어 둔다.
    """
    poisson = option_float(options, "poisson_ratio")
    if not -1.0 < poisson < 0.5:
        raise ProcessingError(
            f"포아송비는 -1 과 0.5 사이여야 합니다: {poisson}. "
            f"0.5 는 완전 비압축성이라 그 자체로는 쓸 수 없습니다."
        )
    storage, loss = _moduli(frame, options)
    factor = 2.0 * (1.0 + poisson)
    return StepResult(
        frame.with_columns(
            {
                "storage_modulus_shear": storage / factor,
                "loss_modulus_shear": loss / factor,
            },
            {"storage_modulus_shear": "Pa", "loss_modulus_shear": "Pa"},
        ),
        notes=(
            f"등방·선형 탄성을 가정하고 ν = {poisson:g} 를 상수로 썼습니다. "
            f"ν 는 온도에 따라 변하고, 이방성 재료에서는 이 식이 성립하지 않습니다.",
        ),
    )
