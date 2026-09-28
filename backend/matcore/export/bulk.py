"""Nastran · OptiStruct 렌더러 — 벌크 데이터 큰칸(16칸) 조각.

두 솔버는 한 계보(MAT1 · MATS1 · TABLES1)라 카드 대부분이 같고, **다른 자리 몇 곳**만
갈린다. 그 갈림을 한 파일에 나란히 두어 비교되게 했다(2026-09-27, MSC QRG 2025.1 ·
OptiStruct Reference Guide 로 칸 대조):

    점탄성    MSC  MATVE ISO1 — Gᵢ 절대값, MAT1 이 **순간** 탄성률
              OS   MATVE PRONY — gᵢ 비율,  MAT1 이 **장기** 탄성률(기본 MTIME=LONG)
    초탄성    MSC  MATHP(다항식) — D1 은 K/2, 비우면 1000·(A10+A01)
              OS   MATHE — NEOH·MOONEY·YEOH·OGDEN, Ogden 은 2μ/α² 규약(G = Σμ)
    열 표     둘 다 MATT4 의 표는 MAT4 값에 **곱해진다**(MATT1 은 바꿔 넣는다)

## 덱 전체가 아니라 조각이다

`BEGIN BULK` 과 `ENDDATA` 사이에 `INCLUDE` 하는 카드만 낸다. 해석 절차(SOL·NLPARM·
LGDISP)는 모델의 것이라 여기서 정하지 않고, 필요한 것을 주석으로 적는다.

## 큰칸 형식

첫 줄은 `이름*` + 16칸 넷, 잇는 줄은 1열에 `*` + 16칸 넷이다 — 한 논리 줄(8칸)이 물리
줄 둘이다. 반쪽이 비어도 `*` 줄을 둔다: OptiStruct 는 카드의 마지막 줄에서만 빈 반쪽을
뺄 수 있다. 실수에는 소수점이 있어야 한다(`{:.8E}` 가 늘 찍는다). 8칸 작은칸은 유효숫자가
모자라다 — 예제 덱의 TABLES1 에서 탄성 기울기가 209581(E=210000)로 읽혔다.
"""

from __future__ import annotations

from collections.abc import Sequence

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _header,
    elastic_by_temperature,
    hyperelastic_terms,
    prepare,
    prony_terms,
    register_renderer,
)

Field = int | float | str | None

#: OptiStruct MATVE PRONY 가 한 카드에 받는 항 수. 넘으면 UPRN(항마다 한 줄)으로 쓴다.
OS_PRONY_TERMS = 5


def _field(value: Field) -> str:
    if value is None:
        return " " * 16
    if isinstance(value, str):
        return f"{value:<16}"
    if isinstance(value, int):
        return f"{value:<16d}"
    return f"{value:<16.8E}"


def _card(name: str, fields: Sequence[Field]) -> list[str]:
    """큰칸 카드. `fields` 는 2번 칸부터 — 여덟씩 한 논리 줄, 논리 줄 하나가 물리 줄 둘."""
    rows = [list(fields[start : start + 8]) for start in range(0, len(fields), 8)] or [[]]
    lines: list[str] = []
    for index, row in enumerate(rows):
        row = row + [None] * (8 - len(row))
        first = f"{name}*" if index == 0 else "*"
        lines.append((f"{first:<8}" + "".join(_field(one) for one in row[:4])).rstrip())
        lines.append(("*       " + "".join(_field(one) for one in row[4:])).rstrip())
    return lines


def _pairs_table(name: str, table_id: int, points: Sequence[tuple[float, float]]) -> list[str]:
    """`TABLEM1`·`TABLES1` — 첫 줄은 번호뿐, 다음 줄부터 (x, y) 쌍, 끝에 ENDT."""
    body: list[Field] = [table_id, None, None, None, None, None, None, None]
    for x, y in points:
        body.extend((x, y))
    body.append("ENDT")
    return _card(name, body)


def _table_id(deck: Deck, slot: int) -> int:
    """표 번호 — `재료 번호 * 10 + 자리`. 0 소성 · 1 E(T) · 2 ν(T) · 3 α(T) · 4 K(T) · 5 Cp(T).

    8자리(1억 미만) 안에 들고, 재료 번호가 다르면 겹치지 않는다.
    """
    return deck.solver_id * 10 + slot


