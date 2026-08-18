"""관리자 계정을 만들거나 고친다 — 서버 콘솔에서 쓰는 복구 도구.

비밀번호를 잊었거나, 로그인 아이디를 바꾸거나, 강제 변경 플래그를 풀어야 할 때
쓴다. 화면으로 할 수 없는 일(자기 비밀번호를 모를 때)이라 CLI 로 둔다.

사용:
    # 새 관리자 만들기
    python scripts/set_admin.py --email admin --password '...'

    # 기존 계정의 아이디까지 바꾸기
    python scripts/set_admin.py --email admin --password '...' \
        --rename-from admin@matnexus.local

    # 파일럿·개발 편의로 강제 변경을 끄기 (운영에서는 쓰지 말 것)
    python scripts/set_admin.py --email admin --password '32167' --no-force-change

로그인 아이디는 이메일 형식이 아니어도 된다. 사내 관리자 계정은 `admin` 처럼
짧은 아이디를 쓰는 경우가 많다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
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
from app.modules.accounts.models import User  # noqa: E402
from app.modules.auth import security  # noqa: E402
from app.modules.auth.models import RefreshToken  # noqa: E402
from app.modules.workspaces.models import Workspace, WorkspaceMember  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--email", required=True, help="로그인 아이디 (이메일 형식이 아니어도 된다)"
    )
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--rename-from", default=None, help="이 계정의 아이디를 --email 로 바꾼다"
    )
    parser.add_argument("--display-name", default="시스템 관리자")
    parser.add_argument(
        "--no-force-change",
        action="store_true",
        help="첫 로그인 시 비밀번호 변경 강제를 끈다 (운영에서는 쓰지 말 것)",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))

        if user is None and args.rename_from:
            old = args.rename_from.strip().lower()
            user = db.scalar(select(User).where(User.email == old))
            if user is not None:
                user.email = email
                print(f"아이디 변경: {old} → {email}")

        if user is None:
            workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
            if workspace is None:
                sys.exit("부서가 없습니다. 먼저 scripts/seed_install.py 를 실행하세요.")
            user = User(
                email=email,
                password_hash=security.hash_password(args.password),
                display_name=args.display_name,
                status="active",
                is_system_admin=True,
                home_workspace_id=workspace.id,
            )
            db.add(user)
            db.flush()
            db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
            print(f"관리자 생성: {email}")
        else:
            user.password_hash = security.hash_password(args.password)
            print(f"비밀번호 변경: {email}")

        user.is_system_admin = True
        user.status = "active"
        user.deleted_at = None
        user.must_change_password = not args.no_force_change

        # 비밀번호가 바뀌었으므로 기존 세션을 전부 끊는다.
        revoked = 0
        for token in db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = datetime.now(UTC)
            revoked += 1

        db.commit()

        print(f"  시스템 관리자 : {user.is_system_admin}")
        print(f"  강제 변경     : {user.must_change_password}")
        if revoked:
            print(f"  끊은 세션     : {revoked}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
