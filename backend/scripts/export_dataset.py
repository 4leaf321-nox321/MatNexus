"""물성 데이터 내보내기 — **명령줄 자리.** 계산은 `app/shared/dataset_export.py`.

화면의 「데이터 내보내기」 단추와 **같은 함수**를 부른다. 두 벌로 두면 버튼으로 뽑은
것과 스크립트로 뽑은 것이 달라지고, 그 차이는 아무도 설명할 수 없다.

무엇이 나가고 무엇이 안 나가는지는 그 모듈의 문서에 있다.

사용:
    python scripts/export_dataset.py --out D:\\export
    python scripts/export_dataset.py --out D:\\export --no-curves
    python scripts/export_dataset.py --out D:\\export --no-catalog
    python scripts/export_dataset.py --out D:\\export --workspace metal
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 그 외래키가 가리키는 표가
# 메타데이터에 없어 매핑이 안 풀린다 — 앱에서는 안 드러나고 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.shared import dataset_export  # noqa: E402

survive_cp949()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="내보낼 폴더")
    parser.add_argument("--workspace", default=None, help="부서 slug 하나만. 없으면 전 부서")
    parser.add_argument("--no-curves", action="store_true", help="곡선 파일을 빼고 표만 낸다")
    parser.add_argument(
        "--no-catalog", action="store_true", help="문헌 카탈로그를 뺀다(사내 값만)"
    )
    args = parser.parse_args()

    try:
        report = dataset_export.export(
            Path(args.out),
            workspace=args.workspace,
            with_curves=not args.no_curves,
            with_catalog=not args.no_catalog,
        )
    except ValueError as failed:  # 부서 이름 오타 같은 것 — 스택보다 한 줄이 낫다
        raise SystemExit(str(failed)) from failed
    print(f"내보냄: {args.out}")
    for name, rows in report["counts"].items():
        print(f"  {name:28s} {rows:>8,}줄")
    if report["missing_curve_files"]:
        print(f"  ** 못 읽은 곡선 {len(report['missing_curve_files'])}건 — README 참고")


if __name__ == "__main__":
    main()
