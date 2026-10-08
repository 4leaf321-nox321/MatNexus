"""S-N 카드 블록 — 점(런아웃 표시 포함)이 행, Basquin 계수·피로 강도가 값. LS-DYNA
*MAT_ADD_FATIGUE(2026-09-27) · OptiStruct MATFAT · MSC MATFTG(2026-10-08) 덱도 여기 있다.

## 인장강도 · 항복강도 칸 — 시험이 아니라 적어 둔 값이 채운다

MATFAT · MATFTG 는 STATIC 줄의 인장강도(UTS)가 필수다(평균응력 · 표면 보정에 쓴다). 피로 시험은
그 값을 안 준다 — 그래서 한동안 두 형식을 안 냈다(지어 넣으면 보정이 그 숫자를 믿는다).
칸에 물성 키를 달아 두면 **카드를 저장할 때 재료에 적어 둔 값이 빈 칸을 채운다**
(`app/shared/declared_slots` — 모든 카드 길이 거친다). 기본 항목 「인장강도 · 항복강도」 는 그
키에 이미 이어져 있다. 적어 둔 값이 없으면 칸이 비고, 두 형식은 목록에서 막힌다.

## 범위와 진폭

우리 A 는 **진폭**의 절편이다(S = A·N^b). MATFAT · MATFTG 의 SRI1 은 **범위**의 절편(1 회)이라
2A 를 적는다 — A 를 그대로 적으면 같은 응력에서 수명이 2^(1/b) 배(b=-0.1 이면 1/1024)로
줄어든다. 보수 쪽이라 덱이 멀쩡해 보인다.
둘째 기울기는 첫째와 같게 둔다 — 한 직선, 피로 한도를 지어 넣지 않는다(LS-DYNA 덱과 같다).

ANSYS 의 S-N 명령(FP)은 보관 기능이고, Abaqus·Radioss 는 재료 카드에 S-N 자리가 없다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.export import Deck, ExportError, Need, Rendered, _header, register_renderer
from matcore.export import bulk as _bulk
from matcore.export import dyna as _dyna
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
            Produced(
                key="log_scatter",
                label="흩어짐",
                si_unit="1",
                help="수명의 흩어짐 — log N 잔차의 표준편차(자릿수). 0.3 이면 같은 응력에서 "
                "수명이 약 두 배 갈린다.",
            ),
            Produced(key="strength_at_1e5", label="피로 강도 @1e5", si_unit="Pa"),
            Produced(key="strength_at_1e6", label="피로 강도 @1e6", si_unit="Pa"),
            Produced(key="strength_at_1e7", label="피로 강도 @1e7", si_unit="Pa"),
            # 시험이 안 주는 정적 강도 — 카드를 저장할 때 재료에 적어 둔 값이 채운다.
            Produced(
                key="tensile_strength",
                label="인장강도 (UTS)",
                si_unit="Pa",
                property_key="mechanical.tensile_strength",
                help="재료에 적어 둔 값. OptiStruct · Nastran 피로 카드가 요구한다.",
            ),
            Produced(
                key="yield_strength",
                label="항복강도",
                si_unit="Pa",
                property_key="mechanical.yield_strength",
                help="재료에 적어 둔 값. 있으면 피로 카드의 STATIC 줄에 함께 적는다.",
            ),
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
        # 점 · 곡선이 본체다 — 적어 둔 값(인장강도 · 녹는점)은 곁칸만 채운다(2026-10-08).
        from_values=False,
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
    a, b = _basquin(deck)
    ratios = _ratios(deck)
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
        # 칸에 드는 만큼 정밀하게(`dyna._f10`) — 유효숫자 4자리면 a 의 상대오차가 수명에서
        # 1/|b| 배(b ≈ -0.1 이면 10 배)로 커진다(2026-10-08 고침).
        f"{deck.solver_id:>10}{-3:>10}{0:>10}{_dyna._f10(a)}{_dyna._f10(b)}{'':>10}{0:>10}{1:>10}"
    )
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def _basquin(deck: Deck) -> tuple[float, float]:
    a = deck.number("sn_curve", "basquin_a")
    b = deck.number("sn_curve", "basquin_b")
    assert a is not None and b is not None
    if a <= 0.0 or b >= 0.0:
        raise ExportError(
            f"Basquin a={a:g}, b={b:g} 입니다 — a 는 양수, b 는 음수여야 S-N 곡선입니다."
        )
    return a, b


def _ratios(deck: Deck) -> list[float]:
    return sorted(
        {
            round(float(row["stress_ratio"]), 3)
            for row in deck.rows("sn_curve")
            if isinstance(row.get("stress_ratio"), int | float)
        }
    )


def _ratio_note(ratios: list[float]) -> list[str]:
    if not ratios or ratios == [-1.0]:
        return []
    return [
        f"시험의 응력비 R 이 {', '.join(f'{r:g}' for r in ratios)} 입니다 — 완전 역전(R=-1) "
        f"곡선이 아니므로 평균응력 보정을 쓰면 두 번 보정될 수 있습니다."
    ]


def _tested_to(deck: Deck) -> float:
    """시험이 끝난 수명 — 둘째 기울기가 시작하는 자리(NC1)에 적는다. 두 기울기가 같아 곡선은
    안 바뀐다. 행이 없으면 1e7(피로 강도를 재는 관례 수명)."""
    cycles = [
        float(row["cycles_to_failure"])
        for row in deck.rows("sn_curve")
        if isinstance(row.get("cycles_to_failure"), int | float)
        and row["cycles_to_failure"] > 0
    ]
    return max(cycles) if cycles else 1.0e7


#: 단위계의 응력 기호 → (솔버가 받는 이름, 1 MPa 가 그 단위로 얼마인가). **기호로 가른다** —
#: 정의판도 같은 판단을 해야 하는데 정의판이 읽을 수 있는 것은 기호(`units.Pa`)다.
_STRESS_NAMES = {
    "MPa": ("MPA", 1.0),
    "Pa": ("PA", 1.0e6),
    "psi": ("PSI", 145.0377377),
    "ksi": ("KSI", 0.1450377377),
}
_LENGTH_NAMES = {"m": "M", "mm": "MM", "cm": "CM", "km": "KM", "in": "IN", "ft": "FT"}


def _stress_name(deck: Deck, solver: str) -> tuple[str, float]:
    """`(이름, 1 MPa 의 이 계 숫자)`. 이름이 없는 응력 단위면 멈춘다 — 짐작해 적으면 숫자가
    10⁶ 배 다른 재료가 오류 없이 들어간다."""
    symbol = deck.units.symbol("Pa")
    if symbol not in _STRESS_NAMES:
        raise ExportError(
            f"{solver} 피로 카드는 응력을 MPa · Pa · psi · ksi 로만 받습니다 — 이 단위계의 "
            f"응력({symbol})은 이름이 없습니다. 다른 단위계로 내세요."
        )
    return _STRESS_NAMES[symbol]


def _strengths(deck: Deck) -> tuple[float, float | None]:
    uts = deck.number("sn_curve", "tensile_strength")
    assert uts is not None
    ys = deck.number("sn_curve", "yield_strength")
    if uts <= 0.0 or (ys is not None and ys <= 0.0):
        raise ExportError(
            "인장강도 · 항복강도는 양수여야 합니다 — 재료에 적어 둔 값을 보세요."
        )
    return uts, ys


_FATIGUE_NEEDS = (
    Need("sn_curve", values=("basquin_a", "basquin_b", "tensile_strength")),
    Need("sn_curve", values=("yield_strength",), optional=True),
)


def _range_comments(a: float, b: float, end: float, slope: str, knee: str) -> list[str]:
    return [
        "$ S-N in stress RANGE: SRI1 = 2 x amplitude intercept"
        f" ({a:.6g} * N^{b:.6g} amplitude).",
        f"$ {slope}2 = {slope}1: one straight line, no endurance limit;",
        f"$   {knee} = {end:.6g} cycles is where the tests ended (same slope on both sides -",
        "$   the curve is unchanged).",
        "$ UTS / YS are the values stated on the material, not from the fatigue tests.",
        "$ MID must be the structural MAT1 this fatigue curve belongs to.",
    ]


_MID_NOTE = "피로 카드는 구조 재료(MAT1)에 붙습니다 — MID 를 그 재료 번호로 맞추세요."


@register_renderer(
    key="optistruct_fatigue",
    label="OptiStruct (피로 S-N)",
    extension="fem",
    suffix="_fatigue",
    describe=(
        "MATFAT — STATIC(인장 · 항복강도) + SN(SRI1 = 2A 범위 절편, B1 = B2 = b). 인장강도는 "
        "재료에 적어 둔 값이 카드에 실려 있어야 한다. MID 는 구조 재료(MAT1)의 번호."
    ),
    keywords=("MATFAT*",),
    needs=_FATIGUE_NEEDS,
)
def render_optistruct_fatigue(deck: Deck) -> Rendered:
    """OptiStruct `MATFAT`(Reference Guide) — `MID UNIT LENUNIT` / `STATIC YS UTS` /
    `SN SRI1 B1 NC1 B2 FL SE`.

    **UNIT 를 늘 적는다** — 비우면 MPa 로 읽는다. SI 덱(Pa)의 SRI1 이 10⁶ 배 커진다. LENUNIT 은
    비우면 UNIT 에서 짐작하므로(Pa → m, MPa → mm) 단위계의 길이를 적는다. A/R 은 기본(범위)에
    두고 SRI1 에 2A 를 적는다 — A/R 칸은 판마다 있고 없다. FL(피로 한도)·SE 는 비운다.
    매뉴얼이 MATFAT 의 S-N 을 R=-1 시험의 것으로 본다 — 아니면 말한다.
    """
    a, b = _basquin(deck)
    uts, ys = _strengths(deck)
    end = _tested_to(deck)
    unit, _ = _stress_name(deck, "OptiStruct")
    length = _LENGTH_NAMES.get(deck.units.symbol("m"))
    notes = [_MID_NOTE, *_ratio_note(_ratios(deck))]
    lines = _bulk._head(deck, "OptiStruct")
    lines.extend(_range_comments(a, b, end, "B", "NC1"))
    if length is None:
        lines.append("$ LENUNIT left blank - this length unit has no MATFAT name.")
    lines.extend(
        [
            "$MATFAT* MID             UNIT            LENUNIT",
            "$*      STATIC          YS              UTS",
            "$*      SN              SRI1            B1              NC1",
            "$*      B2              FL              SE",
            *_bulk._card(
                "MATFAT",
                [
                    deck.solver_id, unit, length, None, None, None, None, None,
                    "STATIC", ys, uts, None, None, None, None, None,
                    "SN", 2.0 * a, b, end, b, None, None, None,
                ],
            ),
        ]
    )  # fmt: skip
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="nastran_fatigue",
    label="Nastran (피로 S-N)",
    extension="bdf",
    suffix="_fatigue",
    describe=(
        "MATFTG — STATIC(인장 · 항복강도, 시험 R) + SN(SRI1 = 2A 범위 절편, b1 = b2 = b). "
        "SOL 101 · 103 · 112 임베디드 피로(금속). 모델 응력이 MPa 가 아니면 DTI,UNITS 를 "
        "모델에 둔다."
    ),
    keywords=("MATFTG*",),
    needs=_FATIGUE_NEEDS,
)
def render_nastran_fatigue(deck: Deck) -> Rendered:
    """MSC `MATFTG`(Embedded Fatigue User's Guide) — `MID CNVRT` /
    `STATIC YS UTS CODE TYPE RR SE mp` / `SN SRI1 b1 Nc1 b2 Nfc SE BTHRES`.

    응력은 **모델 단위**로 적는다(CNVRT 기본 1). 피로 모듈은 MPa 로 바꿔 읽으므로 모델이 MPa
    가 아니면 `DTI,UNITS,1,<단위>` 가 모델에 하나 있어야 한다 — **모델 전체의 설정**이라 재료
    조각에 넣지 않고(여러 재료를 한 덱에 합치면 겹친다) 주석과 알림으로 말한다(Abaqus
    `*PHYSICAL CONSTANTS` 와 같은 판단).

    매뉴얼의 허용 범위를 먼저 본다 — UTS 100~4000 MPa(금속 피로만), YS 50~3000 MPa, SRI1
    1~25000 MPa, b1 은 -1 과 -0.02 사이, b2 는 -0.5 보다 커야 한다. 솔버까지 가서 멈추기 전에
    여기서 이유를 말한다. 범위를 벗어난 항복강도는 빼고 말한다(STATIC 줄에서 선택 칸이다).
    """
    a, b = _basquin(deck)
    uts, ys = _strengths(deck)
    end = _tested_to(deck)
    unit, per_mpa = _stress_name(deck, "Nastran")
    notes = [_MID_NOTE]
    if not -1.0 < b < -0.02:
        raise ExportError(
            f"MATFTG 의 b1 은 -1 과 -0.02 사이여야 합니다 — 이 카드는 b = {b:.4g}."
        )
    if not b > -0.5:
        raise ExportError(
            "MATFTG 의 b2 는 -0.5 보다 커야 하는데, 한 직선으로 이으려면 "
            f"b2 = b1 = {b:.4g} 입니다."
        )
    if not 100.0 <= uts / per_mpa <= 4000.0:
        raise ExportError(
            f"MATFTG 는 인장강도 100~4000 MPa 만 받습니다(금속 피로) — 이 카드는 "
            f"{uts / per_mpa:.4g} MPa."
        )
    if not 1.0 <= 2.0 * a / per_mpa <= 2.5e4:
        raise ExportError(
            "MATFTG 의 SRI1 은 1~25000 MPa 만 받습니다 — 이 카드는 "
            f"2A = {2.0 * a / per_mpa:.4g} MPa."
        )
    if ys is not None and not 50.0 <= ys / per_mpa <= 3000.0:
        notes.append(
            f"항복강도 {ys / per_mpa:.4g} MPa 는 MATFTG 범위(50~3000 MPa) 밖이라 뺐습니다."
        )
        ys = None
    ratios = _ratios(deck)
    rr = ratios[0] if len(ratios) == 1 else None
    if len(ratios) > 1:
        notes.append(
            f"시험의 응력비 R 이 여럿입니다({', '.join(f'{r:g}' for r in ratios)}) — "
            "RR 을 비웠습니다(기본 -1). 한 R 의 시험으로 묶은 S-N 이어야 평균응력 보정이 "
            "맞습니다."
        )
    lines = _bulk._head(deck, "MSC Nastran")
    lines.extend(_range_comments(a, b, end, "b", "Nc1"))
    if unit == "MPA":
        lines.append("$ Stresses in MPa - the Nastran fatigue default (no DTI,UNITS needed).")
    else:
        lines.append(
            f"$ Stresses are in {deck.units.symbol('Pa')}: the model needs DTI,UNITS,1,{unit}"
        )
        lines.append("$   (one per model - not written in this material fragment).")
        notes.append(
            f"모델 응력이 {deck.units.symbol('Pa')} 입니다 — Nastran 피로는 MPa 로 바꿔 "
            f"읽으므로 모델에 DTI,UNITS,1,{unit} 를 한 번 두세요(모델 전체 설정이라 덱에 "
            "넣지 않았습니다)."
        )
    if rr is not None:
        lines.append(f"$ RR = {rr:g}: stress ratio R of the tests.")
    lines.extend(
        [
            "$MATFTG* MID",
            "$*      STATIC          YS              UTS             CODE",
            "$*      TYPE            RR              SE              mp",
            "$*      SN              SRI1            b1              Nc1",
            "$*      b2              Nfc             SE              BTHRES",
            *_bulk._card(
                "MATFTG",
                [
                    deck.solver_id, None, None, None, None, None, None, None,
                    "STATIC", ys, uts, None, None, rr, None, None,
                    "SN", 2.0 * a, b, end, b, None, None, None,
                ],
            ),
        ]
    )  # fmt: skip
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
