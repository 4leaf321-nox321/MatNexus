"""운영 지표 — **보여 주지만 알려 주지 않던 것들을 한 곳에서 센다.**

디스크 사용률은 서버 화면에, 보존기간 지난 소프트 삭제는 저장소 리포트에, 실패한
작업은 아무 데도 없었다(2026-09-05 점검). 운영자는 그 화면들을 평소에 안 연다 —
차는 날은 갑자기 온다. 홈의 「남은 일」 과 서버 화면이 **같은 함수**로 세야 두 자리의
숫자가 갈리지 않는다. 그래서 `shared` 에 둔다(통계 모듈과 서버 모듈이 함께 부른다).

**숫자는 서버가 센다.** 목록을 받아 화면이 세면 상한에 걸린 순간 조용히 틀린다.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.models import Job
from app.modules.tests.models import TestRun
from app.shared import filestore

#: 백업이 이보다 오래됐으면 「밀렸다」. 매일 03:00 이 기본이라 하루 반이면 한 번 빠진 것이다.
BACKUP_STALE_HOURS = 36


def disk_percent_used() -> float | None:
    """파일 저장소가 있는 드라이브의 사용률.

    못 읽으면 `None` — 0 으로 두면 「여유 있다」 로 읽힌다.
    """
    try:
        total, used, _free = shutil.disk_usage(filestore.root())
    except OSError:
        return None
    if total <= 0:
        return None
    return round(used / total * 100, 1)


def failed_job_count(db: Session) -> int:
    """재시도를 다 쓰고 `failed` 로 남은 작업. 야간에 조용히 죽은 것이 여기 쌓인다."""
    return int(
        db.scalar(select(func.count()).select_from(Job).where(Job.status == "failed")) or 0
    )


def expired_deleted_run_count(db: Session, *, retention_days: int | None = None) -> int:
    """보존기간이 지난 소프트 삭제 시험. **치우는 손이 없어** 디스크가 조용히 찬다.

    바이트는 안 센다 — 폴더 크기는 파일시스템을 걸어야 하고, 홈은 매번 열린다. 몇 건인지가
    「밀리고 있다」 는 사실을 말하기에 충분하고, 크기는 저장소 정리 화면이 센다.
    """
    keep_days = (
        retention_days
        if retention_days is not None
        else get_settings().filestore_retention_days
    )
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    return int(
        db.scalar(
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.deleted_at.is_not(None), TestRun.deleted_at < cutoff)
        )
        or 0
    )


@dataclass(frozen=True)
class BackupStatus:
    """마지막 백업이 언제였나. **안 보이면 없는 것과 같다.**"""

    configured: bool
    path: str | None
    last_at: datetime | None
    age_hours: float | None
    stale: bool
    problem: str | None


def backup_status(*, now: datetime | None = None) -> BackupStatus:
    """`BACKUP_DIR` 에서 가장 최근 `*.dump` 의 mtime 을 읽는다.

    백업 스크립트(`scripts/deploy/backup.ps1`)가 `<root>/db/db-<시각>.dump` 로 남기고,
    옛 배치(`<root>/<시각>/db.dump`)도 같은 규칙으로 잡힌다 — 이름이 아니라 확장자로 본다.
    설정이 없으면 「백업이 없다」 가 아니라 「설정이 없다」 로 말한다: 둘은 다른 일이다.
    """
    settings = get_settings()
    root = settings.backup_dir
    if root is None:
        return BackupStatus(
            configured=False,
            path=None,
            last_at=None,
            age_hours=None,
            stale=True,
            problem=(
                "BACKUP_DIR 설정이 없습니다 — backend\.env 에 백업 폴더를 적으세요. "
                "예: BACKUP_DIR=D:\MatNexus-backup"
            ),
        )
    base = Path(root)
    if not base.is_dir():
        return BackupStatus(
            configured=True,
            path=str(base),
            last_at=None,
            age_hours=None,
            stale=True,
            problem="백업 폴더가 없습니다. 백업 스크립트가 한 번도 돌지 않았습니다.",
        )
    newest: float | None = None
    for item in base.rglob("*.dump"):
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    if newest is None:
        return BackupStatus(
            configured=True,
            path=str(base),
            last_at=None,
            age_hours=None,
            stale=True,
            problem="백업 폴더에 덤프가 없습니다. 백업 스크립트가 한 번도 돌지 않았습니다.",
        )
    last = datetime.fromtimestamp(newest, tz=UTC)
    moment = now or datetime.now(UTC)
    age = round((moment - last).total_seconds() / 3600, 1)
    stale = age > BACKUP_STALE_HOURS
    return BackupStatus(
        configured=True,
        path=str(base),
        last_at=last,
        age_hours=age,
        stale=stale,
        problem=(
            f"마지막 백업이 {age:.0f}시간 전입니다 — 작업 스케줄러가 돌고 있는지 보세요."
            if stale
            else None
        ),
    )
