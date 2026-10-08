"""Hill48 솔버 덱 — **이방성 카드 + 짝 카드(기준 방향의 경화 곡선·탄성)**.

이방성 카드에는 r 셋만 있다(ADR 0034 — 세 방향을 가로지르므로 방향이 없다). Hill 재료는
거기에 **압연 방향(MD)의 경화 곡선과 탄성**이 한 재료에 함께 들어가야 한다. 카드를 합쳐
새 카드를 만들지 않고 **내보낼 때 짝 카드를 고른다**(`/fitting/cards/{id}/export?with_card=`,
ADR 0037). 그래서 여기 형식은 셋을 요구한다: `anisotropy` · `elastic` · `table`.

## 곡선은 기준 방향의 것이어야 한다

Hill48 의 항복응력비는 기준 방향(R11 = 1)에 대한 비다. 짝 카드가 TD 곡선이면 모든 비가
엇나가는데 덱은 멀쩡히 돈다 — 형식이 그것을 알 길이 없어(짝 카드의 방향은 덱에 안 온다)
**덱에 적고 사람이 고른다.** 짝 카드 목록이 방향을 함께 보인다.

## r 에서 항복응력비로 (Abaqus 이방 항복 문서, 평면 응력, x = 압연 방향)

    R11 = 1
    R22 = √[ r90(r0+1) / (r0(r90+1)) ]
    R33 = √[ r90(r0+1) / (r0+r90) ]
    R12 = √[ 3·r90(r0+1) / ((2·r45+1)(r0+r90)) ]
    R13 = R23 = 1        판재 시험으로는 못 정한다 — 관례값이고, 그 사실을 적는다

**ANSYS 와 Abaqus 는 끝 둘의 차례가 반대다**(ANSYS `…R12, R23, R13` · Abaqus `…R12, R13,
R23`). 지금은 둘 다 1 이라 같은 줄이 나오지만, 언젠가 둘이 달라지는 날 조용히 뒤바뀌지
않게 이름으로 적는다.

OptiStruct `PLASTIC`(2026)은 항복응력비를 받고 차례가 `R11 R22 R33 R12 R31 R23` 이다(Abaqus 와
같은 끝 둘). LS-DYNA `*MAT_036`(M=2)과 Radioss LAW43 은 r 셋을 **그대로** 받는다 — 옮길
것이 없다. 둘 다 **쉘 전용**이다.
"""

from __future__ import annotations

import math

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _elastic_lines,
    _fixed,
    _free,
    _header,
    _thermal_lines,
    prepare,
    register_renderer,
)
from matcore.export import ansys as _ansys
from matcore.export import bulk as _bulk
from matcore.export import dyna as _dyna
from matcore.export import radioss as _radioss

#: 형식마다 같은 요구 — r 셋, 탄성, 기준 방향의 경화 곡선.
_R_VALUES = ("r_0", "r_45", "r_90")

_PAIR_NOTE = (
    "경화 곡선·탄성은 짝 카드에서 왔습니다 — 그 카드가 압연 방향(MD) 곡선이어야 항복응력비가 "
    "맞습니다(R11 = 1 이 그 방향입니다)."
)


def _needs(*, density: bool) -> tuple[Need, ...]:
    elastic = (
        ("youngs_modulus", "poisson_ratio", "density")
        if density
        else (
            "youngs_modulus",
            "poisson_ratio",
        )
    )
    return (
        Need("anisotropy", values=_R_VALUES),
        Need("elastic", values=elastic),
        *(() if density else (Need("elastic", values=("density",), optional=True),)),
        Need("table", rows_min=MIN_POINTS),
    )


def _r_values(deck: Deck) -> tuple[float, float, float]:
    r0, r45, r90 = (deck.number("anisotropy", key) for key in _R_VALUES)
    assert r0 is not None and r45 is not None and r90 is not None
    if min(r0, r45, r90) <= 0.0:
        raise ExportError(
            f"r 값이 0 이하입니다(r₀={r0:g}, r₄₅={r45:g}, r₉₀={r90:g}) — 소성 변형비는 "
            f"양수여야 합니다. 이방성 묶음을 다시 보세요."
        )
    return r0, r45, r90


