"""`*MAT_SIMPLIFIED_JOHNSON_COOK`(098) — **온도항이 없는 카드라 지금 정직하게 낼 수 있다.**

    098   σ = (A + B·εp^n)(1 + C·ln ε̇*)          온도항 없음
    015   σ = (A + B·εp^n)(1 + C·ln ε̇*)(1 - T*^m)  온도항 있음

우리는 A·B·n(이 확장의 적합)과 C(`tensile.rate_family` 묶음)를 낼 수 있지만 **m 은
못 낸다** — 같은 재료를 여러 온도로 당긴 데이터가 없다. 그래서 015 를 내면 m 을
지어내야 하고, 098 을 내면 지어낼 것이 없다. **식에 없는 항은 가정할 일도 없다.**

## 다른 솔버 (2026-09-27)

    Radioss     /MAT/LAW2 — 온도항은 T_melt 를 비워 끈다(1e20 → T* = 0). 여기 있다.
                OpenRadioss 로 돌려 σ = a + b·εp^n 이 손계산과 맞았다(766.50 · 766.47 MPa).
    ANSYS       MAPDL 에 Johnson-Cook 이 없다(TB,RATE 는 Perzyna·Peirce·EVH·Anand 뿐)
    Abaqus      *PLASTIC, HARDENING=JOHNSON COOK 은 m·θmelt·θtransition 이 필수다 — 끄는 칸이
                없어 지어내야 한다. 표(*PLASTIC)로는 이미 나간다
    OptiStruct  MATS1 의 JHCOOK 은 명시 해석 전용이고 칸 차례를 다 대조하지 못했다

## 왜 렌더러가 확장 안에 있나

`matcore/export/dyna.py`(중심 코드)에 두면 그 파일이 `johnson_cook_static` 이라는
**확장의 이름을 알아야** 한다. 그러면 확장이 아니다(ADR 0013, `matcore/extensions.py`
머리말). 확장이 부를 수 있는 등록 함수 넷 중 하나가 `export.register_renderer` 인
것이 바로 이래서다 — 식과 그 식이 나가는 카드는 같은 폴더에 산다.

## C 가 없으면 0 으로 두고 그것을 적는다

속도 묶음을 안 돌린 카드는 `rate_table` 블록이 없다. 그때 C=0 은 **준정적 카드**
라는 뜻이고 그것은 틀린 값이 아니다 — 다만 **적어야 한다.** MaterialTwin 은 늘
C=0 이었다(속도 자료가 없었다). 우리는 있으면 채운다.

## 기준 속도(EPSO)를 1 로 굳히지 않는다

C 는 `σ/σ₀ = 1 + C·ln(ε̇/ε̇₀)` 로 맞춘 값이라 **ε̇₀ 가 무엇이었는지와 한 몸**이다.
묶음이 기준 속도를 함께 내므로(`reference_rate`) 그것을 그대로 적는다. 1 로
굳히면 C 는 그대로인데 기준만 바뀌어 **응력이 조용히 어긋난다.**
"""

from __future__ import annotations

from matcore.export import Deck, ExportError, Need, Rendered, register_renderer
from matcore.export.dyna import _f10

#: 이 식의 파라미터 이름. 등록부와 같아야 한다.
_A, _B, _N = "a", "b", "n"
#: 이 식의 키(`fitting` 등록부)와 이름. 식 키가 없는 옛 카드는 이름으로만 안다.
_FAMILY = "johnson_cook_static"
_LABELS = ("Johnson-Cook", "Johnson-Cook (준정적 항)")


