"""1요소 검증 모델 — 카드의 재료 덱을 1요소 인장 모델에 끼우고 **기대 응답을 함께** 낸다
(2026-10-12).

## 왜

v1.280 ~ v1.282 의 새 형식 열넷은 매뉴얼만 보고 만들었다. 솔버로 실제로 돌려 본 것은 Radioss
아홉뿐이다(2026-10-01, `scripts/check_openradioss.py`). 칸 하나가 밀린 덱도 솔버는 오류 없이
돌고 다른 재료로 계산한다 — 그것은 **돌려서 숫자를 봐야** 드러난다. 그런데 돌려 보려면 해석
담당이 모델을 손으로 짜야 했다. 여기서 모델을 같이 준다 — 돌리고 견주기만 하면 된다.

## 무엇을 내나

    모델          저장소 예제(시뮬레이션 인풋 덱/예제 의 dp600 · rubber)에서 재료만 뺀 틀
                  (`verify_models/`)에, 이 카드가 내보내는 **그대로의** 재료 덱(재료 번호 1)을
                  끼운 것. 예제는 칸을 기계로 대조했고 Radioss 는 OpenRadioss 로 돌렸다.
    expected.csv  카드에서 계산한 응답 — 덱이 맞으면 솔버가 이 숫자를 낸다.
    README.txt    돌리는 법과 견줄 출력.

## 기대 응답

    탄소성   진응력 σ 와 대수변형률 ε — ε = σ/E + εp(가법 분해), σ = h(εp)(덱의 소성 표를 선형
            보간). 소성은 비압축, 탄성 체적은 (1-2ν)σ/E 로 반력의 단면에 넣는다.
    초탄성   카드의 ν 로 체적 항 (K/2)(J-1)² 을 넣은 단축 해 — 덱이 체적 강성을 만드는 K 와
            같다(`hyperelastic_bulk`). 옆 늘림을 옆 응력 0 으로 풀고 σ = (2/J) dev[(W₁ + Ī₁W₂)B̄
            - W₂B̄²] + K(J-1). ν 가 없거나 0.5 면 비압축 해석해 σ = 2(λ² - 1/λ)(W₁ + W₂/λ),
            Ogden 은 Σ (2μ/α)(λ^α - λ^(-α/2)).

**비압축 해석해만 내면 ν = 0.49 카드가 틀려 보인다.** 처음에는 비압축 해석해를 내고 「0.2% 쯤
낮게」 라고 적었다 — OpenRadioss 로 돌려 보니(2026-10-13) ν = 0.4995 는 0.3% 였지만 ν = 0.49
(문헌 고무에 흔하다)는 λ = 2 에서 **4.1% 낮았다**. 1% 문턱으로 읽으면 맞는 덱을 틀렸다고 한다.
압축성 해는 네 경우(Neo-Hookean 둘 · Mooney · Ogden) 모두 0.15% 안쪽으로 맞았다.

**당기는 양은 카드가 아는 범위 안에서만.** 소성 표의 마지막 점 너머는 솔버마다 늘리는 법이
달라(그대로 · 마지막 기울기) 기대값이 하나로 서지 않는다 — 마지막 소성변형률의 90% 까지,
공칭 50% 를 넘지 않게. 초탄성은 맞춘 구간(`strain_max`) 끝까지, 모르면 공칭 100%.

## 단위계는 mm·N·tonne 하나

틀의 모델은 1 mm 정육면체를 0.01 s 에 당긴다 — 명시 솔버(LS-DYNA · Radioss)에서 이 시간
척도가 준정적이다. 같은 모델을 m 계로 쓰면 1 m 정육면체라 관성이 끼어든다. 그래서 키트는 늘
mm·N·tonne 이다 — 환산이 실제로 일어나는(그래서 틀릴 수 있는) 계가 그것이기도 하다.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

from matcore.export import (
    Deck,
    ExportError,
    hyperelastic_bulk,
    hyperelastic_terms,
    prepare,
    to_system,
)
from matcore.export.systems import MM_N_TONNE

MODELS = Path(__file__).with_name("verify_models")

#: 키트를 내는 형식 → (하중, 솔버). 정의판(`<key>_def`)도 같은 키트를 쓴다.
KITS: dict[str, tuple[str, str]] = {
    "abaqus": ("tension", "abaqus"),
    "ansys_plastic": ("tension", "ansys"),
    "dyna": ("tension", "lsdyna"),
    "openradioss": ("tension", "radioss"),
    "nastran_plastic": ("tension", "nastran"),
    "optistruct_plastic": ("tension", "optistruct"),
    "abaqus_hyperelastic": ("rubber", "abaqus"),
    "ansys_hyperelastic": ("rubber", "ansys"),
    "dyna_hyperelastic": ("rubber", "lsdyna"),
    "openradioss_hyperelastic": ("rubber", "radioss"),
    "nastran_hyperelastic": ("rubber", "nastran"),
    "optistruct_hyperelastic": ("rubber", "optistruct"),
}

#: 솔버 → 모델 파일 확장자. Radioss 는 Starter · Engine 둘이라 따로 짓는다.
EXTENSIONS = {
    "abaqus": "inp",
    "ansys": "dat",
    "lsdyna": "k",
    "nastran": "bdf",
    "optistruct": "fem",
}
#: Radioss 런 이름 — Starter 의 `/BEGIN` 과 Engine 의 `/RUN` 이 같아야 한다(틀에 박혀 있다).
RADIOSS_RUN = "mnx_verify"

#: 공칭 변형률의 상한 — 예제와 같은 50%. 1요소라 그 너머는 요소가 찌그러지기 쉽다.
MAX_NOMINAL = 0.5
#: 소성 표의 마지막 점에서 얼마나 안쪽까지 당기나.
INSIDE_TABLE = 0.9
#: 초탄성 기본 늘림 — 맞춘 구간을 모르면 공칭 100%(λ = 2).
DEFAULT_STRETCH = 2.0
#: expected.csv 의 줄 수(0 을 빼고).
STEPS = 20


@dataclass(frozen=True)
class Kit:
    case: str
    solver: str
    pull: float
    """당기는 변위(mm) — 1 mm 정육면체라 공칭 변형률과 같다."""
    files: dict[str, bytes]


def kit_for(key: str) -> tuple[str, str] | None:
    """이 형식에 키트가 있나 — `(하중, 솔버)`."""
    return KITS.get(key.removesuffix("_def"))


# ── 기대 응답 ──────────────────────────────────────────────────────────────


def _interp(points: list[tuple[float, float]], plastic: float) -> float:
    """소성 표(εp, σ)를 선형으로 읽는다. 끝 너머는 끝 값 — 거기까지 안 당긴다."""
    if plastic <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= plastic <= x1:
            return y0 + (y1 - y0) * (plastic - x0) / (x1 - x0)
    return points[-1][1]


def _tension_state(
    points: list[tuple[float, float]], youngs: float, log_strain: float
) -> tuple[float, float]:
    """대수변형률 ε 에서 (σ, εp). ε = σ/E + εp, σ = h(εp) — εp 를 이분법으로 푼다."""
    if youngs * log_strain <= points[0][1]:
        return youngs * log_strain, 0.0
    low, high = 0.0, log_strain
    for _ in range(200):
        middle = (low + high) / 2.0
        if middle + _interp(points, middle) / youngs > log_strain:
            high = middle
        else:
            low = middle
    plastic = (low + high) / 2.0
    return _interp(points, plastic), plastic


def tension(deck: Deck) -> tuple[float, list[dict[str, float]], list[str]]:
    """탄소성 인장 — `(당기는 변위, 기대 응답 줄, 각주)`. 덱은 이미 mm·N·tonne 이다."""
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    if youngs is None or youngs <= 0 or poisson is None:
        raise ExportError("탄성계수 · 푸아송비가 없어 검증 모델의 기대 응답을 못 셉니다.")
    points, _ = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    last = points[-1][0]
    said: list[str] = []
    target = INSIDE_TABLE * last if last > 0 else 0.0
    nominal = math.exp(target + _interp(points, target) / youngs) - 1.0
    if nominal > MAX_NOMINAL:
        nominal = MAX_NOMINAL
        said.append(
            f"공칭 변형률 {MAX_NOMINAL:.0%} 까지 당깁니다 — 소성 표는 그 너머까지 있습니다."
        )
    else:
        said.append(
            f"소성 표의 마지막 소성변형률 {last:.4g} 의 {INSIDE_TABLE:.0%} 까지 당깁니다 — 표 "
            "너머는 솔버마다 늘리는 법이 달라 기대값이 하나로 서지 않습니다."
        )
    pull = round(nominal, 4)
    rows: list[dict[str, float]] = []
    for step in range(STEPS + 1):
        strain = pull * step / STEPS
        log_strain = math.log1p(strain)
        stress, plastic = _tension_state(points, youngs, log_strain)
        # 단면 = 원단면 · J / λ — 소성은 비압축, 탄성 체적만 (1-2ν)σ/E.
        area = math.exp((1.0 - 2.0 * poisson) * stress / youngs) / (1.0 + strain)
        rows.append(
            {
                "nominal_strain": strain,
                "log_strain": log_strain,
                "true_stress_MPa": stress,
                "plastic_strain": plastic,
                "reaction_N": stress * area,
            }
        )
    return pull, rows, said


def _slopes(values: dict[str, float], i1: float, i2: float) -> tuple[float, float]:
    """다항식 꼴의 ∂W/∂I₁ · ∂W/∂I₂."""
    c = {name: values.get(name, 0.0) for name in ("c10", "c01", "c20", "c11", "c02", "c30")}
    w1 = (
        c["c10"] + 2 * c["c20"] * (i1 - 3) + c["c11"] * (i2 - 3) + 3 * c["c30"] * (i1 - 3) ** 2
    )
    w2 = c["c01"] + c["c11"] * (i1 - 3) + 2 * c["c02"] * (i2 - 3)
    return w1, w2


def rubber_stress(family: str, values: dict[str, float], stretch: float) -> float:
    """비압축 단축 인장의 진응력(Cauchy). 계수는 덱의 단위(MPa)."""
    if family == "ogden_1":
        mu, alpha = values["mu"], values["alpha"]
        return float(2.0 * mu / alpha * (stretch**alpha - stretch ** (-alpha / 2.0)))
    i1 = stretch**2 + 2.0 / stretch
    i2 = 2.0 * stretch + 1.0 / stretch**2
    w1, w2 = _slopes(values, i1, i2)
    return 2.0 * (stretch**2 - 1.0 / stretch) * (w1 + w2 / stretch)


def _principal(
    family: str, values: dict[str, float], stretch: float, side: float, bulk: float
) -> tuple[float, float]:
    """늘림 `stretch` · 옆 늘림 `side` 에서 `(축 진응력, 옆 진응력)` — 체적 항 (K/2)(J-1)²."""
    volume = stretch * side * side
    pressure = bulk * (volume - 1.0)
    b_axial = volume ** (-2.0 / 3.0) * stretch * stretch
    b_side = volume ** (-2.0 / 3.0) * side * side
    if family == "ogden_1":
        mu, alpha = values["mu"], values["alpha"]
        l_axial, l_side = b_axial**0.5, b_side**0.5
        mean = (l_axial**alpha + 2.0 * l_side**alpha) / 3.0
        scale = 2.0 * mu / (alpha * volume)
        return (
            scale * (l_axial**alpha - mean) + pressure,
            scale * (l_side**alpha - mean) + pressure,
        )
    i1 = b_axial + 2.0 * b_side
    i2 = 2.0 * b_axial * b_side + b_side * b_side
    w1, w2 = _slopes(values, i1, i2)
    a_axial = (w1 + i1 * w2) * b_axial - w2 * b_axial * b_axial
    a_side = (w1 + i1 * w2) * b_side - w2 * b_side * b_side
    trace = (a_axial + 2.0 * a_side) / 3.0
    return (
        2.0 / volume * (a_axial - trace) + pressure,
        2.0 / volume * (a_side - trace) + pressure,
    )


def rubber_state(
    family: str, values: dict[str, float], stretch: float, bulk: float | None
) -> tuple[float, float]:
    """단축 인장의 `(진응력, 옆 늘림)`. `bulk`(K)가 없으면 비압축 해석해(옆 늘림 λ^-½).

    옆 늘림은 옆 응력이 0 이 되는 자리를 이분법으로 찾는다 — 옆 응력은 옆 늘림에 대해 늘
    오른다(부피가 늘면 압력이 오르고, 편차 몫도 옆으로 커진다)."""
    if bulk is None:
        return rubber_stress(family, values, stretch), stretch**-0.5
    if stretch == 1.0:
        return 0.0, 1.0
    low, high = 0.1 * stretch**-0.5, 1.5
    for _ in range(200):
        middle = 0.5 * (low + high)
        if _principal(family, values, stretch, middle, bulk)[1] > 0.0:
            high = middle
        else:
            low = middle
    side = 0.5 * (low + high)
    return _principal(family, values, stretch, side, bulk)[0], side


def rubber(deck: Deck) -> tuple[float, list[dict[str, float]], list[str]]:
    """초탄성 인장 — `(당기는 변위, 기대 응답 줄, 각주)`."""
    family, values = hyperelastic_terms(deck)
    compressible = hyperelastic_bulk(deck, family, values)
    bulk = compressible[2] if compressible else None
    fitted = deck.number("hyperelastic", "strain_max")
    said: list[str] = []
    if fitted is not None and 0.0 < fitted <= DEFAULT_STRETCH - 1.0:
        pull = round(fitted, 4)
        said.append(f"맞춘 구간의 끝(공칭 {fitted:.4g})까지 늘립니다.")
    else:
        pull = DEFAULT_STRETCH - 1.0
        said.append(
            "맞춘 구간을 몰라 공칭 100%(λ = 2)까지 늘립니다 — 카드가 그 범위를 보증하지는 "
            "않습니다."
        )
    rows: list[dict[str, float]] = []
    for step in range(STEPS + 1):
        strain = pull * step / STEPS
        stretch = 1.0 + strain
        stress, side = rubber_state(family, values, stretch, bulk)
        rows.append(
            {
                "nominal_strain": strain,
                "stretch": stretch,
                "true_stress_MPa": stress,
                # 단면 = 원단면 · 옆 늘림² (비압축이면 1/λ).
                "nominal_stress_MPa": stress * side * side,
                "reaction_N": stress * side * side,
            }
        )
    if compressible is None:
        said.append("기대값은 완전 비압축 해석해입니다 — 카드에 푸아송비가 없거나 0.5 입니다.")
    else:
        poisson, _, _ = compressible
        apart = 1.0 - rows[-1]["true_stress_MPa"] / rubber_stress(family, values, 1.0 + pull)
        said.append(
            f"기대값은 카드의 푸아송비 {poisson:g} 로 체적 항 (K/2)(J-1)² 을 넣은 "
            f"단축 해입니다(K = {bulk:.6g} MPa, 덱이 쓰는 것과 같은 K). 비압축 해석해보다 "
            f"끝에서 {apart:.2%} 낮습니다. 솔버마다 체적 항의 꼴이 조금 달라 0.2% 안쪽에서 "
            "어긋납니다."
        )
    return pull, rows, said


# ── 모델 ───────────────────────────────────────────────────────────────────


def _material(solver: str, rendered: str) -> str:
    """덱 → 틀에 끼울 재료 조각. 덱 전체의 머리 · 끝 줄만 뗀다."""
    lines = rendered.rstrip("\n").split("\n")
    if solver == "lsdyna":
        lines = [line for line in lines if line.strip().upper() not in ("*KEYWORD", "*END")]
    if solver == "radioss":
        # Radioss 는 빈 줄도 한 줄로 읽는다 — 빈 줄은 그대로 둔다(LAW42 의 빈 카드).
        lines = [line for line in lines if line not in ("#RADIOSS STARTER", "/END")]
    return "\n".join(lines)


def _fill(template: str, material: str, pull: float, name: str) -> str:
    out = (
        template.replace("@@MATERIAL@@", material)
        .replace("@@NAME@@", name)
        .replace("@@PULL20@@", f"{pull:>20.4f}")
        .replace("@@PULL8@@", f"{pull:<8.4f}")
        .replace("@@PULL@@", f"{pull:.4f}")
    )
    if "@@" in out:
        raise ExportError("검증 모델 틀에 채우지 못한 자리가 남았습니다.")
    return out


def _csv(rows: list[dict[str, float]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: f"{value:.6g}" for key, value in row.items()})
    return buffer.getvalue().encode("utf-8")


#: 솔버마다 돌리는 법과 견줄 출력.
HOW: dict[str, tuple[str, str]] = {
    "abaqus": (
        "abaqus job=<모델 파일 이름> interactive",
        "이력 출력 S11 · LE11(요소 집합 CUBE), 반력 RF1(절점 집합 PULL 의 합)",
    ),
    "ansys": (
        "ansys -b -i <모델 파일> -o out.txt",
        "/POST1 의 PRETAB(SX), FSUM 의 FX",
    ),
    "lsdyna": (
        "lsdyna i=<모델 파일>",
        "elout 의 sig-xx(요소 1), nodfor 의 x 힘(절점 집합 4)",
    ),
    "radioss": (
        f"starter -i {RADIOSS_RUN}_0000.rad  →  engine -i {RADIOSS_RUN}_0001.rad",
        "T01 의 brick history SX(·PLAS) — th_to_csv 로 풀어 본다. 반력은 pulled\n"
        "       node 의 REACX 인데 힘이 아니라 충격량(∫F dt)이고 당기는 면 네 절점 중\n"
        "       하나의 몫이다 — 마지막 두 기록의 차를 시간 차로 나눠 4 를 곱한다(그대로\n"
        "       읽으면 기대 반력의 0.3% 쯤으로 보이고, 여러 기록에 걸쳐 나누면 힘이 오르는\n"
        "       중이라 낮게 나온다).",
    ),
    "nastran": (
        "nastran <모델 파일>",
        "요소 응력 σx(SX), 당기는 면의 SPCFORCE 합",
    ),
    "optistruct": (
        "optistruct <모델 파일>",
        "요소 응력 σx(SX), 당기는 면의 SPCFORCE 합",
    ),
}

CASE_TEXT = {
    "tension": "탄소성 단축 인장 — 진응력과 대수변형률",
    "rubber": "초탄성 단축 인장 — 진응력과 늘림",
}


def _readme(
    case: str,
    solver: str,
    label: str,
    name: str,
    pull: float,
    rows: list[dict[str, float]],
    said: list[str],
    notes: list[str],
    model: str,
) -> bytes:
    run, compare = HOW[solver]
    end = rows[-1]
    lines = [
        f"MatNexus 1요소 검증 모델 — {label}",
        f"카드: {name} · 단위계 mm·N·tonne(응력 MPa · 힘 N) · 재료 번호 1",
        "",
        f"무엇   {CASE_TEXT[case]}. 한 변 1 mm 정육면체를 x 로 {pull:.4f} mm 당깁니다",
        "       (1/8 대칭이라 순수 단축). 재료 자리에는 이 카드를 내보낼 때와 같은 덱이",
        "       들어 있습니다.",
        f"모델   {model}",
        f"돌리기 {run}",
        f"견주기 {compare}",
        f"       expected.csv 의 마지막 줄 — 진응력 {end['true_stress_MPa']:.6g} MPa · "
        f"반력 {end['reaction_N']:.6g} N",
        "       1% 안쪽이면 카드가 솔버에 제대로 들어간 것입니다. 명시 솔버(LS-DYNA ·",
        "       Radioss)는 0.01 s 에 당겨서 1% 남짓 어긋날 수 있습니다(운동에너지가",
        "       내부에너지의 5% 를 넘으면 종료 시간을 늘립니다).",
        "",
        "기대값",
        *(f"  - {one}" for one in said),
        "",
        "솔버로 돌려 보지 않은 형식이 많습니다 — 이 모델의 결과(맞든 틀리든)를 플랫폼",
        "개발자에게 알려 주시면 형식을 바로잡거나 「확인됨」 으로 적겠습니다.",
    ]
    if notes:
        lines += ["", "덱의 알림", *(f"  - {one}" for one in notes)]
    return ("\n".join(lines) + "\n").encode("utf-8")


EXPECTED: dict[str, Callable[[Deck], tuple[float, list[dict[str, float]], list[str]]]] = {
    "tension": tension,
    "rubber": rubber,
}


def build(key: str, label: str, deck: Deck, rendered: str, notes: tuple[str, ...] = ()) -> Kit:
    """키트를 짓는다. `rendered` 는 이 형식이 **mm·N·tonne · 재료 번호 1** 로 낸 덱 글자다
    (정의판 형식도 그 렌더러로 그린 것을 받는다). `deck` 은 카드 그대로(SI)."""
    found = kit_for(key)
    if found is None:
        raise ExportError(
            "이 형식은 검증 모델이 아직 없습니다 — 탄소성 · 초탄성 인장(여섯 솔버)만 있습니다."
        )
    case, solver = found
    moved = to_system(replace(deck, solver_id=1), MM_N_TONNE)
    pull, rows, said = EXPECTED[case](moved)
    material = _material(solver, rendered)
    files: dict[str, bytes] = {}
    if solver == "radioss":
        starter = (MODELS / f"{case}-radioss_0000.rad").read_text(encoding="ascii")
        engine = (MODELS / "radioss_0001.rad").read_text(encoding="ascii")
        files[f"{RADIOSS_RUN}_0000.rad"] = _fill(starter, material, pull, deck.name).encode()
        files[f"{RADIOSS_RUN}_0001.rad"] = engine.encode("ascii")
        model = f"{RADIOSS_RUN}_0000.rad(Starter) · {RADIOSS_RUN}_0001.rad(Engine)"
    else:
        template = (MODELS / f"{case}-{solver}.{EXTENSIONS[solver]}").read_text(
            encoding="ascii"
        )
        model = f"{deck.name}_verify.{EXTENSIONS[solver]}"
        files[model] = _fill(template, material, pull, deck.name).encode()
    files["expected.csv"] = _csv(rows)
    files["README.txt"] = _readme(
        case, solver, label, deck.name, pull, rows, said, list(notes), model
    )
    return Kit(case=case, solver=solver, pull=pull, files=files)