def hill_ratios(r0: float, r45: float, r90: float) -> dict[str, float]:
    """Lankford r → Hill48 항복응력비. 이름으로 돌려준다 — 솔버마다 차례가 다르다."""
    return {
        "R11": 1.0,
        "R22": math.sqrt(r90 * (r0 + 1.0) / (r0 * (r90 + 1.0))),
        "R33": math.sqrt(r90 * (r0 + 1.0) / (r0 + r90)),
        "R12": math.sqrt(3.0 * r90 * (r0 + 1.0) / ((2.0 * r45 + 1.0) * (r0 + r90))),
        "R13": 1.0,
        "R23": 1.0,
    }


def _ratio_comment(prefix: str, ratios: dict[str, float], r: tuple[float, ...]) -> list[str]:
    return [
        f"{prefix} Hill48 from Lankford r0={r[0]:.4g}, r45={r[1]:.4g}, r90={r[2]:.4g} "
        f"(x = rolling direction, plane stress).",
        f"{prefix} R11=1 R22={ratios['R22']:.6g} R33={ratios['R33']:.6g} "
        f"R12={ratios['R12']:.6g}; R13=R23=1 by convention (sheet tests cannot fix them).",
        f"{prefix} Hardening curve must be the rolling-direction (MD) one "
        "- R11=1 is that direction.",
    ]


@register_renderer(
    key="abaqus_hill",
    label="Abaqus (이방성 Hill48)",
    extension="inp",
    suffix="_hill",
    describe=(
        "*PLASTIC + *POTENTIAL — r 셋에서 만든 Hill48 항복응력비. 이방성 카드에 MD 카드를 "
        "짝으로 골라 낸다(경화 곡선·탄성은 짝 카드에서)."
    ),
    keywords=("*MATERIAL", "*PLASTIC", "*POTENTIAL"),
    needs=_needs(density=False),
)
def render_abaqus_hill(deck: Deck) -> Rendered:
    """`*POTENTIAL` 은 `*PLASTIC` 데이터 **바로 뒤**여야 한다(Abaqus 문서)."""
    r = _r_values(deck)
    ratios = hill_ratios(*r)
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    density = deck.number("elastic", "density")
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.extend(_ratio_comment("**", ratios, r))
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(
        _elastic_lines(
            deck,
            deck.number("elastic", "youngs_modulus"),
            deck.number("elastic", "poisson_ratio"),
        )
    )
    lines.extend(_thermal_lines(deck))
    # **`EXTRAPOLATION=` 을 안 붙인다** — Abaqus 2022 에 생긴 인자라 그 전 판이 덱을
    # 못 읽고, 기본 동작이 이미 상수 외삽이다(중심은 2026-10-03, 이쪽은 2026-10-08).
    lines.append("*PLASTIC, HARDENING=ISOTROPIC")
    lines.extend(f"{_free(stress)}, {_free(strain)}" for strain, stress in points)
    lines.append("*POTENTIAL")
    lines.append(
        ", ".join(_free(ratios[key]) for key in ("R11", "R22", "R33", "R12", "R13", "R23"))
    )
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, _PAIR_NOTE))


@register_renderer(
    key="ansys_hill",
    label="ANSYS (이방성 Hill48)",
    extension="mac",
    suffix="_hill",
    describe=(
        "MP + TB,PLASTIC(MISO) + TB,HILL — r 셋에서 만든 항복응력비. 이방성 카드에 MD 카드를 "
        "짝으로 골라 낸다."
    ),
    keywords=("TB,PLASTIC", "TB,HILL"),
    needs=_needs(density=False),
)
def render_ansys_hill(deck: Deck) -> Rendered:
    """TBDATA 차례는 `R11, R22, R33, R12, R23, R13` 이다 — Abaqus 와 끝 둘이 반대."""
    r = _r_values(deck)
    ratios = hill_ratios(*r)
    lines, notes = _ansys._structural(deck)
    plastic, said = _ansys._plastic(deck)
    lines.extend(plastic)
    lines.extend(_ratio_comment("!", ratios, r))
    lines.append(f"TB,HILL,{_ansys.MATERIAL}")
    lines.append(
        "TBDATA,1,"
        + ",".join(_free(ratios[key]) for key in ("R11", "R22", "R33", "R12", "R23", "R13"))
    )
    return Rendered(text="\n".join(lines) + "\n", notes=(*said, *notes, _PAIR_NOTE))


