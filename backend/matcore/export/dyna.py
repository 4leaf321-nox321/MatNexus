"""LS-DYNA 렌더러 — *MAT_001 · *MAT_024(표·속도별 표) · *MAT_076 · *MAT_027/077 ·
*MAT_THERMAL_ISOTROPIC.

MaterialTwin 이식 2단계(ADR 0027 계획). 원본 `dyna_export.py` 를 통째로 옮기지
않고 **우리 렌더러 틀에 다시 썼다** — 단위계 적용(`to_system`)·모자람 검사·출처
주석(`_header`)은 틀이 이미 하므로 여기는 키워드를 쓰는 일만 한다.

## 고정 10칸이다

LS-DYNA 표준 키워드 형식은 한 줄 8필드, 필드당 10칸이다. 칸이 어긋나면 다른
필드로 읽히고 **솔버는 오류 없이 엉뚱한 재료로 계산한다** — OpenRadioss 의
20칸과 같은 성격의 함정이다. 곡선 점만 20칸 둘(*DEFINE_CURVE 의 관행)이다.

## 카드를 건너뛰지 않는다

매뉴얼의 규칙은 「따로 적지 않았으면 카드는 필수」 다(Vol I, General Card Format).
*MAT_024 의 3·4번 카드(EPS·ES)·*MAT_076 의 2번 카드(LCID…)·*MAT_027 의 2번 카드
(SGL…)가 그런 자리인데, 전에는 값이 없다고 빼서 **다음 줄이 그 카드로 읽혔다**
(2026-09-27, R13·R17 매뉴얼로 확인). 쓸 값이 없어도 0 을 채운 줄을 둔다.

## 단위는 주석으로 선언한다

LS-DYNA 에는 단위 키워드가 없다(Abaqus 와 같다). 값은 `render()` 가 이미 고른
계로 바꿔 놓았고, 여기서는 그 계를 `$` 주석으로 크게 적는다 — 관행 계
(ton·mm·s = MPa)는 사용자 정의 단위계(`systems.derive`)로 고른다.
"""

from __future__ import annotations

from itertools import pairwise

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _header,
    hyperelastic_terms,
    prepare,
    prony_terms,
    rate_curves,
    register_renderer,
    viscoelastic_shift,
    viscoelastic_shift_notes,
)
from matcore.export.template import fit
from matcore.viscoelastic import GAS_CONSTANT

#: *MAT_GENERAL_VISCOELASTIC 이 받는 항 카드 수. **장기 탄성률도 한 장을 쓴다**
#: (β=0 항) — Prony 는 그만큼 덜 받는다.
MAX_PRONY_TERMS = 18

#: 곡선을 솔버가 다시 나누는 점 수의 바닥(`*CONTROL_SOLUTION` 의 LCINT 기본값).
DEFAULT_LCINT = 100


def _f10(value: float) -> str:
    """고정 10칸 숫자 — 칸에 드는 만큼 정밀하게(`template.fit`). 칸이 어긋나면 다른 필드다.

    전에는 유효숫자 4자리(`4.993E-01`)였다 — 고무의 푸아송비 0.49925 가 0.4993 이 되어
    체적 탄성률이 7% 달라졌다(2026-10-03, 공개 덱 대조).
    """
    return fit(value, 10)


def _i10(value: int) -> str:
    return f"{value:>10d}"


def _zeros(count: int = 8) -> str:
    """쓸 값이 없는 카드 — **빼지 않고 0 을 채운다**(머리말 「카드를 건너뛰지 않는다」).

    `0` 으로 적는다. 정수 칸(LCID·NT)에 `0.000E+00` 을 두면 정수로 못 읽는다.
    """
    return "".join(f"{0:>10}" for _ in range(count))


def _units_comment(deck: Deck) -> list[str]:
    return [
        "$ Consistent units: " + deck.units.declaration,
        "$   (LS-DYNA declares no units - every material in this deck must match.)",
    ]


