"""`materialtwin.db` 에서 배포에 동봉할 씨앗을 깎는다.

    python scripts/make_catalog_seed.py --db F:/.../materialtwin.db

`backend/seeds/catalog/materialtwin.db.gz` 를 다시 만든다. **원본 84MB 를 그대로
싣지 않는다** — 이관이 읽는 표는 여섯 개뿐인데 나머지(시험·곡선·처리결과)까지
따라오면 저장소에 안 쓰는 데이터가 쌓인다.

## 왜 저장소에 넣는가

가이드 씨앗과 같은 이유다. **코드 배포 ≠ 데이터 반영**이고, 원본 파일이 서버에
없으면 사람이 USB 로 84MB 를 들고 가야 한다 — 그러면 언젠가 아무도 안 한다
(실측 2026-08-31: 가이드가 운영에서 통째로 비어 있었다. 씨앗은 이미 서버에
가 있었는데 넣는 명령을 아무도 안 돌렸다).

ADR 0027 의 「파일이 유일한 문」 은 **개발 DB 를 운영으로 덤프하지 말라**는
규칙이다. 얼어붙은 원본을 패키지에 실어 같은 스크립트로 넣는 것은 그 규칙 안에
있다 — 어느 환경이든 같은 파일에서 같은 결과가 나온다.

## 어떤 표를 남기는가

**이관이 아는 표를 그대로 따른다.** 여기에 목록을 손으로 적으면, 이관이 표를
하나 더 읽게 된 날 씨앗만 옛것으로 남는다 — 그러면 배포가 「원본에 그 표가
없습니다」 로 거절한다.

## 다시 만들어도 바이트가 같다

gzip 에 시각을 안 적는다. 같은 원본에서 다시 깎으면 같은 파일이 나오므로,
바뀐 것이 없는데 5MB 짜리 diff 가 생기지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.modules.catalog.importer import EXPECTED_COLUMNS as CATALOG_TABLES  # noqa: E402
from app.modules.metrology.importer import EXPECTED_COLUMNS as METROLOGY_TABLES  # noqa: E402

survive_cp949()

SEED = BACKEND_DIR / "seeds" / "catalog" / "materialtwin.db.gz"

#: 이관이 아는 표 전부. 손으로 적지 않는다 — 위 docstring 참조.
KEEP: tuple[str, ...] = tuple(sorted({*CATALOG_TABLES, *METROLOGY_TABLES}))


def carve(source: Path, target: Path) -> dict[str, int]:
    """`source` 에서 `KEEP` 만 옮겨 담는다. 표별 행 수를 돌려준다."""
    counts: dict[str, int] = {}
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        for table in KEEP:
            found = src.execute(
                "select sql from sqlite_master where type='table' and name=?", (table,)
            ).fetchone()
            if found is None:
                raise SystemExit(f"원본에 {table} 표가 없습니다 — 카탈로그 DB 가 맞습니까?")
            dst.execute(found[0])
            columns = [row[1] for row in src.execute(f'pragma table_info("{table}")')]
            rows = src.execute(f'select * from "{table}"').fetchall()
            marks = ",".join("?" * len(columns))
            dst.executemany(f'insert into "{table}" values ({marks})', rows)
            counts[table] = len(rows)
        dst.commit()
        # 색인은 안 옮긴다 — 이관은 전수로 읽고, 색인이 없으면 파일이 작아진다.
        dst.execute("vacuum")
    finally:
        src.close()
        dst.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="배포에 동봉할 카탈로그 씨앗을 만든다")
    parser.add_argument("--db", required=True, type=Path, help="materialtwin.db 경로")
    parser.add_argument("--out", type=Path, default=SEED, help=f"기본: {SEED}")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"원본을 찾을 수 없습니다: {args.db}")

    with tempfile.TemporaryDirectory() as work:
        carved = Path(work) / "materialtwin.db"
        counts = carve(args.db, carved)
        for table, count in counts.items():
            print(f"  {table:<24} {count:>7,}행")

        args.out.parent.mkdir(parents=True, exist_ok=True)
        # **시각을 안 적는다**(mtime=0). 적으면 같은 원본에서 다시 깎아도 바이트가
        # 달라져, 바뀐 것이 없는데 5MB 짜리 diff 가 커밋에 섞인다.
        with (
            carved.open("rb") as plain,
            args.out.open("wb") as packed,
            gzip.GzipFile(fileobj=packed, mode="wb", compresslevel=9, mtime=0) as zipped,
        ):
            shutil.copyfileobj(plain, zipped)

        raw = carved.stat().st_size / 1048576
        small = args.out.stat().st_size / 1048576

    print(f"\n{args.out}")
    print(f"  {raw:.1f}MB → {small:.1f}MB (gzip)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
