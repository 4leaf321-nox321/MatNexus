"""materialtwin.db 를 카탈로그로 이관한다 — **드라이런이 기본이다.**

    python scripts/import_materialtwin.py --db F:/.../materialtwin.db          # 드라이런
    python scripts/import_materialtwin.py --db F:/.../materialtwin.db --apply  # 실제 적재

운영 반영 절차 (ADR 0027):
  ① 배포(마이그레이션 자동) → ② 운영 서버에서 드라이런으로 수를 확인 →
  ③ --apply. **개발 DB 는 운영과 무관하다** — 데이터는 이 스크립트 + 원본
  파일로만 들어가고, 재실행은 갱신이지 중복이 아니다(mt_id 멱등).

원본 스키마에 모르는 컬럼이 있으면 시작 전에 거부한다 — 조용히 버리지 않는다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.all_models  # noqa: F401  (DB 를 만지는 스크립트의 규칙)
from app.database import SessionLocal
from app.modules.catalog import importer
from app.modules.metrology import importer as metrology_importer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="materialtwin.db 경로")
    parser.add_argument(
        "--apply", action="store_true", help="실제로 적재한다 (없으면 드라이런)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = importer.run(db, args.db)
        # 측정법은 카탈로그 다음이다 — 능력의 property_key 가 정의를 가리킨다.
        metrology = metrology_importer.run(db, args.db)
        report.tables.update(metrology.tables)
        report.problems.extend(metrology.problems)
        print(report.line())
        if report.problems:
            print("\n검산 실패 — 적재하지 않습니다:")
            for one in report.problems:
                print(" -", one)
            db.rollback()
            return 1
        if args.apply:
            db.commit()
            print("\n적재 완료.")
        else:
            db.rollback()
            print("\n드라이런 — 아무것도 쓰지 않았습니다. 적재하려면 --apply.")
        return 0
    except importer.ImportRefused as refused:
        db.rollback()
        print(f"거부: {refused}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
