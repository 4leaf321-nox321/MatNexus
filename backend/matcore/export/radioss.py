"""Radioss 렌더러 — `/MAT/LAW1` · `/MAT/LAW36`(속도별) · `/MAT/LAW42`(초탄성·점탄성).

`/MAT/LAW36`(한 속도)과 `/HEAT/MAT` 는 `matcore/export/__init__.py` 에 먼저 있었다
(`openradioss` · `openradioss_thermal`). 여기는 그 뒤에 붙은 물성들이다. key 가
`openradioss_` 로 시작하는 것은 **한 파일에 한 솔버** 규약 때문이다 — 워크벤치가 여러
재료를 한 덱으로 합칠 때 key 의 앞부분으로 솔버를 가른다(`app/shared/litdeck.py`).

## 칸은 파서의 형식 문자열이 정본이다

Altair 문서의 예제가 틀린 자리가 있었다 — LAW36 예제는 `fct_IDp` 값 줄을 빼 먹었고,
저장소의 예제 덱은 VP 를 81~90열(빈 칸)에 적었다. 여기 칸은 OpenRadioss 가 실제로
읽는 형식(`hm_cfg_files/config/CFG/**/matl*.cfg`)을 따른다(2026-09-27 대조).

## Radioss 는 단위를 선언한다

`/UNIT/1` 을 덱 머리에 두고 재료가 그 번호를 가리킨다(`/MAT/LAWnn/<id>/1`). 값은
`render()` 가 이미 고른 계로 바꿔 놓았고, 여기서는 그 계를 선언할 뿐이다.
"""

from __future__ import annotations

from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _chunks,
    _fixed,
    _header,
    _unit_block,
    failure_lines,
    hyperelastic_terms,
    law36_flat_elastic,
    law36_lines,
    prony_terms,
    rate_curves,
    register_renderer,
)

#: LAW36 이 받는 곡선 수 상한(파서가 1~100 을 받는다).
MAX_RATE_CURVES = 100

#: LAW42 의 Prony 항 상한. 문서에는 없지만 읽는 쪽 배열이 100칸이고 **넘어도 검사하지
#: 않는다** — 배열 밖을 쓴다. 여기서 막는다.
MAX_PRONY_TERMS = 100


def _starter(deck: Deck) -> list[str]:
    return ["#RADIOSS STARTER", *_header(deck, "#"), *_unit_block(deck)]


def _rate_function_id(deck: Deck, index: int) -> int:
    """속도 곡선의 함수 번호 — `재료 번호 * 100 + 차례`.

    재료 번호 그대로는 한 곡선밖에 못 붙인다. 이웃 재료의 번호와 겹치지 않게 자릿수를
    올린다 — 겹치면 Starter 가 중복 번호로 멈춘다(조용히 덮지는 않는다).
    """
    return deck.solver_id * 100 + index


