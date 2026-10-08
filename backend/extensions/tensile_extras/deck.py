"""온도 의존 소성 — ANSYS · LS-DYNA · Nastran · OptiStruct · Radioss 덱(2026-09-27).

Abaqus 는 `card.py` 에 먼저 있었다. 여기는 같은 카드(`temperature_table` + 탄성)를 다른
솔버로 낸다. 칸은 각 솔버의 원본으로 맞췄다(ADR 0037 과 같은 방법):

    ANSYS       TB,PLASTIC MISO + 온도마다 TBTEMP — 온도 오름차순
    LS-DYNA     *MAT_255(PIECEWISE_LINEAR_PLASTIC_THERMAL) — TABIDC=TABIDT=온도 표,
                E<0 이면 |E| 가 E(T) 곡선. 표의 곡선은 같은 x 에서 시작·끝나야 한다
    OptiStruct  MATS1 → TABLEST 는 **TYPSTRN=1(소성변형률)일 때만** 된다. LIMIT1 은 비운다 —
                온도마다 항복이 다르고, 표의 첫 점이 그것을 말한다
    Nastran     MSC 는 MATS1 → TABLEST 를 **금한다**(PLASTIC). SOL 400 의 MATEP(FORM=TABLE) +
                MATTEP(T(FID) → TABLEST) + MATT1 이 길이다. MATT1 은 표가 하나는 있어야 한다
    Radioss     LAW109 — σy = f_h(εp)·f_t(εp, T)/f_t(εp, Tref). f_h 를 기준 온도 곡선으로,
                f_t 를 (온도, 곡선) 표로 두면 σy 가 그 온도의 곡선이 된다

## 온도는 절대온도(K)다

카드가 K 로 들고, 덱의 단위계는 온도를 안 바꾼다. **모델이 °C 면 273.15 만큼 어긋난다** —
덱마다 적는다.

## 탄성은 온도별 표가 있을 때만 온도를 탄다

온도별 탄성 표(탄성 블록의 행)가 있으면 그것을 싣고, 없으면 **탄성은 온도 하나의 값**이라고
적는다(Abaqus 덱과 같은 판단). MSC 는 MATT1 에 표가 하나는 있어야 해서, 표가 없으면 E 를
소성 표의 온도마다 같은 값으로 적는다 — 「E 는 온도를 안 탄다」 는 같은 가정을 표로 쓴 것이고
그 사실을 적는다.
"""

from __future__ import annotations

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _fixed,
    _free,
    _header,
    elastic_by_temperature,
    prepare,
    register_renderer,
)
from matcore.export import ansys as _ansys
from matcore.export import bulk as _bulk
from matcore.export import dyna as _dyna
from matcore.export import radioss as _radioss

_NEEDS_TEMPERATURE = Need(
    "temperature_table",
    values=("temperature_count",),
    at_least=(("temperature_count", 2),),
    rows_min=2 * MIN_POINTS,
)

_KELVIN = "Temperatures are absolute (K) - a model in Celsius is off by 273.15."


