"""문헌 카탈로그·측정법을 들인다 — **드라이런이 기본이다.**

    python scripts/import_materialtwin.py                    # 동봉된 씨앗으로 드라이런
    python scripts/import_materialtwin.py --apply            # 실제 적재
    python scripts/import_materialtwin.py --db F:/.../materialtwin.db   # 다른 원본으로

## 원본은 동봉돼 있다

`backend/seeds/catalog/materialtwin.db.gz` 가 패키지에 함께 실리므로, 운영
서버에서 아무것도 반입하지 않고 그대로 돌릴 수 있다(`deploy.ps1` 이 자동으로
한다). 새 스냅샷을 들일 때만 `--db` 로 원본을 직접 준다 — 그때는 씨앗도
`make_catalog_seed.py` 로 다시 깎는다.

ADR 0027 의 「파일이 유일한 문」 은 그대로다. 금지되는 것은 **개발 DB 를 운영으로
덤프하는 것**이고, 어느 환경이든 데이터는 이 스크립트 + 원본 파일로만 들어간다.
재실행은 갱신이지 중복이 아니다(mt_id 멱등).

원본 스키마에 모르는 컬럼이 있으면 시작 전에 거부한다 — 조용히 버리지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.all_models  # noqa: E402,F401  (DB 를 만지는 스크립트의 규칙)
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.catalog import importer  # noqa: E402
from app.modules.metrology import importer as metrology_importer  # noqa: E402

survive_cp949()

SEED = BACKEND_DIR / "seeds" / "catalog" / "materialtwin.db.gz"


@contextmanager
def source(given: str | None) -> Iterator[str]:
    """읽을 sqlite 파일 하나를 준다.

    씨앗은 압축돼 있고 sqlite 는 진짜 파일을 요구하므로 임시로 푼다(73MB, 1초쯤).
    메모리로 열지 않는 이유도 같다 — `sqlite3` 는 경로를 받는다.
    """
    if given:
        yield given
        return
    if not SEED.exists():
        raise SystemExit(
            f"동봉된 씨앗이 없습니다: {SEED}\n"
            "패키지가 불완전하거나 저장소에서 직접 돌리는 중입니다. "
            "원본을 직접 주려면 --db 를 쓰세요."
        )
    with tempfile.TemporaryDirectory() as work:
        plain = Path(work) / "materialtwin.db"
        with gzip.open(SEED, "rb") as packed, plain.open("wb") as out:
            shutil.copyfileobj(packed, out)
        yield str(plain)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="materialtwin.db 경로 (기본: 동봉된 씨앗)")
    parser.add_argument(
        "--apply", action="store_true", help="실제로 적재한다 (없으면 드라이런)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        with source(args.db) as path:
            print(f"원본: {args.db or f'동봉된 씨앗 ({SEED.name})'}")
            report = importer.run(db, path)
            # 측정법은 카탈로그 다음이다 — 능력의 property_key 가 정의를 가리킨다.
            metrology = metrology_importer.run(db, path)
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
