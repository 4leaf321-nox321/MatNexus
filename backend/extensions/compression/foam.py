"""폼 — 시편 여럿의 **공칭 압축 응력-변형률**을 한 표로, 그 표를 폼 카드로(2026-10-20).

사용자 보고: 압축 시험을 처리할 단계는 생겼는데, 폼 소재를 해석 카드로 내보낼 경로가 없었다
— 「폼 카드 공칭응력-변형률 표 블록 대응 필요」.

    묶음   foam_curve(members)   시편마다 곡선을 공통 구간(가장 짧은 시편의 끝까지)에 보간해
                                 평균. 압축이 양수인 공칭 축 그대로다.
    카드   card_blocks           `foam_curve` 블록(표) + 탄성 블록의 E(평균 곡선의 처음 기울기)

**공칭이다 — 진응력으로 바꾸지 않는다.** 저밀도 폼 재료(LS-DYNA *MAT_LOW_DENSITY_FOAM 등)는
공칭 응력 대 공칭 변형률 곡선을 그대로 받는다. 폼은 눌려도 옆으로 거의 안 퍼져(푸아송비가 0
가까이) 진응력 환산의 가정(체적 보존)이 맞지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from matcore.groups import GroupError, GroupOutcome, Member

from . import compress

#: 평균을 내는 촘촘한 격자. 표는 이것을 다시 솎아 싣는다.
DENSE = 201
#: 카드 표의 점 수 — 덱의 *DEFINE_CURVE 한 벌. 치밀화에서 가팔라지는 끝을 따라갈 만큼.
TABLE_POINTS = 41
#: 한 시편에 이보다 점이 적으면 곡선이 아니다.
MIN_POINTS = 5
#: 처음 기울기(E)를 잴 구간 — 공통 구간 끝의 이 비율까지, 그리고 2 % 를 넘지 않는다.
MODULUS_SHARE = 0.1
MODULUS_CAP = 0.02


def _curve(member: Member) -> tuple[np.ndarray, np.ndarray]:
    """한 시편의 곡선 — 압축(양수) 구간만, 변형률 오름차순, 겹친 점은 하나로."""
    strain = np.asarray(member.columns.get(compress.STRAIN, ()), dtype=np.float64)
    stress = np.asarray(member.columns.get(compress.STRESS, ()), dtype=np.float64)
    keep = np.isfinite(strain) & np.isfinite(stress) & (strain >= 0)
    strain, stress = strain[keep], stress[keep]
    order = np.argsort(strain, kind="stable")
    strain, stress = strain[order], stress[order]
    strain, first = np.unique(strain, return_index=True)
    return strain, stress[first]


def foam_curve(members: list[Member]) -> GroupOutcome:
    """시편 여럿의 압축 곡선 → **공통 구간의 평균 곡선**(공칭, 압축이 양수).

    가장 짧은 시편의 끝에서 자른다 — 더 가는 시편만으로 끝을 이으면 평균이 아니라 그
    시편의 곡선이 끝을 정한다. 잘랐다는 사실은 경고로 남긴다.
    """
    curves: list[tuple[str, np.ndarray, np.ndarray]] = []
    for one in members:
        strain, stress = _curve(one)
        if len(strain) < MIN_POINTS:
            raise GroupError(
                f"'{one.label}' 의 압축 곡선 점이 {len(strain)}개입니다 — 처리에 「압축 응력-"
                "변형률」 단계가 있는지 보세요."
            )
        curves.append((one.label, strain, stress))
    if not curves:
        raise GroupError("묶을 압축 곡선이 없습니다.")

    end = float(min(strain[-1] for _, strain, _ in curves))
    if end <= 0:
        raise GroupError("공통 압축 구간이 없습니다 — 시편 곡선이 0 에서 안 나아갑니다.")
    grid = np.linspace(0.0, end, DENSE)
    stacked = np.vstack([np.interp(grid, strain, stress) for _, strain, stress in curves])
    mean = stacked.mean(axis=0)
    mean[0] = 0.0  # 원점에서 시작한다 — 접촉점(변형 0)에서 응력 0.

    warnings: list[str] = []
    longer = [label for label, strain, _ in curves if strain[-1] > end * 1.02]
    if longer:
        warnings.append(
            f"가장 짧은 시편의 끝(변형률 {end:.3g})에서 잘랐습니다 — 더 간 시편: "
            f"{', '.join(longer)}."
        )
    if len(curves) == 1:
        warnings.append("시편 1개의 곡선입니다 — 평균이 아니라 그 시편의 곡선입니다.")
    if np.any(np.diff(mean) < -1e-9 * max(float(np.max(np.abs(mean))), 1.0)):
        warnings.append(
            "평균 곡선에 응력이 내려가는 구간이 있습니다(항복 봉우리) — 경질 폼이면 저밀도 폼 "
            "재료가 아니라 파쇄형 폼(crushable foam) 재료가 맞습니다."
        )

    top = min(MODULUS_SHARE * end, MODULUS_CAP)
    window = grid <= max(top, grid[3])
    x, y = grid[window], mean[window]
    modulus = float(np.dot(x, y) / np.dot(x, x)) if np.dot(x, x) > 0 else 0.0

    table = np.linspace(0.0, end, TABLE_POINTS)
    rows = np.interp(table, grid, mean)
    return GroupOutcome(
        values={
            "sample_count": float(len(curves)),
            "strain_max": end,
            "stress_at_max": float(mean[-1]),
            "initial_modulus": modulus,
        },
        columns={compress.STRAIN: table, compress.STRESS: rows},
        detail={
            "table": [[float(s), float(p)] for s, p in zip(table, rows, strict=True)],
            "modulus_window": float(x[-1]),
        },
        warnings=warnings,
        used=[label for label, _, _ in curves],
    )


def card_blocks(
    values: Mapping[str, float], detail: Mapping[str, Any], warnings: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """묶음 → `foam_curve` 블록(표) + **탄성 블록의 E**(평균 곡선의 처음 기울기).

    E 는 폼 재료가 인장 쪽에 쓰는 탄성계수다(압축은 표가 정한다). 밀도 · 푸아송비는 중심이
    물려받는다 — 이 블록은 E 칸만 이긴다.
    """
    table = detail.get("table") or []
    if len(table) < MIN_POINTS:
        raise ValueError("이 묶음에 폼 곡선 표가 없습니다.")
    modulus = float(values.get("initial_modulus") or 0.0)
    note = (
        f"공칭 압축 응력-변형률 — 시편 {int(values.get('sample_count', 0))}개 곡선을 변형률 "
        f"{float(values.get('strain_max', 0.0)):.3g} 까지 평균했습니다(압축이 양수)."
    )
    blocks: dict[str, dict[str, Any]] = {
        "foam_curve": {
            "values": {
                "source": "compression_mean",
                "sample_count": float(values.get("sample_count", 0)),
                "strain_max": float(values.get("strain_max", 0.0)),
            },
            "rows": [{"strain": float(s), "stress": float(p)} for s, p in table],
            "notes": [note, *warnings],
        }
    }
    if modulus > 0:
        blocks["elastic"] = {
            "values": {"youngs_modulus": modulus},
            "notes": [
                f"탄성계수는 평균 곡선의 처음 기울기입니다(변형률 "
                f"{float(detail.get('modulus_window', 0.0)):.3g} 까지, 원점을 지나는 직선)."
            ],
        }
    return blocks
