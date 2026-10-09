"""ANSYS `TB,RATE,,,,ANAND` — Anand 점소성 9항.

    TB,RATE,<재료>,,,ANAND
    TBDATA,1,s0,Q/R,A,ξ,m,h0          (차례는 ANSYS 이론 안내서 표 4.3)
    TBDATA,7,ŝ,n,a

## 벌을 이름이 아니라 항으로 알아본다

블록의 행은 `set`(어느 벌) · `name`(항) · `value` · `unit` 이다. 벌의 이름표는 출처마다 다르게
적혀 와서(`anand/wang1998_60sn40pb`, 모델 칸이 빈 벌 …) 이름으로 고르지 않는다 — **9항이 다
있는 벌**이 Anand 다. 둘 이상이면 고르지 않고 거절한다: 카드에 하나만 실어야 덱이 무엇을
냈는지 분명하다.

## 단위는 항마다 다르다 — 환산은 여기서

이 값들은 SI 가 아니라 그 항의 원래 단위다(h0 = 2640.75 MPa). 블록이 「환산하지 않는다」 고
적은 그대로라 `to_system` 이 손대지 않는다. 그래서 덱의 단위계로 옮기는 것은 이 렌더러다 —
응력 셋(s0 · h0 · ŝ)은 응력 단위, A 는 1/시간, Q/R 은 K. **단위가 그 차원이 아니면 멈춘다** —
문헌 값의 단위 칸이 「1」 로 와서 MPa 를 Pa 로 읽으면 백만 배 틀린 솔더가 오류 없이 돈다.

## 정의판(쌍둥이)이 없다

항마다 단위를 읽어 환산하는 것은 계산이다 — 정의 언어로 적지 않는다(ADR 0023 「계산이
필요하면 코드로」, Zemax AGF 와 같은 자리).
"""

from __future__ import annotations

from typing import Any

from matcore import units
from matcore.export import Deck, ExportError, Need, Rendered, _free, register_renderer
from matcore.export import ansys as _ansys

#: TBDATA 1~9 의 차례 — s0, Q/R, A, ξ, m, h0, ŝ, n, a.
TERMS = ("s0", "Q/R", "A", "xi", "m", "h0", "s_hat", "n", "a")

#: 항 → 그 값의 SI 단위와 받는 차원들. 여기 없는 항은 무차원이다.
DIMENSIONED: dict[str, tuple[str, tuple[str, ...]]] = {
    "s0": ("Pa", ("stress",)),
    "h0": ("Pa", ("stress",)),
    "s_hat": ("Pa", ("stress",)),
    "A": ("1/s", ("strain_rate", "frequency")),
    "Q/R": ("K", ("temperature",)),
}

#: 출처마다 다른 표기 → 우리 이름. **대소문자는 접지 않는다** — A(전지수 인자)와
#: a(경화 감도)는 다른 항이다.
ALIASES = {"ξ": "xi", "ŝ": "s_hat", "s*": "s_hat", "S0": "s0", "H0": "h0", "Q_R": "Q/R"}


def _sets(deck: Deck) -> dict[str, dict[str, tuple[float, str]]]:
    found: dict[str, dict[str, tuple[float, str]]] = {}
    for row in deck.rows("model_params"):
        name = str(row.get("name") or "")
        value = row.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        name = ALIASES.get(name, name)
        found.setdefault(str(row.get("set") or ""), {})[name] = (
            float(value),
            str(row.get("unit") or "1").strip() or "1",
        )
    return found


def anand_terms(deck: Deck) -> tuple[str, dict[str, float]]:
    """`(벌 이름, 항 → 덱 단위계의 값)`. 9항이 다 있는 벌이 하나여야 한다."""
    sets = _sets(deck)
    complete = {key: terms for key, terms in sets.items() if set(TERMS) <= set(terms)}
    if not complete:
        near = max(sets.values(), key=lambda terms: len(set(TERMS) & set(terms)), default={})
        missing = [term for term in TERMS if term not in near]
        raise ExportError(
            "카드에 Anand 9항이 다 있는 벌이 없습니다"
            + (f" — 가장 가까운 벌에 빠진 항: {', '.join(missing)}." if near else ".")
            + " 재료의 파라미터 벌에서 Anand 한 벌을 카드에 실으세요."
        )
    if len(complete) > 1:
        raise ExportError(
            f"카드에 Anand 벌이 {len(complete)}개 있습니다({', '.join(sorted(complete))}) — "
            "한 덱에는 한 벌만 냅니다. 카드에 하나만 실으세요."
        )
    ((where, terms),) = complete.items()
    converted: dict[str, float] = {}
    for name in TERMS:
        value, unit = terms[name]
        canonical = units.canonical(unit)
        found = units.unit_of(canonical).dimension if canonical else None
        if name not in DIMENSIONED:
            if found is None or not units.same_dimension(found, "dimensionless"):
                raise ExportError(
                    f"Anand {name} 은 무차원이어야 하는데 단위가 '{unit}' 입니다."
                )
            converted[name] = value
            continue
        si_unit, dimensions = DIMENSIONED[name]
        if found is None or not any(units.same_dimension(found, one) for one in dimensions):
            raise ExportError(
                f"Anand {name} 의 단위가 '{unit}' 입니다 — {dimensions[0]} 단위여야 합니다. "
                "단위가 틀리면 값이 자릿수째 틀린 채 덱이 돕니다."
            )
        assert canonical is not None
        converted[name] = deck.units.convert(units.to_si(value, canonical), si_unit)
    return where, converted


@register_renderer(
    key="ansys_anand",
    label="ANSYS (Anand 점소성)",
    extension="mac",
    suffix="_anand",
    describe=(
        "MP(EX · PRXY) + TB,RATE(ANAND) — 솔더의 Anand 9항(s0 · Q/R · A · ξ · m · h0 · ŝ · "
        "n · a). 카드의 모델 파라미터 벌을 그대로 싣는다. 온도는 절대온도(K)여야 한다."
    ),
    keywords=(f"EX,{_ansys.MATERIAL}", "TB,RATE", "ANAND"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("model_params", rows_min=len(TERMS)),
    ),
)
def render_ansys_anand(deck: Deck) -> Rendered:
    where, terms = anand_terms(deck)
    lines, notes = _ansys._structural(deck)
    stress, rate = deck.units.symbol("Pa"), deck.units.symbol("1/s")
    lines.extend(
        [
            f"! Anand viscoplasticity (TB,RATE TBOPT=ANAND) - parameter set: {where or '-'}",
            "! C1..C9 = s0, Q/R, A, xi, m, h0, s_hat, n, a",
            f"! s0, h0, s_hat in {stress}; A in {rate}; Q/R in K - temperatures must be K.",
            f"TB,RATE,{_ansys.MATERIAL},,,ANAND",
            "TBDATA,1," + ",".join(_free(terms[name]) for name in TERMS[:6]),
            "TBDATA,7," + ",".join(_free(terms[name]) for name in TERMS[6:]),
        ]
    )
    said: list[Any] = [
        f"Anand 9항은 파라미터 벌 「{where or '이름 없음'}」 을 그대로 실었습니다 — 탄성(EX · "
        "PRXY)은 카드의 탄성 블록입니다. Q/R 이 K 라 모델의 온도도 절대온도여야 합니다."
    ]
    return Rendered(text="\n".join(lines) + "\n", notes=(*notes, *said))
