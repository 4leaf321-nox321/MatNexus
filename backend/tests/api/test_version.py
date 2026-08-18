"""이 설치가 어느 버전인가.

**전에는 답할 데가 없었다.** `/api/health` 는 `{"status": "ok"}` 만 줬고, OpenAPI
버전은 `0.1.0` 에 하드코딩돼 있었으며, 배포 로그도 버전을 안 남겼다. 태그를
지정하지 않고 배포하면 나중에 무엇이 깔렸는지 되짚을 수 없었다 — 문제가 났을 때
"지금 서버 버전이 뭐냐" 를 못 답하면 원인 찾기가 크게 어려워진다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import version


def test_health_가_버전을_함께_준다(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"] == version.current()
    assert body["version"] != version.UNKNOWN


def test_배포본은_패키지가_넣어_준_값을_쓴다(tmp_path: Path) -> None:
    """**패키지가 자기 버전을 들고 온다.**

    서버에 따로 적어 두는 방식이면 그 기록과 실제 코드가 어긋날 수 있다.
    """
    build_info = tmp_path / "BUILD_INFO.txt"
    build_info.write_text("python=3.13\nversion=v9.9.9\n", encoding="utf-8")

    original = version.BACKEND_DIR
    try:
        version.BACKEND_DIR = tmp_path / "backend"
        assert version._from_build_info() == "v9.9.9"
    finally:
        version.BACKEND_DIR = original


def test_개발_중에는_package_json_을_본다() -> None:
    """auto-tag 워크플로도 같은 파일을 본다 — 정본이 하나여야 어긋나지 않는다."""
    assert (version._from_package_json() or "").startswith("v")


def test_어디서도_못_찾으면_모른다고_말한다(tmp_path: Path) -> None:
    """**0.1.0 같은 그럴듯한 거짓말을 하지 않는다.** 하드코딩된 버전이 실제와
    다르면, 그것을 믿고 원인을 엉뚱한 데서 찾게 된다."""
    original = version.BACKEND_DIR
    version.current.cache_clear()
    try:
        version.BACKEND_DIR = tmp_path / "nowhere" / "backend"
        assert version.current() == version.UNKNOWN
    finally:
        version.BACKEND_DIR = original
        version.current.cache_clear()