def _head(deck: Deck, solver: str) -> list[str]:
    return [
        *_header(deck, "$"),
        f"$ Consistent units: {deck.units.declaration}",
        f"$ {solver} Bulk Data fragment - INCLUDE it between BEGIN BULK and ENDDATA.",
        "$ Large field format: 16-character fields, continuation lines start with *.",
    ]


def _thermal_table(deck: Deck, key: str) -> list[tuple[float, float]]:
    return sorted(
        (float(row["temperature"]), float(row[key]))
        for row in deck.rows("thermal")
        if isinstance(row.get(key), int | float)
        and isinstance(row.get("temperature"), int | float)
    )


def _mat1(
    deck: Deck,
    *,
    youngs: float | None = None,
    shear: float | None = None,
    poisson: float | None = None,
    with_tables: bool = True,
) -> tuple[list[str], list[str]]:
    """`MAT1` (+ `MATT1`·`TABLEM1`). `(줄, 남길 말)`.

    E·G·ν 는 **셋 중 둘만** 준다 — 셋이 서로 안 맞으면 어느 것이 이겼는지 모른 채 결과가
    나온다. 보통은 E·ν 이고, 장기 탄성률을 맞춰야 하는 OptiStruct 점탄성만 E·G 다.

    열팽창(A)과 기준 온도(TREF)는 카드에 있을 때만. TREF 를 지어 넣지 않는다 — 비우면 0 이고
    그 사실을 적는다(Abaqus `ZERO` 와 같은 판단).
    """
    notes: list[str] = []
    density = deck.number("elastic", "density")
    expansion = deck.number("thermal", "thermal_expansion")
    zero = deck.number("thermal", "thermal_expansion_temperature")
    if youngs is None:
        youngs = deck.number("elastic", "youngs_modulus")
        poisson = deck.number("elastic", "poisson_ratio")
    alpha_table = _thermal_table(deck, "thermal_expansion")
    if alpha_table:
        expansion = alpha_table[0][1]
    lines: list[str] = []
    if density is None:
        notes.append("밀도가 카드에 없어 RHO 를 비웠습니다 — 질량이 0 인 재료입니다.")
        lines.append("$ RHO: no measured density on this card - left blank (no mass).")
    if expansion is not None and zero is None:
        lines.append("$ TREF not on the card - left blank (0).")
    lines.append("$MAT1*  MID             E               G               NU")
    lines.append("$*      RHO             A               TREF            GE")
    lines.extend(
        _card(
            "MAT1",
            [
                deck.solver_id,
                youngs,
                shear,
                poisson,
                density,
                expansion,
                zero if expansion is not None else None,
            ],
        )
    )
    if not with_tables:
        return lines, notes
    rows = elastic_by_temperature(deck)
    if rows or len(alpha_table) > 1:
        # MATT1 의 칸은 자리로 뜻이 정해진다 — E(3) · G(4) · NU(5) · RHO(6) · A(7). 하나
        # 밀면 G 의 표가 NU 로 들어가 포아송비가 20만이 되는데 경고가 안 난다.
        lines.append(
            "$ MATT1: field 3 = E(T), field 5 = NU(T), field 7 = A(T). Tables REPLACE MAT1."
        )
        lines.append("$ Temperatures are absolute (K) - the model must use K too.")
        e_table = _table_id(deck, 1) if rows else None
        nu_table = _table_id(deck, 2) if rows else None
        a_table = _table_id(deck, 3) if len(alpha_table) > 1 else None
        lines.extend(_card("MATT1", [deck.solver_id, e_table, None, nu_table, None, a_table]))
        if rows:
            lines.extend(
                _pairs_table("TABLEM1", _table_id(deck, 1), [(t, e) for t, e, _ in rows])
            )
            lines.extend(
                _pairs_table("TABLEM1", _table_id(deck, 2), [(t, n) for t, _, n in rows])
            )
        if a_table is not None:
            lines.extend(_pairs_table("TABLEM1", a_table, alpha_table))
    return lines, notes


