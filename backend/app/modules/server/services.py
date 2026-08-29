"""서버가 선 컴퓨터의 형편 — **디스크가 차기 전에 알아야 한다.**

폐쇄망에 설치해 두고 나면 그 PC 를 아무도 안 본다. 곡선 원본과 그림이 계속
쌓이는데, 「저장소 정리」 는 *우리가 쌓은 것*만 세지 실제 남은 공간은 모른다 —
같은 드라이브에 다른 프로그램이 있으면 그 수는 답이 아니다.

## `/proc` 을 먼저 보고 없으면 Windows 로 간다

참고한 ReportArchive 는 리눅스 전용이라 `/proc/meminfo` 를 읽는다. 여기는
**Windows 에 설치돼 있다.** 그래서 순서를 둔다 — `/proc` 이 있으면 그것을 쓰고
(나중에 리눅스로 옮겨도 그대로 돈다), 없으면 kernel32 를 부른다.

**psutil 을 안 쓴다.** 폐쇄망에서는 의존성 하나가 곧 「wheel 을 어떻게 넣지」 다.
여기서 필요한 것은 넷뿐이고 ctypes 로 닿는다.

## 못 읽으면 0 이 아니라 `null`

모르는 것을 0 으로 채우면 화면이 「메모리가 0 바이트」 라고 적는다. 그것은 값이
아니라 거짓말이다 — 모른다고 말하는 편이 낫다.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":  # pragma: no cover - 리눅스에서는 이 모듈이 없다
    from ctypes import wintypes

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import version
from app.config import get_settings
from app.database import engine

_KB = 1024


def _proc(path: str) -> str:
    """읽히면 읽고 아니면 빈 문자열. Windows 에는 이 파일들이 없다."""
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def _windows_memory() -> tuple[int, int] | None:
    """전체·가용 물리 메모리. kernel32 의 `GlobalMemoryStatusEx`."""

    class Status(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except (AttributeError, OSError):
        return None


def _memory() -> dict[str, Any]:
    total: int | None = None
    available: int | None = None
    text = _proc("/proc/meminfo")
    if text:
        found: dict[str, int] = {}
        for line in text.splitlines():
            matched = re.match(r"^(\w+):\s+(\d+)\s+kB", line)
            if matched:
                found[matched.group(1)] = int(matched.group(2)) * _KB
        total = found.get("MemTotal")
        # MemAvailable 은 「지금 당장 새 프로세스에 줄 수 있는」 양이다 — page cache 를
        # 뺀 MemFree 보다 사람이 묻는 것에 가깝다.
        available = found.get("MemAvailable", found.get("MemFree"))
    else:
        pair = _windows_memory()
        if pair:
            total, available = pair

    if not total or available is None:
        return {
            "total_bytes": None,
            "available_bytes": None,
            "used_bytes": None,
            "percent_used": None,
        }
    used = total - available
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "percent_used": round(used * 100 / total, 1),
    }


def _uptime() -> int | None:
    text = _proc("/proc/uptime")
    if text:
        try:
            return int(float(text.split()[0]))
        except (ValueError, IndexError):
            return None
    try:
        # 밀리초. 49.7일에서 넘치던 GetTickCount 와 달리 64비트다.
        return int(ctypes.windll.kernel32.GetTickCount64() // 1000)
    except (AttributeError, OSError):
        return None


def _cpu_model() -> str:
    for line in _proc("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return line.partition(":")[2].strip()
    # Windows 는 여기에 모델명을 넣어 둔다. `platform.processor()` 는 「AMD64」 만
    # 주는 때가 많아 뒤로 뺀다.
    return (
        os.environ.get("PROCESSOR_IDENTIFIER", "").strip()
        or platform.processor()
        or "알 수 없음"
    )


def _cpu() -> dict[str, Any]:
    load: tuple[float, float, float] | None = None
    try:
        # Windows 의 `os` 에는 이 함수가 아예 없다 — mypy 도 그것을 안다.
        load = os.getloadavg()  # type: ignore[attr-defined,unused-ignore]
    except (AttributeError, OSError):
        # Windows 에는 load average 라는 것이 없다. **0 으로 채우지 않는다** —
        # 「한가하다」 로 읽힌다.
        load = None
    return {
        "model": _cpu_model(),
        "logical_cpus": os.cpu_count(),
        "load_avg_1m": round(load[0], 2) if load else None,
        "load_avg_5m": round(load[1], 2) if load else None,
        "load_avg_15m": round(load[2], 2) if load else None,
    }


def _disk(label: str, path: Path) -> dict[str, Any] | None:
    try:
        total, used, free = shutil.disk_usage(path)
    except OSError:
        return None
    return {
        "label": label,
        "path": str(path),
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "percent_used": round(used * 100 / total, 1) if total else 0.0,
    }


def _disks() -> list[dict[str, Any]]:
    """**드라이브가 같으면 한 줄로 합친다.** 같은 수를 두 번 보이면 사람은 둘을
    더해서 읽는다."""
    settings = get_settings()
    wanted = [
        ("파일 저장소", Path(settings.filestore_dir)),
        ("프로그램", Path(sys.prefix).parent),
    ]
    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for label, path in wanted:
        row = _disk(label, path)
        if row is None:
            continue
        # 같은 볼륨인지는 전체 크기와 남은 양으로 본다 — 경로만으로는 심볼릭
        # 링크나 마운트가 있을 때 틀린다.
        key = f"{row['total_bytes']}|{row['free_bytes']}"
        if key in seen:
            rows[seen[key]]["label"] += f" · {label}"
            continue
        seen[key] = len(rows)
        rows.append(row)
    return rows


def _windows_rss() -> int | None:
    """이 프로세스가 붙들고 있는 물리 메모리. psapi 의 WorkingSetSize.

    **인자 타입을 선언해야 한다.** `GetCurrentProcess` 는 유사 핸들 `-1` 을 주는데,
    restype 을 안 정하면 ctypes 가 그것을 `c_int` 로 받고 64비트 HANDLE 자리에
    32비트로 잘려 들어간다 — 호출은 실패하고 `GetLastError` 는 0 이라 **아무
    단서도 안 남는다.** 실측(2026-08-29): 조용히 `null` 이 나왔다.
    """

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), ctypes.c_ulong]
        query.restype = wintypes.BOOL

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not query(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    except (AttributeError, OSError):
        return None


def _process() -> dict[str, Any]:
    pid = os.getpid()
    rss: int | None = None
    for line in _proc(f"/proc/{pid}/status").splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                rss = int(parts[1]) * _KB
            break
    if rss is None:
        rss = _windows_rss()
    return {"pid": pid, "rss_bytes": rss, "python_version": sys.version.split()[0]}


def _database(db: Session) -> dict[str, Any]:
    version_text = "알 수 없음"
    size: int | None = None
    try:
        found = db.execute(select(func.current_setting("server_version"))).scalar()
        version_text = str(found) if found else version_text
        size = db.execute(select(func.pg_database_size(func.current_database()))).scalar()
    except Exception:
        pass

    pool: dict[str, int] = {}
    for name in ("size", "checkedout", "checkedin", "overflow"):
        member = getattr(engine.pool, name, None)
        if not callable(member):
            continue
        try:
            value = member()
        except Exception:
            continue
        if isinstance(value, int):
            pool[name] = value
    return {
        "version": version_text,
        "size_bytes": int(size) if size else None,
        "pool": pool,
    }


def info(db: Session) -> dict[str, Any]:
    return {
        "host": {
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "kernel": platform.version(),
            "arch": platform.machine(),
            "uptime_seconds": _uptime(),
        },
        "cpu": _cpu(),
        "memory": _memory(),
        "disks": _disks(),
        "process": _process(),
        "database": _database(db),
        "app_version": version.current(),
    }
