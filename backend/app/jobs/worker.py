"""워커 루프.

별도 프로세스로 돈다(`run_worker.py`). API 프로세스와 분리하는 이유는 단순하다 —
Phase 3의 곡선 처리·피팅은 수십 초가 걸리고, 그것을 요청 처리 안에서 돌리면
브라우저가 기다리다 끊긴다.

콘솔 실행(D9)이라 창을 닫으면 멈춘다. 그때 `running` 으로 남은 작업은
`reclaim_stalled` 이 되살린다.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from types import FrameType

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.jobs import handlers, queue

logger = logging.getLogger(__name__)

POLL_SECONDS = 2
RECLAIM_EVERY_SECONDS = 60

_stop = False


def _request_stop(signum: int, frame: FrameType | None) -> None:
    global _stop
    _stop = True
    logger.info("종료 신호(%s)를 받았습니다. 현재 작업을 끝내고 멈춥니다.", signum)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_once(session: Session | None = None) -> bool:
    """작업 하나를 처리한다. 처리했으면 True.

    테스트가 루프 없이 한 번만 돌릴 수 있게 분리해 둔다. 세션을 넘기면 그것을
    쓴다 — 테스트는 자기 트랜잭션 안에서 확인해야 하기 때문이다.
    """
    db = session or SessionLocal()
    owns_session = session is None
    try:
        job = queue.claim_next(db, worker_id=worker_id())
        if job is None:
            return False

        logger.info("작업 시작 %s (%s, 시도 %s)", job.id, job.kind, job.attempts)
        try:
            handlers.get(job.kind)(db, job.payload)
        except Exception as exc:  # 핸들러의 어떤 실패도 워커를 죽이지 않는다
            logger.exception("작업 실패 %s (%s)", job.id, job.kind)
            db.rollback()
            queue.fail(db, job, f"{type(exc).__name__}: {exc}")
        else:
            queue.complete(db, job)
            logger.info("작업 완료 %s (%s)", job.id, job.kind)
        return True
    finally:
        if owns_session:
            db.close()


def main() -> None:
    handlers.load_all()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    logger.info("워커 시작 %s — 처리 가능한 작업: %s", worker_id(), handlers.known_kinds())
    last_reclaim = 0.0

    while not _stop:
        now = time.monotonic()
        if now - last_reclaim > RECLAIM_EVERY_SECONDS:
            db = SessionLocal()
            try:
                revived = queue.reclaim_stalled(db)
                if revived:
                    logger.warning("멈춰 있던 작업 %s건을 되살렸습니다.", revived)
            finally:
                db.close()
            last_reclaim = now

        if not run_once():
            time.sleep(POLL_SECONDS)

    logger.info("워커를 멈췄습니다.")