def _mats1(deck: Deck) -> tuple[list[str], list[str]]:
    """`MATS1` + `TABLES1` — **진응력 대 전체 변형률**, 첫 점 원점, 둘째 점이 항복점.

    카드의 표는 소성변형률이다. `ε = εₚ + σ/E` 로 옮기고 원점을 앞에 끼운다 — 그러면
    둘째 점이 (σy/E, σy) 가 되어 MAT1 의 탄성 기울기와 **정확히 같은 선**이 된다(어긋나면
    초기 강성이 두 번 정의된다). E 는 MAT1 에 적은 값(가장 낮은 온도)이다.

    OptiStruct 의 TYPSTRN 은 비워 둔다(0 = 전체 변형률) — MSC 와 같은 표가 두 솔버에서 같은
    뜻이 된다. MSC 의 TABLES1 은 TYPE 을 비워야 한다(2 = 소성변형률은 MATS1 에서 오류).
    """
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    youngs = deck.number("elastic", "youngs_modulus")
    assert youngs is not None
    total = [(0.0, 0.0), *((strain + stress / youngs, stress) for strain, stress in points)]
    table = _table_id(deck, 0)
    lines = [
        "$ MATS1: TABLES1 is true stress vs TOTAL strain (eps = eps_p + sigma/E), first point",
        "$   the origin, second point the yield point - on the MAT1 elastic line.",
        "$ Needs a nonlinear subcase (NLSTAT / SOL 400) - a linear one ignores MATS1.",
        "$MATS1* MID             TID             TYPE            H",
        "$*      YF              HR              LIMIT1          LIMIT2",
        *_card("MATS1", [deck.solver_id, table, "PLASTIC", None, 1, 1, points[0][1]]),
        *_pairs_table("TABLES1", table, total),
    ]
    if len(elastic_by_temperature(deck)) > 1:
        notes.append(
            "탄성이 온도를 따라가지만 소성 표는 온도 하나의 것입니다 — TABLES1 의 전체 "
            "변형률은 MAT1 의 E(가장 낮은 온도)로 만들었습니다."
        )
    return lines, notes


def _mat4(deck: Deck, solver: str) -> tuple[list[str], list[str]]:
    """`MAT4` (+ `MATT4`). **MATT4 의 표는 MAT4 값에 곱해진다** — MATT1 과 반대다.

    그래서 MAT4 에 가장 낮은 온도의 값을 적고, 표에는 그 값에 대한 **비율**을 적는다.
    절대값을 표에 넣으면 값이 제곱으로 나간다(K * K(T)). 덱만 봐서는 티가 안 난다.
    """
    notes: list[str] = []
    density = deck.number("elastic", "density")
    series: dict[str, list[tuple[float, float]]] = {}
    constants: dict[str, float | None] = {}
    for key in ("thermal_conductivity", "specific_heat"):
        table = _thermal_table(deck, key)
        if len(table) > 1:
            series[key] = table
            constants[key] = table[0][1]
        else:
            constants[key] = table[0][1] if table else deck.number("thermal", key)
    lines = ["$MAT4*  MID             K               CP              RHO"]
    lines.extend(
        _card(
            "MAT4",
            [
                deck.solver_id,
                constants["thermal_conductivity"],
                constants["specific_heat"],
                density,
            ],
        )
    )
    if series:
        lines.append("$ MATT4 tables MULTIPLY the MAT4 value - they hold K(T)/K and CP(T)/CP.")
        k_table = _table_id(deck, 4) if "thermal_conductivity" in series else None
        cp_table = _table_id(deck, 5) if "specific_heat" in series else None
        lines.extend(_card("MATT4", [deck.solver_id, k_table, cp_table]))
        for key, table_id in (("thermal_conductivity", k_table), ("specific_heat", cp_table)):
            if table_id is None:
                continue
            base = series[key][0][1]
            lines.extend(
                _pairs_table(
                    "TABLEM1", table_id, [(t, value / base) for t, value in series[key]]
                )
            )
        notes.append(
            "온도별 열물성을 MATT4 로 실었습니다 — 표는 MAT4 값(가장 낮은 온도)에 대한 "
            "비율입니다."
        )
    if constants["specific_heat"] is None:
        notes.append("비열이 없어 CP 를 비웠습니다 — 정상 열해석에만 쓰입니다.")
    return lines, notes


def _rendered(lines: list[str], notes: list[str]) -> Rendered:
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── 선형 · 탄소성 · 열 — 두 솔버가 같은 카드 ─────────────────────────────────────


