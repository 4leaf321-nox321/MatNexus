"""설치 시드 — 초기 관리자와 기본 부서.

**데모 시드와 분리한다**(개발계획 §9.2). 운영 설치에 합성 재료 데이터가 들어갈
이유가 없다. 65는 데모 시드가 설치 경로에 섞여 있어 운영 설치에도 DP780 합성
데이터가 들어간다.

**멱등하다.** 이미 있으면 아무것도 바꾸지 않는다 — 특히 비밀번호를 되돌리지
않는다. 설치가 중간에 끊겨 다시 돌릴 때 운영 계정의 비밀번호가 초기값으로
되돌아가면 사고다.

사용:
    python scripts/seed_install.py                    # 비밀번호 자동 생성
    python scripts/seed_install.py --password '...'   # 직접 지정
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.auth import security  # noqa: E402
from app.modules.workspaces.models import Workspace, WorkspaceMember  # noqa: E402

DEFAULT_EMAIL = "admin@matnexus.local"
DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_WORKSPACE_NAME = "기본 부서"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=None, help="생략하면 난수로 만든다")
    parser.add_argument("--workspace-slug", default=DEFAULT_WORKSPACE_SLUG)
    parser.add_argument("--workspace-name", default=DEFAULT_WORKSPACE_NAME)
    parser.add_argument(
        "--no-force-change",
        action="store_true",
        help="첫 로그인 시 비밀번호 변경 강제를 끈다 (파일럿·개발 편의용)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == args.workspace_slug))
        if workspace is None:
            workspace = Workspace(
                slug=args.workspace_slug, name=args.workspace_name, kind="org"
            )
            db.add(workspace)
            db.flush()
            print(f"부서 생성: {workspace.slug} ({workspace.name})")
        else:
            print(f"부서 이미 있음: {workspace.slug}")

        email = args.email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            print(f"관리자 이미 있음: {email} — 비밀번호를 바꾸지 않았습니다.")
            db.commit()
            return

        password = args.password or secrets.token_urlsafe(12)
        user = User(
            email=email,
            password_hash=security.hash_password(password),
            display_name="시스템 관리자",
            status="active",  # 초기 관리자는 승인 절차를 거치지 않는다
            is_system_admin=True,
            # 시드 비밀번호가 그대로 남는 사고 방지. 파일럿에서만 --no-force-change 로 끈다.
            must_change_password=not args.no_force_change,
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
        db.commit()

        print("\n관리자 계정을 만들었습니다. 이 비밀번호는 다시 표시되지 않습니다.")
        print(f"  아이디   : {email}")
        print(f"  비밀번호 : {password}")
        if user.must_change_password:
            print("  첫 로그인 시 비밀번호 변경이 강제됩니다.\n")
        else:
            print("  ! 비밀번호 변경 강제가 꺼져 있습니다 (--no-force-change).\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
