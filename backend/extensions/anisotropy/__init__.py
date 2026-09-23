"""이방성 — 폭이 얼마나 줄어드나(r값)와 세 방향을 모은 r̄·Δr·Hill48. **폴더 하나로.**

## 값이 들어오는 길이 **둘**이다

장비가 갈린다(2026-09-22 확인): 수동 시험기에는 폭 신율계가 달려 있고 자동 시험기에는
없다. 그래서 같은 r값이 두 길로 들어온다 —

    폭 채널이 있는 시험    처리 단계(`anisotropy.r_value`)가 곡선에서 잰다
    폭 채널이 없는 시험    사람이 「표로 시험 입력」 에서 요약값 `r_value` 로 적는다

묶음은 **둘을 가리지 않고 받되 어느 쪽인지 기억한다**(`measured` · `stated`). 카드에
실릴 때 그 구별이 값마다 `_source` 로 붙고, 등급 판정이 그것을 읽는다 — 사람이 적은
값이 하나라도 섞이면 그 카드의 이방성 값은 「적은 값」 으로 센다.

## 방향을 가로지르는 첫 물성이다

r̄ 는 세 방향을 함께 써서 나오므로 **방향이 없는 값**이다. 카드 한 장은 방향 하나라는
규칙(`_lineage_of_group`)의 예외이고, 그 예외는 블록이 `meta["cross_orientation"]` 으로
선언한다 — 카드를 만드는 쪽이 그 표시를 본다.

계산은 `rvalue.py`, 카드 블록은 `card.py`. 솔버 덱은 아직 안 낸다 — Hill48 을 받는
형식(*MAT_036 등)의 칸 자리를 검증할 실측이 없다. 낼 때는 내보내기 정의(데이터)로
`anisotropy.hill_f` 를 가리키면 된다.
"""

from __future__ import annotations

from typing import Any

from matcore.processing import Frame, StepResult
from matcore.registry import ParamSpec, Produced, register

from . import card, rvalue  # noqa: F401  (card 는 import 만으로 블록을 등록한다)


@register(
    id="anisotropy.r_value",
    kind="processing",
    label="소성 변형비 r",
    params=(
        ParamSpec(
            name="minimum_strain",
            dimension="strain",
            label="구간 시작",
            type="float",
            default=rvalue.DEFAULT_START,
            unit="1",
            help=(
                "**진변형률**입니다. 항복 뒤 소성역에서 잡습니다 — 앞쪽은 탄성이 섞여 "
                "r 이 과하게 나옵니다."
            ),
        ),
        ParamSpec(
            name="maximum_strain",
            dimension="strain",
            label="구간 끝",
            type="float",
            default=rvalue.DEFAULT_END,
            unit="1",
            help="균일 연신 안쪽이어야 합니다 — 넥킹에 들어가면 폭 변형이 국부화됩니다.",
        ),
        ParamSpec(
            name="strain",
            label="길이 변형률 열",
            type="str",
            role="column",
            default=rvalue.STRAIN,
        ),
        ParamSpec(
            name="width",
            label="폭 열",
            type="str",
            role="column",
            default=rvalue.WIDTH,
            help=(
                "**폭 그 자체**입니다(m). 폭 신율계가 있는 장비에만 있습니다 — 채널 "
                "이름이 다르면 형식 프로파일에서 이 이름으로 이어 주세요. 없으면 이 "
                "단계 대신 **표로 r값을 적습니다.**"
            ),
        ),
        ParamSpec(
            name="initial_width",
            dimension="length",
            label="초기 폭",
            type="float",
            unit="m",
            help=(
                "시편 정의에서 옵니다. 비우면 곡선의 첫 점을 씁니다 — 예하중이 걸린 "
                "뒤의 점이면 그만큼 변형률이 밀립니다."
            ),
        ),
    ),
    applies_to=("tensile",),
    # **시험종류 키만 보고 거르지 않는다.** 폭 채널이 없는 장비의 인장에는 이 단계가
    # 뜨면 안 된다 — 눌러 보고서야 안 된다는 것을 알게 된다.
    requires_channels=((rvalue.WIDTH,),),
    makes_values=(
        Produced(
            key="r_value",
            label="소성 변형비 r",
            si_unit="1",
            help=(
                "폭 변형률 / 두께 변형률. 두께는 부피 일정 가정으로 뺍니다. "
                "**한 점에서 나누지 않고 구간에 직선을 맞춥니다.**"
            ),
        ),
        Produced(
            key="r_value_r_squared",
            label="r 구간 R²",
            si_unit="1",
            help=(
                "그 구간에서 폭-길이 관계가 직선이었나. "
                f"**{rvalue.MIN_R_SQUARED} 미만이면 r 을 내지 않습니다.**"
            ),
        ),
        Produced(
            key="r_value_point_count",
            label="r 구간 점 수",
            si_unit="1",
            help=(
                f"{rvalue.MIN_POINTS}개 미만이면 r 을 내지 않습니다 — "
                "값이 왜 없는지 이 수가 말합니다."
            ),
        ),
    ),
    # **길이 진변형률 다음이다** — `tensile.true_plastic`(order 90)이 그 열을 만든다.
    # 앞에 서면 화면의 '변형률 열' 목록이 비어 있다.
    order=95,
    version="1",
)
def r_value(frame: Frame, options: dict[str, Any]) -> StepResult:
    """구간에서 r 을 잰다. **곡선은 안 바뀐다.**

    못 믿을 값은 아예 안 낸다 — 왜 못 냈는지는 각주로 남는다. 그 각주가 「폭 채널이
    없다」 이면 이 시험은 표로 적는 길로 가야 한다.
    """
    from matcore.processing import Scalar

    length = frame.require(str(options.get("strain") or rvalue.STRAIN), what="길이 변형률")
    raw_width = frame.require(str(options.get("width") or rvalue.WIDTH), what="폭")
    fitted = rvalue.fit(
        length,
        rvalue.width_strain(raw_width, options.get("initial_width")),
        start=float(options.get("minimum_strain", rvalue.DEFAULT_START)),
        end=float(options.get("maximum_strain", rvalue.DEFAULT_END)),
    )
    scalars = [
        Scalar("r_value_r_squared", "r 구간 R²", fitted.r_squared, "1"),
        Scalar("r_value_point_count", "r 구간 점 수", float(fitted.points), "1"),
    ]
    notes = [
        f"r 을 {fitted.start:.3g}~{fitted.end:.3g} 구간의 점 {fitted.points}개로 쟀습니다"
        f"(R²={fitted.r_squared:.4f})."
    ]
    if fitted.value is None:
        notes.append(f"**r 을 내지 않았습니다** — {fitted.why}")
    else:
        scalars.insert(0, Scalar("r_value", "소성 변형비 r", fitted.value, "1"))
    return StepResult(frame=frame, notes=tuple(notes), scalars=tuple(scalars))