@register_renderer(
    key="openradioss_elastic",
    label="Radioss (선형)",
    extension="rad",
    suffix="_elastic",
    describe="/MAT/LAW1 — 선형 탄성. 소성 표가 없는 카드(문헌 값·DMA 선형 구간)용.",
    keywords=("/MAT/LAW1/", "/UNIT/1", "/END"),
    needs=(
        # RHO_I 는 자리 있는 필드다 — 명시적 솔버라 비울 수 없다(LAW36 과 같다).
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("lve", optional=True),
    ),
)
def render_openradioss_elastic(deck: Deck) -> Rendered:
    """`/MAT/LAW1` — RHO_I 한 줄, E·ν 한 줄. 그 밖의 칸은 없다."""
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None

    notes: list[str] = []
    lines = _starter(deck)
    if len(deck.rows("elastic")) > 1:
        # LAW1 은 상수 하나다. 표를 누르는 것은 조용히 할 일이 아니라 적는다.
        notes.append(
            "온도별 탄성 표가 있는데 LAW1 은 상수 하나입니다 — 블록의 대푯값(가장 낮은 "
            "온도)을 썼습니다."
        )
        lines.append(
            "# LAW1 is temperature independent: the lowest-temperature value is used."
        )
    limit = deck.number("lve", "lve_strain_limit")
    if limit is not None:
        lines.append(
            f"# E is the DMA storage modulus in the linear range - valid up to strain "
            f"{limit:.4g}."
        )
    lines.append(f"/MAT/LAW1/{deck.solver_id}/1")
    lines.append(deck.name)
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(f"#{'E':>19}{'nu':>20}")
    lines.append(_fixed(youngs) + _fixed(poisson))
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="openradioss_rate",
    label="Radioss (속도 의존)",
    extension="rad",
    suffix="_rate",
    describe=(
        "/MAT/LAW36 + 속도마다 /FUNCT — 속도별 소성 표를 그대로 싣는다. 속도 사이는 "
        "로그 보간(Fsmooth=2), 곡선은 소성변형률 속도로 고른다(VP=1)."
    ),
    keywords=("/MAT/LAW36", "/FUNCT/", "/UNIT/1", "/END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        # 속도가 하나뿐이면 이 덱을 낼 이유가 없다 — 그건 `openradioss` 가 한다.
        Need(
            "rate_table",
            values=("rate_count",),
            at_least=(("rate_count", 2),),
            rows_min=2 * MIN_POINTS,
        ),
    ),
)
def render_openradioss_rate(deck: Deck) -> Rendered:
    """LAW36 에 곡선 여럿 — **표가 잰 것이고 식은 요약이다**(Abaqus 속도 의존과 같다).

    `Fsmooth=2` 는 속도 사이를 로그로 보간한다. 속도가 자릿수로 벌어지는데 선형으로
    두면 0.001 과 100 /s 사이(1 /s 등)가 거의 0.001 /s 곡선이 된다 — 거리의 99% 가
    마지막 자릿수에 있다(2026-10-08 바로잡음: 전에는 「거의 100 /s」 로 거꾸로 적었다).
    `VP=1` 은 소성변형률 속도로 곡선을 고른다 — 시험의 속도는 전체 변형률 속도지만
    소성 구간에서는 거의 같고, 탄성파의 떨림이 항복응력으로 번지지 않는다.
    """
    curves, notes = rate_curves(deck)
    if len(curves) > MAX_RATE_CURVES:
        raise ExportError(
            f"속도가 {len(curves)}개입니다 — LAW36 은 곡선을 {MAX_RATE_CURVES}개까지 받습니다."
        )
    lines = _starter(deck)
    flat, said = law36_flat_elastic(deck)
    lines.extend(flat)
    notes.extend(said)
    fail, said = failure_lines(deck, "#", "Eps_p_max")
    lines.extend(fail)
    notes.extend(said)
    lines.append(
        f"# Strain rate dependent: {len(curves)} rates "
        f"({curves[0][0]:.4g} ~ {curves[-1][0]:.4g} per time unit), "
        f"log interpolation, plastic strain rate."
    )
    lines.append("# Outside the tested rates Radioss holds the nearest curve.")
    model = deck.values("rate_table").get("model")
    if model == "cowper_symonds":
        d, p = deck.number("rate_table", "cs_d"), deck.number("rate_table", "cs_p")
        if d is not None and p is not None:
            lines.append(f"# Cowper-Symonds summary (not used): D={d:.6g}, p={p:.6g}")
    lines.extend(
        law36_lines(
            deck,
            [
                (rate, _rate_function_id(deck, index), points)
                for index, (rate, points) in enumerate(curves, start=1)
            ],
            fsmooth=2,
            vp=1,
        )
    )
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def _law42_lines(
    deck: Deck,
    poisson: float,
    terms: list[tuple[float, float]],
    prony: list[tuple[float, float]] | None = None,
) -> list[str]:
    """`/MAT/LAW42` — `terms` 는 `(μ, α)` 로 **Radioss 규약**(G = Σμα/2)이다.

    μ·α 줄은 다섯씩 **두 장씩** 늘 적는다 — 파서가 네 줄을 무조건 읽는다. 둘째 장을 빼면
    α 줄이 μ₆~μ₁₀ 으로 먹힌다(예제 덱을 만들 때 실제로 그랬다).

    `prony` 는 `(Gᵢ 절대값, τᵢ)` — 있으면 M 칸에 항 수를 적고 Gᵢ 들 다음에 τᵢ 들을 싣는다.
    """
    density = deck.number("elastic", "density")
    assert density is not None
    padded = terms + [(0.0, 0.0)] * (10 - len(terms))
    count = len(prony or [])
    lines = [f"/MAT/LAW42/{deck.solver_id}/1", deck.name]
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(
        f"#{'nu':>19}{'sigma_cut':>20}{'':>10}{'fct_IDbulk':>10}{'Fscale_bulk':>20}"
        f"{'M':>10}{'Iform':>10}"
    )
    # sigma_cut·체적 함수·배율·Iform 은 비운다 — 기본값(컷 없음·Iform 1)이다.
    lines.append(f"{_fixed(poisson)}{'':>20}{'':>10}{0:>10}{'':>20}{count:>10}")
    lines.append("#" + "".join(f"{f'mu_{index}':>20}" for index in range(1, 6))[1:])
    lines.append("".join(_fixed(mu) for mu, _ in padded[:5]))
    lines.append("".join(_fixed(mu) for mu, _ in padded[5:]))
    lines.append("#" + "".join(f"{f'alpha_{index}':>20}" for index in range(1, 6))[1:])
    lines.append("".join(_fixed(alpha) for _, alpha in padded[:5]))
    lines.append("".join(_fixed(alpha) for _, alpha in padded[5:]))
    if prony:
        lines.append("#" + "".join(f"{f'G_{index}':>20}" for index in range(1, 6))[1:])
        lines.extend(_chunks([_fixed(g) for g, _ in prony]))
        lines.append("#" + "".join(f"{f'tau_{index}':>20}" for index in range(1, 6))[1:])
        lines.extend(_chunks([_fixed(tau) for _, tau in prony]))
    return lines