@register_renderer(
    key="dyna_hill",
    label="LS-DYNA (이방성 Hill48 · 쉘)",
    extension="k",
    suffix="_hill",
    describe=(
        "*MAT_3-PARAMETER_BARLAT(036), M=2(= Hill48) + R00·R45·R90 + *DEFINE_CURVE — "
        "**쉘 전용**. "
        "이방성 카드에 MD 카드를 짝으로 골라 낸다."
    ),
    keywords=("*KEYWORD", "*MAT_3-PARAMETER_BARLAT", "*DEFINE_CURVE", "*END"),
    needs=_needs(density=True),
)
def render_dyna_hill(deck: Deck) -> Rendered:
    """`*MAT_036` 은 필수 카드가 다섯이다(1 · 2a · 4a · 5 · 6) — 쓸 값이 없어도 0 으로 채운다.

    M=2 에서 Barlat89 는 Hill48 이다(항복 함수가 이차가 되고 계수가 Hill 평면 응력 계수와
    같아진다). HR=3 은 LCID 가 곡선이라는 뜻이다. AOPT=0 이면 재료 축이 요소 절점
    1→2 방향이라 **요소를 압연 방향에 맞춰 만들어야** 한다 — 덱에 적는다.
    """
    r0, r45, r90 = _r_values(deck)
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    f10, i10, zeros = _dyna._f10, _dyna._i10, _dyna._zeros
    lines = ["*KEYWORD", *_header(deck, "$"), *_dyna._units_comment(deck)]
    lines.append("$ Hill48 = Barlat 1989 with M=2, R00/R45/R90 as measured (Lankford).")
    lines.append(
        "$ SHELLS ONLY. AOPT=0: material axis a = element node 1->2 - align with rolling."
    )
    lines.append("$ Hardening curve must be the rolling-direction (MD) one.")
    lines.append("*MAT_3-PARAMETER_BARLAT")
    lines.append(
        "$      mid        ro         e        pr        hr        p1        p2      iter"
    )
    lines.append(i10(deck.solver_id) + f10(density) + f10(youngs) + f10(poisson) + f10(3.0))
    lines.append(
        "$        m       r00       r45       r90      lcid        e0       spi        p3"
    )
    lines.append(f10(2.0) + f10(r0) + f10(r45) + f10(r90) + i10(deck.solver_id))
    lines.append(
        "$     aopt         c         p     vlcid               pb       hta       htb"
    )
    lines.append(zeros())
    lines.append("$                             a1        a2        a3       htc       htd")
    lines.append(zeros())
    lines.append(
        "$       v1        v2        v3        d1        d2        d3      beta    htflag"
    )
    lines.append(zeros())
    lines.extend(_dyna._curve(deck.solver_id, points))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, _PAIR_NOTE))


