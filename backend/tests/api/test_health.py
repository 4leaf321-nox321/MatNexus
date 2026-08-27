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


def test_프레임워크가_내는_오류도_같은_봉투에_담긴다() -> None:
    """**실사용에서 걸렸다.** 없는 메서드를 부르면 Starlette 이
    `{"detail": "Method Not Allowed"}` 를 그대로 냈다. 프론트의 오류 파서는
    봉투(`error.message`)를 읽으므로 **오류를 읽다가 오류가 났고**, 화면에는
    원인 대신 `Cannot read properties of undefined (reading 'message')` 가 떴다.

    그러면 사람은 요청이 왜 실패했는지가 아니라 프론트가 깨졌다고 읽는다.
    """
    response = client.put("/api/health")
    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "MNX-COMMON-0405"
    # **우리말로 말한다.** `Method Not Allowed` 한 줄은 사람에게 아무것도 안
    # 알려 준다. 그리고 SPA 폴백이 모든 경로를 GET 으로 잡고 있어서, `/api` 아래
    # 없는 주소를 DELETE 로 부르면 404 가 아니라 여기가 나온다 — 이 문구를 보는
    # 사람은 대개 「서버에 그 기능이 아직 없다」 를 겪는 중이다.
    assert "옛 버전" in body["error"]["message"]
    # **`Allow` 를 떨어뜨리지 않는다** — 어떤 메서드가 되는지 알 방법이 그것뿐이다.
    assert "GET" in response.headers.get("allow", "")
