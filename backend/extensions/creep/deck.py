"""ANSYS `TB,CREEP` TBOPT 8 — 일반화 Garofalo(쌍곡사인) 정상상태 크리프.

    ε̇_cr = C1 · [sinh(C2·σ)]^C3 · exp(-C4 / T)        T 는 절대온도(K)

    TB,CREEP,<재료>,1,4,8
    TBDATA,1,C1,C2,C3,C4

번호(8 = Generalized Garofalo)는 Ansys 재료 안내서 표 4.2, 상수의 단위(C1 1/s · C2 1/MPa ·
C3 무차원 · C4 K)는 Ansys 무연 솔더 크리프 기술 예제(35.4)에서 확인했다. 식 모양은 도움말에
그림으로만 있어 IPC 논문(Sn-Ag-Cu 크리프, 「Garofalo 식이 TBOPT 8 의 입력 꼴과
같다」)으로 맞췄다.

## 받는 벌 — 같은 꼴만

문헌 Garofalo 벌은 꼴이 고르지 않다(개발 DB, 2026-10-08):

    받는다     C1 · C2 · C3 · C4 (ANSYS 꼴)  또는  A · alpha · n · Q (같은 식의 다른 이름)
    안 받는다  전단 기준(전단 변형률 속도 · τ) — 인장 등가로 옮기려면 √3 의 자리를
               정해야 한다
               Darveaux 꼴(C1 · G/T · σ/G) — 전단탄성률 G(T)가 있어야 같은 식이 된다
               상수가 빠진 벌(A 없이 alpha · n · Q 만)

한 출처의 상수가 모델 글자 차이로 두 벌로 갈려 들어온 경우가 있어(`C1` 만 다른 벌) **벌 이름
(`set_id`)이 같으면 합쳐 본다.** 활성화 에너지는 Q/R(K)로 옮긴다 — J/mol · kJ/mol 은 기체
상수로, eV 는 볼츠만 상수로 나눈다.

## 정의판(쌍둥이)이 없다

항마다 단위를 읽어 옮기는 것은 계산이다(Anand · Zemax AGF 와 같은 자리, ADR 0023).
"""

from __future__ import annotations

import re

from matcore import units
from matcore.export import Deck, ExportError, Need, Rendered, _free, register_renderer
from matcore.export import ansys as _ansys

#: 기체 상수(J/(mol·K))와 볼츠만 상수(eV/K) — 활성화 에너지를 Q/R(K)로 옮긴다.
GAS_CONSTANT = 8.314462618
BOLTZMANN_EV = 8.617333262e-5
#: 활성화 에너지 단위 → Q/R(K)로 나누는 수.
ENERGY = {"J/mol": GAS_CONSTANT, "kJ/mol": GAS_CONSTANT / 1000.0, "eV": BOLTZMANN_EV, "K": 1.0}

#: 받는 이름 → C1~C4. ANSYS 꼴과 같은 식의 흔한 이름.
SPELLINGS = (
    {"C1": "C1", "C2": "C2", "C3": "C3", "C4": "C4"},
    {"A": "C1", "alpha": "C2", "n": "C3", "Q": "C4"},
    # 섞인 이름(Darveaux 표) — 받아서 단위 검사가 꼴을 가른다.
    {"C1": "C1", "alpha": "C2", "n": "C3", "Q": "C4"},
)

_PAREN = re.compile(r"\s*\(.*\)\s*$")


def _name(raw: str) -> str:
    """`C2 (= ANSYS a, alpha)` → `C2`. 괄호 풀이는 사람이 읽으라고 붙은 것이다."""
    return _PAREN.sub("", raw).strip()


def _sets(deck: Deck) -> dict[str, dict[str, tuple[float, str]]]:
    """벌 → 항 → (값, 단위). **같은 `set_id` 는 합친다** — 모델 글자만 다른 두 벌이
    실재한다."""
    found: dict[str, dict[str, tuple[float, str]]] = {}
    for row in deck.rows("model_params"):
        value = row.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        # 덱 블록의 `group`(set_id + 변형)으로 묶는다 — `set` 이름표를 `/` 로 가르면 모델
        # 글자 안의 `/`(…exp(-C4/T))에서 갈린다.
        key = str(row.get("group") or row.get("set") or "")
        found.setdefault(key, {})[_name(str(row.get("name") or ""))] = (
            float(value),
            str(row.get("unit") or "1").strip() or "1",
        )
    return found


def _match(terms: dict[str, tuple[float, str]]) -> dict[str, tuple[float, str]] | None:
    for spelling in SPELLINGS:
        if set(spelling) <= set(terms):
            return {mine: terms[theirs] for theirs, mine in spelling.items()}
    return None


