"""이미 읽어 둔 곡선에 **값 지문**을 채운다 — 배포 후 한 번 돌리는 보정(2026-11-14, VOC 54).

`curves.fingerprint` 는 읽을 때 잰다. 그 칸이 생기기 전에 읽은 곡선은 비어 있고, 비어 있으면
중복 점검 · 통계의 「같은 지문은 하나로」 가 그 곡선을 못 본다.

**다시 읽지 않는다.** 저장된 곡선 파일(Parquet)을 열어 지문만 잰다 — 재파싱은 처리 결과와
채택을 흔들 수 있다. 읽을 때와 같은 규칙이다: 시험 종류가 정의한 채널만, 정의가 없으면 전부.

끝에 **같은 지문이 둘 이상인 묶음**을 센다 — 같은 측정이 통계에 두 번 들어갔을 수 있는 자리다.
고치지 않는다(재시험 · 반복 측정일 수 있다). 다시 읽으면 시험 점검에도 선다.

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

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 이런 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.tests.models import Curve, TestChannel, TestRun  # noqa: E402
from app.shared import filestore  # noqa: E402
from matcore import curves as curvekit  # noqa: E402

survive_cp949()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제로 채운다 (없으면 세어 보기만)"
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
            .where(Curve.fingerprint.is_(None), TestRun.deleted_at.is_(None))
        ).all()
        print(f"지문이 빈 곡선 {len(rows)}개를 봅니다.")
        for curve, type_id in rows:
            try:
                columns = curvekit.read_columns(filestore.read_bytes(curve.storage_path))
            except (FileNotFoundError, OSError):
                missing += 1
                continue
            keys = defined.get(type_id) or set()
            curve.fingerprint = curvekit.fingerprint(
                {key: values for key, values in columns.items() if not keys or key in keys}
            )
            filled += 1
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
        if not args.apply:
            db.rollback()
    finally:
        db.close()

    verb = "채웠습니다" if args.apply else "채울 수 있습니다(--apply 로 채움)"
    print(f"{filled}개 {verb}. 곡선 파일을 못 읽은 것 {missing}개.")
    print(f"같은 지문이 여러 시험에 있는 묶음 {len(doubled)}개.")
    for names in list(doubled.values())[:10]:
        unique = list(dict.fromkeys(names))
        print(
            f"  - {', '.join(unique[:4])}"
            + (f" 외 {len(unique) - 4}건" if len(unique) > 4 else "")
        )


if __name__ == "__main__":
    main()
