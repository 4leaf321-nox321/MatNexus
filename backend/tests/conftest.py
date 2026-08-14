"""테스트 픽스처 — **개발 DB에 붙지 않는다.**

비교표가 RA의 CI화를 막고 있는 원인으로 지목한 항목이다: *"conftest 가 dev DB 에
직접 붙어 격리가 없어 CI 화가 막혀 있다"*. 테스트가 개발 데이터를 지우면 아무도
테스트를 돌리지 않게 되고, 그러면 릴리스 게이트로 승격시킬 수도 없다.

그래서 `<개발DB>_test` 를 따로 만들어 쓰고, 매 테스트 후 테이블을 비운다.
스키마는 `create_all` 로 만든다 — 빠르고, 마이그레이션 경로 자체는 별도
`tests/migrations`(Phase 2)가 검증한다.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.all_models  # noqa: F401  (Base.metadata 채우기)
from app.config import get_settings
from app.database import Base, get_db
from app.main import create_app


def _test_url() -> str:
    url = make_url(get_settings().database_url)
    # str(URL) 은 비밀번호를 '***' 로 마스킹한다. 그대로 쓰면 인증에 실패한다.
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _ensure_database(url_str: str) -> None:
    url = make_url(url_str)
    admin = psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname="postgres",
    )
    admin.autocommit = True
    with admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
        ).fetchone()
        if not exists:
            admin.execute(f"CREATE DATABASE \"{url.database}\" ENCODING 'UTF8'")


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    url = _test_url()
    _ensure_database(url)
    eng = create_engine(url, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        # 서비스가 commit 하므로 롤백으로는 격리되지 않는다. 테이블을 비운다.
        with engine.begin() as conn:
            tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db: Session, engine) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    # 요청 처리 밖에서 DB 를 쓰는 곳(접근 로그 미들웨어)도 테스트 DB 를 보게 한다.
    application.state.session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
    application.dependency_overrides.clear()


ADMIN_PASSWORD = "admin-password-1"


@pytest.fixture
def workspace(db: Session):  # type: ignore[no-untyped-def]
    """기본 부서 하나. 계정은 부서 없이 존재할 수 없다(가입 시 희망 부서를 고른다)."""
    from app.modules.workspaces.models import Workspace

    item = Workspace(slug="metal", name="금속재료팀")
    db.add(item)
    db.commit()
    return item


@pytest.fixture
def admin(db: Session, workspace):  # type: ignore[no-untyped-def]
    from app.modules.accounts.models import User
    from app.modules.auth import security
    from app.modules.workspaces.models import WorkspaceMember

    user = User(
        email="admin",
        password_hash=security.hash_password(ADMIN_PASSWORD),
        display_name="시스템 관리자",
        status="active",
        is_system_admin=True,
        home_workspace_id=workspace.id,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
    db.commit()
    return user


@pytest.fixture
def admin_headers(client: TestClient, admin) -> dict[str, str]:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/auth/login", json={"email": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
