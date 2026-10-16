"""굽힘 시험 → 굽힘 응력 · 변형률 · 등가 E · 강도 · 등가 E 카드(확장 `flexural`, 2026-10-16).

답을 아는 보의 처짐으로 E 가 그대로 돌아오는지 본다. 직사각형 단면 b · h, 단면 2차 모멘트
I = b·h³/12, 하중 F(전체), 모멘트 팔 a = (L - Lᵢ)/2:

    3점 가운데 처짐     δ = F·L³ / (48·E·I)
    4점 가운데 처짐     δ = F·a·(3L² - 4a²) / (48·E·I)
    4점 하중점 처짐     δ = F·a²·(3L - 4a) / (12·E·I)

크로스헤드에 장비 처짐 C·F 를 섞으면 컴플라이언스를 줘야 E 가 돌아온다 — **조용히 틀리는
자리**라 사보타주 대상이다(계수 하나를 바꾸면 E 가 몇 % 어긋난 채 그럴듯하다).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import cards, extensions, processing
from matcore.groups import GroupError, Member
from matcore.processing import Frame, ProcessingError, Scalar, Step

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()

bending = importlib.import_module(f"{extensions.PACKAGE}.flexural.bending")

E = 3.0e9
WIDTH = 0.010
THICKNESS = 0.004
SPAN = 0.064
INERTIA = WIDTH * THICKNESS**3 / 12


def _force(top: float = 200.0, points: int = 200) -> np.ndarray:
    return np.linspace(0.0, top, points)


def _frame(**columns: np.ndarray) -> Frame:
    units = {"force": "N", "deflection": "m", "displacement": "m"}
    return Frame(dict(columns), {key: units[key] for key in columns})


def _options(**extra: Any) -> dict[str, Any]:
    return {"support_span": SPAN, "width": WIDTH, "thickness": THICKNESS, **extra}


def _modulus(frame: Frame, **options: Any) -> dict[str, float]:
    step = bending.modulus(frame, options)
    return {one.key: one.value for one in step.scalars}


def test_3점_가운데_처짐에서_E_가_돌아온다() -> None:
    force = _force()
    deflection = force * SPAN**3 / (48 * E * INERTIA)
    step = bending.engineering(_frame(force=force, deflection=deflection), _options())
    stress = step.frame.columns[bending.STRESS]
    # σ = 3FL/(2bh²) — ISO 178 · D790 그대로.
    assert stress[-1] == pytest.approx(3 * force[-1] * SPAN / (2 * WIDTH * THICKNESS**2))
    found = _modulus(step.frame)
    assert found["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    assert any("3점" in one for one in step.notes)


def test_4점_계수는_D6272_의_4_70_과_4_36() -> None:
    """D6272: Lᵢ = L/3 이면 ε = 4.70·hδ/L², Lᵢ = L/2 이면 4.36·hδ/L²."""
    third = bending.strain_factor(SPAN, (SPAN - SPAN / 3) / 2, "midspan") * SPAN**2
    half = bending.strain_factor(SPAN, (SPAN - SPAN / 2) / 2, "midspan") * SPAN**2
    assert third == pytest.approx(4.70, abs=0.005)
    assert half == pytest.approx(4.36, abs=0.005)
    # 3점(a = L/2)이면 6hδ/L².
    assert bending.strain_factor(SPAN, SPAN / 2, "midspan") * SPAN**2 == pytest.approx(6.0)


@pytest.mark.parametrize("load_span", [SPAN / 3, SPAN / 2])
def test_4점_가운데_처짐계에서_E_가_돌아온다(load_span: float) -> None:
    force = _force()
    arm = (SPAN - load_span) / 2
    deflection = force * arm * (3 * SPAN**2 - 4 * arm**2) / (48 * E * INERTIA)
    step = bending.engineering(
        _frame(force=force, deflection=deflection), _options(load_span=load_span)
    )
    stress = step.frame.columns[bending.STRESS]
    assert stress[-1] == pytest.approx(3 * force[-1] * arm / (WIDTH * THICKNESS**2))
    assert _modulus(step.frame)["flexural_modulus"] == pytest.approx(E, rel=1e-6)


def test_4점_크로스헤드는_하중점_처짐으로_본다() -> None:
    """자동이면 4점 크로스헤드는 하중점 — 가운데로 보면 E 가 몇 % 어긋난다."""
    force = _force()
    load_span = SPAN / 3
    arm = (SPAN - load_span) / 2
    at_load = force * arm**2 * (3 * SPAN - 4 * arm) / (12 * E * INERTIA)
    frame = _frame(force=force, displacement=at_load)
    auto = bending.engineering(frame, _options(load_span=load_span))
    assert _modulus(auto.frame)["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    wrong = bending.engineering(
        frame, _options(load_span=load_span, deflection_point="midspan")
    )
    assert _modulus(wrong.frame)["flexural_modulus"] == pytest.approx(E, rel=0.5)
    assert abs(_modulus(wrong.frame)["flexural_modulus"] / E - 1) > 0.05


def test_처짐계가_있으면_크로스헤드보다_먼저() -> None:
    force = _force()
    true = force * SPAN**3 / (48 * E * INERTIA)
    frame = _frame(force=force, deflection=true, displacement=true * 3)
    step = bending.engineering(frame, _options())
    assert _modulus(step.frame)["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    forced = bending.engineering(frame, _options(deflection_source="displacement"))
    assert _modulus(forced.frame)["flexural_modulus"] == pytest.approx(E / 3, rel=1e-6)


def test_장비_컴플라이언스를_빼야_E_가_돌아온다() -> None:
    """칩처럼 짧고 단단하면 장비 처짐이 시편 처짐과 같은 자릿수다."""
    force = _force()
    true = force * SPAN**3 / (48 * E * INERTIA)
    compliance = 1e-5  # m/N — 시편 컴플라이언스(약 3.4e-5)의 30% 남짓
    frame = _frame(force=force, displacement=true + compliance * force)
    raw = bending.engineering(frame, _options())
    assert _modulus(raw.frame)["flexural_modulus"] < 0.9 * E
    assert any("크로스헤드" in one for one in raw.notes)
    fixed = bending.engineering(frame, _options(machine_compliance=compliance))
    assert _modulus(fixed.frame)["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    # 강성(하중/처짐)도 같은 구간에서 — 보정 뒤 처짐 기준.
    stiffness = _modulus(fixed.frame)["flexural_stiffness"]
    assert stiffness == pytest.approx(48 * E * INERTIA / SPAN**3, rel=1e-6)


def test_처짐은_첫_점을_0_으로() -> None:
    force = _force()
    deflection = force * SPAN**3 / (48 * E * INERTIA) + 0.0012
    step = bending.engineering(_frame(force=force, deflection=deflection), _options())
    assert step.frame.columns[bending.USED][0] == 0.0
    assert _modulus(step.frame)["flexural_modulus"] == pytest.approx(E, rel=1e-6)


def test_스팬이_두께의_16배보다_짧으면_말한다() -> None:
    force = _force()
    span = 0.030
    deflection = force * span**3 / (48 * E * INERTIA)
    step = bending.engineering(
        _frame(force=force, deflection=deflection), _options(support_span=span)
    )
    assert any("전단 처짐" in one for one in step.notes)
    ratio = {one.key: one.value for one in step.scalars}["span_to_depth_ratio"]
    assert ratio == pytest.approx(span / THICKNESS)


def test_큰_처짐_보정은_3점에만() -> None:
    force = _force()
    deflection = force * SPAN**3 / (48 * E * INERTIA)
    plain = bending.engineering(_frame(force=force, deflection=deflection), _options())
    corrected = bending.engineering(
        _frame(force=force, deflection=deflection), _options(large_deflection=True)
    )
    ratio = deflection[-1] / SPAN
    factor = 1 + 6 * ratio**2 - 4 * (THICKNESS / SPAN) * ratio
    assert corrected.frame.columns[bending.STRESS][-1] == pytest.approx(
        plain.frame.columns[bending.STRESS][-1] * factor
    )
    four = bending.engineering(
        _frame(force=force, deflection=deflection),
        _options(load_span=SPAN / 3, large_deflection=True),
    )
    assert any("4점에는 적용하지" in one for one in four.notes)


def test_하중_스팬이_지지_스팬보다_길면_멈춘다() -> None:
    force = _force()
    with pytest.raises(ProcessingError, match="하중 스팬"):
        bending.engineering(
            _frame(force=force, deflection=force * 1e-6), _options(load_span=SPAN * 1.2)
        )


def test_단위가_다르면_멈춘다() -> None:
    frame = Frame({"force": _force(), "deflection": _force() * 1e-6}, {"force": "kN"})
    with pytest.raises(ProcessingError, match="force"):
        bending.engineering(frame, _options())


def _curve() -> Frame:
    """토우(처음 눕는 구간) → 직선 → 항복 → 최대 → 파단 뒤 떨어짐."""
    strain = np.linspace(0, 0.05, 501)
    toe = 0.0005
    stress = np.where(strain < toe, E * strain**2 / (2 * toe), E * (strain - toe / 2))
    stress = np.minimum(stress, 60e6 + 2e8 * strain)  # 항복 뒤 완만히
    stress[-20:] = np.linspace(stress[-21], 10e6, 20)  # 파단
    return Frame(
        {bending.STRAIN: strain, bending.STRESS: stress},
        {bending.STRAIN: "1", bending.STRESS: "Pa"},
    )


def test_접선은_토우를_건너뛴다() -> None:
    frame = _curve()
    tangent = _modulus(frame, method="tangent", tangent_width=0.002)
    assert tangent["flexural_modulus"] == pytest.approx(E, rel=0.01)
    secant = _modulus(frame, method="secant", maximum_strain=0.002)
    assert secant["flexural_modulus"] < tangent["flexural_modulus"]


def test_회귀는_R2_를_함께_낸다() -> None:
    found = _modulus(_curve(), method="regression", minimum_strain=0.001, maximum_strain=0.01)
    assert found["flexural_modulus"] == pytest.approx(E, rel=1e-3)
    assert found["flexural_modulus_r2"] == pytest.approx(1.0, abs=1e-6)


def test_응력_띠는_변형률을_몰라도_된다() -> None:
    found = _modulus(_curve(), method="stress_window", band_low=0.1, band_high=0.4)
    assert found["flexural_modulus"] == pytest.approx(E, rel=0.01)


def test_구간에_못_닿으면_실패하지_않고_까닭을_남긴다() -> None:
    step = bending.modulus(_curve(), {"method": "chord", "maximum_strain": 0.5})
    assert step.scalars == ()
    assert any("안 갑니다" in one for one in step.notes)


def test_강도_파단_규정_처짐_응력() -> None:
    frame = _curve()
    stress = frame.columns[bending.STRESS]
    strain = frame.columns[bending.STRAIN]
    found = {one.key: one.value for one in bending.strength(frame, {}).scalars}
    peak = int(np.argmax(stress))
    assert found["flexural_strength"] == pytest.approx(stress[peak])
    assert found["flexural_strain_at_strength"] == pytest.approx(strain[peak])
    assert found["flexural_stress_at_break"] == pytest.approx(10e6)
    assert found["flexural_stress_at_3_5pct"] == pytest.approx(60e6 + 2e8 * 0.035, rel=1e-3)


def test_규정_처짐에_못_닿으면_σfC_를_안_낸다() -> None:
    strain = np.linspace(0, 0.01, 50)
    frame = Frame(
        {bending.STRAIN: strain, bending.STRESS: E * strain},
        {bending.STRAIN: "1", bending.STRESS: "Pa"},
    )
    found = {one.key for one in bending.strength(frame, {}).scalars}
    assert "flexural_stress_at_3_5pct" not in found


def _member(label: str, modulus: float, strength: float | None = None) -> Member:
    values = {"flexural_modulus": modulus}
    if strength is not None:
        values["flexural_strength"] = strength
    return Member(label=label, columns={}, values=values)


def test_시편_여럿을_묶어_등가_E() -> None:
    outcome = bending.equivalent_modulus(
        [_member("S1", 3.0e9, 90e6), _member("S2", 3.2e9, 94e6), _member("S3", 3.1e9)]
    )
    assert outcome.values["flexural_modulus"] == pytest.approx(3.1e9)
    assert outcome.values["flexural_modulus_sd"] == pytest.approx(0.1e9)
    assert outcome.values["flexural_modulus_cv"] == pytest.approx(0.1 / 3.1)
    assert outcome.values["sample_count"] == 3
    assert outcome.values["flexural_strength"] == pytest.approx(92e6)
    assert outcome.used == ["S1", "S2", "S3"]
    assert outcome.warnings == []


def test_흩어지면_말한다() -> None:
    outcome = bending.equivalent_modulus([_member("S1", 2.0e9), _member("S2", 3.0e9)])
    assert any("변동계수" in one for one in outcome.warnings)


def test_하나로는_안_묶는다() -> None:
    with pytest.raises(GroupError, match="둘 이상"):
        bending.equivalent_modulus([_member("S1", 3.0e9), _member("S2", 0.0)])


def test_카드는_탄성_블록의_E_와_참고_물성() -> None:
    outcome = bending.equivalent_modulus(
        [_member("S1", 3.0e9, 90e6), _member("S2", 3.2e9, 94e6)]
    )
    blocks = bending.card_blocks(outcome.values, outcome.detail, outcome.warnings)
    assert blocks["elastic"]["values"] == {"youngs_modulus": pytest.approx(3.1e9)}
    assert "등가 E" in blocks["elastic"]["notes"][0]
    assert blocks["reference"]["values"] == {
        "flexural_modulus": pytest.approx(3.1e9),
        "flexural_strength": pytest.approx(92e6),
    }
    # 블록 칸이 카드 정의에 있는 키인가 — 없는 칸은 카드가 조용히 버린다.
    for key, block in blocks.items():
        known = {made.key for made in cards.block(key).produces}
        assert set(block["values"]) <= known, key


# ── 하중 스팬은 「있으면 쓴다」(`@?`, 2026-10-16) ─────────────────────────────


def _given(load_span: float | None) -> list[Scalar]:
    given = [
        Scalar("specimen_span", "스팬", SPAN, "m"),
        Scalar("specimen_width", "폭", WIDTH, "m"),
        Scalar("specimen_thickness", "두께", THICKNESS, "m"),
    ]
    if load_span is not None:
        given.append(Scalar("specimen_load_span", "하중 스팬", load_span, "m"))
    return given


ENGINEERING = {
    "support_span": "@specimen_span",
    "width": "@specimen_width",
    "thickness": "@specimen_thickness",
    "load_span": "@?specimen_load_span",
}


def test_시편에_하중_스팬이_있으면_4점_없으면_3점() -> None:
    """**4점 시편을 3점 식으로 조용히 계산하던 자리**(2026-10-16). 기본 순서에 하중 스팬이 비어
    있어서, 시편에 값이 있어도 3점으로 돌았다 — 응력 · E 가 오류 없이 틀렸다."""
    force = _force()
    load_span = SPAN / 3
    arm = (SPAN - load_span) / 2
    four = force * arm * (3 * SPAN**2 - 4 * arm**2) / (48 * E * INERTIA)
    three = force * SPAN**3 / (48 * E * INERTIA)
    steps = [Step("flexural.engineering", ENGINEERING), Step("flexural.modulus", {})]

    as_four = processing.apply(
        steps, _frame(force=force, deflection=four), given=_given(load_span)
    )
    found = {one.key: one.value for one in as_four.stages[-1].scalars}
    assert found["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    assert any("4점" in one for one in as_four.stages[0].notes)

    as_three = processing.apply(
        steps, _frame(force=force, deflection=three), given=_given(None)
    )
    found = {one.key: one.value for one in as_three.stages[-1].scalars}
    assert found["flexural_modulus"] == pytest.approx(E, rel=1e-6)
    assert any("3점" in one for one in as_three.stages[0].notes)


def test_꼭_있어야_하는_참조는_여전히_멈춘다() -> None:
    """4점 규격(D6272)은 `@` 로 둔다 — 하중 스팬이 없으면 3점으로 넘어가지 않고 멈춘다."""
    force = _force()
    strict = {**ENGINEERING, "load_span": "@specimen_load_span"}
    with pytest.raises(ProcessingError, match="specimen_load_span"):
        processing.apply(
            [Step("flexural.engineering", strict)],
            _frame(force=force, deflection=force * 1e-6),
            given=_given(None),
        )