def _register_common(prefix: str, solver: str, extension: str) -> None:
    """두 솔버가 **같은 카드**를 쓰는 형식 셋을 등록한다."""

    @register_renderer(
        key=f"{prefix}_elastic",
        label=f"{solver} (선형)",
        extension=extension,
        suffix="_elastic",
        describe=(
            "MAT1 — 선형 탄성(큰칸). 온도별 표면 MATT1 + TABLEM1, 열팽창이 있으면 A·TREF."
        ),
        keywords=("MAT1*",),
        needs=(
            Need("elastic", values=("youngs_modulus", "poisson_ratio")),
            Need("elastic", values=("density",), optional=True),
            Need("thermal", optional=True),
            Need("lve", optional=True),
        ),
    )
    def render_elastic(deck: Deck) -> Rendered:
        lines = _head(deck, solver)
        limit = deck.number("lve", "lve_strain_limit")
        if limit is not None:
            lines.append(
                f"$ E is the DMA storage modulus in the linear range - valid up to strain "
                f"{limit:.4g}."
            )
        body, notes = _mat1(deck)
        return _rendered([*lines, *body], notes)

    @register_renderer(
        key=f"{prefix}_plastic",
        label=f"{solver} (탄소성)",
        extension=extension,
        suffix="_plastic",
        describe=(
            "MAT1 + MATS1 + TABLES1 — 진응력 대 전체 변형률 표(소성변형률에 σ/E 를 더하고 "
            "원점을 끼운다). 비선형 서브케이스에서만 먹는다."
        ),
        keywords=("MAT1*", "MATS1*", "TABLES1*", "ENDT"),
        needs=(
            Need("elastic", values=("youngs_modulus", "poisson_ratio")),
            Need("elastic", values=("density",), optional=True),
            Need("thermal", optional=True),
            Need("table", rows_min=MIN_POINTS),
        ),
    )
    def render_plastic(deck: Deck) -> Rendered:
        plastic, said = _mats1(deck)
        body, notes = _mat1(deck)
        return _rendered([*_head(deck, solver), *body, *plastic], [*said, *notes])

    @register_renderer(
        key=f"{prefix}_thermal",
        label=f"{solver} (열물성)",
        extension=extension,
        suffix="_thermal",
        describe=(
            "MAT4 — 열전도율·비열·밀도(밀도가 있어야 낸다). 온도별 표면 MATT4 + TABLEM1(비율)."
        ),
        keywords=("MAT4*",),
        needs=(
            Need("thermal", values=("thermal_conductivity",)),
            # **밀도를 요구한다.** MSC 의 MAT4 는 RHO 를 비우면 1.0 으로 봐서 열용량(밀도
            # 곱하기 비열)이 조용히 틀린다. 렌더러 안에서 거절하면 메뉴는 「가능」 인데
            # 내려받기가 422 다 — 미리 말한다(개발 DB 의 열 카드 하나가 그랬다, 2026-09-27).
            Need("elastic", values=("density",)),
        ),
    )
    def render_thermal(deck: Deck) -> Rendered:
        body, notes = _mat4(deck, solver)
        lines = _head(deck, solver)
        lines.append("$ Thermal material - pair it with the structural MAT1 of the same MID.")
        return _rendered([*lines, *body], notes)


_register_common("nastran", "Nastran", "bdf")
_register_common("optistruct", "OptiStruct", "fem")


# ── 점탄성 — 두 솔버가 반대로 읽는다 ───────────────────────────────────────────


def _prony_basis(deck: Deck) -> tuple[float, float, float, tuple[tuple[float, float], ...]]:
    """`(G0, K0, G∞, 항)` — 순간 전단·체적 탄성률과 장기 전단 탄성률."""
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    assert youngs is not None and poisson is not None
    if not 0.0 < poisson < 0.5:
        raise ExportError(f"푸아송비가 {poisson:g} 입니다 — 0 과 0.5 사이여야 합니다.")
    terms = prony_terms(deck)
    shear0 = youngs / (2.0 * (1.0 + poisson))
    bulk0 = youngs / (3.0 * (1.0 - 2.0 * poisson))
    return shear0, bulk0, (1.0 - sum(g for g, _ in terms)) * shear0, terms


def _reference_notes(deck: Deck, lines: list[str], notes: list[str]) -> None:
    reference = deck.number("viscoelastic", "reference_temperature_k")
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