def _params(deck: Deck) -> dict[str, float]:
    """경화 블록에서 A·B·n 을 꺼낸다.

    **식 키를 먼저 본다**(2026-10-08). 전에는 파라미터 이름(a · b · n)만 봐서, 사용자가
    「계산식」 으로 만든 다른 식이 같은 이름을 쓰면 그 계수가 JC 자리에 실렸다 — 덱은
    나오고 해석은 조용히 틀린다. 식 키가 없는 옛 카드는 이름이 Johnson-Cook 일 때만 받는다.
    혼합 곡선(`blend_with`)은 A·B·n 한 벌이 그 곡선이 아니라 받지 않는다.

    그다음 파라미터 이름을 본다 — Voce 면 `sigma_0·q·b` 라 여기서 걸린다.
    """
    values = deck.values("hardening")
    family, label = values.get("family"), values.get("label") or "이름 없는 적합"
    if family != _FAMILY and not (family is None and label in _LABELS):
        raise ExportError(
            f"카드의 경화식이 '{label}' 입니다 — Johnson-Cook 준정적 항으로 적합한 카드에서만 "
            "A·B·n 을 냅니다. 표 형식이 필요하면 *MAT_024 를 쓰세요."
        )
    if values.get("blend_with"):
        raise ExportError(
            f"경화 곡선이 '{values['blend_with']}' 와 혼합돼 있습니다 — A·B·n 한 벌이 그 "
            "곡선이 아닙니다. 혼합 없이 맞춘 카드를 쓰세요."
        )
    found: dict[str, float] = {}
    for row in deck.rows("hardening"):
        name, value = row.get("name"), row.get("value")
        if isinstance(name, str) and isinstance(value, int | float):
            found[name] = float(value)
    missing = [one for one in (_A, _B, _N) if one not in found]
    if missing:
        label = deck.values("hardening").get("label") or "이름 없는 적합"
        raise ExportError(
            f"카드의 경화식이 '{label}' 이라 A·B·n 이 없습니다(빠진 것: {missing}). "
            "*MAT_098 은 Johnson-Cook 준정적 항으로 적합한 카드에서만 나옵니다 — "
            "표 형식이 필요하면 *MAT_024 를 쓰세요."
        )
    return found


