"""LS-DYNA 렌더러 — *MAT_024 · *MAT_076 · *MAT_THERMAL_ISOTROPIC.

MaterialTwin 이식 2단계(ADR 0027 계획). 원본 `dyna_export.py` 를 통째로 옮기지
않고 **우리 렌더러 틀에 다시 썼다** — 단위계 적용(`to_system`)·모자람 검사·출처
주석(`_header`)은 틀이 이미 하므로 여기는 키워드를 쓰는 일만 한다.

## 고정 10칸이다

LS-DYNA 표준 키워드 형식은 한 줄 8필드, 필드당 10칸이다. 칸이 어긋나면 다른
필드로 읽히고 **솔버는 오류 없이 엉뚱한 재료로 계산한다** — OpenRadioss 의
20칸과 같은 성격의 함정이다. 곡선 점만 20칸 둘(*DEFINE_CURVE 의 관행)이다.

## 단위는 주석으로 선언한다

LS-DYNA 에는 단위 키워드가 없다(Abaqus 와 같다). 값은 `render()` 가 이미 고른
계로 바꿔 놓았고, 여기서는 그 계를 `$` 주석으로 크게 적는다 — 관행 계
(ton·mm·s = MPa)는 사용자 정의 단위계(`systems.derive`)로 고른다.
"""

from __future__ import annotations

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _header,
    prepare,
    register_renderer,
)

#: *MAT_GENERAL_VISCOELASTIC 이 받는 최대 항 수.
MAX_PRONY_TERMS = 18


def _f10(value: float) -> str:
    """고정 10칸 숫자. 유효숫자 4자리 — 칸이 어긋나면 다른 필드다."""
    return f"{value:>10.3E}"


def _i10(value: int) -> str:
    return f"{value:>10d}"


def _units_comment(deck: Deck) -> list[str]:
    return [
        "$ Consistent units: " + deck.units.declaration,
        "$   (LS-DYNA declares no units - every material in this deck must match.)",
    ]


@register_renderer(
    key="dyna",
    label="LS-DYNA",
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
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    assert youngs is not None and poisson is not None and density is not None
    yield_stress = points[0][1]

    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    lines.append("*MAT_PIECEWISE_LINEAR_PLASTICITY")
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
    lines.append("$        c         p      lcss      lcsr")
    # C·P(Cowper-Symonds)는 잰 값이 없으면 비운다 — 0 을 적는 것과 비우는 것이
    # LS-DYNA 에서는 같지만, 칸을 그려 두면 넣을 자리가 보인다.
    lines.append(" " * 10 + " " * 10 + _i10(deck.solver_id))
    lines.append("*DEFINE_CURVE")
    lines.append("$     lcid      sidr       sfa       sfo      offa      offo    dattyp")
    lines.append(_i10(deck.solver_id))
    lines.append("$                 a1                  o1")
    # 소성변형률이 먼저, 응력이 나중 — *DEFINE_CURVE 는 (가로축, 세로축)이다.
    lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in points)
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="dyna_viscoelastic",
    label="LS-DYNA (점탄성)",
    extension="k",
    suffix="_viscoelastic",
    describe=(
        "*MAT_GENERAL_VISCOELASTIC(076) — 다항 Prony 전단 완화. 체적은 탄성(K 상수)으로 둔다."
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
    """
    prony = tuple(
        (float(row["relative_modulus"]), float(row["relaxation_time_s"]))
        for row in deck.rows("viscoelastic")
        if "relative_modulus" in row and "relaxation_time_s" in row
    )
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    reference = deck.number("viscoelastic", "reference_temperature_k")
    assert youngs is not None and poisson is not None and density is not None
    if not prony:
        raise ExportError(
            "점탄성 카드인데 Prony 계수가 없습니다. 마스터커브를 만들고 "
            "Prony 를 맞춘 뒤에 내보내세요."
        )
    if len(prony) > MAX_PRONY_TERMS:
        raise ExportError(
            f"Prony 가 {len(prony)}항입니다 — *MAT_076 은 {MAX_PRONY_TERMS}항까지 "
            f"받습니다. 적합의 항 수를 줄이세요."
        )
    if poisson >= 0.5:
        raise ExportError(
            f"푸아송비가 {poisson:g} 입니다 — 0.5 이상이면 체적 탄성률이 발산합니다."
        )
    total = sum(g for g, _ in prony)
    if total >= 1.0:
        raise ExportError(
            f"Prony 상대 탄성률의 합이 {total:.4f} 로 1 이상입니다. "
            f"평형 탄성률이 0 이하라는 뜻이라 솔버가 거부합니다."
        )

    shear = youngs / (2.0 * (1.0 + poisson))
    bulk = youngs / (3.0 * (1.0 - 2.0 * poisson))

    notes: list[str] = [
        f"Prony {len(prony)}항, 상대 탄성률 합 {total:.4f} "
        f"(평형은 순간의 {1 - total:.4f} 배).",
        "인장 E 를 전단 G 로 돌렸습니다 — 푸아송비가 시간에 안 변한다는 가정입니다.",
    ]
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
    lines.append(f"$ G0 = E/(2(1+nu)) = {shear:.6E}   (E={youngs:.6E}, nu={poisson:g})")
    lines.append(f"$ K  = E/(3(1-2nu)) = {bulk:.6E}   - bulk stays elastic (not measured)")
    lines.append("$ Gi = gi * G0,  BETAi = 1/tau_i   - shear ratios from tensile/flexural E")
    if reference is not None:
        lines.append(
            f"$ Valid at {reference:.2f} K only - master curve reference temperature."
        )
        notes.append(
            f"기준 온도 {reference - 273.15:.1f} °C 에서만 유효하다는 사실을 덱 주석에 "
            f"적었습니다."
        )
    else:
        notes.append(
            "기준 온도가 카드에 없어 덱에 적지 못했습니다. 이 카드가 어느 온도의 "
            "것인지 덱만으로는 알 수 없습니다."
        )
    lines.append("*MAT_GENERAL_VISCOELASTIC")
    lines.append("$      mid        ro      bulk      pcf       ef      tref")
    lines.append(_i10(deck.solver_id) + _f10(density) + _f10(bulk))
    lines.append("$       gi     betai")
    lines.extend(_f10(g * shear) + _f10(1.0 / tau) for g, tau in prony)
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

    이 키워드는 표(온도 의존)를 받지 않는다 — 온도 의존이 필요하면
    *MAT_THERMAL_ISOTROPIC_TD 인데, 그건 표가 카드에 실릴 때 만든다. 값이
    표에서 온 경우(첫 값만 쓰는 것)는 **조용히 누르는 일**이라 하지 않는다.
    """
    heat = deck.number("thermal", "specific_heat")
    conductivity = deck.number("thermal", "thermal_conductivity")
    density = deck.number("elastic", "density")
    assert heat is not None and conductivity is not None

    notes: list[str] = []
    lines = ["*KEYWORD", *_header(deck, "$"), *_units_comment(deck)]
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