@register_renderer(
    key="openradioss_hill",
    label="Radioss (이방성 Hill48 · 쉘)",
    extension="rad",
    suffix="_hill",
    describe=(
        "/MAT/LAW43(HILL_TAB) + /FUNCT — r00·r45·r90 과 표 경화. **쉘 전용**(/PROP/TYPE9·10). "
        "이방성 카드에 MD 카드를 짝으로 골라 낸다."
    ),
    keywords=("/MAT/LAW43", "/FUNCT/", "/UNIT/1", "/END"),
    needs=_needs(density=True),
)
def render_openradioss_hill(deck: Deck) -> Rendered:
    """LAW43 은 곡선 줄에 개수 칸이 없다 — 다음 키워드까지가 목록이다(최대 10).

    **Iyield0 = 1 을 적는다.** 기본(0)은 곡선을 「평균 항복응력」 으로 읽어 항복 함수를 r̄ 로
    정규화한다(A₁ = H(1 + 1/r₀₀), H = r̄/(1 + r̄)). 우리 곡선은 압연 방향의 것이라 기본으로
    두면 그 방향 응력이 조용히 높게 나온다 — 돌려 봐서야 드러났다(r 은 맞게 나오고 응력만
    1.3% 높았다). 1 이면 곡선이 직교 방향 1(속성 /PROP/TYPE9 의 Vx)의 항복응력이다 — 그
    방향을 압연 방향에 둔다.

    끝 두 줄(ε_p^max … Fsmooth)은 기본값이라 **빈 줄**로 둔다 — Radioss 는 빈 줄도 한 줄로
    읽으므로 빼면 곡선 줄이 그 자리로 간다.
    """
    r0, r45, r90 = _r_values(deck)
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    fid = deck.solver_id
    lines = _radioss._starter(deck)
    lines.append(
        "# Hill48 from Lankford r00/r45/r90 as measured. SHELLS ONLY (/PROP/TYPE9 or 10)."
    )
    lines.append("# Hardening curve must be the rolling-direction (MD) one.")
    lines.append(f"/MAT/LAW43/{deck.solver_id}/1")
    lines.append(deck.name)
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(f"#{'E':>19}{'nu':>20}")
    lines.append(_fixed(youngs) + _fixed(poisson))
    lines.append(f"#{'fct_IDE':>9}{'':>10}{'Einf':>20}{'CE':>20}")
    lines.append(f"{0:>10}")
    lines.append(f"#{'r00':>19}{'r45':>20}{'r90':>20}{'Chard':>20}{'Iyield0':>10}")
    # **Iyield0 = 1** — 곡선이 직교 방향 1(= 압연 방향)의 항복응력이라는 뜻. 기본 0 은
    # 「평균 항복응력」 이라 r̄ 로 정규화한다: MD 곡선을 그대로 주면 압연 방향 응력이 √R22 배
    # 높게 나온다(r0=1.8·r45=1.4·r90=2.1 에서 1.3%, OpenRadioss 로 돌려 확인, 2026-09-27).
    lines.append(_fixed(r0) + _fixed(r45) + _fixed(r90) + f"{'':>20}{1:>10}")
    lines.append(f"#{'Eps_p_max':>19}{'Eps_t':>20}{'Eps_m':>20}{'Fcut':>20}{'Fsmooth':>10}")
    lines.append("")
    lines.append(f"#{'fct_ID':>9}{'':>10}{'Fscale':>20}{'Eps_dot':>20}")
    lines.append(f"{fid:>10}{'':>10}{_fixed(1.0)}{_fixed(0.0)}")
    lines.append(f"/FUNCT/{fid}")
    lines.append(f"{deck.name}_TRUE_STRESS_VS_TRUE_PLASTIC_STRAIN")
    lines.append(f"#{'X':>19}{'Y':>20}")
    lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in points)
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, _PAIR_NOTE))


@register_renderer(
    key="nastran_hill",
    label="Nastran (이방성 Hill48)",
    extension="bdf",
    suffix="_hill",
    describe=(
        "MAT1 + MATEP(FORM=TABLE, RYIELD=HILL, Aniso) + TABLES1(TYPE=2, 소성변형률) — SOL 400 "
        "전용. 이방성 카드에 MD 카드를 짝으로 골라 낸다."
    ),
    keywords=("MAT1*", "MATEP*", "TABLES1*", "ENDT"),
    needs=_needs(density=False),
)
def render_nastran_hill(deck: Deck) -> Rendered:
    """MSC 는 Hill 을 MATEP 로 받는다(SOL 400). Aniso 줄은 `R11 R22 R33 R12 R23 R31` —
    항복응력비이고, 차례는 ANSYS 와 같다(Abaqus 와 끝 둘이 반대).

    FORM=TABLE 이면 Y0 는 안 쓰인다 — 항복은 표의 첫 점이다. 표는 TYPE=2(진응력 대
    소성변형률)로 싣는다 — MATEP 는 둘 다 받고, 이쪽이 카드 표 그대로다.
    """
    r = _r_values(deck)
    ratios = hill_ratios(*r)
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    table = _bulk._table_id(deck, 0)
    lines = _bulk._head(deck, "MSC Nastran")
    lines.extend(_ratio_comment("$", ratios, r))
    lines.append("$ SOL 400 only - MATEP is the advanced plasticity entry.")
    body, said = _bulk._mat1(deck, with_tables=False)
    lines.extend(body)
    lines.append("$MATEP* MID             FORM            Y0              FID")
    lines.append("$*      RYIELD          WKHARD                          H")
    lines.append("$*      Aniso           N/A             R11             R22")
    lines.append("$*      R33             R12             R23             R31")
    lines.extend(
        _bulk._card(
            "MATEP",
            [
                deck.solver_id, "TABLE", None, table, "HILL", None, None, None,
                "Aniso", None, ratios["R11"], ratios["R22"],
                ratios["R33"], ratios["R12"], ratios["R23"], ratios["R13"],
            ],
        )
    )  # fmt: skip
    lines.append("$ TABLES1 TYPE=2: true stress vs PLASTIC strain, first point (0, yield).")
    body_table: list[_bulk.Field] = [table, 2, None, None, None, None, None, None]
    for strain, stress in points:
        body_table.extend((strain, stress))
    body_table.append("ENDT")
    lines.extend(_bulk._card("TABLES1", body_table))
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, *said, _PAIR_NOTE))


