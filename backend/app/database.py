"""DB 세션과 선언적 기반.

제약 이름 규약을 여기서 고정한다. 이름이 자동으로 정해지면 Alembic이
autogenerate에서 제약을 지웠다 만드는 diff를 내고, 마이그레이션 경로 테스트가
매번 흔들린다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,  # 사내망에서 유휴 커넥션이 끊겨도 조용히 재연결
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
