"""굽힘 시험(3점 · 4점) — 하중-처짐에서 굽힘 응력 · 변형률 · 탄성률(등가 E) · 강도(2026-10-16).

칩 · 모듈처럼 인장 시편을 못 만드는 것의 **등가 E** 를 이 길로 낸다 — 직사각형 단면을 통째
균질한 보로 보고, 같은 굽힘 강성을 내는 E 다. 플라스틱 · 복합재 · 세라믹의 굽힘 규격(ISO 178 ·
ASTM D790 · D6272 · D7264 · ISO 14125 · C1161 · ISO 14704)도 같은 식이다.

## 한 식으로 3점과 4점

지지 스팬 L, 하중 스팬 Lᵢ(3점이면 0), 모멘트 팔 a = (L - Lᵢ)/2, 폭 b, 두께 h:

    σ = 3·F·a / (b·h²)
    ε = 12·h·δ / (3L² - 4a²)            δ 가 스팬 가운데 처짐일 때
    ε = 3·h·δ / (a·(3L - 4a))           δ 가 하중점 처짐일 때(4점에서 크로스헤드로 잴 때)

3점(a = L/2)이면 σ = 3FL/(2bh²), ε = 6hδ/L² — ISO 178 · D790 그대로다. 4점 Lᵢ = L/3 이면
ε = 4.70·hδ/L², Lᵢ = L/2 이면 4.36·hδ/L² — D6272 의 계수가 이 식에서 나온다(시험이 문다).

## 처짐을 무엇으로 쟀나

처짐계(LVDT · 비디오 신율계)가 있으면 그것, 없으면 크로스헤드 변위다. 크로스헤드에는 **장비
자신의 처짐**이 섞인다 — 칩처럼 짧고 단단한 시편은 그것이 시편 처짐과 같은 자릿수라 E 가 크게
작게 나온다. 장비 컴플라이언스 C(m/N)를 주면 δ - C·F 로 뺀다.

## 하지 않는 것

전단 처짐 보정(티모셴코)은 G 를 몰라 하지 않는다 — 스팬/두께가 16 보다 작으면 E 가 작게 나올
수 있다고 **말한다**. 큰 처짐 보정은 D790 3점 식만 둔다(4점 보정식은 하중 스팬마다 달라서).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore import slopes
from matcore.groups import GroupError, GroupOutcome, Member
from matcore.processing import Frame, ProcessingError, Scalar, StepResult, option_float

#: 장비 채널 키 — 중심의 시험 종류(`flexural`)가 정한다.
FORCE = "force"
DEFLECTION = "deflection"
DISPLACEMENT = "displacement"

#: 이 확장이 만드는 열.
STRAIN = "flexural_strain"
STRESS = "flexural_stress"
USED = "deflection_used"

#: 스팬/두께가 이보다 작으면 전단 처짐이 커진다(ISO 178 · D790 의 16).
SHEAR_RATIO = 16.0

#: ISO 178 의 규정 처짐 1.5·h 에 해당하는 굽힘 변형률 — σ_fC 를 여기서 읽는다.
CONVENTIONAL_STRAIN = 0.035


def _float_or_none(options: Mapping[str, Any], key: str) -> float | None:
    raw = options.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _arm(support: float, load: float | None) -> float:
    inner = load or 0.0
    if inner < 0 or inner >= support:
        raise ProcessingError(
            f"하중 스팬({inner * 1e3:.4g} mm)은 0 이상, 지지 스팬({support * 1e3:.4g} mm)보다 "
            "작아야 합니다 — 3점이면 하중 스팬을 비우세요."
        )
    return (support - inner) / 2.0


def strain_factor(support: float, arm: float, point: str) -> float:
    """처짐 δ 에 곱해 ε 를 만드는 계수(두께 h 를 뺀 것) — ε = h · δ · 이 값."""
    if point == "load_point":
        return 3.0 / (arm * (3.0 * support - 4.0 * arm))
    return 12.0 / (3.0 * support**2 - 4.0 * arm**2)


def engineering(frame: Frame, options: dict[str, Any]) -> StepResult:
    """하중 · 처짐 → 굽힘 응력 · 변형률."""
    support = option_float(options, "support_span")
    width = option_float(options, "width")
    thickness = option_float(options, "thickness")
    load_span = _float_or_none(options, "load_span")
    compliance = _float_or_none(options, "machine_compliance") or 0.0
    for name, value in (("지지 스팬", support), ("폭", width), ("두께", thickness)):
        if value <= 0:
            raise ProcessingError(f"{name}이 0 이하입니다: {value} m")
    arm = _arm(support, load_span)
    four_point = bool(load_span)

    force_key = str(options.get("force") or FORCE)
    force = frame.require(force_key, what="하중")
    source = str(options.get("deflection_source") or "auto")
    if source == "auto":
        source = DEFLECTION if DEFLECTION in frame.columns else DISPLACEMENT
    deflection_key = DEFLECTION if source == DEFLECTION else DISPLACEMENT
    deflection = frame.require(deflection_key, what="처짐")
    for key, expected in ((force_key, "N"), (deflection_key, "m")):
        unit = frame.units.get(key)
        if unit not in (None, expected):
            raise ProcessingError(f"'{key}' 는 {expected} 여야 하는데 '{unit}' 입니다.")

    notes: list[str] = []
    used = np.asarray(deflection, dtype=np.float64) - float(deflection[0])
    if compliance > 0:
        used = used - compliance * np.asarray(force, dtype=np.float64)
        notes.append(f"장비 컴플라이언스 {compliance:.4g} m/N 로 장비 처짐(C·F)을 뺐습니다.")
    elif deflection_key == DISPLACEMENT:
        notes.append(
            "처짐을 크로스헤드 변위로 냈습니다 — 장비 자신의 처짐이 섞여 E 가 작게 나올 수 "
            "있습니다. 짧고 단단한 시편이면 장비 컴플라이언스를 주세요."
        )

    point = str(options.get("deflection_point") or "auto")
    if point == "auto":
        # 4점에서 크로스헤드는 하중점(누르는 노즈)의 처짐이다. 처짐계는 대개 가운데를 잰다.
        point = "load_point" if four_point and deflection_key == DISPLACEMENT else "midspan"

    stress = 3.0 * np.asarray(force, dtype=np.float64) * arm / (width * thickness**2)
    strain = thickness * used * strain_factor(support, arm, point)

    if bool(options.get("large_deflection")):
        if four_point:
            notes.append("큰 처짐 보정은 3점(D790) 식만 있어 4점에는 적용하지 않았습니다.")
        else:
            ratio = used / support
            stress = stress * (1.0 + 6.0 * ratio**2 - 4.0 * (thickness / support) * ratio)
            notes.append("ASTM D790 의 큰 처짐 보정을 응력에 적용했습니다.")

    span_ratio = support / thickness
    if span_ratio < SHEAR_RATIO:
        notes.append(
            f"스팬/두께가 {span_ratio:.1f} 로 {SHEAR_RATIO:.0f} 보다 작습니다 — "
            "전단 처짐이 커져 "
            "굽힘 탄성률이 실제보다 작게 나올 수 있습니다(보정하지 않았습니다)."
        )
    layout = (
        f"4점(지지 {support * 1e3:.4g} mm · 하중 {load_span * 1e3:.4g} mm)"
        if four_point and load_span
        else f"3점(지지 {support * 1e3:.4g} mm)"
    )
    where = {"midspan": "스팬 가운데", "load_point": "하중점"}[point]
    notes.insert(
        0,
        f"{layout}, 폭 {width * 1e3:.4g} mm · 두께 {thickness * 1e3:.4g} mm, 처짐은 "
        f"'{deflection_key}'({where})로 굽힘 응력 · 변형률을 냈습니다.",
    )
    return StepResult(
        frame.with_columns(
            {STRAIN: strain, STRESS: stress, USED: used},
            {STRAIN: "1", STRESS: "Pa", USED: "m"},
        ),
        notes=tuple(notes),
        scalars=(
            Scalar(
                key="span_to_depth_ratio",
                label="스팬/두께",
                value=float(span_ratio),
                si_unit="1",
                dimension="dimensionless",
            ),
            # **잰 배치를 결과에 남긴다**(2026-10-20) — 하중/처짐 기울기(강성)는 이
            # 배치에서만 뜻이 있다. 묶음이 구조 강성 블록을 만들 때 시편마다 같은 배치였는지
            # 이것으로 본다.
            *(
                Scalar(
                    key=key, label=label, value=float(value), si_unit="m", dimension="length"
                )
                for key, label, value in (
                    ("support_span", "지지 스팬", support),
                    ("load_span", "하중 스팬", load_span or 0.0),
                    ("beam_width", "시편 폭", width),
                    ("beam_thickness", "시편 두께", thickness),
                )
            ),
        ),
    )


def modulus(frame: Frame, options: dict[str, Any]) -> StepResult:
    """굽힘 탄성률(등가 E) — 고른 방법 · 구간. 못 내면 실패하지 않고 까닭을 남긴다."""
    strain = frame.require(str(options.get("strain") or STRAIN), what="굽힘 변형률")
    stress = frame.require(str(options.get("stress") or STRESS), what="굽힘 응력")
    method = str(options.get("method") or "chord")
    try:
        found = slopes.measure(
            strain,
            stress,
            method=method,
            low=float(options.get("minimum_strain", 0.0005)),
            high=float(options.get("maximum_strain", 0.0025)),
            band_low=float(options.get("band_low", 0.1)),
            band_high=float(options.get("band_high", 0.4)),
            tangent_width=float(options.get("tangent_width", 0.001)),
        )
    except slopes.SlopeError as exc:
        return StepResult(frame, notes=(f"굽힘 탄성률을 내지 않았습니다 — {exc}",))
    if found.value <= 0:
        return StepResult(frame, notes=("기울기가 0 이하라 굽힘 탄성률을 내지 않았습니다.",))

    scalars = [
        Scalar(
            key="flexural_modulus",
            label="굽힘 탄성률(등가 E)",
            value=found.value,
            si_unit="Pa",
            dimension="stress",
        )
    ]
    if found.r2 is not None:
        scalars.append(
            Scalar(
                key="flexural_modulus_r2",
                label="굽힘 탄성률 회귀 R²",
                value=found.r2,
                si_unit="1",
                dimension="dimensionless",
            )
        )
    # 하중-처짐 기울기(강성) — 같은 구간에서. 등가 E 를 다른 단면으로 옮길 때 쓴다.
    start, end = found.indices
    if FORCE in frame.columns and USED in frame.columns and end - start >= slopes.MIN_POINTS:
        stiffness = float(
            np.polyfit(frame.columns[USED][start:end], frame.columns[FORCE][start:end], 1)[0]
        )
        if stiffness > 0:
            scalars.append(
                Scalar(
                    key="flexural_stiffness",
                    label="굽힘 강성(하중/처짐)",
                    value=stiffness,
                    si_unit="N/m",
                )
            )
    labels = {
        "chord": "현",
        "regression": "회귀",
        "secant": "할선",
        "tangent": "접선(가장 가파른 처음 직선)",
        "stress_window": "응력 띠",
    }
    return StepResult(
        frame,
        notes=(
            f"{labels[method]} 방법, 변형률 {found.low:.4g} ~ {found.high:.4g}"
            f"(점 {found.points}개)에서 굽힘 탄성률 {found.value / 1e9:.4g} GPa.",
        ),
        scalars=tuple(scalars),
    )


def strength(frame: Frame, options: dict[str, Any]) -> StepResult:
    """굽힘 강도 · 그때의 변형률 · 파단 · ISO 178 규정 처짐 응력(σ_fC)."""
    strain = np.asarray(
        frame.require(str(options.get("strain") or STRAIN), what="굽힘 변형률")
    )
    stress = np.asarray(frame.require(str(options.get("stress") or STRESS), what="굽힘 응력"))
    if len(stress) == 0:
        raise ProcessingError("굽힘 응력 열이 비었습니다.")
    peak = int(np.argmax(stress))
    scalars = [
        Scalar(
            key="flexural_strength",
            label="굽힘 강도",
            value=float(stress[peak]),
            si_unit="Pa",
            dimension="stress",
        ),
        Scalar(
            key="flexural_strain_at_strength",
            label="굽힘 강도에서의 변형률",
            value=float(strain[peak]),
            si_unit="1",
            dimension="strain",
        ),
        Scalar(
            key="flexural_stress_at_break",
            label="파단 굽힘 응력(마지막 점)",
            value=float(stress[-1]),
            si_unit="Pa",
            dimension="stress",
        ),
        Scalar(
            key="flexural_strain_at_break",
            label="파단 굽힘 변형률(마지막 점)",
            value=float(strain[-1]),
            si_unit="1",
            dimension="strain",
        ),
    ]
    notes = [f"최대 굽힘 응력 {stress[peak] / 1e6:.4g} MPa(변형률 {strain[peak]:.4g})."]
    rising = slice(0, peak + 1)
    if float(np.max(strain[rising])) >= CONVENTIONAL_STRAIN:
        conventional = float(np.interp(CONVENTIONAL_STRAIN, strain[rising], stress[rising]))
        scalars.append(
            Scalar(
                key="flexural_stress_at_3_5pct",
                label="규정 처짐 응력 σfC(변형률 3.5%)",
                value=conventional,
                si_unit="Pa",
                dimension="stress",
            )
        )
        notes.append("ISO 178 규정 처짐(1.5·h, 변형률 3.5%)의 응력 σfC 도 냈습니다.")
    return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))


# ── 묶음 · 카드 ───────────────────────────────────────────────────────────


def equivalent_modulus(members: list[Member]) -> GroupOutcome:
    """시편 여럿의 굽힘 탄성률 → 등가 E(평균) · 흩어짐 · 굽힘 강도."""
    moduli = [
        (one.label, float(one.values["flexural_modulus"]))
        for one in members
        if isinstance(one.values.get("flexural_modulus"), int | float)
        and float(one.values["flexural_modulus"]) > 0
    ]
    if len(moduli) < 2:
        raise GroupError(
            f"굽힘 탄성률이 있는 시편이 {len(moduli)}개입니다 — 둘 이상이어야 묶습니다. "
            "처리에 「굽힘 탄성률」 단계가 있는지 보세요."
        )
    values = np.array([value for _, value in moduli])
    mean = float(np.mean(values))
    sd = float(np.std(values, ddof=1))
    out: dict[str, float] = {
        "flexural_modulus": mean,
        "flexural_modulus_sd": sd,
        "flexural_modulus_cv": sd / mean if mean > 0 else 0.0,
        "flexural_modulus_min": float(np.min(values)),
        "flexural_modulus_max": float(np.max(values)),
        "sample_count": float(len(moduli)),
    }
    strengths = [
        float(one.values["flexural_strength"])
        for one in members
        if isinstance(one.values.get("flexural_strength"), int | float)
    ]
    if strengths:
        out["flexural_strength"] = float(np.mean(strengths))
    warnings: list[str] = []
    out.update(_stiffness(members, warnings))
    if out["flexural_modulus_cv"] > 0.1:
        warnings.append(
            f"굽힘 탄성률의 변동계수가 {out['flexural_modulus_cv']:.0%} 입니다 — 시편 치수 · "
            "스팬 · 처짐 측정을 다시 보세요."
        )
    return GroupOutcome(
        values=out,
        detail={
            "members": [{"label": label, "flexural_modulus": value} for label, value in moduli]
        },
        warnings=warnings,
        used=[label for label, _ in moduli],
    )


#: 구조 강성을 평균해도 되는 배치 차이 — 스팬 · 폭 · 두께가 이보다 다르면 강성이 다른 부품이다.
SAME_LAYOUT = 0.01
#: 배치 칸 — `engineering` 이 결과에 남기는 이름.
LAYOUT = ("support_span", "load_span", "beam_width", "beam_thickness")


def _stiffness(members: Sequence[Member], warnings: list[str]) -> dict[str, float]:
    """시편마다의 하중/처짐 기울기(`flexural_stiffness`) → **같은 배치일 때만**
    평균(2026-10-20).

    강성은 재료가 아니라 **그 부품 · 그 배치**의 값이다 — 스팬이 두 배면 3점 강성은 1/8 이
    된다.
    배치가 다르면 평균하지 않고 말한다(등가 E 는 배치를 걷어 낸 값이라 그대로 평균한다).
    """
    rows = [
        one
        for one in members
        if isinstance(one.values.get("flexural_stiffness"), int | float)
        and float(one.values["flexural_stiffness"]) > 0
    ]
    if not rows:
        return {}
    layout: dict[str, float] = {}
    for key in LAYOUT:
        found = [
            float(one.values[key])
            for one in rows
            if isinstance(one.values.get(key), int | float)
        ]
        if len(found) != len(rows):
            warnings.append(
                "배치(스팬 · 폭 · 두께)를 모르는 결과가 있어 구조 강성을 내지 않았습니다 — "
                "굽힘 응력-변형률 단계를 다시 돌린 결과를 채택하세요."
            )
            return {}
        top, bottom = max(found), min(found)
        if top > 0 and (top - bottom) / top > SAME_LAYOUT:
            warnings.append(
                f"시편마다 배치가 다릅니다({key} {bottom:.4g} ~ {top:.4g} m) — 강성은 "
                "배치마다 다른 값이라 구조 강성을 평균하지 않았습니다. 같은 배치끼리 묶으세요."
            )
            return {}
        layout[key] = float(np.mean(found))
    stiffness = np.array([float(one.values["flexural_stiffness"]) for one in rows])
    mean = float(np.mean(stiffness))
    spread = float(np.std(stiffness, ddof=1)) if len(stiffness) > 1 else 0.0
    return {
        "flexural_stiffness": mean,
        "flexural_stiffness_cv": spread / mean if mean > 0 else 0.0,
        # 강성이 있는 시편만 센다 — 묶음의 `sample_count` 는 굽힘 탄성률이 있는 시편 수라,
        # 다섯 중 둘만 평균해도 블록이 「5」 라고 적었다(2026-10-20 검토).
        "flexural_stiffness_count": float(len(rows)),
        **layout,
    }


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 → **탄성 블록의 E(등가)** + 참고 물성(굽힘 탄성률 · 강도).

    굽힘 탄성률은 대개 덱의 E 로 쓰지 않는다(참고 물성의 말 그대로). 이 카드는 **일부러**
    그렇게 쓰는 길이다 — 칩 · 모듈처럼 인장 시편을 못 만드는 것의 등가 E. 그래서 근거에 그
    사실을 적는다. 푸아송비 · 밀도는 중심이 물려받는다(이 블록은 E 칸만 이긴다).
    """
    modulus_value = values.get("flexural_modulus")
    if not isinstance(modulus_value, int | float) or modulus_value <= 0:
        raise ValueError("이 묶음에 굽힘 탄성률이 없습니다.")
    reference = {"flexural_modulus": float(modulus_value)}
    if isinstance(values.get("flexural_strength"), int | float):
        reference["flexural_strength"] = float(values["flexural_strength"])
    note = (
        f"탄성계수는 굽힘 시험 {int(values.get('sample_count', 0))}개의 등가 E(평균)입니다 — "
        "직사각형 단면을 균질한 보로 본 값이라 인장 탄성계수와 다를 수 있습니다"
        "(적층 · 이방성)."
    )
    blocks: dict[str, dict[str, Any]] = {
        "elastic": {
            "values": {"youngs_modulus": float(modulus_value)},
            "notes": [note, *warnings],
        },
        "reference": {"values": reference},
    }
    stiffness = values.get("flexural_stiffness")
    if isinstance(stiffness, int | float) and stiffness > 0:
        # **부품의 강성을 그 배치와 함께 싣는다**(2026-10-20) — 칩 · 모듈처럼 균질한 보가 아닌
        # 것은 등가 E 보다 잰 강성이 정직하다. 배치가 없으면 그 숫자는 아무 데도 못 옮긴다.
        load_span = float(values.get("load_span", 0.0))
        blocks["structural_stiffness"] = {
            "values": {
                "stiffness": float(stiffness),
                "stiffness_cv": float(values.get("flexural_stiffness_cv", 0.0)),
                "support_span": float(values.get("support_span", 0.0)),
                "load_span": load_span,
                "width": float(values.get("beam_width", 0.0)),
                "thickness": float(values.get("beam_thickness", 0.0)),
                "sample_count": float(
                    values.get("flexural_stiffness_count", values.get("sample_count", 0.0))
                ),
                "loading": "4점 굽힘" if load_span > 0 else "3점 굽힘",
            },
            "notes": [
                "하중/처짐 기울기 — 이 배치(스팬 · 폭 · 두께)에서만 그 값입니다. 다른 "
                "스팬으로 옮기려면 보 식(3점: k = 48EI/L³)으로 바꾸세요."
            ],
        }
    return blocks