def _rubber_poisson(deck: Deck) -> float:
    poisson = deck.number("elastic", "poisson_ratio")
    assert poisson is not None
    if not 0.0 < poisson < 0.5:
        raise ExportError(
            f"푸아송비가 {poisson:g} 입니다 — LAW42 는 0 과 0.5 사이만 받습니다(0.5 면 "
            f"체적 탄성률이 발산합니다). 고무는 보통 0.495~0.4995 입니다."
        )
    return poisson


@register_renderer(
    key="openradioss_hyperelastic",
    label="Radioss (초탄성)",
    extension="rad",
    suffix="_hyperelastic",
    describe=(
        "/MAT/LAW42(OGDEN) — Neo-Hookean·Mooney-Rivlin·Ogden 을 Ogden 꼴로 옮긴다. "
        "Yeoh 는 이 꼴로 못 적어 안 낸다. 비압축 정도는 카드의 푸아송비로 준다."
    ),
    keywords=("/MAT/LAW42", "/UNIT/1", "/END"),
    needs=(
        Need("hyperelastic", rows_min=1),
        # **푸아송비를 지어내지 않는다.** 명시적 솔버는 체적 강성이 있어야 돌고, 그 값을
        # 0.495 로 채우면 잰 값인지 우리가 넣은 값인지 덱에서 모른다.
        Need("elastic", values=("poisson_ratio", "density")),
    ),
)
def render_openradioss_hyperelastic(deck: Deck) -> Rendered:
    """Ogden 꼴 `W = Σ μₚ/αₚ (λ̄₁^αₚ + λ̄₂^αₚ + λ̄₃^αₚ - 3)` — 초기 전단탄성률 Σμα/2.

    옮기는 식(초기 전단탄성률이 그대로인지로 검산한다):

        Neo-Hookean    μ₁ = 2·C10, α₁ = 2
        Mooney-Rivlin  μ₁ = 2·C10, α₁ = 2 ;  μ₂ = -2·C01, α₂ = -2
        Ogden(1항)     μ₁ = 2μ/α,  α₁ = α   — 우리 μ 는 Abaqus 규약(G = μ)이다
    """
    family, values = hyperelastic_terms(deck)
    poisson = _rubber_poisson(deck)
    if family == "neo_hookean":
        terms = [(2.0 * values["c10"], 2.0)]
        said = "mu_1 = 2*C10, alpha_1 = 2 (Neo-Hookean)"
    elif family == "mooney_rivlin":
        terms = [(2.0 * values["c10"], 2.0), (-2.0 * values["c01"], -2.0)]
        said = "mu_1 = 2*C10, alpha_1 = 2 ; mu_2 = -2*C01, alpha_2 = -2 (Mooney-Rivlin)"
    elif family == "ogden_1":
        mu, alpha = values["mu"], values["alpha"]
        terms = [(2.0 * mu / alpha, alpha)]
        said = "mu_1 = 2*mu/alpha (card mu is the Abaqus convention, G = mu), alpha_1 = alpha"
    else:
        raise ExportError(
            f"'{family}' 는 LAW42(Ogden 꼴)로 정확히 못 옮깁니다 — Yeoh 는 I₁ 의 고차항이라 "
            f"Ogden 항으로 바꾸면 다른 재료가 됩니다. Neo-Hookean·Mooney-Rivlin·Ogden 으로 "
            f"맞춘 카드를 쓰세요."
        )
    shear = sum(mu * alpha for mu, alpha in terms) / 2.0
    lines = _starter(deck)
    lines.append("# Nominal (engineering) stress fit - uniaxial data only.")
    lines.append(f"# {said}")
    lines.append(f"# Initial shear modulus sum(mu*alpha)/2 = {shear:.6g}")
    lines.append(f"# nu = {poisson:g} from the card sets the bulk modulus.")
    lines.extend(_law42_lines(deck, poisson, terms))
    lines.append("/END")
    notes = (
        f"{family} 계수를 LAW42 의 Ogden 꼴로 옮겼습니다({said}). 초기 전단탄성률 "
        f"{shear:.6g} 가 카드와 같은지 덱 주석으로 대조할 수 있습니다.",
    )
    return Rendered(text="\n".join(lines) + "\n", notes=notes)