register(
    id="anisotropy.r_family",
    kind="grouping",
    label="이방성 (세 방향 r값)",
    applies_to=("tensile",),
    params=(
        ParamSpec(
            name="hill48",
            label="Hill48 계수도 낸다",
            type="bool",
            default=True,
            help=(
                "F·G·H·N 을 r 셋에서 계산합니다. 평면 응력·등방 경화 가정이고, "
                "받는 솔버 형식이 정해지기 전에는 값만 남습니다."
            ),
        ),
    ),
    makes_values=(
        Produced(key="r_0", label="r₀ (MD)", si_unit="1"),
        Produced(key="r_45", label="r₄₅ (DD)", si_unit="1"),
        Produced(key="r_90", label="r₉₀ (TD)", si_unit="1"),
        Produced(key="r_bar", label="평균 이방성 r̄", si_unit="1"),
        Produced(key="delta_r", label="면내 이방성 Δr", si_unit="1"),
        Produced(key="hill_f", label="Hill48 F", si_unit="1"),
        Produced(key="hill_g", label="Hill48 G", si_unit="1"),
        Produced(key="hill_h", label="Hill48 H", si_unit="1"),
        Produced(key="hill_n", label="Hill48 N", si_unit="1"),
        Produced(
            key="sigma_0",
            label="σ₀ (MD 항복)",
            si_unit="Pa",
            help=(
                "**있으면 싣는다** — 없어도 r̄·Δr 은 나옵니다. 물성 키는 일부러 안 답니다: "
                "방향 없는 「항복강도」 를 적어 둔 값이 MD 칸에 앉으면 그것이 어느 방향의 "
                "값인지 아무도 모르게 됩니다."
            ),
        ),
        Produced(key="sigma_45", label="σ₄₅ (DD 항복)", si_unit="Pa"),
        Produced(key="sigma_90", label="σ₉₀ (TD 항복)", si_unit="Pa"),
        Produced(
            key="sigma_ratio_45",
            label="σ₄₅/σ₀",
            si_unit="1",
            help="솔버가 이방성 계수로 받는 모양. 1 에서 멀수록 방향에 따라 더 다릅니다.",
        ),
        Produced(key="sigma_ratio_90", label="σ₉₀/σ₀", si_unit="1"),
        Produced(key="specimen_count", label="쓴 시편 수", si_unit="1"),
        Produced(key="stated_count", label="그중 사람이 적은 값", si_unit="1"),
    ),
    #: **구성원을 모으는 법.** r값은 채택된 결과에 있을 수도(폭 채널이 있는 장비),
    #: 표로 적은 요약값에 있을 수도 있다(없는 장비) — 둘 다 받고 어느 쪽인지 남긴다.
    #: 방향은 시편에서 읽는다: 그것이 없으면 이 묶음은 아무 말도 못 한다.
    members={
        "from": "measured_or_stated",
        "values": [rvalue.R_VALUE],
        #: **있으면 싣고 없으면 그만이다.** 여기 것을 `values` 로 올리면 항복강도를
        #: 안 적은 옛 시험이 통째로 안 묶인다 — r̄ 만 보려던 사람이 막힌다.
        #: 이름이 셋인 이유는 `rvalue.YIELD_KEYS` 에 적어 두었다.
        "optional": list(rvalue.YIELD_KEYS),
        "specimen": ["orientation"],
    },
    card=rvalue.card_blocks,
    order=35,
    version="1",
)(rvalue.r_family)
