"""파일스토어 정리 — 정기 실행용.

**만들어 두고 실행 경로를 안 만들면 없는 것과 같다.** 정리 잡 핸들러는 있었는데
큐에 넣는 곳이 없어서 한 번도 돌지 않았고, 그동안 파일이 쌓였다.

치우는 것이 세 종류다.

  오펀       DB 에 행이 없는 폴더. 트랜잭션이 파일시스템까지 덮지 못해 생긴다
  미완성     쓰다 만 `.part`. 폴더는 살아 있어 오펀 탐색에 안 걸린다
  보존만료   소프트 삭제 후 보존기간이 지난 것. **행이 있어서 오펀으로 영원히
             안 잡힌다** — 실측으로 확인한, 셋 중 가장 큰 구멍이다

기본은 미리보기다. 지우려면 `--apply` 를 명시해야 한다 — 되돌릴 수 없다.

사용:
    python scripts/cleanup_storage.py                    # 미리보기
    python scripts/cleanup_storage.py --apply            # 실제로 지운다
    python scripts/cleanup_storage.py --retention-days 7 # 보존기간을 덮어쓴다

작업 스케줄러에 걸 때는 미리보기를 먼저 며칠 돌려 보고 `--apply` 로 바꾼다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.modules.tests import services  # noqa: E402


def _mb(value: int) -> str:
    return f"{value / (1024 * 1024):.2f}MB"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="실제로 지운다 (없으면 미리보기)")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="소프트 삭제 파일 보존기간. 생략하면 설정값",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = services.cleanup_storage(
            db, dry_run=not args.apply, retention_days=args.retention_days
        )
    finally:
        db.close()

    print(f"저장소   : {result['root']}")
    print(f"전체     : {_mb(result['total_bytes'])}")
    print(f"살아있음 : {result['live_count']}건 {_mb(result['live_bytes'])}")
    print(f"보존기간 : {result['retention_days']}일")
    print()

    for label, key in (("오펀", "orphans"), ("미완성", "incomplete"), ("보존만료", "expired")):
        items = result[key]
        print(f"{label:<8} {len(items)}건 {_mb(sum(int(i['bytes']) for i in items))}")
        for item in items[:20]:
            extra = ""
            if key == "expired":
                extra = f"  ({item['record_name']}, 삭제 {item['deleted_at']:%Y-%m-%d})"
            elif key == "incomplete":
                extra = f"  ({item['age_hours']}시간 전)"
            print(f"    {item['path']}{extra}")
        if len(items) > 20:
            print(f"    … 외 {len(items) - 20}건")

    print()
    if result["dry_run"]:
        print(f"미리보기입니다. 지울 수 있는 용량: {_mb(result['reclaimable_bytes'])}")
        if result["reclaimable_bytes"]:
            print("실제로 지우려면 --apply 를 붙이세요.")
    else:
        print(f"삭제 {len(result['removed'])}건 · 확보 {_mb(result['freed_bytes'])}")


if __name__ == "__main__":
    main()
