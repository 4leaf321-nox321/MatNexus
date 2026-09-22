"""서버 현황 응답 모양. **읽기 전용이다** — 여기서 서버를 만지지 않는다."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class HostOut(BaseModel):
    hostname: str
    os: str
    kernel: str
    arch: str
    uptime_seconds: int | None
    """부팅 후 경과. **모르면 `null`** — 0 으로 두면 「방금 켰다」 로 읽힌다."""


class CpuOut(BaseModel):
    model: str
    logical_cpus: int | None
    load_avg_1m: float | None
    """Windows 에는 load average 가 없다. 그때는 `null` 이고 화면이 「—」 를 적는다."""
    load_avg_5m: float | None
    load_avg_15m: float | None


class MemoryOut(BaseModel):
    total_bytes: int | None
    available_bytes: int | None
    used_bytes: int | None
    percent_used: float | None


class DiskOut(BaseModel):
    """디스크 한 칸. **경로마다 다른 드라이브일 수 있다** — 파일 저장소와 프로그램이
    같은 드라이브라는 보장이 없고, 찬 쪽이 어느 쪽인지가 곧 할 일이다."""

    label: str
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float


class ProcessOut(BaseModel):
    pid: int
    rss_bytes: int | None
    python_version: str


class DatabaseOut(BaseModel):
    version: str
    size_bytes: int | None
    """DB 가 쓰는 바이트. 디스크가 찰 때 **어느 쪽이 먹고 있는지**를 가른다."""
    pool: dict[str, int]


class BackupOut(BaseModel):
    """마지막 백업이 언제였나. **안 보이면 없는 것과 같다**(2026-09-05)."""

    configured: bool
    path: str | None
    last_at: datetime | None
    age_hours: float | None
    stale: bool
    problem: str | None


class ServerInfoOut(BaseModel):
    host: HostOut
    cpu: CpuOut
    memory: MemoryOut
    disks: list[DiskOut]
    process: ProcessOut
    database: DatabaseOut
    app_version: str
    backup: BackupOut


class FailedJobOut(BaseModel):
    id: uuid.UUID
    kind: str
    kind_label: str
    attempts: int
    max_attempts: int
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None


class QueueOut(BaseModel):
    """큐 현황. 도는 것은 문제없다 — **보이지 않는 것이 문제였다.**

    재시도 3회를 다 쓰고 `failed` 가 된 작업을 보는 화면도 API 도 없었다. 파싱 실패는
    시험 목록에 상태로라도 보이지만 알림 발송·드리프트 점검은 야간에 조용히 죽고, 알림이
    안 온 사람은 알림이 없었다고 여긴다.
    """

    queued: int
    running: int
    failed: int
    done_last_24h: int
    failures: list[FailedJobOut]


class ExportRequest(BaseModel):
    """물성 데이터 내보내기 요청.

    **기본이 전부다** — 곡선도 문헌도 포함. 받는 쪽이 「구조 없이 데이터만」 을
    원할 때 빠진 것이 있으면 다시 뽑아야 하고, 그 왕복이 며칠이 된다.
    """

    workspace: str | None = None
    """부서 slug 하나. 비우면 **전 부서**. 전역 재료는 어느 쪽이든 함께 나간다."""
    curves: bool = True
    """곡선 점까지 낼까. 끄면 표만 — 용량이 크게 준다."""
    catalog: bool = True
    """문헌 카탈로그까지 낼까. **재배포 판단이 붙는다** — 줄마다 출처와 라이선스가
    함께 나가고, 산출물의 README 가 그 사실을 적는다."""
    note: str | None = Field(default=None, max_length=60)
    """폴더 이름 끝에 붙는 메모. 「누구에게 주려고 뽑았나」 를 적어 두면 반년 뒤에
    그 폴더가 무엇인지 안다."""


class ExportQueuedOut(BaseModel):
    status: str
    folder: str
    """만들어질 폴더 이름. **요청할 때 정해진다** — 큐에서 기다린 만큼 이름이 밀리면
    화면에서 본 것과 폴더가 달라진다."""
    path: str
    message: str


class ExportOut(BaseModel):
    """만들어 둔 내보내기 하나."""

    name: str
    path: str
    size_bytes: int
    generated_at: datetime | None
    workspace: str | None
    curves: bool | None
    catalog: bool | None
    row_total: int
    done: bool
    """manifest 가 있나. **없으면 만드는 중이거나 실패한 것**이다 — 폴더만 있고
    속이 빈 것을 완성으로 보이면 그것을 건넨다."""
