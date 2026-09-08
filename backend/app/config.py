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
    extensions_dir: Path = BACKEND_DIR / "extensions"
    """물성 확장이 사는 폴더. **폴더에 넣으면 읽는다**(`matcore.extensions`).

    새 물성을 더할 때 중심 코드에 이름을 적지 않아도 되게 하는 자리다. 여러
    사람이 각자 물성을 붙여도 같은 줄을 서로 고치지 않는다."""
    """곡선 Parquet와 장비 원본이 사는 곳. DB에는 경로와 해시만 둔다(D10)."""

    backup_dir: Path | None = None
    """백업 스크립트(`scripts/deploy/backup.ps1`)가 덤프를 남기는 폴더. 서버 화면이
    여기서 **마지막 백업 시각**을 읽는다 — 안 보이면 없는 것과 같다(2026-09-05)."""

    disk_alert_percent: int = 85
    """파일 저장소 드라이브 사용률이 이 위면 홈의 「남은 일」 에 경고가 선다."""

    login_delay_after: int = 5
    """같은 계정의 로그인 실패가 이 횟수부터 응답을 늦춘다. **잠그지 않는다** —
    관리자 복구가 외길인 시스템에서 잠금은 자해다."""
    login_delay_step_seconds: int = 2
    login_delay_max_seconds: int = 30
    login_failure_window_minutes: int = 15
    """이 시간 안의 실패만 센다. 지나면 처음부터."""

    filestore_retention_days: int = 30
    """소프트 삭제한 시험의 **파일**을 며칠 뒤에 지울지.

    행은 남긴다 — 이름과 계보는 조회할 수 있어야 한다. 파일만 지운다.

    이 값이 필요한 이유: 소프트 삭제는 행을 남기므로 그 파일은 오펀 탐색으로
    **영원히 안 잡힌다**(오펀은 정의상 DB 에 없는 것이다). 실측으로 확인했다 —
    지운 시험 2건의 파일이 그대로 남아 있었다."""

    max_upload_bytes: int = 50 * 1024 * 1024
    """업로드 한도의 전역 기본값. 시험 종류가 `max_upload_bytes` 로 덮을 수 있다.

    한도를 두는 이유는 디스크가 아니라 **거절 시점**이다. 한도가 없으면 잘못 고른
    수 GB 파일을 끝까지 다 받은 뒤에야 파싱이 실패하고, 그때는 이미 디스크를 쓴
    뒤다. `filestore.save_stream` 은 읽는 도중에 멈춘다."""

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

    # --- 의미 검색 --------------------------------------------------------
    #
    # **셋 다 없어도 검색은 돈다.** 「일치·포함·비슷」 은 DB 만으로 돌고, 여기 것들이
    # 갖춰지면 「비슷」 에 **뜻이 비슷한 것**이 얹힌다. 선택 부품을 필수로 만들면
    # 엔진이 죽는 날 검색이 통째로 죽는다.

    embedding_backend: str = "off"
    """`off` · `mock` · `ollama`.

    기본이 `off` 인 이유: 설치 안 한 곳에서 켜져 있으면 매 검색이 11434 를 두드리다
    타임아웃한다 — 느려진 이유를 아무도 모른다. 켜는 것은 명시적이어야 한다.
    `mock` 은 텍스트 해시로 결정적 벡터를 만든다(시험·CI 용, 뜻은 없다)."""

    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    """**모델이 내는 차원과 같아야 한다.** 다르면 저장할 때 거절한다 — 섞이면
    거리 계산이 조용히 엉뚱해진다. `setup_ollama.ps1` 이 실제 차원을 찍어 준다."""

    embedding_timeout_s: float = 30.0
    embedding_batch: int = 16
    """한 번에 보낼 청크 수. 크게 잡으면 한 번의 실패로 잃는 것이 많아진다."""


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