def temperature_curves(
    deck: Deck,
) -> tuple[list[tuple[float, list[tuple[float, float]]]], list[str]]:
    """온도별 소성 표를 **온도마다 나눠 정리한다** — `([(온도, 점들)], 남길 말)`.

    곡선마다 `prepare` 를 따로 돈다. 온도가 하나뿐이면 거부한다 — 그 덱은 탄소성 형식이
    낼 것이고, 여기서 내면 온도 의존이 있는 척이 된다.
    """
    by_temperature: dict[float, list[tuple[float, float]]] = {}
    for row in deck.rows("temperature_table"):
        try:
            by_temperature.setdefault(float(row["temperature"]), []).append(
                (float(row["plastic_strain"]), float(row["true_stress"]))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportError(
                "온도별 소성 표의 행에 온도·변형률·응력이 다 있어야 합니다."
            ) from exc
    if len(by_temperature) < 2:
        raise ExportError(
            "온도가 하나뿐입니다. 온도 의존 덱은 둘 이상의 온도가 있어야 합니다 — "
            "하나면 탄소성 형식을 쓰세요."
        )
    curves: list[tuple[float, list[tuple[float, float]]]] = []
    notes: list[str] = []
    for temperature in sorted(by_temperature):
        points, said = prepare(tuple(sorted(by_temperature[temperature])))
        notes.extend(f"온도 {temperature:.1f} K: {line}" for line in said)
        curves.append((temperature, points))
    return curves, notes


def _elastic_note(deck: Deck) -> str | None:
    if elastic_by_temperature(deck):
        return None
    return "탄성은 온도 하나의 값입니다 — 온도별 탄성계수는 카드에 없습니다."


def _summary(deck: Deck, curves: list[tuple[float, list[tuple[float, float]]]]) -> str:
    return (
        f"Temperature dependent plasticity: {len(curves)} temperatures "
        f"({curves[0][0]:.5g} ~ {curves[-1][0]:.5g} K), tabular."
    )


# ── ANSYS ──────────────────────────────────────────────────────────────────


@register_renderer(
    key="ansys_temperature",
    label="ANSYS (온도 의존)",
    extension="mac",
    suffix="_temperature",
    describe="MP + TB,PLASTIC(MISO) + 온도마다 TBTEMP — 온도별 소성 표. 온도는 K.",
    keywords=("TB,PLASTIC", "TBTEMP", "TBPT"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        _NEEDS_TEMPERATURE,
    ),
)
def render_ansys_temperature(deck: Deck) -> Rendered:
    """NTEMP·NPTS 는 ANSYS 가 안 쓰지만(TBPT 가 점을 끼워 넣는다) 읽기 좋게 적는다."""
    curves, notes = temperature_curves(deck)
    lines, said = _ansys._structural(deck)
    lines.append(f"! {_summary(deck, curves)}")
    lines.append(f"! {_KELVIN}")
    elastic = _elastic_note(deck)
    if elastic:
        lines.append(
            "! EX, PRXY are single-temperature values (not measured per temperature)."
        )
    npts = max(len(points) for _, points in curves)
    lines.append(f"TB,PLASTIC,{_ansys.MATERIAL},{len(curves)},{npts},MISO")
    for temperature, points in curves:
        lines.append(f"TBTEMP,{_free(temperature)}")
        lines.extend(f"TBPT,DEFI,{_free(strain)},{_free(stress)}" for strain, stress in points)
    return Rendered(
        text="\n".join(lines) + "\n",
        notes=(*notes, *said, *((elastic,) if elastic else ())),
    )


# ── LS-DYNA ────────────────────────────────────────────────────────────────


def _cut_common(
    curves: list[tuple[float, list[tuple[float, float]]]],
) -> tuple[list[tuple[float, list[tuple[float, float]]]], float, list[float]]:
    end = min(points[-1][0] for _, points in curves)
    cut = [(key, _dyna._cut(points, end)) for key, points in curves]
    trimmed = [key for key, points in curves if points[-1][0] > end]
    return cut, end, trimmed


@register_renderer(
    key="dyna_temperature",
    label="LS-DYNA (온도 의존)",
    extension="k",
    suffix="_temperature",
    describe=(
        "*MAT_PIECEWISE_LINEAR_PLASTIC_THERMAL(255) + *DEFINE_TABLE(온도) + 온도마다 "
        "*DEFINE_CURVE. 온도는 연성 해석이나 *LOAD_THERMAL_* 이 준다."
    ),
    keywords=(
        "*KEYWORD",
        "*MAT_PIECEWISE_LINEAR_PLASTIC_THERMAL",
        "*DEFINE_TABLE",
        "*DEFINE_CURVE",
        "*END",
    ),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("thermal", optional=True),
        _NEEDS_TEMPERATURE,
    ),
)
def render_dyna_temperature(deck: Deck) -> Rendered:
    """카드 셋: `MID RO E PR C P FAIL TDEL` / `TABIDC TABIDT LALPHA _ VP` / `ALPHA TREF`.

    인장·압축에 같은 표를 쓴다(TABIDC = TABIDT). 온도별 탄성 표가 있으면 E·PR 를 음수(곡선
    번호)로 둔다. ALPHA 는 카드의 선팽창계수(상수) — 없으면 0(열변형 없음)이고 그 사실을
    적는다.
    """
    density = deck.number("elastic", "density")
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    assert density is not None and youngs is not None and poisson is not None
    curves, notes = temperature_curves(deck)
    cut, end, trimmed = _cut_common(curves)
    if trimmed:
        notes.append(
            f"온도별 곡선의 끝이 달라 모두 소성변형률 {end:.4g} 에서 잘랐습니다 — "
            f"LS-DYNA 표는 곡선이 같은 x 에서 끝나야 합니다. 잘린 온도: "
            f"{', '.join(f'{one:.1f}' for one in trimmed)} K."
        )
    table_id = deck.solver_id
    rows = elastic_by_temperature(deck)
    e_curve = deck.solver_id * 100 + 90 if rows else None
    nu_curve = deck.solver_id * 100 + 91 if rows else None
    alpha = deck.number("thermal", "thermal_expansion")
    f10, i10 = _dyna._f10, _dyna._i10

    lines = ["*KEYWORD", *_header(deck, "$"), *_dyna._units_comment(deck)]
    lines.append(f"$ {_summary(deck, cut)}")
    lines.append(f"$ {_KELVIN}")
    lines.append("$ Temperatures come from a coupled run or *LOAD_THERMAL_* (Remark 4).")
    if trimmed:
        lines.append(
            f"$ All curves cut at plastic strain {end:.6g} (a table needs one x range)."
        )
    if rows:
        lines.append("$ E < 0 and PR < 0: |value| is a load curve of E(T), PR(T).")
    else:
        lines.append("$ E, PR are single-temperature values (not measured per temperature).")
        notes.append("탄성은 온도 하나의 값입니다 — 온도별 탄성계수는 카드에 없습니다.")
    if alpha is None:
        lines.append("$ ALPHA = 0: no thermal expansion on the card.")
    lines.append("*MAT_PIECEWISE_LINEAR_PLASTIC_THERMAL")
    lines.append(
        "$      mid        ro         e        pr         c         p      fail      tdel"
    )
    lines.append(
        i10(deck.solver_id)
        + f10(density)
        + (f10(-float(e_curve)) if e_curve else f10(youngs))
        + (f10(-float(nu_curve)) if nu_curve else f10(poisson))
    )
    lines.append("$   tabidc    tabidt    lalpha                  vp")
    lines.append(i10(table_id) + i10(table_id))
    lines.append("$    alpha      tref")
    lines.append(f10(alpha if alpha is not None else 0.0))
    lines.append("*DEFINE_TABLE")
    lines.append("$     tbid       sfa      offa")
    lines.append(i10(table_id))
    lines.append("$  temperature (ascending, one per line)")
    lines.extend(f"{temperature:>20.12E}" for temperature, _ in cut)
    lcint = max(_dyna.DEFAULT_LCINT, *(len(points) for _, points in cut))
    for index, (_, points) in enumerate(cut, start=1):
        lines.extend(_dyna._curve(deck.solver_id * 100 + index, points, lcint))
    if rows:
        lines.extend(_dyna._curve(deck.solver_id * 100 + 90, [(t, e) for t, e, _ in rows]))
        lines.extend(_dyna._curve(deck.solver_id * 100 + 91, [(t, nu) for t, _, nu in rows]))
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── Nastran · OptiStruct ───────────────────────────────────────────────────


