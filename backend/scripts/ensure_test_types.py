"""기본 시험 종류 정의를 보장한다 — 배포 후 한 번 돌리는 보정 스크립트.

시험 종류는 데이터라서 마이그레이션이 만들어 주지 않는다. 멱등하므로 여러 번
돌려도 되고, 관리자가 라벨을 고쳐 두었다면 그대로 둔다.

사용:
    python scripts/ensure_test_types.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다.** 스크립트가 손대는 모델만 import 하면, 그 모델의
# 외래키가 가리키는 테이블이 메타데이터에 없어 SQLAlchemy 가 매핑을 못 푼다
# (실측: `test_types.owner_workspace_id` 가 'workspaces' 를 못 찾음). 앱은
# main 이 전부 부르므로 안 드러나고, **배포용 스크립트에서만 터진다.**
import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.tests.definitions import ensure_builtin_test_types  # noqa: E402
from app.modules.tests.legacy_profiles import (  # noqa: E402
    ensure_builtin_format_profiles,
)
from app.modules.tests.models import TestChannel, TestConditionField, TestType  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        created = ensure_builtin_test_types(db)
        profiles = ensure_builtin_format_profiles(db)
        db.commit()
        if profiles:
            print(f"형식 프로파일 {len(profiles)}건: {', '.join(profiles)}")

        if created:
            print(f"시험 종류 {len(created)}건을 새로 만들었습니다: {', '.join(created)}")
        else:
            print("새로 만들 시험 종류가 없습니다 (이미 모두 있음).")

        for test_type in db.scalars(select(TestType).order_by(TestType.sort_order)):
            channels = db.scalars(
                select(TestChannel.key).where(TestChannel.test_type_id == test_type.id)
            ).all()
            conditions = db.scalars(
                select(TestConditionField.key).where(
                    TestConditionField.test_type_id == test_type.id
                )
            ).all()
            print(f"  {test_type.key:<12} {test_type.label} ({test_type.abbr})")
            print(f"      채널 {len(channels)}: {', '.join(channels)}")
            print(f"      조건 {len(conditions)}: {', '.join(conditions)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
