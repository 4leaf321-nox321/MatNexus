"""접선 · 응력 띠로 낸 **옛 버전 탄성률 결과**가 몇 건인지 센다(읽기만, 2026-11-14).

## 왜

ADR 0088: 굽힘 · 압축 탄성률의 접선은 가장 가파른 창 하나에서 직선 구간 전체로, 응력 띠의
「닿음」 은 다섯 점 연속으로 바뀌었다(탄성률 단계 버전 3). 저장된 결과는 불변이라 그대로다 —
접선으로 낸 옛 값은 잡음에 따라 수 %~수십 % 높을 수 있고, 다시 처리해야 바뀐다. 화면은 옛 버전
결과를 따로 가려 주지 않는다.

「다시 처리를 권할지」 를 정하기 전에 규모를 본다 — **채택된** 결과 중 그 방법 · 옛 버전으로 낸
것이 시험 종류 · 방법마다 몇 건인지.

**고치지 않는다.** 다시 처리는 `scripts/reprocess_adopted.py` 가 한다.

사용:
    python scripts/count_slope_results.py            # 채택된 결과만
    python scripts/count_slope_results.py --all      # 채택 안 된 결과까지
    python scripts/count_slope_results.py --list 30  # 시험 이름 30건도
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다** — 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.processing.models import ProcessingResult  # noqa: E402
from app.modules.tests.models import TestRun  # noqa: E402

survive_cp949()

#: 단계 → 이 버전부터가 새 규칙이다.
CURRENT = {"flexural.modulus": 3, "compression.modulus": 3}
#: 규칙이 바뀐 방법.
CHANGED = ("tangent", "stress_window")
#: 단계의 `method` 를 비웠을 때의 기본값(`extensions/*/__init__.py`).
DEFAULT_METHOD = {"flexural.modulus": "chord", "compression.modulus": "secant"}


def _version(stage: dict[str, object]) -> int:
    try:
        return int(str(stage.get("version") or 0))
    except ValueError:
        return 0


def old_slope_stage(stages: list[dict[str, object]]) -> tuple[str, str] | None:
    """`(단계, 방법)` — 접선 · 응력 띠를 옛 버전으로 돌린 단계가 있으면."""
    for stage in stages or []:
        plugin = str(stage.get("plugin") or "")
        if plugin not in CURRENT or _version(stage) >= CURRENT[plugin]:
            continue
        options = stage.get("options")
        method = (options.get("method") if isinstance(options, dict) else None) or (
            DEFAULT_METHOD[plugin]
        )
        if method in CHANGED:
            return plugin, str(method)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="채택 안 된 결과까지 센다")
    parser.add_argument("--list", type=int, default=0, metavar="N", help="시험 이름 N건")
    args = parser.parse_args()

    counts: Counter[tuple[str, str]] = Counter()
    names: list[str] = []
    looked = 0
    with SessionLocal() as db:
        query = select(ProcessingResult.stages, TestRun.record_name).join(
            TestRun,
            TestRun.adopted_result_id == ProcessingResult.id
            if not args.all
            else TestRun.id == ProcessingResult.test_run_id,
        )
        for stages, name in db.execute(query.where(TestRun.deleted_at.is_(None))):
            looked += 1
            found = old_slope_stage(stages)
            if found is None:
                continue
            counts[found] += 1
            if len(names) < args.list:
                names.append(f"{name}  ({found[0]} · {found[1]})")

    scope = "모든 결과" if args.all else "채택된 결과"
    print(f"{scope} {looked}건을 봤습니다.")
    if not counts:
        print("접선 · 응력 띠를 옛 버전으로 낸 탄성률 결과가 없습니다.")
        return 0
    print("옛 규칙(버전 3 앞)으로 낸 탄성률 결과:")
    for (plugin, method), count in sorted(counts.items()):
        print(f"  {plugin:<22} {method:<14} {count}건")
    print(f"  합계 {sum(counts.values())}건")
    print(
        "접선은 다시 처리하면 대개 내려갑니다(잡음에 따라 수 %~수십 %). 응력 띠는 튄 점이 "
        "문턱 앞에 있던 곡선만 바뀝니다."
    )
    for line in names:
        print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
