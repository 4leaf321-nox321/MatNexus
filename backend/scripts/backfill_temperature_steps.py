"""이미 읽어 둔 시험의 **온도 단 수**를 채운다 — 배포 후 한 번 돌리는 보정.

`test_runs.temperature_step_count` 는 읽을 때 세어 둔다. 그 칸이 생기기 전에 읽은
시험은 `NULL`(모름)이고, 재료 화면은 모르는 것을 세지 않는다 — 그래서 그냥 두면
「겹칠 수 있는데 아직 안 만든 시험」 안내가 옛 데이터에서 계속 0으로 나온다.

**다시 읽지 않는다.** 저장된 곡선을 열어 온도만 센다 — 재파싱은 처리 결과와 채택을
흔들 수 있고, 여기서 필요한 것은 그저 온도 단 수다.

사용:
    python scripts/backfill_temperature_steps.py            # 세어 보기만
    python scripts/backfill_temperature_steps.py --apply    # 실제로 채운다
"""

from __future__ import annotations

import argparse
import contextlib
import statistics
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# **콘솔 인코딩에 걸려 죽지 않게 한다.** 운영은 Windows 이고 기본 콘솔이 CP949 라,
# 줄표(—) 하나가 `UnicodeEncodeError` 를 내며 스크립트를 끝낸다(실측 2026-08-31).
# 보정 스크립트가 출력 때문에 멈추면, 정작 한 일이 커밋됐는지도 알 수 없다.
with contextlib.suppress(AttributeError, OSError):  # 파이프로 넘길 때는 이미 안전하다
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다.** 스크립트가 손대는 모델만 import 하면 외래키가
# 가리키는 테이블이 메타데이터에 없어 매핑을 못 푼다. 앱에서는 안 드러나고
# 배포용 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.tests.models import Curve, TestRun, TestType  # noqa: E402
from app.shared import filestore  # noqa: E402
from matcore import curves as curvekit  # noqa: E402
from matcore import viscoelastic  # noqa: E402


def steps_of(db_curves: list[Curve]) -> int | None:
    """저장된 곡선에서 온도 단 수를 센다. 온도가 없으면 `None`.

    측정 곡선만 본다 — 장비가 계산한 표(마스터커브·이동인자)에도 온도 열이 있는데
    그것은 잰 단이 아니라 겹친 결과다.
    """
    found: list[float] = []
    for curve in db_curves:
        if curve.kind != "measured":
            continue
        try:
            columns = curvekit.read_columns(filestore.read_bytes(curve.storage_path))
        except (FileNotFoundError, OSError) as exc:
            print(f"  ! {curve.key}: 곡선 파일을 못 읽었습니다 ({exc})")
            continue
        values = [
            float(one)
            for one in columns.get("temperature", [])
            if one is not None and float(one) == float(one)
        ]
        if values:
            found.append(statistics.median(values))
    if not found:
        return None
    return viscoelastic.count_temperature_levels(found)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제로 채운다 (없으면 세어 보기만)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        runs = list(
            db.scalars(
                select(TestRun).where(
                    TestRun.temperature_step_count.is_(None),
                    TestRun.deleted_at.is_(None),
                    TestRun.status == "parsed",
                )
            )
        )
        print(f"안 세어 본 시험 {len(runs)}건")

        # 시험종류 이름을 미리 읽어 둔다. **건너뛴 것을 종류별로 말하기 위해서다** —
        # 「채울 수 있는 것 0건」 만 적으면 인장뿐이라 0인지, DMA 인데 온도 열을 못
        # 찾아 0인지 구별할 수 없다. 앞은 정상이고 뒤는 프로파일 문제다.
        kinds = {row.id: (row.key, row.label) for row in db.scalars(select(TestType))}

        counted = 0
        skipped: dict[str, int] = {}
        for run in runs:
            db_curves = list(db.scalars(select(Curve).where(Curve.test_run_id == run.id)))
            steps = steps_of(db_curves)
            if steps is None:
                # 온도를 안 재는 시험(인장 등)이 대부분이다. 그 시험에는 이 값이
                # 뜻이 없으므로 넘기되, **무엇을 넘겼는지는 세어 둔다.**
                key, label = kinds.get(run.test_type_id, ("?", "종류 모름"))
                skipped[f"{label}({key})"] = skipped.get(f"{label}({key})", 0) + 1
                continue
            print(f"  {run.record_name}: {steps}단")
            if args.apply:
                run.temperature_step_count = steps
            counted += 1

        if skipped:
            print("온도 열이 없어 건너뛴 시험:")
            for name, count in sorted(skipped.items(), key=lambda one: -one[1]):
                print(f"  {name}: {count}건")
            # 온도를 재는 시험이 여기 있으면 그것은 **읽기 설정 문제**다.
            suspects = [name for name in skipped if "dma" in name.lower() or "점탄성" in name]
            if suspects:
                print(
                    "  ! 위 중 온도를 재는 종류가 있습니다 — 장비 파일 정의에서 온도 열이"
                    " `temperature` 로 매핑됐는지 보세요."
                )

        if args.apply:
            db.commit()
            print(f"채웠습니다: {counted}건")
        else:
            print(f"채울 수 있는 것: {counted}건. 실제로 채우려면 --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main()
