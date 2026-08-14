"""로그 — 콘솔과 파일 양쪽에. 콘솔만으로는 창을 닫는 순간 증거가 사라진다.

D9(콘솔 실행)를 택한 대가를 여기서 갚는다. 개발계획 §9.3.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from app.config import Settings
from app.shared.request_context import get_request_id

_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.app_env == "development" else logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(_FORMAT)
    id_filter = _RequestIdFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(id_filter)
    root.addHandler(console)

    # 자정마다 app.log -> app.log.YYYY-MM-DD 로 넘긴다.
    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "app.log",
        when="midnight",
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(id_filter)
    root.addHandler(file_handler)

    # uvicorn의 기동·오류·접근 로그를 모두 우리 핸들러로 흘린다.
    #
    # 접근 로그를 따로 만들지 않는 이유: uvicorn 줄이 우리 핸들러를 타면
    # _RequestIdFilter가 요청 id를 붙여 주고, 클라이언트 주소까지 함께 남는다.
    # 우리가 미들웨어에서 한 줄 더 찍으면 같은 요청이 두 줄이 될 뿐이다.
    #   16:47:43 INFO [5a820bef03c5] uvicorn.access: 127.0.0.1 - "GET /api/health" 200
    #
    # (uvicorn은 run.py의 access_log 설정이 아니라 `uvicorn.access` 로거의
    #  hasHandlers() 로 발행 여부를 정한다 — 루트에 핸들러가 있으면 켜진다.)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