_VISCO_NEEDS = (
    Need("elastic", values=("youngs_modulus", "poisson_ratio")),
    Need("elastic", values=("density",), optional=True),
    Need("viscoelastic", rows_min=1),
)


@register_renderer(
    key="nastran_viscoelastic",
    label="Nastran (점탄성)",
    extension="bdf",
    suffix="_viscoelastic",
    describe=(
        "MAT1(순간 탄성률) + MATVE ISO1 — 전단 Prony 항(Gᵢ 절대값·완화시간). SOL 400 과 "
        "고급 요소(PSLDN1)가 필요하다. 체적은 탄성."
    ),
    keywords=("MAT1*", "MATVE*"),
    needs=_VISCO_NEEDS,
)
def render_nastran_viscoelastic(deck: Deck) -> Rendered:
    """MSC 의 MATVE 는 **짝 MAT1 을 순간(t=0) 탄성률로** 읽는다(QRG Note 2) — 카드의
    E₀ 그대로다.
    G∞ = G₀ - ΣGᵢ 가 따라온다. ISO1 은 항 수 제한이 없고 항마다 한 줄이다."""
    shear0, _, long_term, terms = _prony_basis(deck)
    notes = [
        f"Prony {len(terms)}항 — Gᵢ = gᵢ·G₀ 로 옮겼습니다(G₀ = {shear0:.6g}, "
        f"장기 {long_term:.6g}).",
        "인장 E 를 전단 G 로 돌렸습니다 — 푸아송비가 시간에 안 변한다는 가정입니다.",
    ]
    lines = _head(deck, "MSC Nastran")
    lines.append("$ MAT1 = INSTANTANEOUS moduli (MSC MATVE Note 2). Gi = gi*G0, Tdi = tau_i.")
    lines.append("$ Bulk relaxation not measured by DMA - Ki left blank (elastic bulk).")
    lines.append(
        "$ SOL 400 only, with the advanced solid (PSLDN1) - MATVE is ignored otherwise."
    )
    _reference_notes(deck, lines, notes)
    body, said = _mat1(deck, with_tables=False)
    lines.extend(body)
    lines.append("$MATVE* MID             MODEL")
    lines.append("$*      Gi              Tdi             Ki              Tvi")
    fields: list[Field] = [deck.solver_id, "ISO1", None, None, None, None, None, None]
    for g, tau in terms:
        fields.extend((g * shear0, tau, None, None, None, None, None, None))
    lines.extend(_card("MATVE", fields))
    return _rendered(lines, [*notes, *said])


