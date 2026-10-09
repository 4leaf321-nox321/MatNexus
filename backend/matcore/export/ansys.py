"""ANSYS Mechanical APDL 렌더러 — `MP`(선형·열) · `TB`(소성·속도·점탄성·초탄성).

Workbench 의 Engineering Data 도 결국 이 두 계열의 명령으로 번역된다. 여기서 내는
파일은 **Command Snippet 이나 `/INPUT` 으로 읽는 명령 묶음**이다 — 모델 전체가
아니다. `/PREP7` 안에서 읽힌다.

## 재료 번호는 한 곳에만 적는다

첫 줄에 `MNX_MAT = <번호>` 를 두고 모든 명령이 그 매개변수를 쓴다. Mechanical 의
Body 아래 스니펫에서는 그 줄을 `MNX_MAT = matid` 로 바꾸면 된다 — Mechanical 이
스니펫 앞에 `matid` 를 넣어 준다. 번호를 명령마다 박으면 재료 배정이 바뀔 때 남의
재료를 덮는다.

## 스니펫의 숫자는 환산되지 않는다

GUI 물성은 단위계를 따라 환산되지만 스니펫의 숫자는 **그 시점의 활성 단위계로 그대로
읽힌다.** 덱 머리에 단위계를 적는다 — 받는 사람이 대조할 유일한 자리다.

## 확인한 함정(2026-09-27, 2024 R2 도움말)

    ALPX 는 할선 열팽창계수      순간 값은 CTEX 다. 카드의 값은 Abaqus *EXPANSION 과 같은
                                할선 값이라 ALPX 로 나간다. 기준은 REFT(상수만).
    MPTEMP·MPDATA 의 0           첫 칸이 아니면 **0 과 빈칸이 이전 값을 그대로 둔다.**
                                그래서 한 명령에 값 하나씩 적는다 — 길어도 틀리지 않는다.
    TB,PLASTIC 의 NTEMP·NPTS     안 쓰인다(점은 TBPT 가 끼워 넣는다). 읽기 좋게 적기만 한다.
    Ogden 의 μ                   W = Σ μ/α (λ̄^α - 3) — 초기 전단탄성률이 Σμα/2 다.
                                우리 μ 는 Abaqus 규약(G = μ)이라 2μ/α 로 옮긴다.
"""

from __future__ import annotations

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _free,
    _header,
    elastic_by_temperature,
    hyperelastic_bulk,
    hyperelastic_terms,
    low_rubber_poisson,
    prepare,
    prony_terms,
    register_renderer,
    viscoelastic_shift,
    viscoelastic_shift_notes,
)
from matcore.export.electronics import frequency_series, resistivity
from matcore.export.systems import SI
from matcore.viscoelastic import GAS_CONSTANT

#: 재료 번호를 담는 APDL 매개변수. 스니펫에서는 `= matid` 로 바꾼다.
MATERIAL = "MNX_MAT"

#: 구형 `TB,MISO` 의 한도. 새 `TB,PLASTIC` 은 문서에 한도가 없다 — 넘으면 적기만 한다.
OLD_MISO_POINTS = 100

#: `TB,PRONY` 의 항 상한(18.2 도움말: 100항).
MAX_PRONY_TERMS = 100


def _head(deck: Deck) -> list[str]:
    return [
        *_header(deck, "!"),
        f"! Consistent units: {deck.units.declaration}",
        "!   Snippet numbers are NOT converted - the active unit system must match.",
        "! Read inside /PREP7 (Command Snippet or /INPUT).",
        f"! In a Mechanical Command Snippet under a body write:  {MATERIAL} = matid",
        f"{MATERIAL} = {deck.solver_id}",
    ]


