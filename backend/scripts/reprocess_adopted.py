"""채택된 처리 결과를 **그때의 레시피 그대로** 다시 돌린다.

    python scripts/reprocess_adopted.py                  # 무엇이 바뀌는지만 본다
    python scripts/reprocess_adopted.py --apply          # 실제로 저장하고 채택을 옮긴다
    python scripts/reprocess_adopted.py --apply --only-modulus   # 탄성계수가 있는 것만

## 왜 필요한가

계산이 바뀌면 이미 저장된 결과는 옛 계산의 값을 그대로 들고 있다. v1.159.0 에서
「탄성 구간에 5점 미만이면 탄성계수를 안 낸다」 를 넣었는데, 그 전에 나온 값들은
DB 에 남아 통계·물성 카드로 계속 흘러간다.

## 고치지 않고 새로 만든다

처리 결과는 **불변**이다(ADR 0007). 값을 덮어쓰면 「예전 결과를 열었더니 값이
달라졌다」 가 가능해진다. 그래서 새 결과를 만들고 `TestRun.adopted_result_id` 만
옮긴다 — 옛 결과는 그대로 남아 「그때는 이 값이었다」 에 답한다.

## 화면과 같은 경로를 쓴다

`processing.routes._store` 를 그대로 부른다. 여기서 따로 구현하면 「화면에서는
되는데 배치는 다른 값이 나온다」 가 가능해지고, 그 어긋남은 숫자로만 드러난다.

**기본은 dry-run.** 무엇이 사라지는지 보고 나서 `--apply` 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.processing.models import ProcessingRecipe, ProcessingResult  # noqa: E402
from app.modules.processing.routes import _store  # noqa: E402
from app.modules.tests.models import TestRun  # noqa: E402
from app.shared.errors import AppError  # noqa: E402
from matcore.processing import ProcessingError  # noqa: E402

WATCH = ("youngs_modulus", "elastic_intercept", "elastic_r_squared")


def _scalars(item: ProcessingResult) -> dict[str, float]:
    return {
        str(one["key"]): one["value"]
        for one in item.scalars
        if isinstance(one.get("value"), int | float)
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="실제로 저장하고 채택을 옮긴다")
    parser.add_argument(
        "--unadopt-broken",
        action="store_true",
        help=(
            "지금 규칙으로 못 도는 결과는 **채택을 푼다**. 그 값은 「이 시험의 물성」 "
            "이 아니게 되고, 시험은 「처리 대기」 로 돌아가 목록에 뜬다. 결과 행은 "
            "지운 적 없다 — 다시 채택할 수 있다."
        ),
    )
    parser.add_argument(
        "--only-modulus",
        action="store_true",
        help="탄성계수가 들어 있는 결과만 — 나머지는 이 변경과 무관하다",
    )
    args = parser.parse_args()

    changed = same = failed = 0
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.is_system_admin.is_(True)))
        if actor is None:
            print("시스템 관리자 계정이 없습니다.")
            return

        runs = list(
            db.scalars(
                select(TestRun).where(
                    TestRun.adopted_result_id.is_not(None), TestRun.deleted_at.is_(None)
                )
            )
        )
        for run in runs:
            old = db.get(ProcessingResult, run.adopted_result_id)
            if old is None or not old.steps_snapshot:
                continue
            before = _scalars(old)
            if args.only_modulus and "youngs_modulus" not in before:
                continue
            recipe = db.get(ProcessingRecipe, old.recipe_id) if old.recipe_id else None
            try:
                made = _store(
                    db,
                    run,
                    old.source_curve_key,
                    list(old.steps_snapshot),
                    recipe,
                    actor,
                )
            except (AppError, ProcessingError) as error:
                # **레시피가 지금 코드로는 안 돌 수 있다.** 그것도 결과다 — 조용히
                # 넘기지 않고 이름과 이유를 남긴다. 흔한 것: 탄성계수를 안 내게
                # 되면서 뒤 단계의 `@youngs_modulus` 가 갈 곳을 잃는 경우.
                #
                # 이때 **채택은 그대로 둔다.** 옛 값이 남는 것이 「값이 통째로
                # 사라진 시험」 보다 낫다 — 사람이 레시피를 고칠 때까지의 상태다.
                failed += 1
                reason = str(getattr(error, "message", error)).split(".")[0]
                db.rollback()
                if args.unadopt_broken and args.apply:
                    # **나쁜 값을 채택한 채로 두지 않는다.** 레시피가 지금 규칙으로
                    # 못 돈다는 것은 그 값이 지금 규칙을 안 지킨다는 뜻이다.
                    run.adopted_result_id = None
                    db.commit()
                    print(f"  x {run.record_name}: 채택 풀었음 — {reason}")
                else:
                    print(f"  x {run.record_name}: {reason}")
                continue

            after = _scalars(made)
            gone = [key for key in WATCH if key in before and key not in after]
            moved = [
                key
                for key in after
                if key in before and abs(after[key] - before[key]) > abs(before[key]) * 1e-9
            ]
            if not gone and not moved:
                same += 1
                db.rollback()  # 새 행을 남기지 않는다 — 바뀐 것이 없다
                continue

            changed += 1
            detail = ""
            if "youngs_modulus" in gone:
                points = after.get("elastic_point_count")
                detail = (
                    f"탄성계수 {before['youngs_modulus'] / 1e9:.2f} GPa → 없음"
                    f"{f' (구간 {int(points)}점)' if points is not None else ''}"
                )
            elif moved:
                detail = ", ".join(
                    f"{key} {before[key]:.4g} → {after[key]:.4g}" for key in moved[:3]
                )
            print(f"  · {run.record_name}: {detail}")

            if args.apply:
                run.adopted_result_id = made.id
                db.commit()
            else:
                db.rollback()

    print()
    print(f"바뀜 {changed} · 그대로 {same} · 실패 {failed}")
    if not args.apply:
        print("**아직 아무것도 안 바꿨습니다.** 적용하려면 --apply 를 주세요.")


if __name__ == "__main__":
    main()