#: OptiStruct PLASTIC 의 TEMP 칸 — 「기본 없음, 0 보다 큼」. 줄이 하나면 보간할 것이 없어 모든
#: 온도에서 그 값을 쓴다(매뉴얼: 여러 줄이면 요소 온도로 보간). 상온(K)을 적고 덱에 말한다.
_OS_TEMP = 293.15


@register_renderer(
    key="optistruct_hill",
    label="OptiStruct (이방성 Hill48)",
    extension="fem",
    suffix="_hill",
    describe=(
        "MAT1 + PLASTIC(CRIT HILL 항복응력비 + HARD ISOT 표) — OptiStruct 2026 이상. 암시적 "
        "해석은 솔리드만, 쉘은 명시적 해석에서. 이방성 카드에 MD 카드를 짝으로 골라 낸다."
    ),
    keywords=("MAT1*", "PLASTIC*"),
    needs=_needs(density=False),
)
def render_optistruct_hill(deck: Deck) -> Rendered:
    """OptiStruct `PLASTIC`(Reference Guide 2026) — MAT1 에 소성을 얹는 모듈식 항목.

        PLASTIC  MID
                 CRIT  HILL
                 R11  R22  R33  R12  R31  R23  TEMP     ← 항복응력비, **R31 이 R23 앞**
                 HARD  ISOT
                 YIELD  PLAS  TEMP                       ← **응력이 먼저**(TABLES1 과 반대)
                 YIELD  PLAS

    항복응력비는 Abaqus · ANSYS 와 같은 값이다(Rii = σYii/σY, Rij = √3·τYij/σY) — `LANK`(r 를
    그대로 받는 꼴)를 안 쓰는 이유: 암시적 해석은 솔리드만 받는데 LANK 가 면외 계수를 어떻게
    정하는지 매뉴얼에 없다. 여기서는 R13 = R23 = 1 을 덱에 적어 둔다(다른 솔버와 같다).

    **2026 도움말에만 있는 항목**이다 — 그 이전 판은 읽지 못한다(덱에 적는다).
    """
    r = _r_values(deck)
    ratios = hill_ratios(*r)
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    lines = _bulk._head(deck, "OptiStruct")
    lines.extend(_ratio_comment("$", ratios, r))
    lines.append(
        "$ PLASTIC needs OptiStruct 2026 or later. Implicit analysis: SOLID elements only;"
    )
    lines.append("$   shells only in explicit analysis.")
    lines.append(
        f"$ TEMP = {_OS_TEMP:g} (one data set - OptiStruct uses it at every temperature)."
    )
    body, said = _bulk._mat1(deck, with_tables=False)
    lines.extend(body)
    lines.append("$PLASTIC*MID")
    lines.append("$*      CRIT            HILL")
    lines.append("$*      R11             R22             R33             R12")
    lines.append("$*      R31             R23             TEMP")
    lines.append("$*      HARD            ISOT")
    lines.append("$*      YIELD           PLAS            TEMP")
    fields: list[_bulk.Field] = [
        deck.solver_id, None, None, None, None, None, None, None,
        "CRIT", "HILL", None, None, None, None, None, None,
        ratios["R11"], ratios["R22"], ratios["R33"], ratios["R12"],
        ratios["R13"], ratios["R23"], _OS_TEMP, None,
        "HARD", "ISOT", None, None, None, None, None, None,
    ]  # fmt: skip
    for index, (strain, stress) in enumerate(points):
        fields.extend((stress, strain, _OS_TEMP if index == 0 else None, *[None] * 5))
    lines.extend(_bulk._card("PLASTIC", fields))
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, *said, _PAIR_NOTE))
