"""S-N 카드 블록 — 점(런아웃 표시 포함)이 행, Basquin 계수·피로 강도가 값. LS-DYNA
*MAT_ADD_FATIGUE 덱도 여기 있다(2026-09-27).

OptiStruct MATFAT · MSC MATFTG 는 안 낸다 — 둘 다 STATIC 줄의 인장강도(UTS)가 필수인데(평균응력
보정에 쓴다) S-N 카드에는 없다. 지어 넣으면 보정이 그 숫자를 믿는다. ANSYS 의 S-N 명령(FP)은
보관 기능이고, Abaqus·Radioss 는 재료 카드에 S-N 자리가 없다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.export import Deck, ExportError, Need, Rendered, _header, register_renderer
from matcore.registry import Produced

SN_CURVE = register_block(
    BlockSpec(
        key="sn_curve",
        label="S-N 곡선",
        help=(
            "시편마다 (응력 진폭, 파단 수명) 점과 그것을 이은 Basquin 식 S = A·N^b. "
            "**런아웃은 행에 남되 적합에서는 뺀 값이다** — 그 점은 수명이 아니라 하한이다."
        ),
        produces=(
            Produced(key="source", label="표를 만든 방법", si_unit="1"),
            Produced(key="model", label="식", si_unit="1", help="`basquin`."),
            Produced(key="basquin_a", label="Basquin A", si_unit="Pa"),
            Produced(key="basquin_b", label="Basquin b", si_unit="1"),
            Produced(key="sn_r_squared", label="적합의 R²", si_unit="1"),
            Produced(key="point_count", label="적합에 쓴 점 수", si_unit="1"),
            Produced(key="runout_count", label="런아웃 수", si_unit="1"),
            Produced(key="log_scatter", label="흩어짐", si_unit="1"),
            Produced(key="strength_at_1e5", label="피로 강도 @1e5", si_unit="Pa"),
            Produced(key="strength_at_1e6", label="피로 강도 @1e6", si_unit="Pa"),
            Produced(key="strength_at_1e7", label="피로 강도 @1e7", si_unit="Pa"),
        ),
        rows=(
            Produced(key="stress_amplitude", label="응력 진폭", si_unit="Pa"),
            Produced(key="cycles_to_failure", label="파단 수명", si_unit="1"),
            Produced(
                key="runout", label="런아웃", si_unit="1", help="1 이면 안 부러진 채 멈춤."
            ),
            Produced(
                key="stress_ratio",
                label="응력비 R",
                si_unit="1",
                help="σ_min/σ_max. S-N 곡선은 R 하나의 것이다 — -1 이 완전 역전.",
            ),
        ),
        order=45,
        kind_priority=3,
    )
)


@register_renderer(
    key="dyna_fatigue",
    label="LS-DYNA (피로 S-N)",
    extension="k",
    suffix="_fatigue",
    describe=(
        "*MAT_ADD_FATIGUE — Basquin S = a·N^b 를 식으로(LCID=-3, SNTYPE=1 진폭). 시간·주파수 "
        "영역 피로에 쓴다. MID 는 구조 재료의 번호로 맞춘다."
    ),
    keywords=("*KEYWORD", "*MAT_ADD_FATIGUE", "*END"),
    needs=(Need("sn_curve", values=("basquin_a", "basquin_b")),),
)
def render_dyna_fatigue(deck: Deck) -> Rendered:
    """카드 1b(LCID<0): `MID LCID LTYPE A B STHRES SNLIMT SNTYPE`.

    LCID=-3 이 `S = a·N^b` — 우리 Basquin 과 **같은 꼴**이라 옮길 것이 없다. **SNTYPE 을 늘
    적는다**: 기본이 0(응력 범위)이고 우리 곡선은 진폭이다. 매뉴얼 Remark 1 은 S 를 진폭이라
    부르면서 기본은 범위라 서로 어긋난다 — 비워 두면 수명이 2^(1/b) 배 틀린다.

    이 카드는 **다른 재료에 얹는다** — MID 가 구조 재료의 번호여야 한다. 카드 번호에서 만든
    수로는 짝이 안 맞으므로 덱에 적는다(내보낼 때 재료 번호를 고를 수 있다).
    """
    a = deck.number("sn_curve", "basquin_a")
    b = deck.number("sn_curve", "basquin_b")
    assert a is not None and b is not None
    if a <= 0.0 or b >= 0.0:
        raise ExportError(
            f"Basquin a={a:g}, b={b:g} 입니다 — a 는 양수, b 는 음수여야 S-N 곡선입니다."
        )
    ratios = sorted(
        {
            round(float(row["stress_ratio"]), 3)
            for row in deck.rows("sn_curve")
            if isinstance(row.get("stress_ratio"), int | float)
        }
    )
    notes = [
        "*MAT_ADD_FATIGUE 는 구조 재료에 얹는 카드입니다 — MID 를 그 재료 번호로 맞추세요."
    ]
    lines = ["*KEYWORD", *_header(deck, "$")]
    lines.append(f"$ Consistent units: {deck.units.declaration}")
    lines.append("$ S = a * N^b  (LCID=-3), S = stress AMPLITUDE (SNTYPE=1).")
    lines.append("$ MID must be the structural material this fatigue curve belongs to.")
    if ratios:
        lines.append(f"$ Stress ratio R of the tests: {', '.join(f'{r:g}' for r in ratios)}.")
        if ratios != [-1.0]:
            notes.append(
                f"시험의 응력비 R 이 {', '.join(f'{r:g}' for r in ratios)} 입니다 — "
                f"완전 역전(R=-1) 곡선이 아니므로 평균응력 보정을 쓰면 두 번 보정될 수 "
                f"있습니다."
            )
    lines.append("*MAT_ADD_FATIGUE")
    lines.append(
        "$      mid      lcid     ltype         a         b    sthres    snlimt    sntype"
    )
    lines.append(
        f"{deck.solver_id:>10}{-3:>10}{0:>10}{a:>10.3E}{b:>10.3E}{'':>10}{0:>10}{1:>10}"
    )
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
