"""기존 계정에 기본 알림 규칙을 보장한다 — 한 번 돌리면 되는 보정 스크립트.

알림 규칙은 계정이 **승인·생성될 때** 만들어진다(1-4). 그 기능이 생기기 전에
만들어진 계정(설치 시드의 초기 관리자 등)에는 규칙이 없어서, 가입 신청이 들어와도
알림을 받지 못한다.

멱등하다. 이미 있으면 아무것도 하지 않으므로 여러 번 돌려도 된다.

사용:
    python scripts/ensure_notification_rules.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.notifications import services  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        users = list(
            db.scalars(select(User).where(User.status == "active", User.deleted_at.is_(None)))
        )
        for user in users:
            services.ensure_rules(db, user)
        db.commit()

        print(f"활성 계정 {len(users)}명의 알림 규칙을 확인했습니다.")
        for user in users:
            kinds = ["account.decided"] + (["account.signup"] if user.is_system_admin else [])
            print(f"  {user.email:<20} {', '.join(kinds)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
