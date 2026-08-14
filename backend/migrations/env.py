"""Alembic 환경 — 접속 정보와 메타데이터를 앱 설정에서 가져온다.

alembic.ini에 DSN을 적지 않는다. 적어 두면 운영 서버에서 .env와 ini 두 곳이
서로 다른 DB를 가리키는 사고가 난다.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.database import Base

# 모든 모델이 Base.metadata에 등록되도록 한 곳에서 모아 import 한다.
# (모듈이 늘어나면 여기에 추가 — 빠뜨리면 autogenerate가 테이블을 지우려 든다)
import app.all_models  # noqa: F401  isort:skip

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