@register_renderer(
    key="dyna_johnson_cook",
    label="LS-DYNA (Johnson-Cook 단순화)",
    extension="k",
    suffix="_jc",
    describe=(
        "*MAT_SIMPLIFIED_JOHNSON_COOK(098) — σ=(A+B·εp^n)(1+C·ln ε̇*). "
        "온도항이 없는 카드라 온도 데이터 없이도 지어내는 값이 없다. "
        "C 는 속도 묶음이 있으면 채우고, 없으면 0(준정적)으로 두고 덱에 적는다."
    ),
    keywords=("*KEYWORD", "*MAT_SIMPLIFIED_JOHNSON_COOK", "*END"),
    needs=(
        # RO 는 자리 있는 필드다 — 동적 해석 솔버라 비울 수 없다(*MAT_024 와 같다).
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("hardening", rows_min=3),
        # 속도 묶음은 없어도 덱이 나온다. 그 사실은 아래에서 덱에 적는다.
        Need("rate_table", optional=True),
    ),
)
def render_dyna_johnson_cook(deck: Deck) -> Rendered:
    found = _params(deck)
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    if youngs is None or poisson is None or density is None:
        raise ExportError("*MAT_098 은 탄성계수·푸아송비·밀도가 다 있어야 합니다.")

    notes: list[str] = []
    lines = ["*KEYWORD", f"$ MatNexus — {deck.name}", f"$ 단위계: {deck.units.declaration}"]
    for one in deck.provenance:
        lines.append(f"$ {one}")

    rate_c = deck.number("rate_table", "jc_c")
    reference = deck.number("rate_table", "reference_rate")
    if rate_c is None:
        rate_c = 0.0
        reference = 1.0
        lines.append(
            "$ C=0 (준정적). 속도 묶음이 없어 변형률속도 의존을 재지 않았습니다 — "
            "이 덱은 충격·낙하 해석에 그대로 쓰이지 못합니다."
        )
        notes.append(
            "속도 묶음이 없어 C=0 으로 두고 그 사실을 덱에 적었습니다. "
            "속도가 다른 인장 시험을 「속도별 소성 곡선」 으로 묶으면 채워집니다."
        )
    else:
        if reference is None:
            raise ExportError(
                "속도 묶음에 C 는 있는데 기준 속도가 없습니다. "
                "C 는 기준 속도와 한 몸이라 그것 없이는 덱에 적을 수 없습니다."
            )
        lines.append(f"$ C 는 기준 속도 {reference:.4g} (덱 단위) 에서 맞춘 값입니다.")

    lines.append("$ sigma = (A + B*eps_p^n) * (1 + C*ln(eps_dot/EPSO))  — 온도항 없음(098)")
    quality = deck.number("hardening", "r_squared")
    if quality is not None:
        lines.append(f"$ 경화 적합 R^2 = {quality:.4f}")
    lines.append("$ 온도 의존은 이 카드에 없습니다. 고온 해석이면 *MAT_015 가 필요하고,")
    lines.append("$ 그러려면 여러 온도의 인장 시험이 있어야 합니다 — 지금은 없습니다.")

    lines.append("*MAT_SIMPLIFIED_JOHNSON_COOK")
    lines.append("$#     mid        ro         e        pr        vp")
    # VP=1 — 점소성 정식화. 0(비율속 항복응력 배율)이면 속도항이 응력 전체를
    # 배로 늘려 탄성까지 흔든다.
    lines.append(
        f"{deck.solver_id:>10}{_f10(density)}{_f10(youngs)}{_f10(poisson)}{_f10(1.0)}"
    )
    lines.append(
        "$#       a         b         n         c    psfail    sigmax    sigsat      epso"
    )
    lines.append(
        f"{_f10(found[_A])}{_f10(found[_B])}{_f10(found[_N])}{_f10(rate_c)}"
        f"{_f10(0.0)}{_f10(0.0)}{_f10(0.0)}{_f10(float(reference))}"
    )
    lines.append("*END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="openradioss_johnson_cook",
    label="Radioss (Johnson-Cook)",
    extension="rad",
    suffix="_jc",
    describe=(
        "/MAT/LAW2(PLAS_JOHNS) — σ=(a+b·εp^n)(1+c·ln ε̇*). 온도항은 비운다(T_melt 가 비면 "
        "꺼진다). c 는 속도 묶음이 있으면 채우고, 없으면 0(준정적)으로 두고 덱에 적는다."
    ),
    keywords=("/MAT/LAW2/", "/UNIT/1", "/END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("hardening", rows_min=3),
        Need("rate_table", optional=True),
    ),
)
def render_openradioss_johnson_cook(deck: Deck) -> Rendered:
    """LAW2 는 칸이 다섯 줄이다(OpenRadioss `matl2_plas_johns.cfg`):

        rho
        E  ν  Iflag(10)  VP(10)  Pmin
        a  b  n  εp_max  σ_max0
        c  ε̇0  ICC(10)  Fsmooth(10)  Fcut  Chard
        m  T_melt  rho_Cp  T_r  T_max

    **온도항은 끄는 칸이 따로 없다** — m=0 은 파서가 1 로 바꾼다. T_melt 를 비우면 1e20 이 되어
    T* 가 0 에 머문다: 온도를 안 잰 카드에서 지어낼 것이 없다. rho_Cp 도 비운다(단열 가열
    없음).
    VP=1 은 소성변형률 속도로 속도항을 읽는다 — *MAT_098 의 VP=1 과 같은 선택이다.
    """
    from matcore.export import _fixed, _unit_block

    found = _params(deck)
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    if youngs is None or poisson is None or density is None:
        raise ExportError("LAW2 는 탄성계수·푸아송비·밀도가 다 있어야 합니다.")
    rate_c = deck.number("rate_table", "jc_c")
    reference = deck.number("rate_table", "reference_rate")
    notes: list[str] = []
    lines = [
        "#RADIOSS STARTER",
        f"# MatNexus — {deck.name}",
        *(f"# {one}" for one in deck.provenance),
    ]
    lines.extend(_unit_block(deck))
    lines.append(
        "# sigma = (a + b*eps_p^n) * (1 + c*ln(eps_dot/eps_dot0)) - temperature term off"
    )
    if rate_c is None:
        lines.append("# c = 0 (quasi-static): no strain-rate groups on the card.")
        notes.append(
            "속도 묶음이 없어 c=0 으로 두고 그 사실을 덱에 적었습니다. 속도가 다른 인장 "
            "시험을 「속도별 소성 곡선」 으로 묶으면 채워집니다."
        )
    elif reference is None:
        raise ExportError(
            "속도 묶음에 C 는 있는데 기준 속도가 없습니다. C 는 기준 속도와 한 몸이라 그것 "
            "없이는 덱에 적을 수 없습니다."
        )
    else:
        lines.append(f"# c fitted against the reference rate {reference:.4g} (deck units).")
    lines.append("# T_melt blank = 1e20: T* stays 0 (no temperature data on this card).")
    lines.append(f"/MAT/LAW2/{deck.solver_id}/1")
    lines.append(deck.name)
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(f"#{'E':>19}{'nu':>20}{'Iflag':>10}{'VP':>10}{'Pmin':>20}")
    lines.append(f"{_fixed(youngs)}{_fixed(poisson)}{0:>10}{1:>10}")
    lines.append(f"#{'a':>19}{'b':>20}{'n':>20}{'Eps_p_max':>20}{'Sig_max0':>20}")
    lines.append(_fixed(found[_A]) + _fixed(found[_B]) + _fixed(found[_N]))
    lines.append(
        f"#{'c':>19}{'Eps_dot_0':>20}{'ICC':>10}{'Fsmooth':>10}{'Fcut':>20}{'Chard':>20}"
    )
    lines.append(
        _fixed(rate_c if rate_c is not None else 0.0)
        + (_fixed(reference) if rate_c is not None and reference is not None else "")
    )
    lines.append(f"#{'m':>19}{'T_melt':>20}{'rho_Cp':>20}{'T_r':>20}{'T_max':>20}")
    lines.append("")
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
