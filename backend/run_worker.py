"""워커 기동 진입점.

API 와 **별도 프로세스**로 돈다. 창을 하나 더 열어 실행한다.

    .\run_worker.ps1

콘솔 실행(D9)이라 창을 닫으면 멈춘다. 그때 처리 중이던 작업은 다음 기동 때
`reclaim_stalled` 이 되살린다 — 영영 `running` 으로 남지 않는다.
"""

from __future__ import annotations

from app.config import get_settings
from app.jobs.worker import main
from app.logging_setup import setup_logging


def run() -> None:
    settings = get_settings()
    setup_logging(settings)
    print(
        f"""
    ================================================================
      MatNexus 워커
      env      : {settings.app_env}
      logs     : {settings.log_dir}
    ================================================================
    """
    )
    main()


if __name__ == "__main__":
    run()
