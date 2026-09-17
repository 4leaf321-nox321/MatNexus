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
    # **연결 시도는 기다리다 끊는다.** psycopg 의 기본은 무한 대기다 — 실측(2026-09-10,
    # 두 번): 사내망에서 DB 연결이 잠깐 안 되자 백엔드가 요청을 받지 않는 채로 남았다.
    # 연결 하나가 매달리면 그 요청을 든 스레드가 영영 안 돌아오고, 그런 것이 쌓이면
    # 서버 전체가 멈춘 것처럼 보인다. 10초면 정상 연결(수 ms)에는 넉넉하고, 매달린
    # 것은 오류로 바뀌어 `/api/health` 가 503 을 낼 수 있다.
    #
    # **이미 맺은 연결이 조용히 죽는 것은 keepalive 가 잡는다.** `pool_pre_ping` 은 풀에서
    # 꺼낼 때만 살펴본다 — 질의가 도는 도중에 망이 끊기면 그 스레드는 응답을 영영 기다린다
    # (윈도우 TCP 기본 재전송은 십수 분). keepalive 를 켜면 30초 놀다가 10초 간격으로 세 번
    # 찔러 보고 끊긴 것으로 판정한다 — 1분 안에 오류가 나고 풀이 새 연결을 맺는다.
    # `keepalives_count` 는 윈도우 libpq 가 무시하지만(문서대로) 넣어 둔다 — 리눅스에서는 쓴다.
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
