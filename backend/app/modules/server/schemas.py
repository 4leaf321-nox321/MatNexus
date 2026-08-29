"""서버 현황 응답 모양. **읽기 전용이다** — 여기서 서버를 만지지 않는다."""

from __future__ import annotations

from pydantic import BaseModel


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


class ServerInfoOut(BaseModel):
    host: HostOut
    cpu: CpuOut
    memory: MemoryOut
    disks: list[DiskOut]
    process: ProcessOut
    database: DatabaseOut
    app_version: str
