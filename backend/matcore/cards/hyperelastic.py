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
                help="Neo-Hookean·Mooney-Rivlin·Yeoh·Ogden 중 고른 것.",
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


#: 벌의 모델 이름 → (우리 식, 받는 항 이름 묶음들). 묶음마다 **우리 계수 차례**로 대응한다.
#:
#: 이름은 출처마다 다르다(개발 DB 문헌 벌, 2026-10-08): Mooney-Rivlin · Yeoh 는 `C10 · C01` 과
#: 원래 표기 `C1 · C2` 가 섞여 온다. 원래 표기는 식마다 뜻이 정해져 있어 옮긴다 — Mooney 의
#: W = C1(I1-3) + C2(I2-3), Yeoh 의 W = Σ Ci(I1-3)^i. **Neo-Hookean 의 `C1` 은 받지 않는다** —
#: 출처에 따라 μ 이기도 하고 μ/2(= C10)이기도 해서, 옮기면 둘 중 하나는 강성이 두 배로 틀린다.
#: Neo-Hookean 은 `mu`(초기 전단탄성률, C10 = μ/2)나 `C10` 만 받는다.
FROM_SET: dict[str, tuple[str, tuple[tuple[str, ...], ...]]] = {
    "neo_hookean": ("neo_hookean", (("C10",), ("c10",))),
    "mooney_rivlin_2": ("mooney_rivlin", (("C10", "C01"), ("c10", "c01"), ("C1", "C2"))),
    "yeoh_3": ("yeoh", (("C10", "C20", "C30"), ("c10", "c20", "c30"), ("C1", "C2", "C3"))),
    "yeoh_2": ("yeoh", (("C10", "C20"), ("c10", "c20"), ("C1", "C2"))),
}


def from_parameter_set(model: str, terms: Mapping[str, tuple[float, str]]) -> FromSet | str:
    """`terms` 는 항 → (값, 단위). 옮길 수 있으면 `FromSet`, 아니면 **까닭 글자**.

    계수는 응력 단위여야 한다 — 아니면 멈춘다(단위 칸이 「1」 로 와서 MPa 를 Pa 로 읽으면
    고무가 백만 배 무르게 돈다). 덱이 받는 식은 넷뿐이라(`HYPERELASTIC_PARAMETERS`) Ogden N≥2 ·
    Arruda-Boyce · Gent 같은 벌은 옮기지 않는다.
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
        return FromSet("neo_hookean", {"c10": mu / 2.0}, "μ 를 C10 = μ/2 로 옮겼습니다.")
    found = FROM_SET.get(model)
    if found is None:
        return f"덱이 받는 식이 아닙니다: {model}"
    family, spellings = found
    names = next((one for one in spellings if set(one) <= set(terms)), None)
    if names is None:
        if model == "neo_hookean" and "C1" in terms:
            return (
                "Neo-Hookean 의 C1 은 출처마다 μ 이기도 하고 μ/2 이기도 해서 옮기지 "
                "않았습니다 — mu 나 C10 으로 적힌 벌만 받습니다."
            )
        return f"{model} 의 항 이름을 모릅니다: {', '.join(sorted(terms))}"
    ours = HYPERELASTIC_ORDER[family]
    values: dict[str, float] = {}
    for theirs, mine in zip(names, ours, strict=False):
        converted = stress(theirs)
        if isinstance(converted, str):
            return converted
        values[mine] = converted
    note = None
    if model == "yeoh_2":
        values["c30"] = 0.0
        note = "2항 Yeoh 라 C30 = 0 으로 적었습니다 — 같은 식입니다."
    return FromSet(family, values, note)


#: 우리 식의 계수 차례 — `matcore.export.HYPERELASTIC_PARAMETERS` 와 같아야 한다
#: (시험이 대 본다).
HYPERELASTIC_ORDER: dict[str, tuple[str, ...]] = {
    "neo_hookean": ("c10",),
    "mooney_rivlin": ("c10", "c01"),
    "yeoh": ("c10", "c20", "c30"),
    "ogden_1": ("mu", "alpha"),
}
