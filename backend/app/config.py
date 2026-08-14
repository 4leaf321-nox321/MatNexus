"""설정 — DB행 → 환경변수 → 기본값 3단 fallback.

세 번째 단(DB행)은 아직 테이블이 없어 비어 있지만, 자리를 지금 만들어 둔다.
자주 바뀌는 값(워커 수·타임아웃·임계값)을 나중에 관리 화면에서 고치려면
읽는 지점이 한 곳이어야 하기 때문이다. 65는 os.getenv 45개가 코드에 흩어져
있어 값 하나를 바꾸려면 재배포해야 한다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # utf-8-sig 로 읽는다. BOM 이 붙은 .env 는 **첫 줄 키만 조용히 무시된다** —
    # `APP_ENV` 가 `﻿APP_ENV` 가 되어 기본값으로 떨어진다.
    #
    # 실측: install.ps1 이 PowerShell 5.1 의 `Set-Content -Encoding utf8` 로 .env 를
    # 쓰자 BOM 이 붙었고, 배포된 앱이 production 이 아니라 development 로 떠서
    # reload 가 켜진 채 돌았다(리로드 자식 프로세스가 폴더를 잡아 배포까지 막았다).
    # 서버에서 메모장으로 .env 를 고쳐도 같은 일이 생기므로 읽는 쪽에서 흡수한다.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8-sig", extra="ignore"
    )

    app_env: str = "development"
    """development | production. 기동 방식과 로그 수준을 가른다."""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/matnexus"

    host: str = "0.0.0.0"
    port: int = 8010
    """8010 고정. 사내 개발 PC에서 5173·5174·3000~3010은 다른 플랫폼이 쓰고 있다.

    0.0.0.0 은 IPv4 전역 바인딩이라 localhost(::1) 로는 닿지 않는다.
    확인은 127.0.0.1 로 한다.
    """

    log_dir: Path = BACKEND_DIR / "logs"
    log_retention_days: int = 30

    filestore_dir: Path = BACKEND_DIR / "filestore"
    """곡선 Parquet와 장비 원본이 사는 곳. DB에는 경로와 해시만 둔다(D10)."""

    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    """존재하면 API와 같은 프로세스가 SPA를 서빙한다. 개발 중에는 없다."""

    jwt_secret: str = "dev-only-insecure-secret-change-me"
    """운영에서는 install.ps1 이 난수로 만들어 .env 에 넣는다. §9.1

    기본값이 운영에 새어 나가면 아무나 토큰을 위조할 수 있으므로,
    app_env=production 이면서 이 값이 그대로면 기동을 거부한다(main.py)."""

    access_token_minutes: int = 720  # 12시간
    refresh_token_days: int = 30
    refresh_cookie_name: str = "mnx_refresh"
    refresh_cookie_secure: bool = False
    """사내망 http 배포가 기본이라 False. https 로 서비스하면 True 로 올린다.
    (True 인데 http 로 접속하면 브라우저가 쿠키를 버려 로그인이 유지되지 않는다)"""

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5190", "http://127.0.0.1:5190"]
    )
    """개발 서버(Vite)용. 배포에서는 동일 출처라 필요 없다."""


class RuntimeSettingProvider(Protocol):
    """DB 기반 런타임 설정의 자리. Phase 1에서 runtime_settings 테이블이 구현한다."""

    def get(self, key: str) -> str | None: ...


class _NullProvider:
    def get(self, key: str) -> str | None:
        return None


_provider: RuntimeSettingProvider = _NullProvider()


def set_runtime_provider(provider: RuntimeSettingProvider) -> None:
    global _provider
    _provider = provider


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_setting(key: str) -> str | None:
    """3단 fallback으로 값 하나를 읽는다. DB행이 있으면 환경변수를 이긴다."""
    from_db = _provider.get(key)
    if from_db is not None:
        return from_db
    value = getattr(get_settings(), key, None)
    return None if value is None else str(value)
