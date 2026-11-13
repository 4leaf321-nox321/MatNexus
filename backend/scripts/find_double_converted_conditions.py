"""시험 조건이 **한 번 더 환산됐을 수 있는** 시험을 찾는다 — 읽기만 한다(2026-11-14).

## 무엇이 있었나

파일이 조건 칸을 채울 때(형식 프로파일의 조건 규칙), 이미 있던 칸 — 사람이 업로드 폼에 적은
값 — 을 사람이 적은 단위(°C · mm/min)와 함께 다시 정규화했다. 그 값은 이미 SI 로 저장돼
있었으므로 **한 번 더 환산됐다**: 25 °C → 298.15 K → 571.3 K, 10 mm/min → 1/60000 배.
다시 읽기를 할 때마다 한 번씩 더 환산됐을 수 있다. v1.312.0 에서 고쳤다
(`tests/services._apply_conditions`).

## 무엇을 하나

1. 사람이 SI 가 아닌 단위로 적은 조건이 있는 시험만 본다(그 밖에는 걸릴 수 없다).
2. 원본 파일을 **저장 없이** 다시 읽어, 파일이 주는 조건이 있는지 본다(없으면 안 걸렸다).
3. 걸렸을 수 있는 칸마다 지금 값과 「한 번 되돌린 값」 · 「두 번 되돌린 값」 을 보인다.

**고치지 않는다.** 몇 번 환산됐는지는 기록에 없다 — 사람이 값을 보고 정한다. 고칠 때는 시험
화면에서 조건을 다시 적는다(그 칸의 입력 단위로).

사용:
    python scripts/find_double_converted_conditions.py
"""

from __future__ import annotations

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
from app.modules.tests import services  # noqa: E402
from app.modules.tests.models import TestRun, TestType  # noqa: E402
from app.shared import filestore  # noqa: E402
from app.shared.conditions import normalize_conditions  # noqa: E402
from app.shared.errors import AppError  # noqa: E402
from matcore import units  # noqa: E402

survive_cp949()


def _is_si(symbol: str) -> bool:
    """1 을 SI 로 바꿔도 1 이고 0 이 0 이면 SI 다(°C 는 0 → 273.15)."""
    try:
        return units.to_si(1.0, symbol) == 1.0 and units.to_si(0.0, symbol) == 0.0
    except units.UnknownUnit:
        return True  # 모르는 단위는 환산되지 않았다


def _close(left: object, right: object) -> bool:
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        return left == right
    return abs(float(left) - float(right)) <= 1e-9 * max(1.0, abs(float(right)))


def main() -> None:
    db = SessionLocal()
    found = 0
    try:
        runs = list(
            db.scalars(
                select(TestRun).where(
                    TestRun.status == "parsed", TestRun.input_units.is_not(None)
                )
            )
        )
        print(f"조건 입력 단위가 있는 시험 {len(runs)}건을 봅니다.")
        for run in runs:
            human = {
                key: unit
                for key, unit in (run.input_units or {}).items()
                if unit and not _is_si(unit)
            }
            if not human or not run.source_path:
                continue
            test_type = db.get(TestType, run.test_type_id)
            if test_type is None:
                continue
            try:
                data = filestore.read_bytes(run.source_path)
            except (FileNotFoundError, OSError):
                print(f"  ! {run.record_name}: 원본 파일을 못 읽었습니다")
                continue
            reader = services._pick_reader(db, test_type, run, data)
            if reader is None:
                continue
            try:
                parsed = reader[1](data)
            except Exception as exc:  # 진단이라 다음 시험으로 넘어간다
                print(f"  ! {run.record_name}: 다시 읽지 못했습니다 ({exc})")
                continue
            if not parsed.conditions:
                continue  # 파일이 조건을 안 채운다 — 이 결함에 안 걸린다
            try:
                from_file, _ = normalize_conditions(
                    db, test_type, dict(parsed.conditions), dict(parsed.condition_units)
                )
            except AppError:
                continue
            conditions = run.conditions or {}
            filled = [
                key
                for key, value in from_file.items()
                if key not in human and _close(conditions.get(key), value)
            ]
            suspects = {
                key: unit
                for key, unit in human.items()
                if key in conditions
                and isinstance(conditions[key], int | float)
                and not _close(conditions[key], from_file.get(key))
            }
            if not filled or not suspects:
                continue
            found += 1
            print(f"\n- {run.record_name} ({run.id}) — 파일이 채운 칸: {', '.join(filled)}")
            for key, unit in suspects.items():
                now = float(conditions[key])
                once = units.from_si(now, unit)  # 한 번 더 환산되기 전의 SI 값
                twice = units.from_si(once, unit)
                print(
                    f"    {key}: 지금 {units.from_si(now, unit):.6g} {unit}"
                    f" · 한 번 되돌리면 {units.from_si(once, unit):.6g} {unit}"
                    f" · 두 번 되돌리면 {units.from_si(twice, unit):.6g} {unit}"
                )
    finally:
        db.close()
    print(
        f"\n걸렸을 수 있는 시험 {found}건." if found else "\n걸렸을 수 있는 시험이 없습니다."
    )


if __name__ == "__main__":
    main()
