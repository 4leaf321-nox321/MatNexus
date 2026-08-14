"""기동 진입점.

FastAPI는 ASGI라 52가 쓰는 waitress(WSGI)를 쓸 수 없다. uvicorn으로 띄운다.
개발에서는 reload, 운영에서는 워커 수를 설정에서 읽는다.
"""

from __future__ import annotations

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    dev = settings.app_env == "development"
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
