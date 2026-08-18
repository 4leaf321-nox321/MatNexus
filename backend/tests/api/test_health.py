"""기동과 오류 규약의 최소 확인."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import version
from app.main import create_app

client = TestClient(create_app(), raise_server_exceptions=False)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    # **버전을 함께 준다.** 원격에서 "지금 서버에 뭐가 깔렸나" 를 물을 수 있는
    # 유일한 자리다 — 값 자체는 tests/api/test_version.py 가 본다.
    assert response.json() == {"status": "ok", "version": version.current()}


def test_request_id_is_returned() -> None:
    """사용자 신고와 로그를 잇는 끈이 모든 응답에 있어야 한다."""
    response = client.get("/api/health")
    assert response.headers.get("X-Request-ID")


def test_unknown_api_path_is_json_404() -> None:
    """없는 엔드포인트가 HTML을 돌려주면 프론트에서 원인이 흐려진다."""
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