@register_renderer(
    key="optistruct_viscoelastic",
    label="OptiStruct (점탄성)",
    extension="fem",
    suffix="_viscoelastic",
    describe=(
        "MAT1(장기 탄성률) + MATVE PRONY — 전단 Prony 비율 gᵢ·완화시간 τᵢ. 체적은 탄성. "
        "서브케이스에 VISCO 가 있어야 완화가 돈다."
    ),
    keywords=("MAT1*", "MATVE*"),
    needs=_VISCO_NEEDS,
)
def render_optistruct_viscoelastic(deck: Deck) -> Rendered:
    """OptiStruct 는 짝 MAT1 을 **기본이 장기(MTIME=LONG)** 로 읽는다 — MSC 와 반대다.

    그래서 MAT1 에 장기 값을 적는다. 다만 E·ν 로 적으면 체적 탄성률도 장기 전단을 따라
    무르게 된다 — 체적은 순간 값 K₀ 로 두는 것이 다른 솔버 덱과 같은 재료다. **E·G 로
    적는다**: G = G∞, E′ = 9K₀G∞/(3K₀ + G∞) 이면 MAT1 이 G∞ 와 K₀ 를 낸다.
    """
    _, bulk0, long_term, terms = _prony_basis(deck)
    youngs_long = 9.0 * bulk0 * long_term / (3.0 * bulk0 + long_term)
    notes = [
        f"Prony {len(terms)}항 — MAT1 에 장기 전단 탄성률 {long_term:.6g} 와, 체적이 순간 값 "
        f"K₀ 로 남게 맞춘 E′ = {youngs_long:.6g} 를 적었습니다(OptiStruct 는 MAT1 을 장기로 "
        f"읽습니다).",
        "체적 완화 항(gB)은 비웠습니다 — 체적은 탄성이라는 가정입니다.",
    ]
    lines = _head(deck, "OptiStruct")
    lines.append("$ MAT1 = LONG-TERM moduli (OptiStruct default MTIME=LONG).")
    lines.append(f"$   G = Ginf = (1 - sum g_i) G0 = {long_term:.6E},  G0 = E0/(2(1+nu))")
    lines.append(
        f"$   E' = 9 K0 Ginf/(3 K0 + Ginf) = {youngs_long:.6E}, "
        f"K0 = E0/(3(1-2nu)) = {bulk0:.6E}"
    )
    lines.append(
        "$ gD_i = relative shear moduli, tD_i = relaxation times. gB blank (elastic bulk)."
    )
    lines.append("$ Relaxation runs only with a VISCO case control entry.")
    _reference_notes(deck, lines, notes)
    body, said = _mat1(
        deck, youngs=youngs_long, shear=long_term, poisson=None, with_tables=False
    )
    lines.extend(body)
    if len(terms) <= OS_PRONY_TERMS:
        lines.append("$MATVE* MID             MODEL")
        lines.append("$*      gD1             tD1             gB1             tB1")
        fields: list[Field] = [deck.solver_id, "PRONY", None, None, terms[0][0], terms[0][1]]
        if len(terms) > 1:
            fields.extend((None, None))
            for g, tau in terms[1:]:
                fields.extend((g, tau))
        lines.extend(_card("MATVE", fields))
    else:
        # PRONY 는 다섯 항까지다. 넘으면 UPRN — 항마다 한 줄(gD tD gB tB).
        lines.append("$MATVE* UPRN: one continuation per term - gD_i tD_i gB_i tB_i")
        fields = [deck.solver_id, "UPRN", None, None, None, None, None, None]
        for g, tau in terms:
            fields.extend((g, tau, None, None, None, None, None, None))
        lines.extend(_card("MATVE", fields))
    return _rendered(lines, [*notes, *said])


# ── 초탄성 — 카드가 다르다 ──────────────────────────────────────────────────────


def _hyper_head(deck: Deck, solver: str) -> list[str]:
    return [
        *_head(deck, solver),
        "$ Nominal (engineering) stress fit - uniaxial data only.",
    ]


@register_renderer(
    key="nastran_hyperelastic",
    label="Nastran (초탄성)",
    extension="bdf",
    suffix="_hyperelastic",
    describe=(
        "MATHP — Neo-Hookean·Mooney-Rivlin·Yeoh(다항식). D1 은 카드의 푸아송비로 만들고, "
        "없으면 비워 기본값(K = 1000·G 쯤)을 쓴다. Ogden 은 MSC 에서 MATHE(SOL 400)라 안 낸다."
    ),
    keywords=("MATHP*",),
    needs=(
        Need("hyperelastic", rows_min=1),
        Need("elastic", values=("poisson_ratio", "density"), optional=True),
    ),
)
def render_nastran_hyperelastic(deck: Deck) -> Rendered:
    """MATHP `U = Σ Aᵢⱼ(Ī₁-3)ⁱ(Ī₂-3)ʲ + Σ Dᵢ(J-1)²ⁱ` — **D1 = K/2 다**(Abaqus·ANSYS 의
    D1 = 2/K 와
    같은 기호, 역수). 비우면 1000·(A10+A01), 곧 K ≈ 1000·G 로 거의 비압축이다.

    Yeoh 는 NA=3 을 적어야 A20·A30 이 읽힌다(2번 줄 3칸 NA · 4칸 ND, A20 은 3번 줄 · A30 은
    4번 줄 첫 칸).
    """
    family, values = hyperelastic_terms(deck)
    if family == "ogden_1":
        raise ExportError(
            "MSC Nastran 의 MATHP 는 다항식이라 Ogden 을 못 받습니다 — MATHE(OGDEN)는 SOL 400 "
            "전용이고 체적 탄성률 칸의 뜻을 우리가 대조하지 못했습니다. OptiStruct·Abaqus·"
            "ANSYS·LS-DYNA·Radioss 형식은 Ogden 을 냅니다."
        )
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    a10 = values["c10"]
    a01 = values.get("c01", 0.0)
    notes: list[str] = []
    lines = _hyper_head(deck, "MSC Nastran")
    d1: float | None = None
    if poisson is not None:
        if not 0.0 < poisson < 0.5:
            raise ExportError(f"푸아송비가 {poisson:g} 입니다 — 0 과 0.5 사이여야 합니다.")
        shear = 2.0 * (a10 + a01)
        bulk = 2.0 * shear * (1.0 + poisson) / (3.0 * (1.0 - 2.0 * poisson))
        d1 = bulk / 2.0
        lines.append(
            f"$ D1 = K/2 from the card nu={poisson:g}: K = {bulk:.6g} (MSC D1 is K/2)."
        )
    else:
        lines.append("$ D1 blank - MSC default 1000*(A10+A01), about K = 1000 G.")
        notes.append(
            "푸아송비가 카드에 없어 D1 을 비웠습니다 — MSC 기본값(1000·(A10+A01), "
            "곧 K ≈ 1000·G)"
            "으로 거의 비압축입니다."
        )
    if density is None:
        notes.append("밀도가 없어 RHO 를 비웠습니다 — 동적 해석에는 그대로 못 씁니다.")
    lines.append("$MATHP* MID             A10             A01             D1")
    lines.append("$*      RHO             AV              TREF            GE")
    fields: list[Field] = [deck.solver_id, a10, a01, d1, density, None, None, None]
    if family == "yeoh":
        lines.append("$ Yeoh: NA=3 (line 2 field 3), A20 line 3, A30 line 4.")
        fields.extend((None, 3, 1, None, None, None, None, None))
        fields.extend((values["c20"], None, None, None, None, None, None, None))
        fields.extend((values["c30"], None, None, None, None, None, None, None))
    lines.extend(_card("MATHP", fields))
    return _rendered(lines, notes)