def _plastic_table(
    table_id: int, points: list[tuple[float, float]], *, typed: bool
) -> list[str]:
    """TABLES1 — 진응력 대 **소성**변형률, 첫 점 (0, 항복). MSC 는 TYPE=2 를 적는다."""
    fields: list[_bulk.Field] = [
        table_id,
        2 if typed else None,
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    for strain, stress in points:
        fields.extend((strain, stress))
    fields.append("ENDT")
    return _bulk._card("TABLES1", fields)


def _tablest(table_id: int, pairs: list[tuple[float, int]]) -> list[str]:
    fields: list[_bulk.Field] = [table_id, None, None, None, None, None, None, None]
    for temperature, tid in pairs:
        fields.extend((temperature, tid))
    fields.append("ENDT")
    return _bulk._card("TABLEST", fields)


#: 온도별 TABLES1 이 쓰는 표 번호 자리 — `재료 번호 * 10 + 자리` 의 4~9(중심 `_bulk._table_id`
#: 가 0 소성 · 1 E · 2 ν · 3 α 를 쓴다). 그래서 온도는 여섯까지다.
_CURVE_SLOTS = range(4, 10)


def _curve_ids(deck: Deck, count: int) -> list[int]:
    """온도별 TABLES1 번호 — **8자리 안**(재료 번호 * 10 + 4~9).

    전에는 `재료 번호 * 100 + 10 + 차례` 라 재료 번호(최대 7자리)가 크면 9자리가 됐다 —
    Nastran 의 번호는 1억 미만이다(2026-10-04 점검, 2026-10-08 고침). 자리를 넘으면 지어
    붙이지 않고 말한다 — LS-DYNA · Abaqus 형식은 온도 수에 제한이 없다.
    """
    if count > len(_CURVE_SLOTS):
        raise ExportError(
            f"온도가 {count}개입니다 — Nastran · OptiStruct 덱은 재료 하나의 표 번호 자리"
            f"(8자리 안)에 온도 {len(_CURVE_SLOTS)}개까지 싣습니다. 온도를 줄이거나 "
            f"LS-DYNA · Abaqus 형식을 쓰세요."
        )
    return [_bulk._table_id(deck, slot) for slot in _CURVE_SLOTS[:count]]


@register_renderer(
    key="optistruct_temperature",
    label="OptiStruct (온도 의존)",
    extension="fem",
    suffix="_temperature",
    describe=(
        "MAT1(+MATT1) + MATS1(TYPSTRN=1) → TABLEST → 온도마다 TABLES1(소성변형률). 온도는 K."
    ),
    keywords=("MAT1*", "MATS1*", "TABLEST*", "TABLES1*"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        _NEEDS_TEMPERATURE,
    ),
)
def render_optistruct_temperature(deck: Deck) -> Rendered:
    curves, notes = temperature_curves(deck)
    body, said = _bulk._mat1(deck)
    tablest = _bulk._table_id(deck, 0)
    ids = _curve_ids(deck, len(curves))
    lines = _bulk._head(deck, "OptiStruct")
    lines.append(f"$ {_summary(deck, curves)}")
    lines.append(f"$ {_KELVIN}")
    lines.append(
        "$ TYPSTRN=1: TABLES1 are true stress vs PLASTIC strain - only then may MATS1"
    )
    lines.append(
        "$   reference a TABLEST. LIMIT1 blank: each table's first point is its yield."
    )
    elastic = _elastic_note(deck)
    if elastic:
        lines.append("$ E, NU are single-temperature values (not measured per temperature).")
    lines.extend(body)
    lines.append("$MATS1* MID             TID             TYPE            H")
    lines.append("$*      YF              HR              LIMIT1")
    lines.append("$*      TYPSTRN")
    lines.extend(
        _bulk._card(
            "MATS1",
            [deck.solver_id, tablest, "PLASTIC", None, 1, 1, None, None, 1],
        )
    )
    lines.extend(_tablest(tablest, list(zip((t for t, _ in curves), ids, strict=True))))
    for tid, (_, points) in zip(ids, curves, strict=True):
        lines.extend(_plastic_table(tid, points, typed=False))
    return Rendered(
        text="\n".join(lines) + "\n",
        notes=(*notes, *said, *((elastic,) if elastic else ())),
    )


@register_renderer(
    key="nastran_temperature",
    label="Nastran (온도 의존)",
    extension="bdf",
    suffix="_temperature",
    describe=(
        "MAT1 + MATT1 + MATEP(FORM=TABLE) + MATTEP → TABLEST → 온도마다 TABLES1(TYPE=2). "
        "SOL 400 전용 — MSC 는 MATS1 에서 TABLEST 를 금한다."
    ),
    keywords=("MAT1*", "MATT1*", "MATEP*", "MATTEP*", "TABLEST*"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        _NEEDS_TEMPERATURE,
    ),
)
def render_nastran_temperature(deck: Deck) -> Rendered:
    """MATTEP 의 칸은 같은 자리의 MATEP 칸을 **바꿔 넣는다**(Remark 1). MATEP 의 FID 에는 기준
    온도의 표를 적는다 — MATTEP 만 두고 FID 를 비워도 되는지는 문서가 말하지 않아 안전한 쪽.

    MATT1 은 3~7칸 중 하나는 표여야 한다(MATTEP Remark 5). 온도별 탄성이 없으면 E 를 소성
    표의 온도마다 같은 값으로 적는다.
    """
    curves, notes = temperature_curves(deck)
    youngs = deck.number("elastic", "youngs_modulus")
    assert youngs is not None
    body, said = _bulk._mat1(deck, with_tables=False)
    rows = elastic_by_temperature(deck)
    tablest = _bulk._table_id(deck, 0)
    e_table = _bulk._table_id(deck, 1)
    nu_table = _bulk._table_id(deck, 2) if rows else None
    ids = _curve_ids(deck, len(curves))
    lines = _bulk._head(deck, "MSC Nastran")
    lines.append(f"$ {_summary(deck, curves)}")
    lines.append(f"$ {_KELVIN}")
    lines.append(
        "$ SOL 400: MAT1 + MATEP(FORM=TABLE) + MATT1 + MATTEP (MATS1 may not use TABLEST)."
    )
    lines.append("$ TABLES1 TYPE=2: true stress vs PLASTIC strain, first point (0, yield).")
    lines.extend(body)
    if rows:
        e_points = [(t, e) for t, e, _ in rows]
    else:
        e_points = [(t, youngs) for t, _ in curves]
        lines.append("$ E is a single-temperature value - MATT1 needs a table, so it is flat.")
        notes.append(
            "탄성은 온도 하나의 값입니다 — MSC 의 MATT1 은 표가 하나는 있어야 해서 E 를 소성 "
            "표의 온도마다 같은 값으로 적었습니다."
        )
    lines.append("$ MATT1: field 3 = E(T), field 5 = NU(T). Tables REPLACE MAT1.")
    lines.extend(_bulk._card("MATT1", [deck.solver_id, e_table, None, nu_table]))
    lines.extend(_bulk._pairs_table("TABLEM1", e_table, e_points))
    if rows and nu_table is not None:
        lines.extend(_bulk._pairs_table("TABLEM1", nu_table, [(t, n) for t, _, n in rows]))
    lines.append("$MATEP* MID             FORM            Y0              FID")
    lines.extend(_bulk._card("MATEP", [deck.solver_id, "TABLE", None, ids[0]]))
    lines.append("$MATTEP* MID                            T(Y0)           T(FID)")
    lines.extend(_bulk._card("MATTEP", [deck.solver_id, None, None, tablest]))
    lines.extend(_tablest(tablest, list(zip((t for t, _ in curves), ids, strict=True))))
    for tid, (_, points) in zip(ids, curves, strict=True):
        lines.extend(_plastic_table(tid, points, typed=True))
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, *said))


