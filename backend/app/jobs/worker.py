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

import app.all_models  # noqa: F401  — 모델을 전부 메타데이터에 올린다(아래 설명)
from app.database import SessionLocal
from app.jobs import handlers, queue, schedule

# **워커는 라우터를 안 부른다.** 서버는 `main` 이 라우터를 다 실으면서 모델이 전부
# 따라오지만, 워커는 핸들러가 손대는 모델만 import 한다. 그래서 어느 모델이 워커가
# 모르는 표를 외래키로 가리키는 순간 첫 flush 에서 죽는다:
#
#     NoReferencedTableError: Foreign key associated with column
#     'test_runs.commission_item_id' could not find table 'commission_items'
#
# 실측(2026-09-15, v1.234): 측정 의뢰가 `test_runs` 에 열 하나를 더했더니 CI 스모크의
# 워커가 파싱마다 이 오류로 죽었다 — pytest 는 `app.main` 을 먼저 실어 못 봤고, 서버는
# 멀쩡했고, 화면은 「대기」 만 보였다. 배포용 스크립트에 걸어 둔 규칙(AGENTS.md,
# `test_scripts_models`)이 워커에도 똑같이 필요했다.

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

        # **이름을 먼저 떼어 둔다.** 핸들러가 flush 에서 죽으면 세션은 롤백 대기
        # 상태고, 그때 `job.id` 를 읽는 것도 DB 를 건드리는 일이라 또 터진다 —
        # except 절 안에서 터지면 워커가 통째로 죽는다(실측 2026-09-15: 파싱 하나가
        # NoReferencedTableError 로 죽자 워커가 로그 한 줄을 남기다 사라졌고, 그 뒤
        # 모든 시험이 「대기」 로 남았다).
        job_id, job_kind = job.id, job.kind
        logger.info("작업 시작 %s (%s, 시도 %s)", job_id, job_kind, job.attempts)
        try:
            handlers.get(job_kind)(db, job.payload)
        except Exception as exc:  # 핸들러의 어떤 실패도 워커를 죽이지 않는다
            db.rollback()
            logger.exception("작업 실패 %s (%s)", job_id, job_kind)
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
                # 주기 작업. **같은 타이머에 얹는다** — 6시간짜리를 위해 타이머를
                # 하나 더 두면 그 둘이 어긋나는 날이 온다.
                due = schedule.enqueue_due(db)
                if due:
                    db.commit()
                    logger.info("주기 작업을 넣었습니다: %s", ", ".join(due))
            finally:
                db.close()
            last_reclaim = now

        if not run_once():
            time.sleep(POLL_SECONDS)

    logger.info("워커를 멈췄습니다.")
