"""DB 스키마가 코드보다 뒤처져 있는가 — **기동할 때 한 번 본다.**

## 왜 있는가

개발 중에 마이그레이션이 생기면, 서버를 켜 둔 사람은 그 사실을 **화면의 500 으로**
먼저 만난다. ORM 이 없는 컬럼을 SELECT 하기 때문인데, 오류 메시지는
`MNX-COMMON-0500` 뿐이라 원인이 "DB 가 한 리비전 뒤에 있다" 라는 것을 알 방법이
없다. 실제로 그렇게 겪었다 — 기준정보 화면이 통째로 500 이었고, 옆의 어긋남 점검
패널만 멀쩡했다(그건 새 컬럼을 안 건드리는 쿼리라서).

**운영은 이 문제가 없다.** `deploy.ps1` 이 배포 때마다 `alembic upgrade head` 를
돌린다. 이건 개발 서버를 위한 안내다.

## 막지는 않는다

기동을 실패시키지 않는다. 뒤처진 상태로도 되는 일이 많고(로그인·조회 대부분),
무엇보다 **DB 에 못 붙는 상황에서 서버가 안 뜨면 원인을 볼 화면조차 없다.**
로그로 크게 말하고 넘어간다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

#: `alembic.ini` 는 `backend/` 에 있다. 이 파일은 `backend/app/` 이다.
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def code_head() -> str | None:
    """코드가 갖고 있는 마지막 리비전. 못 읽으면 `None`."""
    try:
        config = Config(str(_ALEMBIC_INI))
        # `alembic.ini` 의 상대 경로는 `backend/` 기준이다. 워커·테스트가 다른
        # 디렉터리에서 켜져도 같은 답이 나와야 한다.
        script_location = config.get_main_option("script_location") or "migrations"
        config.set_main_option("script_location", str(_ALEMBIC_INI.parent / script_location))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # pragma: no cover - 마이그레이션 폴더가 없는 설치
        logger.debug("마이그레이션 head 를 읽지 못했습니다.", exc_info=True)
        return None


def db_revision(engine: Engine) -> str | None:
    """DB 에 찍혀 있는 리비전. 붙지 못하거나 표가 없으면 `None`."""
    try:
        with engine.connect() as connection:
            found = connection.scalar(text("SELECT version_num FROM alembic_version"))
        return str(found) if found is not None else None
    except Exception:
        logger.debug("alembic_version 을 읽지 못했습니다.", exc_info=True)
        return None


def warn_if_behind(engine: Engine) -> str | None:
    """뒤처져 있으면 로그에 크게 남기고 그 head 를 돌려준다.

    같으면(또는 판정할 수 없으면) `None`. 기동을 막지 않는다.
    """
    head = code_head()
    current = db_revision(engine)
    if head is None or current is None or current == head:
        return None

    logger.warning(
        "데이터베이스가 코드보다 뒤처져 있습니다: %s → %s. "
        "`alembic upgrade head` 를 돌리세요. "
        "그전까지는 새 컬럼을 읽는 화면이 500 으로 실패합니다.",
        current,
        head,
    )
    return head