def _curve(curve_id: int, points: list[tuple[float, float]], lcint: int = 0) -> list[str]:
    """`*DEFINE_CURVE` — (가로축, 세로축) 20칸 둘. LCINT 는 8번째 칸이다."""
    lines = ["*DEFINE_CURVE"]
    lines.append(
        "$     lcid      sidr       sfa       sfo      offa      offo    dattyp     lcint"
    )
    lines.append(_i10(curve_id) + (" " * 60 + _i10(lcint) if lcint else ""))
    lines.append("$                 a1                  o1")
    lines.extend(f"{x:>20.12E}{y:>20.9E}" for x, y in points)
    return lines


@register_renderer(
    key="dyna_elastic",
    label="LS-DYNA (선형)",
    extension="k",
    suffix="_elastic",
    describe=(
        "*MAT_ELASTIC(001) — 선형 탄성. 소성 표가 없는 재료(문헌 스칼라·DMA 선형 구간)용."
    ),
    keywords=("*KEYWORD", "*MAT_ELASTIC", "*END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("lve", optional=True),
    ),
)
def render_dyna_elastic(deck: Deck) -> Rendered:
    """LS-DYNA `*MAT_001` — E·ν·밀도 셋이면 나온다.

    문헌 카탈로그의 스칼라 재료가 주 고객이다 — 소성 표가 없어도 강성·모드
    해석에는 이것으로 충분하다. 표가 있는 카드는 `dyna`(*MAT_024)가 맞다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None

    notes: list[str] = []
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    if len(deck.rows("elastic")) > 1:
        # *MAT_001 은 상수 하나다. 표를 누르는 것은 조용히 할 일이 아니라 적는다.
        notes.append(
            "온도별 탄성 표가 있는데 *MAT_ELASTIC 은 상수 하나입니다 — 블록의 대푯값"
            "(가장 낮은 온도)을 썼습니다."
        )
        lines.append("$ *MAT_ELASTIC is temperature independent: lowest-temperature value.")
    limit = deck.number("lve", "lve_strain_limit")
    if limit is not None:
        lines.append(
            f"$ E is the DMA storage modulus in the linear range - valid up to strain "
            f"{limit:.4g}."
        )
    lines.append("*MAT_ELASTIC")
    lines.append("$      mid        ro         e        pr        da        db         k")
    lines.append(_i10(deck.solver_id) + _f10(density) + _f10(youngs) + _f10(poisson))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def _flat_elastic(deck: Deck) -> tuple[list[str], list[str]]:
    """온도별 탄성 표를 **상수 하나로 접는다** — 덱 주석과 각주로 말한다(`*MAT_001` 과 같다).

    *MAT_024 의 E · PR 은 상수다. 2026-10-07 까지는 표가 있어도 아무 말 없이 첫 줄을 썼다 —
    덱만 받은 사람은 온도를 타는 탄성이 빠진 줄 몰랐다. `(덱 줄, 각주)` 를 돌려준다.
    """
    if len(deck.rows("elastic")) <= 1:
        return [], []
    return (
        ["$ *MAT_024 E and PR are temperature independent: lowest-temperature value."],
        [
            "온도별 탄성 표가 있는데 *MAT_024 의 E · PR 은 상수 하나입니다 — 블록의 대푯값"
            "(가장 낮은 온도)을 썼습니다."
        ],
    )


def _mat024_head(deck: Deck, yield_stress: float, lcss: int, vp: float | None) -> list[str]:
    """*MAT_024 카드 넷 — 1(탄성·SIGY) · 2(C·P·LCSS·LCSR·VP) · 3(EPS) · 4(ES)."""
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None
    lines = ["*MAT_PIECEWISE_LINEAR_PLASTICITY"]
    lines.append(
        "$      mid        ro         e        pr      sigy      etan      fail      tdel"
    )
    lines.append(
        _i10(deck.solver_id)
        + _f10(density)
        + _f10(youngs)
        + _f10(poisson)
        + _f10(yield_stress)
    )
    lines.append("$        c         p      lcss      lcsr        vp")
    # C·P(Cowper-Symonds)는 비운다 — LCSS 가 표면 둘 다 안 쓰이고, 곡선이면 잰 값이
    # 없는 자리다. 0 을 적는 것과 비우는 것이 LS-DYNA 에서는 같지만, 칸을 그려 두면
    # 넣을 자리가 보인다.
    card2 = " " * 20 + _i10(lcss)
    if vp is not None:
        card2 += " " * 10 + f"{vp:>10.1f}"
    lines.append(card2)
    # 3·4번 카드는 LCSS 가 있으면 안 쓰이지만 **카드는 있어야 한다** — 빼면 다음
    # 키워드 앞의 줄이 EPS 자리로 읽힌다.
    lines.append(
        "$     eps1      eps2      eps3      eps4      eps5      eps6      eps7      eps8"
    )
    lines.append(_zeros())
    lines.append(
        "$      es1       es2       es3       es4       es5       es6       es7       es8"
    )
    lines.append(_zeros())
    return lines


@register_renderer(
    key="dyna",
    label="LS-DYNA (탄소성)",
    extension="k",
    describe="*MAT_PIECEWISE_LINEAR_PLASTICITY(024) + *DEFINE_CURVE — 표 형식 소성.",
    keywords=("*KEYWORD", "*MAT_PIECEWISE_LINEAR_PLASTICITY", "*DEFINE_CURVE", "*END"),
    needs=(
        # RO 는 자리 있는 필드다 — 동적 해석 솔버라 비울 수 없다(OpenRadioss 와 같다).
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("table", rows_min=MIN_POINTS),
    ),
)
def render_dyna(deck: Deck) -> Rendered:
    """LS-DYNA `*MAT_024` — 진응력·진소성변형률 표 소성.

    SIGY 는 표의 첫 점(항복점)에서 온다. LCSS 가 있으면 솔버는 ETAN 을 안 보므로
    0 으로 두고, 곡선 번호는 재료 번호와 같은 수를 쓴다(다른 이름 공간이라 겹쳐도
    된다 — 사람이 덱 안에서 짝을 알아보기 쉽다).
    """
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    flat, said = _flat_elastic(deck)
    lines.extend(flat)
    notes.extend(said)
    lines.extend(_mat024_head(deck, points[0][1], deck.solver_id, None))
    # 소성변형률이 먼저, 응력이 나중 — *DEFINE_CURVE 는 (가로축, 세로축)이다.
    lines.extend(_curve(deck.solver_id, points))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def _cut(points: list[tuple[float, float]], end: float) -> list[tuple[float, float]]:
    """`end` 에서 자른다. 끝점은 **이웃 두 점 사이의 직선**으로 읽는다 — 잰 구간 안이다."""
    kept = [point for point in points if point[0] < end]
    if points[-1][0] == end or any(x == end for x, _ in points):
        return [*kept, next(point for point in points if point[0] == end)]
    after = next(point for point in points if point[0] > end)
    before = kept[-1]
    ratio = (end - before[0]) / (after[0] - before[0])
    return [*kept, (end, before[1] + ratio * (after[1] - before[1]))]


def _stress_at(points: list[tuple[float, float]], x: float) -> float:
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _rate_curve_id(deck: Deck, index: int) -> int:
    """속도 곡선 번호 — `재료 번호 * 100 + 차례`. 표 번호가 재료 번호를 쓰고, 표와 곡선은
    **번호 공간을 함께 쓴다** — 겹치면 LS-DYNA 가 중복 번호로 멈춘다."""
    return deck.solver_id * 100 + index


@register_renderer(
    key="dyna_rate",
    label="LS-DYNA (속도 의존)",
    extension="k",
    suffix="_rate",
    describe=(
        "*MAT_024 + *DEFINE_TABLE(변형률 속도) + 속도마다 *DEFINE_CURVE — 속도별 소성 표를 "
        "그대로 싣는다. 곡선은 소성변형률 속도로 고른다(VP=1)."
    ),
    keywords=(
        "*KEYWORD",
        "*MAT_PIECEWISE_LINEAR_PLASTICITY",
        "*DEFINE_TABLE",
        "*DEFINE_CURVE",
        "*END",
    ),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        # 속도가 하나뿐이면 이 덱을 낼 이유가 없다 — 그건 `dyna` 가 한다.
        Need(
            "rate_table",
            values=("rate_count",),
            at_least=(("rate_count", 2),),
            rows_min=2 * MIN_POINTS,
        ),
    ),
)
def render_dyna_rate(deck: Deck) -> Rendered:
    """LCSS 가 표(*DEFINE_TABLE)를 가리키면 *MAT_024 는 **속도마다 곡선**을 쓴다.

    ## 표의 규칙 셋(R13·R17 매뉴얼)

        값(속도)은 오름차순, 곡선은 표 **바로 뒤에 값의 차례대로** — 번호가 아니라
                                                   자리로 짝짓는다
        곡선이 **같은 x 에서 시작하고 끝나야** 한다 — 우리 곡선은 속도 묶음마다 공통
                                                   구간이 달라 끝이 다르다
        곡선이 서로 **교차하면 안 된다**(시작점 제외)

    끝이 다르면 **가장 짧은 곡선의 끝에서 모두 자르고 그 사실을 적는다.** 긴 곡선을
    늘리는 것은 값을 지어내는 일이다. 교차는 막지 않고 적는다 — 높은 속도에서 열 연화가
    실제로 그럴 수 있고, 거부하면 사람은 시스템 밖에서 표를 고친다.

    ## VP=1

    소성변형률 속도로 곡선을 고른다. VP=0(전체 변형률 속도)은 탄성파의 떨림이 항복응력에
    그대로 실린다 — dynasupport 가 VP=1 을 권한다. 시험의 속도는 전체 변형률 속도지만
    소성 구간에서는 거의 같다.
    """
    curves, notes = rate_curves(deck)
    end = min(points[-1][0] for _, points in curves)
    cut = [(rate, _cut(points, end)) for rate, points in curves]
    trimmed = [rate for rate, points in curves if points[-1][0] > end]
    if trimmed:
        notes.append(
            f"속도별 곡선의 끝이 달라 모두 소성변형률 {end:.4g} 에서 잘랐습니다 — LS-DYNA "
            f"표는 곡선이 같은 x 에서 끝나야 합니다. 잘린 속도: "
            f"{', '.join(f'{rate:.3g}' for rate in trimmed)} 1/s. 그 뒤는 LS-DYNA 가 마지막 "
            f"기울기로 늘입니다."
        )
    crossed = [
        (low_rate, high_rate)
        for (low_rate, low), (high_rate, high) in pairwise(cut)
        if any(_stress_at(high, x) < y for x, y in low[1:])
    ]
    if crossed:
        notes.append(
            "**속도가 높은데 응력이 낮은 구간이 있습니다** — 곡선이 교차합니다("
            + ", ".join(f"{a:.3g}↔{b:.3g} 1/s" for a, b in crossed)
            + "). LS-DYNA 표는 곡선이 교차하지 않아야 한다고 요구합니다. 막지는 않았습니다 "
            "— 결과를 확인하세요."
        )
    lcint = max(DEFAULT_LCINT, *(len(points) for _, points in cut))
    table_id = deck.solver_id

    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    flat, said = _flat_elastic(deck)
    lines.extend(flat)
    notes.extend(said)
    lines.append(
        f"$ Strain rate dependent: {len(cut)} rates "
        f"({cut[0][0]:.4g} ~ {cut[-1][0]:.4g} per time unit), tabulated, VP=1."
    )
    lines.append("$ Outside the tested rates LS-DYNA uses the first or last curve.")
    if trimmed:
        lines.append(
            f"$ All curves cut at plastic strain {end:.6g} (a table needs one x range)."
        )
    if crossed:
        lines.append("$ WARNING: curves cross - LS-DYNA requires non-crossing table curves.")
    model = deck.values("rate_table").get("model")
    if model == "cowper_symonds":
        d, p = deck.number("rate_table", "cs_d"), deck.number("rate_table", "cs_p")
        if d is not None and p is not None:
            lines.append(f"$ Cowper-Symonds summary (not used): C={d:.6g}, P={p:.6g}")
    lines.extend(_mat024_head(deck, cut[0][1][0][1], table_id, 1.0))
    lines.append("*DEFINE_TABLE")
    lines.append("$     tbid       sfa      offa")
    lines.append(_i10(table_id))
    lines.append("$  strain rate (ascending, one per line)")
    lines.extend(f"{rate:>20.12E}" for rate, _ in cut)
    # **곡선은 표 바로 뒤에, 값의 차례대로.** 짝은 번호가 아니라 자리다. LCINT 는 모두
    # 같아야 하고, 점이 기본(100)보다 많으면 그만큼 올려 솔버가 곡선을 성기게 다시
    # 나누지 않게 한다.
    for index, (_, points) in enumerate(cut, start=1):
        lines.extend(_curve(_rate_curve_id(deck, index), points, lcint))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="dyna_viscoelastic",
    label="LS-DYNA (점탄성)",
    extension="k",
    suffix="_viscoelastic",
    describe=(
        "*MAT_GENERAL_VISCOELASTIC(076) — 다항 Prony 전단 완화 + 장기 탄성률(β=0 항). "
        "체적은 탄성(K 상수)으로 둔다."
    ),
    keywords=("*KEYWORD", "*MAT_GENERAL_VISCOELASTIC", "*END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("viscoelastic", rows_min=1),
    ),
)
def render_dyna_viscoelastic(deck: Deck) -> Rendered:
    """LS-DYNA `*MAT_076` — Prony 급수 전단 완화.

    우리 행은 상대 탄성률 `g_i` 와 완화 시간 `τ_i` 인데 076 은 **전단 절대값
    `G_i` 와 감쇠 상수 `β_i = 1/τ_i`** 를 받는다. 유도식은 덱 주석에 적는다 —
    G0 = E/(2(1+ν)), K = E/(3(1-2ν)). 인장 E 를 전단으로 돌리는 것은 푸아송비가
    시간에 안 변한다는 가정이고(Abaqus 점탄성과 같은 가정), 그것도 적는다.

    ## 장기 탄성률은 β=0 항이다

    076 의 완화 함수는 `g(t) = Σ Gᵢ·exp(-βᵢ t)` 뿐이고 **평형 탄성률 칸이 없다.** 전에는
    Prony 항만 적어서 재료가 끝내 전단 강성 0 으로 흘러내렸다 — 고무가 유체가 된다.
    G∞ = (1 - Σgᵢ)·G0 를 β=0 항으로 앞에 둔다. 그러면 g(0) = G∞ + ΣGᵢ = G0 다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    reference = deck.number("viscoelastic", "reference_temperature_k")
    assert youngs is not None and poisson is not None and density is not None
    if poisson >= 0.5:
        raise ExportError(
            f"푸아송비가 {poisson:g} 입니다 — 0.5 이상이면 체적 탄성률이 발산합니다."
        )
    rows = deck.rows("viscoelastic")
    if len(rows) > MAX_PRONY_TERMS - 1:
        raise ExportError(
            f"Prony 가 {len(rows)}항입니다 — *MAT_076 은 항 카드를 {MAX_PRONY_TERMS}항까지 "
            f"받고 그중 한 장이 장기 탄성률이라 Prony 는 {MAX_PRONY_TERMS - 1}항까지입니다. "
            f"적합의 항 수를 줄이세요."
        )
    prony = prony_terms(deck)
    total = sum(g for g, _ in prony)

    shear = youngs / (2.0 * (1.0 + poisson))
    bulk = youngs / (3.0 * (1.0 - 2.0 * poisson))
    long_term = (1.0 - total) * shear

    notes: list[str] = [
        f"Prony {len(prony)}항, 상대 탄성률 합 {total:.4f} "
        f"(평형은 순간의 {1 - total:.4f} 배) — 평형 탄성률을 β=0 항으로 함께 적었습니다.",
        "인장 E 를 전단 G 로 돌렸습니다 — 푸아송비가 시간에 안 변한다는 가정입니다.",
    ]
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    lines.append(f"$ G0 = E/(2(1+nu)) = {shear:.6E}   (E={youngs:.6E}, nu={poisson:g})")
    lines.append(f"$ K  = E/(3(1-2nu)) = {bulk:.6E}   - bulk stays elastic (not measured)")
    lines.append(f"$ Ginf = (1 - sum gi) G0 = {long_term:.6E}  - first term, BETA = 0")
    lines.append("$ Gi = gi * G0,  BETAi = 1/tau_i   - shear ratios from tensile/flexural E")
    shift = viscoelastic_shift(deck) if reference is not None else None
    # **Arrhenius 만 싣는다**(2026-10-07). 매뉴얼(R16 Vol II *MAT_076 Remarks)의 Arrhenius 는
    # `Φ = exp[-A(1/T - 1/TREF)]`, 시간을 Φ 로 곱한다 — A = Ea/R 이면 우리 a_T 의 역수라 맞다.
    # 같은 쪽의 WLF `Φ = exp(-A(T-TREF)/(B+T-TREF))` 는 A>0 이면 뜨거울수록 **느려지는** 부호라
    # Arrhenius 와 서로 어긋난다 — 어느 부호로 넣어야 하는지 글로 확인할 수 없어 WLF 는 안
    # 싣는다.
    energy = shift[1][0] if shift is not None and shift[0] == "arrhenius" else None
    if reference is not None and energy is not None:
        lines.append(
            f"$ Prony fitted at {reference:.2f} K ({reference - 273.15:.2f} C); "
            f"Arrhenius shift on card 1 (TREF, A = Ea/R, B = 0)."
        )
        low = deck.number("viscoelastic", "shift_temperature_min_k")
        high = deck.number("viscoelastic", "shift_temperature_max_k")
        if low is not None and high is not None:
            lines.append(
                f"$ Shift measured over {low:.2f}~{high:.2f} K - extrapolated outside."
            )
        notes.extend(viscoelastic_shift_notes(deck, "arrhenius", "*MAT_076 TREF · A"))
    elif reference is not None:
        lines.append(
            f"$ Valid at {reference:.2f} K only - master curve reference temperature."
        )
        notes.append(
            f"기준 온도 {reference - 273.15:.1f} °C 에서만 유효하다는 사실을 덱 주석에 "
            f"적었습니다."
        )
        if shift is not None:
            lines.append(
                "$ WLF shift not written - the *MAT_076 manual prints WLF and Arrhenius "
                "with opposite signs."
            )
            notes.append(
                "LS-DYNA *MAT_076 매뉴얼은 WLF 식과 Arrhenius 식을 서로 어긋나는 부호로 적고 "
                "있어, WLF 상수를 어느 부호로 넣어야 하는지 확인할 수 없습니다 — WLF 이동은 "
                "싣지 않았습니다."
            )
    else:
        notes.append(
            "기준 온도가 카드에 없어 덱에 적지 못했습니다. 이 카드가 어느 온도의 "
            "것인지 덱만으로는 알 수 없습니다."
        )
    lines.append("*MAT_GENERAL_VISCOELASTIC")
    if reference is not None and energy is not None:
        # 1번 카드: MID RO BULK PCF EF TREF A B — B = 0 이면 Arrhenius 를 쓴다(매뉴얼 Remarks).
        lines.append(
            "$      mid        ro      bulk       pcf        ef      tref         a         b"
        )
        lines.append(
            _i10(deck.solver_id)
            + _f10(density)
            + _f10(bulk)
            + " " * 20
            + _f10(reference)
            + _f10(energy / GAS_CONSTANT)
            + _f10(0.0)
        )
    else:
        lines.append("$      mid        ro      bulk      pcf       ef      tref")
        lines.append(_i10(deck.solver_id) + _f10(density) + _f10(bulk))
    # **2번 카드는 비워도 있어야 한다** — 「Prony 카드를 쓰면 비워 두라」 는 칸이지
    # 빼도 되는 카드가 아니다. 빼면 첫 Prony 줄이 LCID·NT 로 읽힌다.
    lines.append(
        "$     lcid        nt    bstart     tramp     lcidk       ntk   bstartk    trampk"
    )
    lines.append(_zeros())
    lines.append("$       gi     betai")
    lines.append(_f10(long_term) + _f10(0.0))
    lines.extend(_f10(g * shear) + _f10(1.0 / tau) for g, tau in prony)
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="dyna_hyperelastic",
    label="LS-DYNA (초탄성)",
    extension="k",
    suffix="_hyperelastic",
    describe=(
        "Neo-Hookean·Mooney-Rivlin 은 *MAT_027, Yeoh 는 *MAT_077_H, Ogden 은 *MAT_077_O. "
        "비압축 정도는 카드의 푸아송비로 준다(0.495~0.4995)."
    ),
    keywords=("*KEYWORD", "*MAT_", "*END"),
    needs=(
        Need("hyperelastic", rows_min=1),
        # **푸아송비를 지어내지 않는다.** 명시적 솔버는 체적 강성이 있어야 돌고, 그 값을
        # 0.4995 로 채우면 잰 값인지 우리가 넣은 값인지 덱에서 모른다.
        Need("elastic", values=("poisson_ratio", "density")),
    ),
)
def render_dyna_hyperelastic(deck: Deck) -> Rendered:
    """식마다 키워드가 갈린다. 계수는 이름으로 찾아 옮긴다.

    Neo-Hookean    *MAT_027  A = C10, B = 0
    Mooney-Rivlin  *MAT_027  A = C10, B = C01          (전단탄성률 2(A+B))
    Yeoh           *MAT_077_H  C10·C20·C30 (N=0, 계수 직접)
    Ogden(1항)     *MAT_077_O  MU1 = 2μ/α, ALPHA1 = α — 077_O 는 W = Σ μ/α (λ^α - 1)
                               이라 G = Σμα/2 다. 우리 μ 는 Abaqus 규약(G = μ)이다.
    """
    family, values = hyperelastic_terms(deck)
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert poisson is not None and density is not None
    if not 0.0 < poisson < 0.5:
        raise ExportError(
            f"푸아송비가 {poisson:g} 입니다 — 고무 카드는 0 과 0.5 사이여야 합니다(0.5 면 "
            f"체적 탄성률이 발산합니다). 보통 0.495~0.4995 입니다."
        )

    notes: list[str] = []
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    lines.append("$ Nominal (engineering) stress fit - uniaxial data only.")
    lines.append(f"$ PR = {poisson:g} from the card sets the bulk stiffness.")
    if poisson < 0.49:
        notes.append(
            f"푸아송비가 {poisson:g} 로 고무치고 낮습니다 — 체적이 쉽게 변하는 재료로 "
            f"계산됩니다. 보통 0.495~0.4995 입니다."
        )
    head = _i10(deck.solver_id) + _f10(density) + _f10(poisson)
    if family in ("neo_hookean", "mooney_rivlin"):
        c01 = values.get("c01", 0.0)
        lines.append(
            f"$ A = C10, B = C01 ({family}); "
            f"shear modulus 2(A+B) = {2 * (values['c10'] + c01):.6g}"
        )
        lines.append("*MAT_MOONEY-RIVLIN_RUBBER")
        lines.append("$      mid        ro        pr         a         b       ref")
        lines.append(head + _f10(values["c10"]) + _f10(c01) + _f10(0.0))
        # 2번 카드는 시험 데이터로 맞출 때 쓰는 칸이다. 0 이면 A·B 를 그대로 쓴다 —
        # **비워도 있어야 한다.**
        lines.append("$      sgl        sw        st      lcid")
        lines.append(_zeros(4))
    elif family == "yeoh":
        lines.append("$ Yeoh = polynomial with C10, C20, C30 only (N=0: coefficients given).")
        lines.append("*MAT_HYPERELASTIC_RUBBER")
        lines.append(
            "$      mid        ro        pr         n        nv         g      sigf       ref"
        )
        lines.append(head + _zeros(5))
        lines.append("$      c10       c01       c11       c20       c02       c30    therml")
        lines.append(
            _f10(values["c10"])
            + _f10(0.0)
            + _f10(0.0)
            + _f10(values["c20"])
            + _f10(0.0)
            + _f10(values["c30"])
            + f"{0:>10}"
        )
    else:
        mu, alpha = values["mu"], values["alpha"]
        converted = 2.0 * mu / alpha
        lines.append(
            f"$ MU1 = 2*mu/alpha = {converted:.6g} (card mu is the Abaqus convention, "
            f"G = mu = {mu:.6g}); 077_O: G = sum(mu*alpha)/2"
        )
        notes.append(
            f"Ogden μ 를 *MAT_077_O 의 규약으로 옮겼습니다 — MU1 = 2μ/α = {converted:.6g}. "
            f"초기 전단탄성률 {mu:.6g} 는 그대로입니다."
        )
        lines.append("*MAT_OGDEN_RUBBER")
        lines.append(
            "$      mid        ro        pr         n        nv         g      sigf       ref"
        )
        lines.append(head + _zeros(5))
        lines.append(
            "$      mu1       mu2       mu3       mu4       mu5       mu6       mu7       mu8"
        )
        lines.append(_f10(converted))
        lines.append(
            "$   alpha1    alpha2    alpha3    alpha4    alpha5    alpha6    alpha7    alpha8"
        )
        lines.append(_f10(alpha))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="dyna_thermal",
    label="LS-DYNA (열물성)",
    extension="k",
    suffix="_thermal",
    describe="*MAT_THERMAL_ISOTROPIC — 열해석용 재료(비열·전도도, 상수).",
    keywords=("*KEYWORD", "*MAT_THERMAL_ISOTROPIC", "*END"),
    needs=(
        Need("thermal", values=("specific_heat", "thermal_conductivity")),
        # 밀도(TRO)는 있으면 적고 없으면 비운다 — 열해석 형태에 따라 필요가 갈린다.
        Need("elastic", optional=True),
    ),
)
def render_dyna_thermal(deck: Deck) -> Rendered:
    """LS-DYNA `*MAT_THERMAL_ISOTROPIC` — 상수 비열·전도도.

    이 키워드는 표(온도 의존)를 받지 않는다 — 온도 의존은 *MAT_THERMAL_ISOTROPIC_TD 다.
    카드에 온도별 열물성 표가 있으면 **첫 줄(가장 낮은 온도)을 쓰고 그렇다고 적는다.**
    여기 설명은 전에 「조용히 누르지 않는다」 였는데, 코드는 표를 보지 않고 첫 값을 그냥
    썼다(2026-10-07 — 모든 형식에서 표의 둘째 줄을 바꿔 보는 점검에서 드러났다).
    """
    heat = deck.number("thermal", "specific_heat")
    conductivity = deck.number("thermal", "thermal_conductivity")
    density = deck.number("elastic", "density")
    assert heat is not None and conductivity is not None

    notes: list[str] = []
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    tabled = [
        row
        for row in deck.rows("thermal")
        if "specific_heat" in row or "thermal_conductivity" in row
    ]
    if len(tabled) > 1:
        notes.append(
            "온도별 열물성 표가 있는데 *MAT_THERMAL_ISOTROPIC 의 비열 · 열전도율은 "
            "상수 하나입니다 — 블록의 대푯값(가장 낮은 온도)을 썼습니다. 온도 의존은 "
            "*MAT_THERMAL_ISOTROPIC_TD 가 받습니다."
        )
        lines.append(
            "$ *MAT_THERMAL_ISOTROPIC is temperature independent: lowest-temperature value."
        )
    for key in ("specific_heat", "thermal_conductivity"):
        source = deck.values("thermal").get(f"{key}_source")
        lines.append(f"$ {key}: source={source or 'unknown'}")
    if density is None:
        notes.append("밀도가 카드에 없어 TRO 를 비우고 그 사실을 덱 주석에 적었습니다.")
        lines.append("$ TRO: no measured density on this card - field left blank.")
    lines.append("*MAT_THERMAL_ISOTROPIC")
    lines.append("$     tmid       tro     tgrlc    tgmult")
    lines.append(_i10(deck.solver_id) + (_f10(density) if density is not None else ""))
    lines.append("$       hc        tc")
    lines.append(_f10(heat) + _f10(conductivity))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
