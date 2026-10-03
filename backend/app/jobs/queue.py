"""작업 큐의 조작 — 넣기, 집어가기, 끝내기.

집어가기는 `SELECT ... FOR UPDATE SKIP LOCKED` 로 한다. 워커를 여러 개 띄워도
같은 작업을 두 번 집지 않는다 — 알림이 두 번 가거나 처리가 두 번 도는 것을
DB 가 막아 준다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.models import Job


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    db: Session,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    delay_seconds: int = 0,
    max_attempts: int = 3,
) -> Job:
    """작업을 넣는다. **커밋은 호출부가 한다.**

    도메인 변경과 같은 트랜잭션에 묶기 위해서다. 따로 커밋하면 "가입은 됐는데
    알림 작업은 안 들어간" 또는 그 반대 상태가 생긴다.
    """
    job = Job(
        kind=kind,
        payload=payload or {},
        max_attempts=max_attempts,
        run_after=_now() + timedelta(seconds=delay_seconds),
    )
    db.add(job)
    return job


def claim_next(db: Session, *, worker_id: str) -> Job | None:
    """실행할 작업 하나를 잠그고 가져온다. 없으면 None."""
    job = db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= _now())
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    job.status = "running"
    job.attempts += 1
    job.locked_at = _now()
    job.locked_by = worker_id
    db.commit()
    return job


def complete(db: Session, job: Job) -> None:
    job.status = "done"
    job.finished_at = _now()
    job.last_error = None
    db.commit()


def fail(db: Session, job: Job, error: str, *, backoff_seconds: int = 30) -> None:
    """실패를 기록한다. 한도가 남았으면 뒤로 미뤄 다시 시도한다."""
    job.last_error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = _now()
    else:
        job.status = "queued"
        job.locked_at = None
        job.locked_by = None
        job.run_after = _now() + timedelta(seconds=backoff_seconds * job.attempts)
    db.commit()


def reclaim_stalled(db: Session, *, older_than_seconds: int = 300) -> int:
    """워커가 죽어 running 으로 남은 작업을 되살린다.

    이 함수가 없으면 워커가 강제 종료될 때마다 그 작업이 영원히 running 으로
    남는다 — 콘솔 실행(D9)이라 창을 닫는 일이 실제로 일어난다.

    **시도 한도를 넘었으면 되살리지 않고 실패로 둔다**(2026-10-04). 전에는 늘 되살려서,
    워커를 죽이는 작업(메모리를 다 먹는 큰 파일 하나)이 되살아날 때마다 워커를 다시
    죽였다 — 그 뒤의 작업은 전부 멈춘다. 시도는 `claim_next` 가 센다.
    """
    cutoff = _now() - timedelta(seconds=older_than_seconds)
    stalled = list(
        db.scalars(select(Job).where(Job.status == "running", Job.locked_at < cutoff))
    )
    for job in stalled:
        job.locked_at = None
        job.locked_by = None
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = _now()
            job.last_error = (
                f"워커가 이 작업을 하다 멈췄습니다({job.attempts}번째). 다시 시도하지 않습니다"
                f"(워커를 죽이는 작업일 수 있습니다). 직전 오류: {job.last_error or '없음'}"
            )[:2000]
            continue
        job.status = "queued"
    if stalled:
        db.commit()
    return len(stalled)


def get(db: Session, job_id: uuid.UUID) -> Job | None:
    return db.get(Job, job_id)
