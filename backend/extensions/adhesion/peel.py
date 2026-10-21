"""박리 · 이탈력 — 하중-변위 곡선에서 최대 하중 · 안정 구간 평균 박리력 · 박리 강도 · 파단
에너지(2026-10-20).

테이프 박리(ASTM D3330 · ISO 8510), 배터리 PTT(당김 시험), SIM 트레이 삽입 · 인출이 같은 모양의
곡선이다 — 하중이 오르고, 떨어지는 동안(박리)이나 끝(이탈)에 값이 있다.

    최대 하중          곡선 전체의 최대 — 이탈 · 삽입력은 이것이 보고값이다.
    안정 구간 평균      변위의 `window_start` ~ `window_end` 비율 구간의 평균 하중 —
                       박리의 보고값. 처음(당겨 세우는 구간)과 끝(떨어지는 구간)을 뺀다.
    박리 강도           안정 구간 평균 ÷ 시편 폭(N/m). 폭이 없으면 안 낸다.
    파단 에너지         곡선 아래 넓이 ∫F dx(J) — 떼어 내는 데 든 일.
    접착 에너지         박리 강도 · (1 - cos θ)(J/m²). 박리 각도를 알 때만 — 90° 면 박리 강도,
                       180° 면 그 두 배. 팔이 늘어나지 않는다(탄성 팔)는 가정이다.

DB 도 HTTP 도 모른다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member
from matcore.processing import Frame, ProcessingError, Scalar, StepResult

FORCE = "force"
DISPLACEMENT = "displacement"

#: 안정 구간 — 변위 폭의 비율(기본). 처음 25 % 와 끝 25 % 를 뺀다.
WINDOW_START = 0.25
WINDOW_END = 0.75
#: 안정 구간에 이보다 점이 적으면 평균이 아니다.
MIN_WINDOW_POINTS = 5


def _float(options: dict[str, Any], key: str) -> float | None:
    raw = options.get(key)
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def peel(frame: Frame, options: dict[str, Any]) -> StepResult:
    """하중-변위 → 최대 하중 · 안정 구간 평균 · 박리 강도 · 파단 에너지 · 접착 에너지."""
    force = np.asarray(frame.require(str(options.get("force") or FORCE), what="하중"))
    displacement = np.asarray(
        frame.require(str(options.get("displacement") or DISPLACEMENT), what="변위")
    )
    keep = np.isfinite(force) & np.isfinite(displacement)
    force, displacement = force[keep], displacement[keep]
    if force.size < MIN_WINDOW_POINTS:
        raise ProcessingError(f"점이 {force.size}개뿐입니다 — 하중-변위 곡선이 아닙니다.")
    # **누르는 쪽을 음수로 적는 장비가 있다**(SIM 트레이 삽입 등, 2026-10-20 검토) —
    # 그대로 두면 최대 하중이 0 근처로, 박리 강도가 음수로 오류 없이 나왔다. 압축
    # 단계와 같은 판단이다.
    flipped: list[str] = []
    if abs(float(np.min(force))) > abs(float(np.max(force))):
        force = -force
        flipped.append("하중")
    if displacement[-1] < displacement[0]:
        displacement = -displacement
        flipped.append("변위")
    travel = displacement - displacement[0]
    span = float(np.max(travel))
    if span <= 0:
        raise ProcessingError("변위가 나아가지 않습니다 — 변위 열을 확인하세요.")

    start = _float(options, "window_start")
    end = _float(options, "window_end")
    start = WINDOW_START if start is None else start
    end = WINDOW_END if end is None else end
    if not 0 <= start < end <= 1:
        raise ProcessingError(f"안정 구간은 0 ≤ 시작 < 끝 ≤ 1 이어야 합니다: {start} ~ {end}")

    top = int(np.argmax(force))
    window = (travel >= start * span) & (travel <= end * span)
    count = int(np.sum(window))
    notes = [f"최대 하중 {float(force[top]):.4g} N (변위 {float(travel[top]) * 1e3:.4g} mm)."]
    if flipped:
        notes.insert(
            0, f"{' · '.join(flipped)}의 부호를 뒤집었습니다 — 장비가 음수로 적었습니다."
        )
    scalars = [
        Scalar(key="max_force", label="최대 하중", value=float(force[top]), si_unit="N"),
        Scalar(
            key="max_force_displacement",
            label="최대 하중의 변위",
            value=float(travel[top]),
            si_unit="m",
        ),
    ]
    # 파단 에너지 — 당기는 쪽(양의 하중)만. 되돌아오는 구간이 있으면 그만큼 빠진다.
    pulled = np.clip(force, 0.0, None)
    energy = float(np.sum((pulled[1:] + pulled[:-1]) / 2.0 * np.diff(travel)))
    scalars.append(
        Scalar(
            key="fracture_energy",
            label="파단 에너지(곡선 아래 넓이)",
            value=energy,
            si_unit="J",
        )
    )

    if count < MIN_WINDOW_POINTS:
        notes.append(
            f"안정 구간(변위 {start:.0%} ~ {end:.0%})에 점이 {count}개뿐이라 "
            "평균 박리력을 내지 않았습니다."
        )
        return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))

    plateau = float(np.mean(force[window]))
    spread = float(np.std(force[window], ddof=1)) if count > 1 else 0.0
    scalars.extend(
        [
            Scalar(
                key="plateau_force", label="안정 구간 평균 하중", value=plateau, si_unit="N"
            ),
            Scalar(
                key="plateau_force_cv",
                label="안정 구간 변동계수",
                value=spread / plateau if plateau > 0 else 0.0,
                si_unit="1",
            ),
        ]
    )
    notes.append(
        f"안정 구간(변위 {start:.0%} ~ {end:.0%}, {count}점) 평균 {plateau:.4g} N — "
        "처음(세우는 구간)과 끝(떨어지는 구간)을 뺐습니다."
    )

    width = _float(options, "width")
    if width is None or width <= 0:
        notes.append("시편 폭이 없어 박리 강도(N/m)를 내지 않았습니다.")
        return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))
    strength = plateau / width
    scalars.append(
        Scalar(key="peel_strength", label="박리 강도", value=strength, si_unit="N/m")
    )

    angle = _float(options, "peel_angle")
    if angle is not None and angle > np.pi + 1e-9:
        # **라디안이다.** 화면은 도로 받아 옮기지만, API · MCP 로 90 을 넣으면 1 - cos(90 rad)
        # = 1.45 가 오류 없이 나왔다(정답 1.0, 2026-10-20 검토).
        raise ProcessingError(
            f"박리 각도 {angle:g} 은 라디안으로 0 ~ π 를 넘습니다 — 도(°)로 적었다면 "
            f"{np.radians(angle):.4g} rad 입니다."
        )
    if angle is None or angle <= 0:
        notes.append("박리 각도가 없어 접착 에너지(J/m²)를 내지 않았습니다.")
    else:
        scalars.append(
            Scalar(
                key="adhesion_energy",
                label="접착 에너지",
                value=strength * (1.0 - float(np.cos(angle))),
                si_unit="J/m2",
            )
        )
        notes.append(
            f"접착 에너지 = 박리 강도 · (1 - cos {np.degrees(angle):.4g}°) — 팔이 늘어나지 "
            "않는다는 가정입니다."
        )
    return StepResult(frame, notes=tuple(notes), scalars=tuple(scalars))


# ── 묶음 · 카드 ──────────────────────────────────────────────────────────────

#: 묶음이 평균하는 값 — 처리 결과(또는 표로 적은 요약값)의 이름.
SUMMARY_KEYS = (
    "max_force",
    "plateau_force",
    "peel_strength",
    "fracture_energy",
    "adhesion_energy",
)


def summary(members: list[Member]) -> GroupOutcome:
    """시편 여럿 → 값마다 평균 · 표준편차 · 변동계수 · 시편 수."""
    out: dict[str, float] = {}
    used: set[str] = set()
    for key in SUMMARY_KEYS:
        found = [
            (one.label, float(one.values[key]))
            for one in members
            if isinstance(one.values.get(key), int | float)
        ]
        if not found:
            continue
        values = np.array([value for _, value in found])
        mean = float(np.mean(values))
        out[key] = mean
        out[f"{key}_cv"] = (
            float(np.std(values, ddof=1)) / mean if len(values) > 1 and mean else 0.0
        )
        used.update(label for label, _ in found)
    if not out:
        raise GroupError(
            "묶을 값이 없습니다 — 처리에 「박리 · 이탈력」 단계가 있는지, 표로 적었다면 "
            f"열 이름이 {', '.join(SUMMARY_KEYS)} 중 하나인지 보세요."
        )
    out["sample_count"] = float(len(used))
    warnings = []
    if len(used) == 1:
        warnings.append("시편 1개의 값입니다 — 평균이 아니라 그 시편의 값입니다.")
    return GroupOutcome(values=out, warnings=warnings, used=sorted(used))


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 → 응집 영역 블록(파괴 에너지) + 참고 물성(박리 강도).

    **최대 견인력은 박리 시험이 주지 않는다** — 팔의 굽힘과 섞여 곡선에서 바로 읽히지
    않는다. 칸은 두고, 재료에 적어 둔 값(`interface.cohesive_strength`)이 채운다.
    """
    blocks: dict[str, dict[str, Any]] = {}
    energy = values.get("adhesion_energy")
    if isinstance(energy, int | float) and energy > 0:
        blocks["cohesive_zone"] = {
            "values": {
                "fracture_energy": float(energy),
                "mode": "모드 I (박리)",
                "sample_count": float(values.get("sample_count", 0.0)),
            },
            "notes": [
                "파괴 에너지 = 박리 강도 · (1 - cos θ) — 팔이 늘어나지 않는다는 "
                "가정입니다. 최대 견인력은 박리 시험이 주지 않습니다(재료에 적어 두면 "
                "채워집니다).",
                *warnings,
            ],
        }
    strength = values.get("peel_strength")
    if isinstance(strength, int | float) and strength > 0:
        blocks["reference"] = {"values": {"peel_strength": float(strength)}}
    if not blocks:
        raise ValueError(
            "카드에 실을 값이 없습니다 — 박리 강도(시편 폭)와 접착 에너지(박리 각도)가 "
            "필요합니다."
        )
    return blocks