def _table(label: str, points: list[tuple[float, float]]) -> list[str]:
    """온도별 물성 — **한 명령에 값 하나씩.** 둘째 칸부터의 0 은 무시되기 때문이다.

    `MPDELE` 로 먼저 지운다 — GUI 가 더 많은 온도점을 써 두었으면 새로 쓴 칸만 바뀌고
    뒤쪽 칸이 남는다. 빈 `MPTEMP` 는 온도표를 비운다(온도표는 재료마다가 아니라 하나다).
    """
    lines = [f"MPDELE,{label},{MATERIAL}", "MPTEMP"]
    lines.extend(
        f"MPTEMP,{index},{_free(temperature)}"
        for index, (temperature, _) in enumerate(points, start=1)
    )
    lines.extend(
        f"MPDATA,{label},{MATERIAL},{index},{_free(value)}"
        for index, (_, value) in enumerate(points, start=1)
    )
    return lines


def _elastic_mp(deck: Deck) -> tuple[list[str], list[str]]:
    """`EX`·`PRXY`·`DENS` — 온도별 표가 있으면 표로. `(줄, 남길 말)`."""
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None
    notes: list[str] = []
    rows = elastic_by_temperature(deck)
    if rows:
        lines = [
            f"! EX, PRXY: {len(rows)} temperatures ({rows[0][0]:.5g} ~ {rows[-1][0]:.5g} K). "
            f"Temperatures are absolute - the model must use K too.",
            *_table("EX", [(temperature, one) for temperature, one, _ in rows]),
            *_table("PRXY", [(temperature, one) for temperature, _, one in rows]),
        ]
    else:
        lines = [f"MP,EX,{MATERIAL},{_free(youngs)}", f"MP,PRXY,{MATERIAL},{_free(poisson)}"]
    if density is not None:
        lines.append(f"MP,DENS,{MATERIAL},{_free(density)}")
    else:
        notes.append("밀도가 카드에 없어 MP,DENS 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append("! DENS: no measured density on this card - not written (no mass).")
    return lines, notes


def _thermal_series(deck: Deck, key: str) -> list[tuple[float, float]] | float | None:
    """열물성 하나 — 표(두 점 이상)·상수·없음. **표가 있으면 표가 이긴다**(Abaqus 와 같다)."""
    table = sorted(
        (float(row["temperature"]), float(row[key]))
        for row in deck.rows("thermal")
        if isinstance(row.get(key), int | float)
        and isinstance(row.get("temperature"), int | float)
    )
    if len(table) > 1:
        return table
    if table:
        return table[0][1]
    return deck.number("thermal", key)


#: 카드의 열물성 → APDL 이름.
THERMAL_LABELS = (
    ("thermal_expansion", "ALPX"),
    ("specific_heat", "C"),
    ("thermal_conductivity", "KXX"),
)


def _thermal_mp(deck: Deck) -> list[str]:
    """`ALPX`·`C`·`KXX` — 있는 것만. `REFT` 는 카드에 열팽창의 기준 온도가 있을 때만.

    `REFT` 를 지어 넣지 않는다 — 없으면 전역 `TREF`(기본 0)가 쓰이고, 그 사실을 적는다.
    293.15 를 적어 넣으면 덱은 멀쩡히 돌고 열응력만 통째로 어긋난다(Abaqus `ZERO` 와 같다).
    """
    lines: list[str] = []
    for key, label in THERMAL_LABELS:
        found = _thermal_series(deck, key)
        if found is None:
            continue
        source = deck.values("thermal").get(f"{key}_source")
        lines.append(f"! {label}: {key}, source={source or 'unknown'}")
        if isinstance(found, list):
            lines.extend(_table(label, found))
        else:
            lines.append(f"MP,{label},{MATERIAL},{_free(found)}")
        if key == "thermal_expansion":
            zero = deck.number("thermal", "thermal_expansion_temperature")
            if zero is not None:
                lines.append(f"MP,REFT,{MATERIAL},{_free(zero)}")
            else:
                lines.append("! REFT not on the card - the global TREF is used (default 0).")
    return lines


def _structural(deck: Deck) -> tuple[list[str], list[str]]:
    """구조 덱의 앞부분 — 머리 · `TBDELE` · 탄성 · 열."""
    lines = _head(deck)
    # GUI 가 넣은 다른 TB(예: BISO)가 남아 우리 표와 겹치지 않게 전부 지우고 시작한다.
    lines.append(f"TBDELE,ALL,{MATERIAL}")
    elastic, notes = _elastic_mp(deck)
    lines.extend(elastic)
    lines.extend(_thermal_mp(deck))
    return lines, notes


def _plastic(deck: Deck) -> tuple[list[str], list[str]]:
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    if len(points) > OLD_MISO_POINTS:
        notes.append(
            f"소성 표가 {len(points)}점입니다 — 구형 TB,MISO 는 {OLD_MISO_POINTS}점까지"
            f"였습니다. "
            f"TB,PLASTIC 은 한도가 문서에 없지만, 오래된 버전이면 레시피의 재샘플 점 수를 "
            f"줄여 다시 내보내세요."
        )
    lines = [
        "! TB,PLASTIC + MISO takes (PLASTIC strain, true stress); first point (0, yield).",
        f"TB,PLASTIC,{MATERIAL},1,{len(points)},MISO",
    ]
    lines.extend(f"TBPT,DEFI,{_free(strain)},{_free(stress)}" for strain, stress in points)
    return lines, notes


@register_renderer(
    key="ansys_elastic",
    label="ANSYS (선형)",
    extension="mac",
    suffix="_elastic",
    describe=(
        "MP,EX·PRXY·DENS — 선형 탄성(온도별 표면 MPTEMP/MPDATA). 열물성이 있으면 "
        "ALPX·C·KXX 가 함께 나간다."
    ),
    keywords=(f"EX,{MATERIAL}", f"PRXY,{MATERIAL}"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("lve", optional=True),
    ),
)
def render_ansys_elastic(deck: Deck) -> Rendered:
    lines, notes = _structural(deck)
    limit = deck.number("lve", "lve_strain_limit")
    if limit is not None:
        lines.insert(
            len(_head(deck)),
            f"! EX is the DMA storage modulus in the linear range - valid up to strain "
            f"{limit:.4g}.",
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="ansys_plastic",
    label="ANSYS (탄소성)",
    extension="mac",
    suffix="_plastic",
    describe="MP + TB,PLASTIC(MISO) + TBPT — 다선형 등방경화. TBPT 는 (소성변형률, 진응력).",
    keywords=(f"EX,{MATERIAL}", "TB,PLASTIC", "TBPT"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("table", rows_min=MIN_POINTS),
    ),
)
def render_ansys_plastic(deck: Deck) -> Rendered:
    lines, notes = _structural(deck)
    plastic, said = _plastic(deck)
    lines.extend(plastic)
    return Rendered(text="\n".join(lines) + "\n", notes=tuple([*said, *notes]))


@register_renderer(
    key="ansys_rate",
    label="ANSYS (속도 의존)",
    extension="mac",
    suffix="_rate",
    describe=(
        "MP + TB,PLASTIC(MISO, 기준 속도 곡선) + TB,RATE(PERZYNA) — 카드의 Cowper-Symonds "
        "D·p 를 gamma = D, m = 1/p 로 옮긴다."
    ),
    keywords=(f"EX,{MATERIAL}", "TB,PLASTIC", "TB,RATE"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("table", rows_min=MIN_POINTS),
        Need("rate_table", values=("cs_d", "cs_p")),
    ),
)
def render_ansys_rate(deck: Deck) -> Rendered:
    """Perzyna `σ = σ₀[1 + (ε̇ₚ/gamma)^m]` 는 Cowper-Symonds `σ/σ₀ = 1 + (ε̇/D)^(1/p)` 를
    gamma = D, m = 1/p 로 적은 것이다. **m 과 1/m 을 뒤바꾸는 것이 대표적인 실수다** — 10% 인
    속도 효과가 엄청나게 커진다.

    ANSYS 는 속도별 표를 이 명령으로 받지 않는다 — 그래서 식이다. σ₀ 는 카드의 소성 표,
    즉 **기준 속도(가장 느린 묶음)의 곡선**이고, D·p 도 그 속도 대비 응력비로 맞춘 것이라
    짝이 맞는다. 다만 Perzyna 는 **소성**변형률 속도를 쓰고 적합은 시험 속도로 했다 —
    소성 구간에서는 거의 같다.
    """
    d = deck.number("rate_table", "cs_d")
    p = deck.number("rate_table", "cs_p")
    assert d is not None and p is not None
    if p < 1.0 or d <= 0.0:
        raise ExportError(
            f"Cowper-Symonds p={p:g}, D={d:g} 입니다 — Perzyna 의 m = 1/p 는 0 과 1 사이여야 "
            f"하고(p ≥ 1), gamma = D 는 양수여야 합니다. 속도 묶음의 적합을 다시 보세요."
        )
    reference = deck.number("rate_table", "reference_rate")
    lines, notes = _structural(deck)
    plastic, said = _plastic(deck)
    lines.extend(plastic)
    lines.append(
        f"! Perzyna: sigma = sigma_static [1 + (eps_dot_pl/gamma)^m], "
        f"gamma = D = {d:.6g}, m = 1/p = 1/{p:.6g}"
    )
    if reference is not None:
        lines.append(
            f"! sigma_static is the curve above, measured at the reference rate "
            f"{reference:.4g} per time unit."
        )
    lines.append(f"TB,RATE,{MATERIAL},,,PERZYNA")
    lines.append(f"TBDATA,1,{_free(1.0 / p)},{_free(d)}")
    notes.append(
        f"Cowper-Symonds D={d:.4g}, p={p:.4g} 를 Perzyna gamma={d:.4g}, m={1 / p:.4g} 로 "
        f"옮겼습니다. 속도별 표 자체는 ANSYS 가 이 명령으로 받지 않아 싣지 않았습니다."
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple([*said, *notes]))


@register_renderer(
    key="ansys_viscoelastic",
    label="ANSYS (점탄성)",
    extension="mac",
    suffix="_viscoelastic",
    describe=(
        "MP,EX(순간 탄성률) + TB,PRONY,SHEAR — 상대 전단 탄성률 αᵢ·완화시간 τᵢ. "
        "체적은 탄성. 기준 온도 하나에서 유효."
    ),
    keywords=(f"EX,{MATERIAL}", "TB,PRONY"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("viscoelastic", rows_min=1),
    ),
)
def render_ansys_viscoelastic(deck: Deck) -> Rendered:
    """`G(t) = G₀[α∞ + Σ αᵢ exp(-t/τᵢ)]` — G₀ 는 MP(EX·PRXY)에서 온다. **ANSYS 는 EX 를
    늘 순간 응답으로 읽는다**(Abaqus 는 기본이 장기다 — 옮길 때 갈리는 자리).

    TBDATA 는 한 명령에 여섯 값(세 항)씩, 자리(STLOC)를 적어 잇는다.
    """
    terms = prony_terms(deck, limit=MAX_PRONY_TERMS)
    reference = deck.number("viscoelastic", "reference_temperature_k")
    lines, notes = _structural(deck)
    lines.append("! EX is the INSTANTANEOUS (t=0) modulus - ANSYS always reads it that way.")
    lines.append("! Shear ratios alpha_i from tensile/flexural E - assumes constant Poisson.")
    lines.append("! Bulk relaxation not measured by DMA - no TB,PRONY,BULK (elastic bulk).")
    shift = viscoelastic_shift(deck) if reference is not None else None
    if reference is not None and shift is not None:
        # **TB,SHIFT**(2026-10-07) — ANSYS 는 시간을 A 로 **곱한다**(ξ = A·t, Material
        # Reference Eq. 4-52) — 우리 a_T 의 역수다. 그래서 매뉴얼의 WLF
        # `log10 A = C1(T-Tr)/(C2+T-Tr)` 에 마이너스가 없어도 C1 · C2 는 그대로 들어간다
        # (매뉴얼도 「문헌은 흔히 반대 부호로 쓴다」 고 적는다). Arrhenius 는 TN 식
        # `ln A = (H/R)(1/Tr - 1/T)` 이 같은 꼴이라 H/R = Ea/R 로 넣는다.
        option = "WLF" if shift[0] == "wlf" else "TN"
        lines.append(
            f"! Prony fitted at {reference:.2f} K ({reference - 273.15:.2f} C); "
            f"TB,SHIFT ({option}) shifts it to other temperatures."
        )
        low = deck.number("viscoelastic", "shift_temperature_min_k")
        high = deck.number("viscoelastic", "shift_temperature_max_k")
        if low is not None and high is not None:
            lines.append(
                f"! Shift measured over {low:.2f}~{high:.2f} K - extrapolated outside."
            )
        if option == "TN":
            lines.append(
                "! TN with H/R = Ea/R is the Arrhenius shift. Temperatures are absolute K "
                "(TOFFST=0)."
            )
        notes.extend(viscoelastic_shift_notes(deck, shift[0], "TB,SHIFT"))
    elif reference is not None:
        lines.append(
            f"! Valid at {reference:.2f} K only - master curve reference temperature "
            f"(no TB,SHIFT: the shift constants are not on the card)."
        )
        notes.append(
            f"기준 온도 {reference - 273.15:.1f} °C 에서만 유효하다는 사실을 덱 주석에 "
            f"적었습니다 — 다른 온도로 해석하려면 TB,SHIFT 가 따로 필요합니다."
        )
    else:
        notes.append(
            "기준 온도가 카드에 없어 덱에 적지 못했습니다. 이 카드가 어느 온도의 "
            "것인지 덱만으로는 알 수 없습니다."
        )
    lines.append(f"TB,PRONY,{MATERIAL},1,{len(terms)},SHEAR")
    for start in range(0, len(terms), 3):
        chunk = terms[start : start + 3]
        values = ",".join(f"{_free(g)},{_free(tau)}" for g, tau in chunk)
        lines.append(f"TBDATA,{2 * start + 1},{values}")
    if reference is not None and shift is not None:
        # TBDATA 자리: WLF 는 1=Tr · 2=C1 · 3=C2, TN 은 1=Tr · 2=H/R(매뉴얼 표).
        method, constants = shift
        if method == "wlf":
            lines.append(f"TB,SHIFT,{MATERIAL},1,3,WLF")
            lines.append(
                f"TBDATA,1,{_free(reference)},{_free(constants[0])},{_free(constants[1])}"
            )
        else:
            lines.append(f"TB,SHIFT,{MATERIAL},1,2,TN")
            lines.append(f"TBDATA,1,{_free(reference)},{_free(constants[0] / GAS_CONSTANT)}")
    total = sum(g for g, _ in terms)
    notes.append(
        f"Prony {len(terms)}항, 상대 탄성률 합 {total:.4f} "
        f"(평형 탄성률은 순간의 {1 - total:.4f} 배)."
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="ansys_hyperelastic",
    label="ANSYS (초탄성)",
    extension="mac",
    suffix="_hyperelastic",
    describe=(
        "TB,HYPER — NEO·MOONEY·YEOH·OGDEN. d 는 카드의 푸아송비로 만들고(d = 2/K), 없으면 "
        "d=0(완전 비압축)이라 혼합 u-P 요소(SOLID185/186 KEYOPT(6)=1)가 필요하다."
    ),
    keywords=("TB,HYPER", "TBDATA"),
    needs=(
        Need("hyperelastic", rows_min=1),
        Need("elastic", values=("poisson_ratio", "density"), optional=True),
    ),
)
def render_ansys_hyperelastic(deck: Deck) -> Rendered:
    """식마다 `TBOPT` 가 갈리고, 상수의 뜻이 우리와 다른 둘이 있다.

    NEO      (μ, d)             μ = 2·C10
    MOONEY   (C10, C01, d)      NPTS=2 를 적는다(문서 안에서 기본값이 2 와 3 으로 갈린다)
    YEOH     (C10, C20, C30, d1, d2, d3)
    OGDEN    (μ₁, α₁, d₁)       μ₁ = 2μ/α — ANSYS 는 G = Σμα/2

    d 는 카드의 푸아송비에서 d = 2/K(네 식 모두 초기 체적 탄성률이 K = 2/d 다). ν 가 없거나
    0.5 면 d = 0 — 완전 비압축이고 혼합 u-P 요소가 필요하다(`hyperelastic_bulk`).
    """
    family, values = hyperelastic_terms(deck)
    density = deck.number("elastic", "density")
    compressible = hyperelastic_bulk(deck, family, values)
    notes: list[str] = []
    lines = _head(deck)
    lines.append(f"TBDELE,ALL,{MATERIAL}")
    lines.append("! Nominal (engineering) stress fit - uniaxial data only.")
    if compressible is None:
        # 0 은 전처럼 `0.0` 으로 적는다 — 비압축 계수를 안 만들었다는 것이 한눈에 보인다.
        d = "0.0"
        notes.append(
            "비압축 계수 d 를 0 으로 두었습니다(카드에 푸아송비가 없거나 0.5 입니다) — 완전 "
            "비압축이라는 뜻이고, ANSYS 는 그때 혼합 u-P 요소(KEYOPT(6)=1)를 요구합니다."
        )
        lines.append(
            "! d = 0 : fully incompressible - needs mixed u-P (SOLID185/186 KEYOPT(6)=1)."
        )
    else:
        poisson, shear, bulk = compressible
        d = _free(2.0 / bulk)
        said = low_rubber_poisson(poisson)
        if said:
            notes.append(said)
        lines.append(
            f"! d = 2/K from the card nu={poisson:g}: mu = {shear:.6g}, K = {bulk:.6g}."
        )
    if density is not None:
        lines.append(f"MP,DENS,{MATERIAL},{_free(density)}")
    else:
        notes.append("밀도가 없어 MP,DENS 를 비웠습니다 — 동적 해석에는 그대로 못 씁니다.")
    if family == "neo_hookean":
        lines.append("! mu = 2*C10 (NEO: W = mu/2 (I1bar-3))")
        lines.append(f"TB,HYPER,{MATERIAL},1,2,NEO")
        lines.append(f"TBDATA,1,{_free(2.0 * values['c10'])},{d}")
    elif family == "mooney_rivlin":
        lines.append(f"TB,HYPER,{MATERIAL},1,2,MOONEY")
        lines.append(f"TBDATA,1,{_free(values['c10'])},{_free(values['c01'])},{d}")
    elif family == "yeoh":
        lines.append(f"TB,HYPER,{MATERIAL},1,3,YEOH")
        lines.append(
            f"TBDATA,1,{_free(values['c10'])},{_free(values['c20'])},{_free(values['c30'])},"
            f"{d},0.0,0.0"
        )
    else:
        mu, alpha = values["mu"], values["alpha"]
        converted = 2.0 * mu / alpha
        lines.append(
            f"! mu_1 = 2*mu/alpha = {converted:.6g} (card mu is the Abaqus convention, "
            f"G = mu = {mu:.6g}); ANSYS: G = sum(mu*alpha)/2"
        )
        lines.append(f"TB,HYPER,{MATERIAL},1,1,OGDEN")
        lines.append(f"TBDATA,1,{_free(converted)},{_free(alpha)},{d}")
        notes.append(
            f"Ogden μ 를 ANSYS 규약으로 옮겼습니다 — μ₁ = 2μ/α = {converted:.6g}. "
            f"초기 전단탄성률 {mu:.6g} 는 그대로입니다."
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="ansys_thermal",
    label="ANSYS (열물성)",
    extension="mac",
    suffix="_thermal",
    describe="MP,KXX·C·DENS(·ALPX) — 열전도 해석용. 온도별 표면 MPTEMP/MPDATA.",
    keywords=(f"KXX,{MATERIAL}",),
    needs=(
        Need("thermal", values=("thermal_conductivity",)),
        Need("elastic", values=("density",), optional=True),
    ),
)
def render_ansys_thermal(deck: Deck) -> Rendered:
    """열 덱은 구조 표(TB)를 건드리지 않는다 — 같은 재료 번호에 구조 스니펫이 따로 있을 수
    있다. 비열이 있는데 밀도가 없으면 과도 해석의 열용량이 0 이 되므로 적는다."""
    density = deck.number("elastic", "density")
    notes: list[str] = []
    lines = _head(deck)
    if density is not None:
        lines.append(f"MP,DENS,{MATERIAL},{_free(density)}")
    elif _thermal_series(deck, "specific_heat") is not None:
        notes.append(
            "비열은 있는데 밀도가 없어 MP,DENS 를 못 적었습니다 — 과도 열해석의 열용량"
            "(밀도 곱하기 비열)이 서지 않습니다. 정상 해석에는 상관없습니다."
        )
        lines.append("! DENS: not on the card - transient heat capacity needs it.")
    lines.extend(_thermal_mp(deck))
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


#: 흡습 블록 칸 → APDL `MP` 이름. 세 방향을 다 적는다 — Y · Z 가 X 를 따르는 기본값에
#: 기대지 않는다(받는 쪽이 이방 재료로 고쳐 쓸 때 어느 칸이 비었는지 보이게).
_MOISTURE_MP = (
    ("moisture_diffusivity", ("DXX", "DYY", "DZZ")),
    ("moisture_saturation", ("CSAT",)),
    ("hygroscopic_expansion", ("BETX", "BETY", "BETZ")),
)


@register_renderer(
    key="ansys_moisture",
    label="ANSYS (흡습)",
    extension="mac",
    suffix="_moisture",
    describe=(
        "MP,DXX · CSAT · BETX — 수분 확산 · 흡습 팽윤 해석용(확산 · 구조-확산 요소). 한 환경"
        "(온도 · 습도)의 값이다."
    ),
    keywords=(f"DXX,{MATERIAL}",),
    needs=(Need("moisture", values=("moisture_diffusivity",)),),
)
def render_ansys_moisture(deck: Deck) -> Rendered:
    """흡습 스니펫 — `DXX..DZZ` · `CSAT` · `BETX..BETZ`. 구조 표(TB)는 안 건드린다
    (열 덱과 같다).

    **팽윤은 실제 농도로 계산된다.** CSAT 이 있으면 농도 자유도는 정규화 농도(C/CSAT)이고,
    팽윤 변형 `BETX·(C - CREF)` 의 C 는 정규화 농도에 CSAT 을 곱한 값이다 — 도움말의 바이모프
    예제가 β(m³/kg)와 CSAT(kg/m³)을 그렇게 짝지었다. 블록이 질량 농도를 드는 이유다.

    `CREF` 는 안 적는다 — 기본 0(마른 상태)이 흡습 팽창 계수의 기준과 같다. `REFT` 를 지어
    넣지 않는 것과 같은 이유로, 모르는 기준을 덱이 정하지 않는다.
    """
    temperature = deck.number("moisture", "temperature")
    humidity = deck.number("moisture", "humidity")
    notes: list[str] = []
    lines = _head(deck)
    lines.append(
        "! Moisture: DXX..DZZ diffusivity, CSAT saturated concentration (mass/volume)."
    )
    lines.append(
        "! With CSAT the CONC dof is normalized (C/CSAT); swelling uses C = CONC*CSAT:"
    )
    lines.append(
        "!   strain = BETX*(C - CREF), BETX in volume/mass. CREF not written (default 0, dry)."
    )
    if temperature is not None:
        lines.append(
            f"! Values measured at {temperature:.5g} K - diffusivity depends on temperature."
        )
    if humidity is not None and deck.number("moisture", "moisture_saturation") is not None:
        lines.append(
            f"! CSAT is the saturation at RH {humidity * 100:.4g} % - other RH, other CSAT."
        )
    for key, labels in _MOISTURE_MP:
        value = deck.number("moisture", key)
        if value is None:
            continue
        lines.extend(f"MP,{label},{MATERIAL},{_free(value)}" for label in labels)
    if deck.number("moisture", "moisture_saturation") is None:
        lines.append(
            "! CSAT not on the card - CONC is the actual concentration (not normalized)."
        )
        notes.append(
            "포화 수분 농도(CSAT)가 카드에 없어 농도 자유도가 실제 농도입니다 — 포화 농도가 "
            "다른 재료가 맞닿는 모델이면 경계에서 농도가 끊겨 정규화 농도(CSAT)가 필요합니다."
        )
    if deck.number("moisture", "hygroscopic_expansion") is None:
        lines.append("! BETX not on the card - no swelling strain.")
        notes.append(
            "흡습 팽창 계수가 카드에 없어 MP,BETX 를 뺐습니다 — 팽윤 변형이 생기지 않습니다."
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


#: 카드 칸 → APDL `MP` 이름. 전부 무차원이라 계와 상관없다(비유전율 · 손실 · 비투자율 ·
#: 방사율).
_ELECTRIC_MP = (
    ("electrical", "relative_permittivity", "PERX"),
    ("electrical", "loss_tangent", "LSST"),
    ("electrical", "relative_permeability", "MURX"),
    ("optical", "emissivity", "EMIS"),
)


@register_renderer(
    key="ansys_electric",
    label="ANSYS (전기)",
    extension="mac",
    suffix="_electric",
    describe=(
        "MP,RSVX · PERX · LSST · MURX(· EMIS) — 열-전기(줄 발열) · 정전기 해석용. 저항률은 "
        "SI(Ω·m) 고정 — 활성 단위계가 SI 여야 한다."
    ),
    keywords=(f"{MATERIAL} =",),
    needs=(Need("electrical"), Need("optical", optional=True)),
    fixed_units=SI,
)
def render_ansys_electric(deck: Deck) -> Rendered:
    """전기 물성 스니펫. **저항률만 계를 탄다** — 나머지(비유전율 · 손실 · 비투자율 · 방사율)는
    무차원이다. mm 계 모델에서 RSVX 는 전류를 A 로 두느냐 mA 로 두느냐에 따라 값이 갈려서
    (`matcore/export/systems.py` 의 `UNSCALED`) 우리가 옮기지 않는다 — SI 로 적고 머리에
    말한다.

    저항온도계수 · 주파수 표는 싣지 않는다 — `MP` 는 값 하나이고, 표로 펴면 우리가 고른 온도 ·
    주파수 점이 잰 값처럼 보인다. 싣지 않았다고 적는다.
    """
    rho, said = resistivity(deck)
    found = [(label, deck.number(block, key)) for block, key, label in _ELECTRIC_MP]
    # 표는 먼저 읽는다 — 겹친 주파수는 쓰기 전에 멈춘다(싣지 않는 표라도 카드가 틀린 것이다).
    tables = [frequency_series(deck, key) for key in ("relative_permittivity", "loss_tangent")]
    if rho is None and all(value is None for label, value in found if label != "EMIS"):
        raise ExportError(
            "ANSYS 전기 스니펫으로 낼 값이 카드에 없습니다 — 체적저항률(또는 전기전도율) · "
            "비유전율 · 유전손실 · 비투자율 가운데 하나는 있어야 합니다."
        )
    notes: list[str] = []
    lines = _head(deck)
    lines.append(
        "! Electrical values are SI (ohm*m; permittivity and permeability are relative)."
    )
    if rho is not None:
        lines.append(f"MP,RSVX,{MATERIAL},{_free(rho)}")
        if said:
            notes.append(said)
    for label, value in found:
        if value is not None:
            lines.append(f"MP,{label},{MATERIAL},{_free(value)}")
    if deck.number("electrical", "resistivity_temperature_coefficient") is not None:
        notes.append(
            "저항온도계수는 싣지 않았습니다 — MP,RSVX 는 값 하나입니다. 온도 의존은 MPTEMP · "
            "MPDATA 로 따로 적습니다."
        )
    if any(len(table) >= 2 for table in tables):
        notes.append(
            "유전 물성의 주파수 표는 싣지 않았습니다 — PERX · LSST 는 값 하나(가장 낮은 "
            "주파수)입니다."
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
