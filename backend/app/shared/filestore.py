"""파일 저장 — 원본과 정규화 결과.

DB 에 넣지 않는 이유는 크기다. 시험 하나가 수천~수만 행이고 장비 파이프라인이
붙으면 계속 늘어난다. 그리고 **배포가 데이터를 복사하지 않아야 한다**(ADR 0003)
— 그래서 저장 위치는 앱 폴더 바깥을 가리키는 `filestore_dir` 이다. 52 는 배포마다
`backend\\uploads` 를 통째로 옮기는데, CAE 시험 데이터에 그 방식은 성립하지 않는다.

파일시스템 저장에는 필연적인 부산물이 있다. **오펀** — DB 행은 지웠는데 파일이
남거나, 파일은 썼는데 행이 안 남는 경우다. 그래서 경로에 소유자(run_id)를 박는다.
파일만 보고도 "이게 누구 것인가"에 답할 수 있어야 정리 잡을 만들 수 있다.

    test-runs/2026/08/<run_id>/source/Example.tra      ← 원본 그대로
    test-runs/2026/08/<run_id>/curves/raw.parquet      ← 정규화 결과

원본을 항상 남기는 이유: 파서를 고쳐 다시 돌릴 수 있어야 하고, 장비가 바뀌어
형식이 달라졌을 때 무엇이 왔었는지 확인할 수 있어야 한다.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.config import get_settings
from app.shared.errors import AppError

#: 한 번에 읽는 크기. 큰 파일을 통째로 메모리에 올리지 않는다.
CHUNK = 1024 * 1024

#: 파일 이름에 남길 문자. 나머지는 `_` 가 된다.
#: 경로 구분자·상위 참조를 원천적으로 없애는 것이 목적이다.
_UNSAFE = re.compile(r"[^0-9A-Za-z가-힣._-]+")

#: Windows 예약 이름. `CON.tra` 같은 파일은 만들 수 없다.
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class Stored:
    """저장 결과. DB 에 그대로 넣는다."""

    relative_path: str
    """`filestore_dir` 기준 상대경로(POSIX). 절대경로를 DB 에 넣으면 서버를
    옮기거나 드라이브 문자가 바뀔 때 전부 못 찾는다."""
    sha256: str
    size: int


class FileTooLarge(AppError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            "MNX-FILES-0001",
            f"파일이 너무 큽니다. 한도는 {limit // (1024 * 1024)}MB 입니다.",
            status=413,
        )


def root() -> Path:
    return get_settings().filestore_dir


def sanitize_filename(name: str) -> str:
    """올린 이름을 그대로 파일명에 쓰지 않는다.

    `..\\..\\.env` 같은 이름이 그대로 경로가 되면 저장소 밖에 쓴다. 확장자는
    남긴다 — 나중에 어떤 형식이었는지 사람이 알아야 한다.
    """
    stem = PurePosixPath(name.replace("\\", "/")).name.strip() or "unnamed"
    cleaned = _UNSAFE.sub("_", stem).strip("._") or "unnamed"
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:180]


def run_dir(run_id: uuid.UUID, when: datetime) -> str:
    """시험 하나가 쓰는 폴더.

    연/월로 나누는 이유: 한 폴더에 수만 개가 쌓이면 탐색기도 백업 스크립트도
    느려진다. 날짜는 등록 시각을 쓴다 — 시험일은 나중에 고쳐질 수 있고, 그러면
    파일이 옮겨져야 하는데 그럴 이유가 없다.
    """
    return f"test-runs/{when:%Y}/{when:%m}/{run_id}"


def resolve(relative: str) -> Path:
    """상대경로를 실제 경로로. **저장소 밖으로 나가면 거부한다.**

    DB 에 들어 있는 값이라 안전하다고 가정하지 않는다. 값이 어떻게든 오염되면
    임의 파일 읽기가 되므로, 최종 경로가 뿌리 안인지 매번 확인한다.
    """
    base = root().resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        raise AppError("MNX-FILES-0002", "잘못된 파일 경로입니다.", status=400)
    return target


def save_stream(
    source: BinaryIO, *, relative_dir: str, filename: str, max_bytes: int
) -> Stored:
    """스트림을 저장하면서 해시와 크기를 함께 구한다.

    한 번 읽으며 셋을 다 한다. 저장한 뒤 다시 읽어 해시를 구하면 큰 파일에서
    두 배로 느리고, 그 사이에 파일이 바뀌면 해시가 내용과 어긋난다.

    한도를 넘으면 **읽던 도중에 멈춘다.** 다 받고 나서 크기를 재면, 한도를 두는
    이유(디스크와 메모리를 지키는 것)가 이미 무너진 뒤다.
    """
    safe = sanitize_filename(filename)
    directory = resolve(relative_dir)
    directory.mkdir(parents=True, exist_ok=True)

    final = directory / safe
    # 쓰는 도중에 죽으면 `.part` 만 남는다. 완성된 파일과 구분돼야 정리 잡이
    # "미완성" 과 "오펀" 을 다르게 다룰 수 있다.
    staging = directory / f"{safe}.part"

    digest = hashlib.sha256()
    size = 0
    try:
        with staging.open("wb") as sink:
            while chunk := source.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLarge(max_bytes)
                digest.update(chunk)
                sink.write(chunk)
        os.replace(staging, final)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    return Stored(
        relative_path=f"{relative_dir}/{safe}",
        sha256=digest.hexdigest(),
        size=size,
    )


def write_bytes(data: bytes, *, relative_dir: str, filename: str) -> Stored:
    """이미 메모리에 있는 것을 저장한다(Parquet 등 우리가 만든 산출물)."""
    safe = sanitize_filename(filename)
    directory = resolve(relative_dir)
    directory.mkdir(parents=True, exist_ok=True)

    final = directory / safe
    staging = directory / f"{safe}.part"
    try:
        staging.write_bytes(data)
        os.replace(staging, final)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    return Stored(
        relative_path=f"{relative_dir}/{safe}",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def read_bytes(relative: str) -> bytes:
    path = resolve(relative)
    if not path.is_file():
        raise AppError("MNX-FILES-0003", "파일을 찾을 수 없습니다.", status=404)
    return path.read_bytes()


def delete_dir(relative_dir: str) -> bool:
    """돌려주는 값은 '실제로 지웠는가'. 없어도 오류가 아니다 — 정리 잡은
    이미 없는 것을 지우려 할 수 있고, 그것은 정상이다."""
    path = resolve(relative_dir)
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    return True


def existing_run_dirs() -> list[str]:
    """저장소에 실제로 있는 시험 폴더. **오펀 정리 잡이 쓴다.**

    DB 를 훑어 파일을 찾는 방향으로는 오펀을 찾을 수 없다 — 오펀은 정의상 DB 에
    없는 것이다. 반대 방향으로 훑어야 한다.
    """
    base = root()
    runs = base / "test-runs"
    if not runs.is_dir():
        return []
    return [
        f"test-runs/{year.name}/{month.name}/{run.name}"
        for year in sorted(runs.iterdir())
        if year.is_dir()
        for month in sorted(year.iterdir())
        if month.is_dir()
        for run in sorted(month.iterdir())
        if run.is_dir()
    ]
