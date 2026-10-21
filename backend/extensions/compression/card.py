"""폼 카드 블록과 덱(2026-10-20). **중심 코드는 이 확장의 이름을 모른다.**

    블록   `foam_curve` — 공칭 압축 변형률 · 공칭 압축 응력(압축이 양수) 행. 시편 여럿의
           곡선을 공통 구간에 평균한 것(`foam.foam_curve`).
    덱     LS-DYNA *MAT_LOW_DENSITY_FOAM(057) + *DEFINE_CURVE — 공칭 응력 대 공칭 변형률
           곡선을 그대로 받는다. E 는 인장 쪽 탄성계수, RO 는 밀도.

사용자 보고: 폼 소재를 해석 카드로 내보낼 경로가 없었다 — 「폼 카드 공칭응력-변형률 표 블록
대응 필요」.
"""

from __future__ import annotations

from itertools import pairwise

from matcore.cards import BlockSpec, register_block
from matcore.export import Deck, ExportError, Need, Rendered, _header, register_renderer
from matcore.export import dyna as _dyna
from matcore.registry import Produced

FOAM_CURVE = register_block(
    BlockSpec(
        key="foam_curve",
        label="폼 압축 곡선 (공칭)",
        help=(
            "공칭 압축 변형률 · 공칭 압축 응력의 표(압축이 양수). **진응력이 아니다** — 폼은 "
            "눌려도 옆으로 거의 안 퍼져 체적 보존 가정이 안 맞고, 저밀도 폼 재료가 이 곡선을 "
            "그대로 받는다. 시편 여럿의 곡선을 공통 구간에 평균한 것."
        ),
        produces=(
            Produced(
                key="source",
                label="표를 만든 방법",
                si_unit="1",
                help="`compression_mean` — 시편 곡선을 가장 짧은 끝까지 보간해 평균한 것.",
            ),
            Produced(key="sample_count", label="시편 수", si_unit="1"),
            Produced(
                key="strain_max",
                label="표의 끝 변형률",
                si_unit="1",
                help="이 너머는 시험이 아니다 — 솔버는 마지막 기울기로 늘인다.",
            ),
        ),
        rows=(
            Produced(key="strain", label="공칭 압축 변형률", si_unit="1"),
            Produced(key="stress", label="공칭 압축 응력", si_unit="Pa"),
        ),
        curve=("strain", "stress"),
        from_tests=("compression",),
        from_values=False,
        order=45,
    )
)


@register_renderer(
    key="dyna_foam",
    label="LS-DYNA (저밀도 폼)",
    extension="k",
    suffix="_foam",
    describe=(
        "*MAT_LOW_DENSITY_FOAM(057) + *DEFINE_CURVE — 공칭 압축 응력 대 공칭 압축 변형률. "
        "연질 폼(폴리우레탄 등)용. 항복 봉우리가 있는 경질 폼은 파쇄형 폼 재료가 맞다."
    ),
    keywords=("*KEYWORD", "*MAT_LOW_DENSITY_FOAM", "*DEFINE_CURVE", "*END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "density")),
        Need("foam_curve", rows_min=3),
    ),
)
def render_dyna_foam(deck: Deck) -> Rendered:
    """LS-DYNA `*MAT_057` — 카드 둘: `MID RO E LCID TC HU BETA DAMP` / `SHAPE FAIL BVFLAG ED
    BETA1 KCON REF`.

    **곡선을 고치지 않는다.** 응력이 내려가는 구간(경질 폼의 항복 봉우리)이 있으면 거부한다 —
    *MAT_057 은 단조 증가 곡선을 전제하고, 눌러 펴서 내보내면 다른 재료가 된다. 그 재료는
    파쇄형 폼(*MAT_CRUSHABLE_FOAM 등)으로 옮겨야 한다.

    나머지 칸은 LS-DYNA 기본값이다 — TC(인장 차단)은 끔(1e20), HU = 1(이력 소산 없음), DAMP
    0.05(매뉴얼 권장 0.05~0.50 의 아래). 이력 · 감쇠는 시험이 정한 값이 아니라 그렇다고 적는다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    density = deck.number("elastic", "density")
    assert youngs is not None and density is not None
    points = sorted(deck.pairs("foam_curve", "strain", "stress"))
    if not points or points[0][0] != 0.0:
        points = [(0.0, 0.0), *[point for point in points if point[0] > 0]]
    stresses = [stress for _, stress in points]
    drops = sum(1 for before, after in pairwise(stresses) if after < before)
    if drops:
        raise ExportError(
            f"폼 곡선에 응력이 내려가는 곳이 {drops}군데 있습니다 — *MAT_LOW_DENSITY_FOAM 은 "
            "단조 증가 곡선을 전제합니다. 항복 봉우리가 있는 경질 폼이면 파쇄형 폼 재료가 "
            "맞습니다(이 형식으로는 내보내지 않습니다)."
        )
    curve_id = deck.solver_id
    lines = ["*KEYWORD", *_header(deck, "$"), *_dyna._units_comment(deck)]
    lines.append(
        f"$ Nominal compressive stress vs nominal strain (compression positive), "
        f"{len(points)} points to strain {points[-1][0]:.4g} - the solver extrapolates "
        "beyond that."
    )
    lines.append("$ HU=1 (no hysteresis), DAMP=0.05: LS-DYNA defaults, not measured.")
    lines.append("*MAT_LOW_DENSITY_FOAM")
    lines.append(
        "$      mid        ro         e      lcid        tc        hu      beta      damp"
    )
    lines.append(
        _dyna._i10(deck.solver_id)
        + _dyna._f10(density)
        + _dyna._f10(youngs)
        + _dyna._i10(curve_id)
        + _dyna._f10(1.0e20)
        + _dyna._f10(1.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.05)
    )
    lines.append("$    shape      fail    bvflag        ed     beta1      kcon       ref")
    lines.append(
        _dyna._f10(1.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.0)
        + _dyna._f10(0.0)
    )
    lines.extend(_dyna._curve(curve_id, points))
    lines.append("*END")
    return Rendered(
        text="\n".join(lines) + "\n",
        notes=(
            "이력(HU) · 감쇠(DAMP)는 LS-DYNA 기본값입니다 — 반복 압축 시험이 있으면 HU 를 "
            "그 시험에서 정하세요.",
        ),
    )
