"""인장 곡선의 **최대 응력 앞 하강** 분포 — 경고 기준값을 운영 데이터로 확인한다
(읽기만, 2026-11-14).

## 왜

VOC 57: 단조 보정(`curve.monotone`)이 항복 강하 · 연화를 덮는다. 「인장강도」 단계가 정렬 직후
공칭 곡선에서 하강을 재 경고하는데, 기준값은 **잠정값**이다 —

    PRE_PEAK_DROP_WARN = 0.5 %   다시 오르지 않는 하강(인장강도 비율)
    YIELD_POINT_WARN   = 2.5 %   상 · 하항복 차이(상항복 비율), 곧 다시 오르는 요철의 경고선

개발 DB 는 대부분 데모 곡선이라(인장 215건 중 계산되는 것 46건) 기준을 정할 근거가 못 됐다. 이
스크립트는 운영 DB 에서 같은 판정을 재 재료군마다 분포와 「몇 건이 경고를 받나」 를 보인다.

## 무엇을 재나

표준 레시피 앞부분 그대로(공칭 → 파단 뒤 자르기 → 정렬)의 곡선에서, 최대 응력 앞의

- 다시 오르지 않는 하강의 폭(ReH - ReL) / ReH — `tensile._first_drop` 과 같은 판정
- 곧 다시 오르는 요철까지 포함한 최대 하강 / 인장강도

**고치지 않는다.** 처리 결과도 만들지 않는다.

사용:
    python scripts/measure_curve_drops.py            # 재료군별 분포
    python scripts/measure_curve_drops.py --list 20  # 하강이 큰 곡선 20건도
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 이런 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.materials.models import Material, Sample, Specimen  # noqa: E402
from app.modules.tests.models import TestRun, TestType  # noqa: E402
from app.shared import curvedata  # noqa: E402
from matcore import processing  # noqa: E402
from matcore.processing import Step  # noqa: E402
from matcore.processing.tensile import (  # noqa: E402
    NOISE_SIGMAS,
    PRE_PEAK_DROP_WARN,
    YIELD_POINT_WARN,
    pre_peak_drop,
)

survive_cp949()

STEPS = [
    Step(
        "tensile.engineering",
        {"gauge_length": "@specimen_gauge_length", "area": "@specimen_area"},
    ),
    Step("tensile.break_cut", {}),
    Step("curve.sort_unique", {"x": "strain_engineering", "duplicate_policy": "mean"}),
]


def measure(strain: np.ndarray, stress: np.ndarray) -> tuple[float, float | None]:
    """`(최대 하강 / 인장강도, 다시 오르지 않는 하강의 ReH 비율 또는 None)` — 경고와 같은
    판정."""
    keep = np.isfinite(strain) & np.isfinite(stress)
    strain, stress = strain[keep], stress[keep]
    found = pre_peak_drop(strain, stress, int(np.argmax(stress)))
    if found is None:
        return 0.0, None
    return found.share, found.gap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", type=int, default=0, help="하강이 큰 곡선을 이만큼 보인다")
    args = parser.parse_args()

    processing.load_builtin()
    db = SessionLocal()
    rows: list[tuple[str, str, float, float | None]] = []
    skipped = 0
    try:
        runs = db.scalars(
            select(TestRun)
            .join(TestType, TestType.id == TestRun.test_type_id)
            .where(TestType.key == "tensile", TestRun.status == "parsed")
        ).all()
        for run in runs:
            try:
                frame, _ = curvedata.load_frame(db, run, None)
                done = processing.apply(
                    STEPS, frame, given=curvedata.specimen_scalars(db, run)
                ).frame
            except Exception:  # 진단이라 다음 시험으로 — 치수 없는 시험이 흔하다
                skipped += 1
                continue
            drop, gap = measure(
                done.columns["strain_engineering"], done.columns["stress_engineering"]
            )
            specimen = db.get(Specimen, run.specimen_id)
            sample = db.get(Sample, specimen.sample_id) if specimen else None
            material = db.get(Material, sample.material_id) if sample else None
            rows.append((run.record_name, material.family if material else "?", drop, gap))
    finally:
        db.close()

    print(f"인장 곡선 {len(rows)}건을 쟀습니다(계산 못 한 시험 {skipped}건 — 치수 없음 등).")
    print(
        f"기준: 다시 오르지 않는 하강 ≥ {PRE_PEAK_DROP_WARN * 100:g} %"
        f"(잡음 σ 의 {NOISE_SIGMAS:g} 배가 더 크면 그것) · "
        f"상하항복 차이 ≥ {YIELD_POINT_WARN * 100:g} % · 요철 ≥ {YIELD_POINT_WARN * 100:g} %\n"
    )
    families = sorted({row[1] for row in rows})
    for family in families:
        mine = [row for row in rows if row[1] == family]
        drops = np.array([row[2] for row in mine])
        gaps = np.array([row[3] for row in mine if row[3] is not None])
        persistent = int(np.count_nonzero(gaps >= PRE_PEAK_DROP_WARN))
        yield_point = int(np.count_nonzero(gaps >= YIELD_POINT_WARN))
        rough = sum(1 for row in mine if row[3] is None and row[2] >= YIELD_POINT_WARN)
        print(f"■ {family}: {len(mine)}건")
        print(
            "  최대 하강/인장강도 — "
            + " · ".join(f"p{q} {np.percentile(drops, q) * 100:.2f} %" for q in (50, 90, 99))
        )
        if gaps.size:
            print(
                f"  다시 오르지 않는 하강 {gaps.size}건 — "
                + " · ".join(f"p{q} {np.percentile(gaps, q) * 100:.2f} %" for q in (50, 90))
            )
        print(
            f"  경고를 받을 곡선: 지속 하강 {persistent}건(그중 항복점 현상 {yield_point}건) "
            f"· 큰 요철 {rough}건"
        )
    if args.list:
        print("\n하강이 큰 곡선:")
        for name, family, drop, gap in sorted(rows, key=lambda row: -row[2])[: args.list]:
            shown = f"{gap * 100:.2f} %" if gap is not None else "없음(곧 다시 오름)"
            print(f"  {name} ({family}): 최대 하강 {drop * 100:.2f} % · 지속 하강 {shown}")


if __name__ == "__main__":
    main()
