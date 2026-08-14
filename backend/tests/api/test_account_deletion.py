"""계정 삭제와 자료 승계.

**행을 지우지 않는다.** 그 사람이 등록한 자료의 소유자 참조가 살아 있어야
"누가 만든 데이터인가"를 잃지 않는다(구조결정 4). 소유권만 넘긴다.

지금은 승계할 자료 테이블이 아직 없다(Phase 2). 그래서 여기서 검증하는 것은
**형태**다 — 소유 컬럼 이름 규약을 따르는 테이블이 생기면 코드 수정 없이 승계
대상이 되는가.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable, DropTable

from app.database import Base
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared.dependents import transfer_ownership


def make_user(db: Session, email: str, workspace: Workspace, role: str = "member") -> User:
    user = User(
        email=email,
        password_hash=security.hash_password("member-password-1"),
        display_name=email,
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    db.commit()
    return user


def test_delete_keeps_the_row_and_cuts_access(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    user = make_user(db, "hong", workspace)

    response = client.request(
        "DELETE", f"/api/accounts/{user.id}", json={}, headers=admin_headers
    )
    assert response.status_code == 200

    db.refresh(user)
    assert user.deleted_at is not None  # 행은 남는다
    assert user.status == "suspended"
    assert user.home_workspace_id is None

    login = client.post(
        "/api/auth/login", json={"email": "hong", "password": "member-password-1"}
    )
    assert login.status_code == 403


def test_delete_removes_memberships(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    """멤버십을 남기면 부서 멤버 목록에 지워진 계정이 계속 뜬다."""
    user = make_user(db, "hong", workspace)
    before = client.get(f"/api/workspaces/{workspace.slug}/members", headers=admin_headers)
    assert len(before.json()) == 2

    client.request("DELETE", f"/api/accounts/{user.id}", json={}, headers=admin_headers)

    after = client.get(f"/api/workspaces/{workspace.slug}/members", headers=admin_headers)
    assert [m["email"] for m in after.json()] == ["admin"]


def test_cannot_delete_last_manager_of_a_workspace(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    other = Workspace(slug="polymer", name="고분자팀")
    db.add(other)
    db.flush()
    boss = make_user(db, "boss", other, role="manager")

    response = client.request(
        "DELETE", f"/api/accounts/{boss.id}", json={}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MNX-ACCOUNTS-0013"
    # 부서 이름을 알려 줘야 관리자가 어디를 손봐야 할지 안다.
    assert "고분자팀" in response.json()["error"]["message"]


def test_cannot_delete_self_or_last_system_admin(
    client: TestClient, admin: User, admin_headers: dict[str, str]
) -> None:
    response = client.request(
        "DELETE", f"/api/accounts/{admin.id}", json={}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MNX-ACCOUNTS-0006"


def test_dependents_preview_lists_what_is_attached(
    client: TestClient, db: Session, workspace: Workspace, admin_headers: dict[str, str]
) -> None:
    user = make_user(db, "hong", workspace)
    client.post("/api/auth/login", json={"email": "hong", "password": "member-password-1"})

    response = client.get(f"/api/accounts/{user.id}/dependents", headers=admin_headers)
    assert response.status_code == 200
    tables = {row["table"]: row for row in response.json()}
    assert tables["workspace_members"]["count"] == 1
    assert tables["workspace_members"]["label"] == "부서 멤버십"
    assert tables["refresh_tokens"]["count"] == 1


def test_ownership_transfer_follows_the_column_name_convention(db: Session) -> None:
    """소유 컬럼 이름을 쓰는 테이블이 생기면 코드 수정 없이 승계 대상이 된다.

    Phase 2의 시험·곡선 테이블이 이 규약을 따르면 승계 함수를 손대지 않아도 된다.
    RA 는 참조 목록을 하드코딩해 두었다가 새 테이블을 놓쳐 장애를 겪었다.
    """
    workspace = Workspace(slug="metal", name="금속재료팀")
    db.add(workspace)
    db.flush()
    leaver = make_user(db, "leaver", workspace)
    successor = make_user(db, "successor", workspace)

    # 아직 없는 미래 테이블을 흉내 낸다 — 규약만으로 편입되는지 보기 위해서다.
    #
    # **DDL 을 세션의 연결에서 실행한다.** 별도 연결(`create_all(engine)`)로 만들면,
    # 세션이 연 트랜잭션과 서로 잠금을 기다리다 영원히 멈춘다(실측: 테스트가 7분을
    # 넘겨 강제 종료됐고, 남은 테이블이 이후 실행까지 막았다).
    samples = Table(
        "sample_records",
        Base.metadata,
        Column("id", PgUUID(as_uuid=True), primary_key=True),
        Column("owner_id", PgUUID(as_uuid=True), ForeignKey("users.id")),
        Column("name", String(50)),
    )
    try:
        db.execute(CreateTable(samples))
        db.execute(
            samples.insert(), [{"id": uuid.uuid4(), "owner_id": leaver.id, "name": "인장-01"}]
        )

        moved = transfer_ownership(db, table="users", from_pk=leaver.id, to_pk=successor.id)

        assert [(ref.table, ref.column, ref.count) for ref in moved] == [
            ("sample_records", "owner_id", 1)
        ]
        owner = db.execute(samples.select()).first()
        assert owner is not None and owner.owner_id == successor.id
    finally:
        db.execute(DropTable(samples, if_exists=True))
        db.commit()
        Base.metadata.remove(samples)
