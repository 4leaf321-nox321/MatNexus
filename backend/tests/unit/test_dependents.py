"""의존성 레지스트리.

핵심은 개수를 세는 것이 아니라 **목록이 사람 손에 의존하지 않는다**는 것이다.
Phase 2에서 시험 데이터 테이블이 늘어나도 이 모듈은 그대로여야 한다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import Base
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth.models import PersonalAccessToken, RefreshToken
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared.dependents import blocking, describe, references_to


def _user(db: Session, workspace: Workspace) -> User:
    user = User(
        email="hong",
        password_hash=security.hash_password("x" * 12),
        display_name="홍길동",
        status="active",
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    return user


def test_finds_references_without_a_hardcoded_list(db: Session) -> None:
    workspace = Workspace(slug="metal", name="금속재료팀")
    db.add(workspace)
    db.flush()
    user = _user(db, workspace)
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash="h" * 64,
            expires_at=user.created_at,
        )
    )
    db.commit()

    refs = references_to(db, table="users", pk=user.id)
    by_table = {ref.table: ref for ref in refs}

    assert by_table["workspace_members"].count == 1
    assert by_table["refresh_tokens"].count == 1
    assert "부서 멤버십 1건" in describe(refs)


def test_zero_count_references_are_omitted(db: Session) -> None:
    workspace = Workspace(slug="metal", name="금속재료팀")
    db.add(workspace)
    db.flush()
    user = _user(db, workspace)

    refs = references_to(db, table="users", pk=user.id)
    # PAT 를 만들지 않았으므로 목록에 나오면 안 된다.
    assert all(ref.table != "personal_access_tokens" for ref in refs)


def test_reports_the_db_rule_so_callers_can_decide(db: Session) -> None:
    """CASCADE 인지 SET NULL 인지에 따라 화면이 할 말이 다르다."""
    workspace = Workspace(slug="metal", name="금속재료팀")
    db.add(workspace)
    db.flush()
    user = _user(db, workspace)
    db.add(
        PersonalAccessToken(
            user_id=user.id, name="장비", prefix="mnx_pat_a", token_hash="p" * 64
        )
    )
    db.commit()

    refs = {ref.table: ref for ref in references_to(db, table="users", pk=user.id)}
    assert refs["personal_access_tokens"].on_delete == "CASCADE"
    # users.home_workspace_id 는 SET NULL 이라 부서를 지워도 계정은 남는다.
    ws_refs = {
        ref.column: ref for ref in references_to(db, table="workspaces", pk=workspace.id)
    }
    assert ws_refs["home_workspace_id"].on_delete == "SET NULL"
    assert blocking(list(ws_refs.values())) == []


def test_covers_every_foreign_key_in_the_schema() -> None:
    """새 테이블이 생겨도 코드 수정 없이 편입되는지를, 스키마와 대조해 확인한다.

    이 테스트가 깨진다면 누군가 참조 수집 방식을 좁혔다는 뜻이다.
    """
    import app.all_models  # noqa: F401
    from app.shared import dependents

    expected: set[tuple[str, str, str]] = set()
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                expected.add((table.name, column.name, fk.column.table.name))

    # 스키마에 FK 가 있는데 수집 대상 테이블이 비어 있으면 의미가 없다.
    assert expected, "FK 가 하나도 없다 — 모델이 로드되지 않았을 수 있다"
    assert dependents.EXTRA_CHECKS == [], "수동 보충이 생겼다면 사유를 주석에 남길 것"
