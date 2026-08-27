"""기동 진입점.

FastAPI는 ASGI라 52가 쓰는 waitress(WSGI)를 쓸 수 없다. uvicorn으로 띄운다.
개발에서는 reload, 운영에서는 워커 수를 설정에서 읽는다.

## 포트가 이미 물려 있으면 멈춘다

**실측으로 나온 규칙이다(2026-08-28).** 같은 PC 에 운영 설치본이 함께 있었고 둘 다
8010 을 썼다. 개발 백엔드를 내린 순간 프론트의 프록시가 **운영 v1.115.0 에 그대로
붙었고**, 화면은 「존재하지 않는 엔드포인트」 만 말했다. 서버가 죽은 것도 코드가
틀린 것도 아니어서 볼 곳이 어디에도 없었다.

포트는 이제 갈라 뒀지만(개발 8011 · 운영 8010), 그것만으로는 부족하다 — 개발
서버를 두 번 띄우면 같은 일이 다시 난다. 그래서 **뜨기 전에 확인하고, 물려
있으면 누가 물었는지 찍고 멈춘다.**

우리가 그 포트에 못 붙는데도 uvicorn 이 조용히 뜨는 것이 문제의 핵심이다. 그러면
「띄웠다」 고 생각한 사람과 실제로 답하는 프로세스가 달라진다.
"""

from __future__ import annotations

import socket
import sys

import uvicorn

from app.config import get_settings


def _who(host: str, port: int) -> str | None:
    """그 포트에 이미 누가 있나. 있으면 **무엇인지까지** 알아본다.

    이름을 못 알아내도 막는 것은 같다 — 알아내기는 거들기이지 판단이 아니다.
    """
    probe = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        if sock.connect_ex((probe, port)) != 0:
            return None  # 아무도 없다

    # **누가 물었는지 말해 준다.** 「이미 쓰는 중」 만으로는 무엇을 내려야 하는지
    # 모른다 — 오늘 걸린 것이 정확히 그 자리였다(운영인지 개발인지 몰랐다).
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(
            f"http://{probe}:{port}/api/health", timeout=1.0
        ) as response:
            said = json.load(response)
        return f"MatNexus {said.get('version', '(버전 모름)')}"
    except Exception:
        return "무언가"


def main() -> None:
    settings = get_settings()
    dev = settings.app_env == "development"

    held = _who(settings.host, settings.port)
    if held is not None:
        print(
            f"""
    ================================================================
      포트 {settings.port} 을 이미 {held} 가 쓰고 있습니다.

      그대로 띄우면 «띄웠다고 생각한 서버»와 «실제로 답하는 서버»가
      달라집니다. 화면은 옛 버전을 보여 주고, 무엇이 잘못됐는지
      볼 곳이 없습니다.

      그것을 내리거나, 이 서버의 PORT 를 .env 에서 바꾸세요.
      개발은 8011, 운영(C:\\Server\\MatNexus)은 8010 입니다.
    ================================================================
    """,
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(
        f"""
    ================================================================
      MatNexus API
      env      : {settings.app_env}
      bind     : http://{settings.host}:{settings.port}
      docs     : http://localhost:{settings.port}/api/docs
      logs     : {settings.log_dir}
    ================================================================
    """
    )
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=dev,
        log_config=None,  # logging_setup이 이미 핸들러를 잡았다
    )


if __name__ == "__main__":
    main()
