"""고무 초탄성 카드의 블록.

**ADR 0012 를 재는 자리다.** 점탄성은 블록 구조를 만들면서 함께 넣은 것이라 공정한
측정이 아니었다. 이 물성은 구조가 굳은 뒤에 붙는 첫 번째다 — 정말 `BlockSpec`
하나로 끝나는지가 여기서 드러난다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

HYPERELASTIC = register_block(
    BlockSpec(
        key="hyperelastic",
        label="초탄성",
        help=(
            "고무의 변형에너지 계수. **공칭 응력·공칭 변형률에 맞춘 값이다** — "
            "금속 경화식과 축이 다르다."
        ),
        produces=(
            Produced(
                key="label",
                label="식",
                si_unit="1",
                help="Neo-Hookean·Mooney-Rivlin·Yeoh·Ogden·다항식(N=2) 중 고른 것.",
            ),
            Produced(
                key="mode",
                label="시험 모드",
                si_unit="1",
                help="맞춘 데이터의 변형 모드. **다른 모드에서는 빗나갈 수 있다.**",
            ),
            Produced(
                key="shear_modulus",
                label="초기 전단탄성률",
                si_unit="Pa",
                help=(
                    "변형이 0 에 가까울 때의 기울기에서 나온다. "
                    "식이 달라도 이 값은 비슷해야 한다."
                ),
            ),
            Produced(
                key="relative_rmse",
                label="상대 RMSE",
                si_unit="1",
                help="적합 구간에서 데이터와 얼마나 벌어지는가.",
            ),
            Produced(key="r_squared", label="R²", si_unit="1"),
            Produced(
                key="max_residual",
                label="최대 잔차",
                si_unit="Pa",
                help="가장 크게 벌어진 한 점. 평균이 좋아도 여기가 크면 국소적으로 안 맞는다.",
            ),
            Produced(
                key="strain_min",
                label="적합 구간 시작",
                si_unit="1",
                help="공칭 변형률. **그 밖은 검증되지 않았다.**",
            ),
            Produced(key="strain_max", label="적합 구간 끝", si_unit="1", help="공칭 변형률."),
        ),
        rows=(
            Produced(key="name", label="파라미터", si_unit="1"),
            Produced(key="value", label="값", si_unit="1", help="행이 자기 단위를 든다."),
        ),
        order=25,
        kind_priority=2,
    )
)


# ── 문헌 · 파라미터 벌에서 (2026-10-08) ─────────────────────────────────────────────


@dataclass(frozen=True)
class FromSet:
    """파라미터 벌을 옮긴 결과 — 블록에 그대로 담는다. 계수는 **SI(Pa)** 다."""

    family: str
    values: dict[str, float]
    note: str | None = None


#: 벌의 모델 이름 → (우리 식, 받는 항 표기들). 표기마다 `{그쪽 항(소문자): 우리 계수}` 다.
#:
#: 이름은 출처마다 다르다(개발 DB 문헌 벌, 2026-10-08): Mooney-Rivlin · Yeoh 는 `C10 · C01` 과
#: 원래 표기 `C1 · C2` 가 섞여 온다. 원래 표기는 식마다 뜻이 정해져 있어 옮긴다 — Mooney 의
#: W = C1(I1-3) + C2(I2-3), Yeoh 의 W = Σ Ci(I1-3)^i. **Neo-Hookean 의 `C1` 은 받지 않는다** —
#: 출처에 따라 μ 이기도 하고 μ/2(= C10)이기도 해서, 옮기면 둘 중 하나는 강성이 두 배로 틀린다.
#: Neo-Hookean 은 `mu`(초기 전단탄성률, C10 = μ/2)나 `C10` 만 받는다.
#:
#: **3 · 5항 Mooney-Rivlin 은 2차 다항식이다**(2026-10-12) — W = Σ Cij(I1-3)^i(I2-3)^j 의
#: Cij 는 솔버마다 뜻이 같아서 옮길 때 판단이 없다. 3항은 출처마다 셋째 항이 `C11` 이기도
#: `C20` 이기도 해서 표기를 둘 받는다. 빠진 항은 0 이다(같은 식).
#:
#: **항은 표기와 똑같아야 받는다.** 일부만 맞는 벌을 받으면 남는 항이 말없이 버려진다.
FROM_SET: dict[str, tuple[str, tuple[dict[str, str], ...]]] = {
    "neo_hookean": ("neo_hookean", ({"c10": "c10"},)),
    "mooney_rivlin_2": (
        "mooney_rivlin",
        ({"c10": "c10", "c01": "c01"}, {"c1": "c10", "c2": "c01"}),
    ),
    "yeoh_3": (
        "yeoh",
        ({"c10": "c10", "c20": "c20", "c30": "c30"}, {"c1": "c10", "c2": "c20", "c3": "c30"}),
    ),
    "yeoh_2": ("yeoh", ({"c10": "c10", "c20": "c20"}, {"c1": "c10", "c2": "c20"})),
    "mooney_rivlin_3": (
        "polynomial_2",
        (
            {"c10": "c10", "c01": "c01", "c11": "c11"},
            {"c10": "c10", "c01": "c01", "c20": "c20"},
        ),
    ),
    "mooney_rivlin_5": (
        "polynomial_2",
        ({"c10": "c10", "c01": "c01", "c20": "c20", "c11": "c11", "c02": "c02"},),
    ),
}


def from_parameter_set(model: str, terms: Mapping[str, tuple[float, str]]) -> FromSet | str:
    """`terms` 는 항 → (값, 단위). 옮길 수 있으면 `FromSet`, 아니면 **까닭 글자**.

    계수는 응력 단위여야 한다 — 아니면 멈춘다(단위 칸이 「1」 로 와서 MPa 를 Pa 로 읽으면
    고무가 백만 배 무르게 돈다). 덱이 받는 식만(`HYPERELASTIC_PARAMETERS`) — Ogden 은 출처마다
    μ 의 규약(μ · μ/α)이 달라 옮기지 않는다. Arruda-Boyce · Gent 도 옮기지 않는다.

    **초기 전단탄성률 2(C10 + C01) 이 0 이하인 벌은 거절한다** — 작은 변형에서 불안정한
    재료라 솔버가 첫 증분에서 멈추거나 거꾸로 선다(문헌 3항 Mooney-Rivlin 가운데 실리콘 둘이
    그렇다: C10 = 21.8 kPa, C01 = -72.2 kPa).
    """
    from matcore import units  # 순환 import 를 피한다 — cards 는 export 보다 먼저 읽힌다

    def stress(name: str) -> float | str:
        value, unit = terms[name]
        canonical = units.canonical(unit or "")
        if canonical is None or not units.same_dimension(
            units.unit_of(canonical).dimension, "stress"
        ):
            return (
                f"{model} 의 {name} 단위가 '{unit or '(없음)'}' 입니다 — 응력 단위여야 합니다."
            )
        return units.to_si(value, canonical)

    if model == "neo_hookean" and "mu" in terms and "C10" not in terms:
        mu = stress("mu")
        if isinstance(mu, str):
            return mu
        return _stable(
            model, FromSet("neo_hookean", {"c10": mu / 2.0}, "μ 를 C10 = μ/2 로 옮겼습니다.")
        )
    found = FROM_SET.get(model)
    if found is None:
        return f"덱이 받는 식이 아닙니다: {model}"
    family, spellings = found
    lowered = {name.lower(): name for name in terms}
    spelling = next((one for one in spellings if set(one) == set(lowered)), None)
    if spelling is None:
        if model == "neo_hookean" and "c1" in lowered:
            return (
                "Neo-Hookean 의 C1 은 출처마다 μ 이기도 하고 μ/2 이기도 해서 옮기지 "
                "않았습니다 — mu 나 C10 으로 적힌 벌만 받습니다."
            )
        return f"{model} 의 항 이름을 모릅니다: {', '.join(sorted(terms))}"
    values: dict[str, float] = {}
    for theirs, mine in spelling.items():
        converted = stress(lowered[theirs])
        if isinstance(converted, str):
            return converted
        values[mine] = converted
    absent = [name for name in HYPERELASTIC_ORDER[family] if name not in values]
    note = None
    if absent:
        values.update(dict.fromkeys(absent, 0.0))
        shown = " · ".join(name.upper() for name in absent)
        note = (
            "2항 Yeoh 라 C30 = 0 으로 적었습니다 — 같은 식입니다."
            if model == "yeoh_2"
            else f"벌에 없는 항 {shown} 은 0 으로 적었습니다 — 같은 식입니다."
        )
    return _stable(model, FromSet(family, values, note))


def _stable(model: str, made: FromSet) -> FromSet | str:
    """초기 전단탄성률(다항식 꼴 2(C10 + C01))이 0 보다 커야 받는다."""
    shear = 2.0 * (made.values.get("c10", 0.0) + made.values.get("c01", 0.0))
    if shear <= 0.0:
        return (
            f"{model} 의 초기 전단탄성률 2(C10 + C01) = {shear:.4g} Pa 가 0 이하입니다 — "
            "작은 변형에서 불안정한 벌이라 덱으로 옮기지 않았습니다."
        )
    return made


#: 우리 식의 계수 차례 — `matcore.export.HYPERELASTIC_PARAMETERS` 와 같아야 한다
#: (시험이 대 본다).
HYPERELASTIC_ORDER: dict[str, tuple[str, ...]] = {
    "neo_hookean": ("c10",),
    "mooney_rivlin": ("c10", "c01"),
    "yeoh": ("c10", "c20", "c30"),
    "ogden_1": ("mu", "alpha"),
    # 2차 다항식 — Abaqus `POLYNOMIAL, N=2` 의 차례(C10, C01, C20, C11, C02).
    "polynomial_2": ("c10", "c01", "c20", "c11", "c02"),
}


# ── 큰 변형의 안정성 (2026-10-23) ───────────────────────────────────────────────────
#
# `_stable` 은 작은 변형만 본다. 고차 계수가 음이면 변형이 커질 때 응력이 줄어드는 구간이
# 생기고(Drucker 조건 위반), 솔버는 거기서 멈추거나 국소화한다. 실측(개발 DB): Ecoflex 00-20
# 의 압축 곡선(0.5~25 %)에서 맞춘 Yeoh(C30 = -41 kPa)는 그 구간에서는 맞지만 **단축 인장
# 33 % · 등이축 17 % 에서 불안정**하다. 같은 재료의 인장 곡선(7~354 %)에서 맞춘 Yeoh 는 인장
# 300 % 까지 안정하다.
#
# 음의 계수만 보고 거르면 틀린다 — Dragon Skin 10 의 C20 = -171 kPa 벌은 끝까지 안정하다.
# 그래서 변형 경로마다 공칭 응력이 늘어나는지(비압축, dP/dλ > 0)를 직접 걷는다.

#: 경로마다 (이름, 늘림비 끝, 덱 기본값이 버텨야 하는 늘림비). 기본값 범위는 고무 부품 해석에서
#: 흔한 변형이다 — 그보다 큰 변형은 그 범위로 맞춘 벌을 사람이 고른다.
STABILITY_PATHS: tuple[tuple[str, float, float], ...] = (
    ("인장", 4.0, 2.0),
    ("압축", 0.3, 0.5),
    ("등이축", 3.0, 1.5),
    ("평면 전단", 3.0, 1.5),
)
_STEP = 0.005


def _terms(values: Mapping[str, float]) -> list[tuple[int, int, float]] | None:
    """`cij` → (i, j, 계수). 다항식 꼴이 아니면(Ogden) None."""
    out = []
    for name, value in values.items():
        if len(name) != 3 or name[0] != "c" or not name[1:].isdigit():
            return None
        out.append((int(name[1]), int(name[2]), float(value)))
    return out


def _nominal(terms: list[tuple[int, int, float]], path: str, stretch: float) -> float:
    """비압축 경로 하나의 공칭 응력 — W = Σ Cij (I1-3)^i (I2-3)^j."""
    lam = stretch
    if path in ("인장", "압축"):
        i1, i2 = lam * lam + 2.0 / lam, 2.0 * lam + 1.0 / (lam * lam)
    elif path == "등이축":
        i1, i2 = 2.0 * lam * lam + lam**-4, lam**4 + 2.0 / (lam * lam)
    else:
        i1 = i2 = lam * lam + 1.0 + 1.0 / (lam * lam)
    a, b = i1 - 3.0, i2 - 3.0
    w1 = sum(i * c * a ** (i - 1) * b**j for i, j, c in terms if i)
    w2 = sum(j * c * a**i * b ** (j - 1) for i, j, c in terms if j)
    if path in ("인장", "압축"):
        return 2.0 * (lam - lam**-2) * (w1 + w2 / lam)
    if path == "등이축":
        return 2.0 * (lam - lam**-5) * (w1 + lam * lam * w2)
    return 2.0 * (lam - lam**-3) * (w1 + w2)


@dataclass(frozen=True)
class Stability:
    """경로마다 **처음 불안정해지는 공칭 변형률**(%, 압축은 줄어든 비율).

    끝까지 안정한 경로는 없다."""

    breaks: dict[str, float]
    weak: tuple[str, ...]
    """덱 기본값 범위(`STABILITY_PATHS` 셋째 칸) 안에서 깨지는 경로."""

    @property
    def ok(self) -> bool:
        return not self.weak

    def describe(self) -> str:
        """「인장 33 % · 등이축 17 % 에서 불안정」 — 다 안정하면 빈 글자."""
        if not self.breaks:
            return ""
        shown = " · ".join(f"{path} {strain:.0f} %" for path, strain in self.breaks.items())
        return f"{shown} 에서 불안정"


def stability(values: Mapping[str, float]) -> Stability | None:
    """다항식 꼴(Neo-Hookean · Mooney-Rivlin · Yeoh · 2차)의 경로별 안정 범위.

    Ogden 처럼 다항식 꼴이 아니면 None."""
    terms = _terms(values)
    if terms is None:
        return None
    breaks: dict[str, float] = {}
    weak: list[str] = []
    for path, end, needed in STABILITY_PATHS:
        down = end < 1.0
        step = -_STEP if down else _STEP
        lam, before = 1.0, 0.0
        while (lam > end) if down else (lam < end):
            lam += step
            now = _nominal(terms, path, lam)
            # 늘리면 커지고 누르면 작아져야 한다 — 거꾸로 가는 첫 자리가 깨지는 곳이다.
            if (now >= before) if down else (now <= before):
                at = lam - step
                breaks[path] = abs(at - 1.0) * 100.0
                if (at > needed) if down else (at < needed):
                    weak.append(path)
                break
            before = now
    return Stability(breaks, tuple(weak))