def garofalo(deck: Deck) -> tuple[str, list[float]]:
    """`(벌 이름, [C1, C2, C3, C4])` — 덱 단위계로 옮긴 값. 못 받으면 까닭을 들고 멈춘다."""
    candidates: dict[str, dict[str, tuple[float, str]]] = {}
    refused: list[str] = []
    for key, terms in _sets(deck).items():
        matched = _match(terms)
        if matched is None:
            if {"alpha", "n", "Q"} <= set(terms) or "A_prime" in terms:
                refused.append(f"{key}: 앞인자 A(1/s)가 없거나 전단 기준(A′)입니다")
            continue
        if "shear" in key.lower() or "A_prime" in terms:
            refused.append(
                f"{key}: 전단 기준(전단 변형률 속도 · τ)이라 인장 등가 식이 아닙니다"
            )
            continue
        candidates[key] = matched
    if not candidates:
        raise ExportError(
            "카드에 ANSYS 꼴(C1 · C2 · C3 · C4 또는 A · α · n · Q)의 Garofalo 벌이 없습니다"
            + (f" — {'; '.join(refused)}." if refused else ".")
        )
    if len(candidates) > 1:
        raise ExportError(
            f"카드에 Garofalo 벌이 {len(candidates)}개 있습니다"
            f"({', '.join(sorted(candidates))}) — "
            "한 덱에는 한 벌만 냅니다."
        )
    ((where, terms),) = candidates.items()
    c1_value, c1_unit = terms["C1"]
    c2_value, c2_unit = terms["C2"]
    c3_value, c3_unit = terms["C3"]
    c4_value, c4_unit = terms["C4"]

    rate = units.canonical(c1_unit)
    if rate is None or not any(
        units.same_dimension(units.unit_of(rate).dimension, one)
        for one in ("strain_rate", "frequency")
    ):
        raise ExportError(
            f"Garofalo C1(앞인자)의 단위가 '{c1_unit}' 입니다 — 1/시간이어야 합니다"
            "(Darveaux 꼴의 K/s/psi 는 전단탄성률이 있어야 같은 식이 됩니다)."
        )
    c1 = deck.units.convert(units.to_si(c1_value, rate), "1/s")

    if not c2_unit.startswith("1/"):
        raise ExportError(
            f"Garofalo C2(α)의 단위가 '{c2_unit}' 입니다 — 1/응력이어야 합니다"
            "(무차원이면 σ/G 로 "
            "정규화한 꼴입니다)."
        )
    stress = units.canonical(c2_unit[2:])
    if stress is None or not units.same_dimension(units.unit_of(stress).dimension, "stress"):
        raise ExportError(f"Garofalo C2(α)의 단위가 '{c2_unit}' 입니다 — 1/응력이어야 합니다.")
    # C2·σ 는 무차원이다 — σ 가 덱 단위계로 f 배가 되면 C2 는 1/f 배.
    c2 = c2_value / units.to_si(1.0, stress) / deck.units.convert(1.0, "Pa")

    if c3_unit not in ("1", "-", ""):
        raise ExportError(f"Garofalo C3(n)은 무차원이어야 하는데 단위가 '{c3_unit}' 입니다.")
    if c4_unit not in ENERGY:
        raise ExportError(
            f"Garofalo C4(Q/R)의 단위가 '{c4_unit}' 입니다 — K · J/mol · kJ/mol · eV 중 "
            "하나여야 "
            "합니다."
        )
    c4 = c4_value / ENERGY[c4_unit]
    return where, [c1, c2, c3_value, c4]


@register_renderer(
    key="ansys_creep",
    label="ANSYS (크리프 Garofalo)",
    extension="mac",
    suffix="_creep",
    describe=(
        "MP(EX · PRXY) + TB,CREEP(TBOPT 8, 일반화 Garofalo) — "
        "크리프 변형률 속도 = C1·sinh(C2·σ)^C3·exp(-C4/T). "
        "카드의 모델 파라미터 벌을 덱 단위계로 옮겨 싣는다. 온도는 절대온도(K)."
    ),
    keywords=(f"EX,{_ansys.MATERIAL}", "TB,CREEP"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("model_params", rows_min=3),
    ),
)
def render_ansys_creep(deck: Deck) -> Rendered:
    where, constants = garofalo(deck)
    lines, notes = _ansys._structural(deck)
    stress, rate = deck.units.symbol("Pa"), deck.units.symbol("1/s")
    lines.extend(
        [
            f"! Implicit creep - generalized Garofalo (TB,CREEP TBOPT=8). Set: {where or '-'}",
            "!   creep strain rate = C1 * sinh(C2*sigma)^C3 * exp(-C4/T), T absolute (K).",
            f"! C1 in {rate}, C2 in 1/{stress}, C3 -, C4 = Q/R in K.",
            f"TB,CREEP,{_ansys.MATERIAL},1,4,8",
            "TBDATA,1," + ",".join(_free(value) for value in constants),
        ]
    )
    return Rendered(
        text="\n".join(lines) + "\n",
        notes=(
            *notes,
            f"Garofalo 벌 「{where or '이름 없음'}」 을 TB,CREEP(TBOPT 8)으로 실었습니다 — "
            "탄소성 위에 "
            "얹는 정상상태 크리프입니다. C4 는 Q/R(K)이라 모델의 온도도 절대온도여야 합니다.",
        ),
    )
