"""BOM 이 붙은 .env 도 정상으로 읽혀야 한다.

실측 사고: install.ps1 이 PowerShell 5.1 의 `Set-Content -Encoding utf8` 로 .env 를
쓰자 BOM 이 붙었고, 첫 줄인 `APP_ENV=production` 이 `﻿APP_ENV` 로 읽혀 무시됐다.
그 결과 배포된 앱이 development 로 떠서 reload 가 켜졌고, 리로드 자식 프로세스가
설치 폴더를 잡아 다음 배포까지 막았다.

서버에서 메모장으로 .env 를 고치면 같은 일이 생기므로(메모장은 UTF-8 BOM 이
기본이다) 읽는 쪽에서 흡수하는 것이 맞다.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings


def _write(path: Path, text: str, *, bom: bool) -> None:
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def test_env_file_with_bom_is_read(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "APP_ENV=production\nPORT=9999\n", bom=True)

    settings = Settings(_env_file=env)  # type: ignore[call-arg]

    assert settings.app_env == "production", "BOM 때문에 첫 줄 키가 무시됐습니다"
    assert settings.port == 9999


def test_env_file_without_bom_is_read(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "APP_ENV=production\nPORT=9999\n", bom=False)

    settings = Settings(_env_file=env)  # type: ignore[call-arg]

    assert settings.app_env == "production"
    assert settings.port == 9999
