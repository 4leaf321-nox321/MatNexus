"""SP 코어 창구에 닿는 주소와 토큰 — **화면(외부 연동)이 먼저, 없으면 `.env`**(2026-10-27).

처음(ADR 0063)에는 `.env` 의 `SP_CORE_URL` · `SP_CORE_TOKEN` 만 읽었다. 운영에서
TestScope 는 「관리 > 외부 연동」 화면으로 붙였는데 SP 는 서버 파일을 고치고 서비스를 다시
띄워야 해서, 사람이 어디서 넣는지 찾지 못했다(사용자). 이제 같은 화면에서 넣고 DB 에
봉인해 둔다. 받기(워커)는 **부를 때마다** 여기서 읽으므로 재기동이 필요 없다.

`.env` 는 계속 읽는다 — 이미 그렇게 넣은 설치가 배포 한 번에 끊기면 안 된다. 화면에 주소와
이 서버가 풀 수 있는 토큰이 다 있으면 화면이 이긴다.

받기(`sp_core`)와 화면(`integrations`)이 함께 쓰는 판정이라 여기 둔다 — 모듈끼리는 직접 부르지
않는다(AGENTS).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.integrations.models import IntegrationConnection
from app.shared import secretbox

SYSTEM = "sp_core"
#: 코어 창구의 끝 — SP 연동 지침서 §4.2.
CORE_SUFFIX = "/api/core"


@dataclass(frozen=True)
class Connection:
    url: str
    """코어 창구(`…/api/core`, 끝 슬래시 없음)."""
    token: str
    source: str
    """`screen`(외부 연동 화면) · `env`(서버 `.env`)."""


def core_url(raw: str) -> str:
    """주소를 코어 창구로 맞춘다 — SP 화면 주소나 `…/api` 를 그대로 붙여 넣는 일이 흔하다."""
    url = raw.strip().rstrip("/")
    if not url or url.endswith(CORE_SUFFIX):
        return url
    if url.endswith("/api"):
        return url + "/core"
    return url + CORE_SUFFIX


def from_screen(db: Session) -> Connection | None:
    row = db.scalar(
        select(IntegrationConnection).where(IntegrationConnection.system == SYSTEM)
    )
    if row is None or not row.base_url:
        return None
    token = secretbox.unseal(row.token_sealed)
    return Connection(row.base_url, token, "screen") if token else None


def from_env() -> Connection | None:
    settings = get_settings()
    if not (settings.sp_core_url and settings.sp_core_token):
        return None
    return Connection(settings.sp_core_url.strip().rstrip("/"), settings.sp_core_token, "env")


def connection(db: Session) -> Connection | None:
    """받기에 쓸 주소 · 토큰 — 화면이 먼저. 둘 다 없으면 None(받지 않는다)."""
    return from_screen(db) or from_env()