@register_renderer(
    key="openradioss_viscoelastic",
    label="Radioss (점탄성)",
    extension="rad",
    suffix="_viscoelastic",
    describe=(
        "/MAT/LAW42 + Prony — Neo-Hookean(장기 전단탄성률) 위에 Prony 항을 얹는다. "
        "작은 변형에서 선형 점탄성과 같다. 체적은 탄성(순간 값 그대로)."
    ),
    keywords=("/MAT/LAW42", "/UNIT/1", "/END"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("viscoelastic", rows_min=1),
    ),
)
def render_openradioss_viscoelastic(deck: Deck) -> Rendered:
    """LAW42 의 μ 는 **장기(평형) 전단탄성률**이고 Gᵢ 가 그 위에 더해진다(순간 = μ + ΣGᵢ).

    카드는 순간 탄성률 E₀ 와 상대 탄성률 gᵢ 를 든다. 옮기는 식:

        G₀ = E₀/(2(1+ν))      G∞ = (1 - Σgᵢ)·G₀ → μ₁ (α₁ = 2, Neo-Hookean)
        Gᵢ = gᵢ·G₀            τᵢ 그대로(LAW42 는 완화시간을 받는다 — 1/τ 가 아니다)

    ## ν 칸은 계산한 값이다

    LAW42 는 체적 탄성률을 **μ(장기)와 ν 로** 만든다. 카드의 ν 를 그대로 적으면 체적이
    장기 전단에 묶여 함께 무르게 된다. 다른 솔버 덱(Abaqus·LS-DYNA)은 체적을 순간 값
    K₀ = E₀/(3(1-2ν)) 로 둔다 — 같은 재료가 되도록 K₀ 가 나오는 ν′ 를 적고, 그 식을
    덱에 적는다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    reference = deck.number("viscoelastic", "reference_temperature_k")
    assert youngs is not None and poisson is not None
    if not 0.0 < poisson < 0.5:
        raise ExportError(f"푸아송비가 {poisson:g} 입니다 — 0 과 0.5 사이여야 합니다.")
    terms = prony_terms(deck, limit=MAX_PRONY_TERMS)
    total = sum(g for g, _ in terms)
    shear0 = youngs / (2.0 * (1.0 + poisson))
    bulk0 = youngs / (3.0 * (1.0 - 2.0 * poisson))
    long_term = (1.0 - total) * shear0
    matched = (3.0 * bulk0 - 2.0 * long_term) / (2.0 * (3.0 * bulk0 + long_term))

    notes = [
        f"Prony {len(terms)}항, 상대 탄성률 합 {total:.4f} — LAW42 의 μ 에 장기 전단탄성률 "
        f"{long_term:.6g} 를, Gᵢ 에 gᵢ·G₀ 를 적었습니다.",
        f"체적 탄성률을 순간 값 K₀ 로 두려고 ν 칸에 {matched:.6f} 를 적었습니다(카드의 "
        f"ν 는 {poisson:g}).",
        "인장 E 를 전단 G 로 돌렸습니다 — 푸아송비가 시간에 안 변한다는 가정입니다.",
    ]
    lines = _starter(deck)
    lines.append(f"# G0 = E0/(2(1+nu)) = {shear0:.6E}   (E0={youngs:.6E}, nu={poisson:g})")
    lines.append(f"# Ginf = (1 - sum g_i) G0 = {long_term:.6E}  -> mu_1 (alpha_1 = 2)")
    lines.append("# G_i = g_i G0 (absolute), tau_i = relaxation time")
    lines.append(f"# K0 = E0/(3(1-2nu)) = {bulk0:.6E} - bulk stays elastic (not measured)")
    lines.append(f"# nu' = (3K0 - 2Ginf)/(2(3K0 + Ginf)) = {matched:.6f} so LAW42 builds K0")
    lines.append("# Neo-Hookean: equals linear viscoelasticity at small strain only.")
    if reference is not None:
        lines.append(
            f"# Valid at {reference:.2f} K only - master curve reference temperature."
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
    lines.extend(
        _law42_lines(
            deck,
            matched,
            [(long_term, 2.0)],
            prony=[(g * shear0, tau) for g, tau in terms],
        )
    )
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
