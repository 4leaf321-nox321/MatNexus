"""이미 읽어 둔 곡선에 **값 지문**을 채운다 — 배포 후 한 번 돌리는 보정(2026-11-14, VOC 54).

`curves.fingerprint` 는 읽을 때 잰다. 그 칸이 생기기 전에 읽은 곡선은 비어 있고, 비어 있으면
중복 점검 · 통계의 「같은 지문은 하나로」 가 그 곡선을 못 본다.

**다시 읽지 않는다.** 저장된 곡선 파일(Parquet)을 열어 지문만 잰다 — 재파싱은 처리 결과와
채택을 흔들 수 있다. 읽을 때와 같은 규칙이다: 시험 종류가 정의한 채널만, 정의가 없으면 전부.

끝에 **같은 지문이 둘 이상인 묶음**을 센다 — 같은 측정이 통계에 두 번 들어갔을 수 있는 자리다.
고치지 않는다(재시험 · 반복 측정일 수 있다). 다시 읽으면 시험 점검에도 선다.

2026-11-17(VOC 54 · ADR 0091): **곡선 모양**(`curves.shape`)도 같은 자리에서 채운다 — 자릿수 ·
점 간격 · 단위 배수만 다른 사본을 알아보는 칸이다. 끝에 같은 재료 · 같은 시험 종류 안에서 거의
같은 곡선 쌍(지문은 다른 것)을 센다. 이것도 고치지 않는다.

사용:
    python scripts/backfill_curve_fingerprints.py            # 세어 보기만
    python scripts/backfill_curve_fingerprints.py --apply    # 실제로 채운다
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 이런 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.materials.models import Sample, Specimen  # noqa: E402
from app.modules.tests.models import Curve, TestChannel, TestRun  # noqa: E402
from app.shared import filestore  # noqa: E402
from app.shared.errors import AppError  # noqa: E402
from matcore import curves as curvekit  # noqa: E402

survive_cp949()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제로 채운다 (없으면 세어 보기만)"
    )
    parser.add_argument(
        "--brief", action="store_true", help="요약만(배포가 이렇게 부른다 — 묶음 목록 없이)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    filled = missing = 0
    try:
        defined: dict[object, set[str]] = defaultdict(set)
        for type_id, key in db.execute(select(TestChannel.test_type_id, TestChannel.key)):
            defined[type_id].add(key)
        rows = db.execute(
            select(Curve, TestRun.test_type_id)
            .join(TestRun, TestRun.id == Curve.test_run_id)
            .where(
                or_(Curve.fingerprint.is_(None), Curve.shape.is_(None)),
                TestRun.deleted_at.is_(None),
            )
        ).all()
        if not args.brief:
            print(f"지문 · 모양이 빈 곡선 {len(rows)}개를 봅니다.")
        for curve, type_id in rows:
            try:
                columns = curvekit.read_columns(filestore.read_bytes(curve.storage_path))
            except (AppError, OSError, ValueError):
                # **파일 하나가 전부를 세우지 않는다**(2026-11-15 전반 점검). 없는 파일은
                # `filestore` 가 `AppError` 로, 깨진 Parquet 는 `ArrowInvalid`(ValueError)로
                # 던지는데 여기는 `OSError` 만 잡았다 — 하나라도 있으면 스크립트가 통째로 죽어
                # 아무것도 커밋되지 않았고, 배포마다 같은 자리에서 죽었다.
                missing += 1
                continue
            keys = defined.get(type_id) or set()
            chosen = {
                key: values for key, values in columns.items() if not keys or key in keys
            }
            if curve.fingerprint is None:
                curve.fingerprint = curvekit.fingerprint(chosen)
            if curve.shape is None:
                curve.shape = curvekit.shape(chosen)
            filled += 1
            # 수백 건마다 적는다 — 한 번에 올리면 중간에 죽을 때 전부 잃는다.
            if args.apply and filled % 500 == 0:
                db.commit()
        if args.apply:
            db.commit()
        else:
            db.flush()

        # 같은 지문이 둘 이상인 묶음 — 같은 측정이 두 번 들어갔을 수 있다.
        groups: dict[str, list[str]] = defaultdict(list)
        for print_, name in db.execute(
            select(Curve.fingerprint, TestRun.record_name)
            .join(TestRun, TestRun.id == Curve.test_run_id)
            .where(Curve.fingerprint.is_not(None), TestRun.deleted_at.is_(None))
        ):
            groups[print_].append(name)
        doubled = {key: names for key, names in groups.items() if len(set(names)) > 1}
        near = near_pairs(db)
        if not args.apply:
            db.rollback()
    finally:
        db.close()

    verb = "채웠습니다" if args.apply else "채울 수 있습니다(--apply 로 채움)"
    print(f"{filled}개 {verb}. 곡선 파일을 못 읽은 것 {missing}개.")
    print(f"같은 지문이 여러 시험에 있는 묶음 {len(doubled)}개.")
    print(f"거의 같은 곡선 쌍(같은 재료 · 시험 종류, 지문은 다름) {len(near)}개.")
    if args.brief:
        return
    for first, second, gap in near[:10]:
        print(f"  ~ {first} · {second}(모양 차이 {gap:.2%})")
    for names in list(doubled.values())[:10]:
        unique = list(dict.fromkeys(names))
        print(
            f"  - {', '.join(unique[:4])}"
            + (f" 외 {len(unique) - 4}건" if len(unique) > 4 else "")
        )


def near_pairs(db: Session) -> list[tuple[str, str, float]]:
    """같은 재료 · 같은 시험 종류에서 거의 같은 측정 곡선 쌍 `(시험, 시험, 차이)` — 지문이 같은
    쌍 · 같은 시험의 곡선끼리는 뺀다(앞에서 센다). 시험 점검과 같은 판정(`curves.copy_gap`)."""
    groups: dict[
        tuple[object, object], list[tuple[curvekit.Shape, str, str | None, object]]
    ] = defaultdict(list)
    for stored, print_, run_id, name, material_id, type_id in db.execute(
        select(
            Curve.shape,
            Curve.fingerprint,
            TestRun.id,
            TestRun.record_name,
            Sample.material_id,
            TestRun.test_type_id,
        )
        .join(TestRun, TestRun.id == Curve.test_run_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(
            Curve.shape.is_not(None), Curve.kind == "measured", TestRun.deleted_at.is_(None)
        )
    ):
        shaped = curvekit.Shape.of(stored)
        if shaped is not None:
            groups[(material_id, type_id)].append((shaped, name, print_, run_id))
    found: list[tuple[str, str, float]] = []
    for members in groups.values():
        for index, (first, first_name, first_print, first_run) in enumerate(members):
            for second, second_name, second_print, second_run in members[index + 1 :]:
                if first_run == second_run or (first_print and first_print == second_print):
                    continue
                got = curvekit.copy_gap(first, second)
                if got is not None and got[0] < curvekit.NEAR_COPY:
                    found.append((first_name, second_name, got[0]))
    return sorted(found, key=lambda one: one[2])


if __name__ == "__main__":
    main()