# ── Radioss ────────────────────────────────────────────────────────────────


@register_renderer(
    key="openradioss_temperature",
    label="Radioss (온도 의존)",
    extension="rad",
    suffix="_temperature",
    describe=(
        "/MAT/LAW109 + /TABLE/1(기준 곡선) + /TABLE/1(온도 → 곡선) + /FUNCT — 온도별 소성 표. "
        "해석 온도는 T0 칸이나 /HEAT/MAT 이 준다."
    ),
    keywords=("/MAT/LAW109", "/TABLE/1/", "/FUNCT/", "/UNIT/1", "/END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        _NEEDS_TEMPERATURE,
    ),
)
def render_openradioss_temperature(deck: Deck) -> Rendered:
    """LAW109 의 항복 `σy = f_h(εp)·f_t(εp, T) / f_t(εp, Tref)`.

    f_h 를 기준 온도(가장 낮은 온도)의 곡선으로, f_t 를 (온도, 곡선) 표로 두고 Tref 를 그
    기준 온도로 적으면 σy 는 **그 온도의 곡선 그대로**다.

    ## 온도가 어디서 오나

    Cp=0 이면 등온이다 — 온도가 T0 에 머문다(T0 를 비우면 Tref). /HEAT/MAT 이 있으면 열해석의
    온도를 쓴다. **구조 해석만 돌리면서 다른 온도의 물성을 보려면 T0 칸에 그 온도를 적는다** —
    덱에 적는다.
    """
    density = deck.number("elastic", "density")
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    assert density is not None and youngs is not None and poisson is not None
    curves, notes = temperature_curves(deck)
    reference = curves[0][0]
    base = deck.solver_id * 100
    reference_table, temperature_table = base + 1, base + 2
    fids = [base + 10 + index for index in range(len(curves))]

    lines = _radioss._starter(deck)
    lines.append(f"# {_summary(deck, curves)}")
    lines.append(f"# {_KELVIN}")
    lines.append(f"# Tref = {reference:.6g} K (lowest). T0 blank = Tref; Cp = 0 = isothermal.")
    lines.append("# To run at another temperature without a heat analysis, write it in T0.")
    if not elastic_by_temperature(deck):
        lines.append("# E, nu are single-temperature values (not measured per temperature).")
        notes.append("탄성은 온도 하나의 값입니다 — 온도별 탄성계수는 카드에 없습니다.")
    lines.append(f"/MAT/LAW109/{deck.solver_id}/1")
    lines.append(deck.name)
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(f"#{'E':>19}{'nu':>20}")
    lines.append(_fixed(youngs) + _fixed(poisson))
    lines.append(f"#{'Cp':>19}{'eta':>20}{'Tref':>20}{'T0':>20}")
    lines.append(f"{'':>20}{'':>20}{_fixed(reference)}")
    lines.append(
        f"#{'tab_ID_h':>9}{'tab_ID_t':>10}{'Xscale_h':>20}{'Yscale_h':>20}{'':>30}{'Ismooth':>10}"
    )
    lines.append(f"{reference_table:>10}{temperature_table:>10}")
    lines.append(f"#{'tab_ID_eta':>9}{'Xscale_eta':>20}")
    lines.append("")
    lines.append(f"/TABLE/1/{reference_table}")
    lines.append(f"{deck.name[:60]}_HARDENING_AT_TREF")
    lines.append(f"#{'dimension':>9}")
    lines.append(f"{1:>10}")
    lines.append(f"#{'X':>19}{'Y':>20}")
    lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in curves[0][1])
    lines.append(f"/TABLE/1/{temperature_table}")
    lines.append(f"{deck.name[:60]}_HARDENING_BY_TEMPERATURE")
    lines.append(f"#{'dimension':>9}")
    lines.append(f"{2:>10}")
    lines.append(f"#{'fct_ID':>9}{'':>10}{'T':>20}{'':>40}{'Scale_y':>20}")
    lines.extend(
        f"{fid:>10}{'':>10}{_fixed(temperature)}{'':>40}{_fixed(1.0)}"
        for fid, (temperature, _) in zip(fids, curves, strict=True)
    )
    for fid, (temperature, points) in zip(fids, curves, strict=True):
        lines.append(f"/FUNCT/{fid}")
        lines.append(f"{deck.name[:60]}_TRUE_STRESS_AT_{temperature:.5g}K")
        lines.append(f"#{'X':>19}{'Y':>20}")
        lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in points)
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