@register_renderer(
    key="optistruct_hyperelastic",
    label="OptiStruct (초탄성)",
    extension="fem",
    suffix="_hyperelastic",
    describe=(
        "MATHE — NEOH·MOONEY·YEOH·OGDEN. 비압축 정도는 NU(카드에 없으면 기본 0.495). "
        "요소 속성은 PLSOLID 다."
    ),
    keywords=("MATHE*",),
    needs=(
        Need("hyperelastic", rows_min=1),
        Need("elastic", values=("poisson_ratio", "density"), optional=True),
    ),
)
def render_optistruct_hyperelastic(deck: Deck) -> Rendered:
    """OptiStruct MATHE 의 Ogden 은 **2μ/α² 규약**(G = Σμ)이라 카드의 μ 를 그대로 싣는다 —
    ANSYS·LS-DYNA·Radioss 와 달리 옮기지 않는다. D1 은 비우고 NU 로 비압축 정도를 준다."""
    family, values = hyperelastic_terms(deck)
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    notes: list[str] = []
    lines = _hyper_head(deck, "OptiStruct")
    lines.append("$ Reference it from a PLSOLID property (not PSOLID).")
    if poisson is None:
        lines.append("$ NU blank - OptiStruct default 0.495.")
        notes.append(
            "푸아송비가 카드에 없어 NU 를 비웠습니다 — OptiStruct 기본값 0.495 가 쓰입니다."
        )
    elif not 0.0 < poisson < 0.5:
        raise ExportError(f"푸아송비가 {poisson:g} 입니다 — 0 과 0.5 사이여야 합니다.")
    if density is None:
        notes.append("밀도가 없어 RHO 를 비웠습니다 — 동적 해석에는 그대로 못 씁니다.")
    head: list[Field]
    rest: list[Field]
    if family == "ogden_1":
        lines.append("$ OGDEN: W = sum 2 mu/alpha^2 (...) - card mu used as is (G = mu).")
        head = [deck.solver_id, "OGDEN", 1, poisson, density, None, None, None]
        rest = [values["mu"], values["alpha"], None, None, None, None, None, None]
    else:
        model = {"neo_hookean": "NEOH", "mooney_rivlin": "MOONEY", "yeoh": "YEOH"}[family]
        head = [deck.solver_id, model, None, poisson, density, None, None, None]
        rest = [values["c10"], values.get("c01"), None, None, None, None, None, None]
        if family == "yeoh":
            rest.extend((values["c20"], None, None, None, None, None, None, None))
            rest.extend((values["c30"], None, None, None, None, None, None, None))
    lines.append("$MATHE* MID             MODEL                           NU")
    lines.extend(_card("MATHE", [*head, *rest]))
    return _rendered(lines, notes)
