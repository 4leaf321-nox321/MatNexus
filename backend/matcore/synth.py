"""스칼라 → σ-ε 곡선 합성 — **실측이 없는 재료의 근사 곡선** (MaterialTwin 이식 5단계).

문헌 카탈로그에는 스칼라(E·항복·인장·연신율)만 있고 곡선이 없다. 그 재료로
소성 해석 덱(*MAT_024)을 내려면 곡선을 **지어야** 하고, 지은 곡선은 어디서든
**「합성」 으로 표시**되어야 한다 — 실측처럼 보이는 순간 이 기능은 해가 된다.

모델은 MaterialTwin 원본(curve_synth.py)의 판단을 그대로 잇는다:

    완전 정보          탄성 직선 + Hollomon 멱경화(σ = K·εp^n) — n 은 항복과
                      (파단 소성변형률, UTS) 를 잇는 로그비
    항복만             탄성-완전소성
    항복 미공표 + UTS   연신율 2% 로 연성/취성을 가른다 — 동박·솔더처럼 항복을
                      공표하지 않는 연성 금속을 취성으로 취급하면 곡선이 통째로
                      틀린다(원본 실측). 연성이면 UTS 평탄부(보수적 — 소성
                      개시를 과대평가한다고 note 로 말한다), 취성이면 선형 파단

덱용 소성 표까지 한 층 더 간다(원본은 공칭 곡선까지였다): 진응력·진소성변형률
변환은 처리 단계(tensile.true_plastic)와 같은 식이다 —

    true_strain = ln(1 + e) · true_stress = s(1 + e) · plastic = true - true_stress/E

첫 점은 (0, 진항복) 으로 앵커한다 — *MAT_024 는 첫 점을 항복으로 읽는다.
DB 도 HTTP 도 모른다(matcore 규칙). 값은 전부 SI(Pa·무차원 변형률)다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: 파단연신율이 이보다 크면 소성 구간이 있다고 본다(항복 미공표일 때).
DUCTILE_ELONGATION = 0.02

#: Hollomon 지수의 허용 구간 — 밖이면 입력 스칼라가 서로 안 맞는 것이다.
HARDENING_RANGE = (0.01, 0.6)


@dataclass(frozen=True)
class SyntheticCurve:
    """합성 곡선 하나 — 공칭 곡선과 (있으면) 덱용 소성 표.

    `note` 는 장식이 아니다: 어떤 근사인지, 무엇을 과대·과소평가하는지가
    적혀 있고, 덱 각주와 화면이 그대로 보여 준다.
    """

    strain: tuple[float, ...]
    """공칭 변형률 — 그래프용."""
    stress_pa: tuple[float, ...]
    model: str
    note: str
    inconsistent: bool = False
    """입력 스칼라끼리 물리적으로 안 맞아 손을 봤다(예: 항복 > 인장강도)."""
    table_rows: tuple[dict[str, float], ...] = field(default=())
    """*MAT_024 소성 표 `{plastic_strain, true_stress}` — 소성 구간이 있을 때만.
    첫 점은 (0, 진항복)이고 진응력·소성변형률 모두 단조 증가다."""


def _plastic_table(
    strain: np.ndarray, stress: np.ndarray, youngs_modulus: float, yield_nominal: float
) -> tuple[dict[str, float], ...]:
    """공칭 곡선의 소성부 → 진응력-진소성변형률 표.

    완전소성 평탄부도 진응력에서는 s(1+e) 로 오르므로 단조가 저절로 선다.
    항복점 부근의 미세 음수 소성변형률(ln 급수 절단)은 0 으로 앵커한다.
    """
    ey = yield_nominal / youngs_modulus
    yield_true = yield_nominal * (1.0 + ey)
    in_plastic = strain >= ey
    e = strain[in_plastic]
    s = stress[in_plastic]
    true_stress = s * (1.0 + e)
    plastic = np.log1p(e) - true_stress / youngs_modulus
    rows: list[dict[str, float]] = [{"plastic_strain": 0.0, "true_stress": float(yield_true)}]
    for ep, st in zip(plastic, true_stress, strict=True):
        # 표는 단조 증가여야 한다 — 솔버는 뒤섞인 표를 조용히 보간한다.
        if ep <= rows[-1]["plastic_strain"] or st <= rows[-1]["true_stress"]:
            continue
        rows.append({"plastic_strain": float(ep), "true_stress": float(st)})
    # 첫 점뿐이면 표가 아니다 — 소성 정보가 사실상 없는 것.
    return tuple(rows) if len(rows) >= 2 else ()


def synthesize(
    youngs_modulus: float | None,
    yield_strength: float | None = None,
    tensile_strength: float | None = None,
    elongation: float | None = None,
    *,
    points: int = 60,
) -> SyntheticCurve | None:
    """스칼라 → 합성 곡선. 입력이 모자라면 None — 지어낼 근거가 없다."""
    E = youngs_modulus
    sigy = yield_strength
    uts = tensile_strength
    if not E or E <= 0:
        return None

    if sigy is None:
        if uts is None or uts <= 0:
            return None
        ef = elongation if elongation and elongation > 0 else uts / E
        if ef > DUCTILE_ELONGATION:
            # 연성인데 항복 미공표 — 항복을 UTS 로 둔 보수적 완전소성.
            ey = uts / E
            e = np.concatenate(
                [np.linspace(0.0, ey, 12), np.linspace(ey, ef, max(8, points - 12))]
            )
            s = np.concatenate(
                [E * np.linspace(0.0, ey, 12), np.full(max(8, points - 12), uts)]
            )
            return SyntheticCurve(
                strain=tuple(map(float, e)),
                stress_pa=tuple(map(float, s)),
                model="elastic-perfectly plastic (yield unknown, capped at UTS)",
                note=(
                    "항복강도 미공표 — UTS 를 소성 평탄부로 둔 보수적 근사. "
                    "실제 항복은 이보다 낮으므로 소성 개시를 과대평가한다."
                ),
                table_rows=_plastic_table(e, s, E, uts),
            )
        e = np.linspace(0.0, ef, max(8, points // 3))
        s = np.minimum(E * e, uts)
        return SyntheticCurve(
            strain=tuple(map(float, e)),
            stress_pa=tuple(map(float, s)),
            model="linear-elastic (brittle)",
            note="취성 재료 — 항복 없이 탄성 파단. 파단점까지 선형이고 소성 표는 없다.",
        )

    inconsistent = uts is not None and uts <= sigy
    ey = sigy / E
    if uts is None or uts <= sigy or not elongation or elongation <= ey:
        # 경화 정보가 없다 — 완전소성.
        ef = max(elongation or ey * 10, ey * 2)
        e = np.concatenate([np.linspace(0, ey, 12), np.linspace(ey, ef, points - 12)])
        s = np.concatenate([E * np.linspace(0, ey, 12), np.full(points - 12, sigy)])
        note = "UTS·연신율 정보 부족 — 완전소성 근사."
        if inconsistent and uts is not None:
            note = (
                f"항복({sigy / 1e6:.0f} MPa)이 인장강도({uts / 1e6:.0f} MPa)보다 커서 "
                "두 값의 출처·조건이 다르다. 항복만 써서 완전소성으로 근사했다."
            )
        return SyntheticCurve(
            strain=tuple(map(float, e)),
            stress_pa=tuple(map(float, s)),
            model="elastic-perfectly plastic",
            note=note,
            inconsistent=bool(inconsistent),
            table_rows=_plastic_table(e, s, E, sigy),
        )

    # 완전 정보 — Hollomon 멱경화. (εp→0+, 항복)과 (파단 소성변형률, UTS)를 잇는다.
    ep_f = elongation - ey
    eps0 = 1e-4
    n_h = float(np.clip(np.log(uts / sigy) / np.log(ep_f / eps0), *HARDENING_RANGE))
    K = uts / (ep_f**n_h)
    e_el = np.linspace(0.0, ey, 12)
    ep = np.linspace(eps0, ep_f, points - 12)
    s_pl = np.maximum(K * ep**n_h, sigy)
    e = np.concatenate([e_el, ey + ep])
    s = np.concatenate([E * e_el, s_pl])
    return SyntheticCurve(
        strain=tuple(map(float, e)),
        stress_pa=tuple(map(float, s)),
        model=f"elastic + Hollomon hardening (n={n_h:.3f})",
        note="항복·UTS·연신율 스칼라에서 합성한 근사 곡선 — 실측이 아니다.",
        inconsistent=False,
        table_rows=_plastic_table(e, s, E, sigy),
    )
