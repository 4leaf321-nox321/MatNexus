"""옛 시험에 **파일이 준 시편 치수**를 채운다 — 배포 후 한 번 돌리는 보정(2026-11-14, VOC 56).

## 무엇이 있었나

`test_runs.dimensions`(그 시험이 잰 치수)는 읽을 때 파일 헤더에서 채운다. 그 칸이 생기기 전에
읽은 시험은 비어 있고, 처리는 그때 **시편 실측 · 규격 공칭**으로 응력을 냈다 — 파일 헤더에
실측 폭 · 두께(`b0` · `a0`)가 있는데도. 개발 DB 에서 인장 215건 중 152건이 그랬다. 단면 모양을
안 고른 규격의 시편(8건)은 그 칸이 아예 없어 새로 읽어도 버려졌다(v1.312.0 에서 고쳤다).

## 무엇을 하나

**다시 읽지 않는다.** 저장해 둔 파일 헤더(`source_metadata`)에서 치수만 읽어 빈 칸에 넣는다 —
재파싱은 곡선 · 처리 결과 · 채택을 흔들 수 있다. 이미 치수가 있는 시험은 건드리지 않는다.

**단면적이 얼마나 바뀌는지 함께 보인다.** 채택된 결과는 옛 단면적으로 낸 응력을 들고
있다(결과는 불변이다). 바뀐 시험은 `scripts/reprocess_adopted.py` 로 다시 처리한다 — 그
스크립트도 먼저 무엇이 바뀌는지만 보여 준다.

사용:
    python scripts/backfill_run_dimensions.py            # 세어 보기만
    python scripts/backfill_run_dimensions.py --apply    # 실제로 채운다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 이런 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.materials.models import Specimen  # noqa: E402
from app.modules.tests.models import TestRun  # noqa: E402
from app.shared import curvedata, specimen_size  # noqa: E402

survive_cp949()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제로 채운다 (없으면 세어 보기만)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    filled = changed_area = 0
    try:
        runs = list(db.scalars(select(TestRun).where(TestRun.source_metadata.is_not(None))))
        for run in runs:
            if run.dimensions:
                continue
            specimen = db.get(Specimen, run.specimen_id) if run.specimen_id else None
            if specimen is None:
                continue
            fields = specimen_size.dimension_fields(db, specimen)
            found = curvedata.instrument_dimensions(run.source_metadata or {}, fields)
            if not found:
                continue
            filled += 1
            before = specimen_size.area_of(db, specimen, {})
            after = specimen_size.area_of(db, specimen, found)
            sizes = ", ".join(
                f"{specimen_size.LEGACY_LABELS.get(key, key)} {value * 1000:.4g} mm"
                for key, value in found.items()
            )
            line = f"- {run.record_name}: {sizes}"
            if before and after and abs(after - before) > 1e-9 * before:
                changed_area += 1
                line += f" — 단면적 {before * 1e6:.4g} → {after * 1e6:.4g} mm²"
                line += f"({(after / before - 1) * 100:+.2f} %)"
                if run.adopted_result_id:
                    line += " · 채택된 결과 있음(다시 처리 대상)"
            print(line)
            if args.apply:
                run.dimensions = found
        if args.apply:
            db.commit()
    finally:
        db.close()
    verb = "채웠습니다" if args.apply else "채울 수 있습니다(--apply 로 채움)"
    print(f"\n{filled}건 {verb}. 그중 단면적이 바뀌는 시험 {changed_area}건.")
    if changed_area:
        print(
            "채택된 결과는 옛 단면적으로 낸 값입니다 — "
            "scripts/reprocess_adopted.py 로 다시 처리하세요."
        )


if __name__ == "__main__":
    main()
