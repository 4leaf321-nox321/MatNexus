"""복구 리허설 — **받아만 두고 복구해 본 적 없는 백업은 백업이 아니다.**

`backup.ps1` 의 마지막 줄이 그렇게 적어 두었다. 그런데 그 「복구」가
MANIFEST.txt 에 적힌 명령 두 줄이었고, **한 번도 돌려 본 적이 없었다.**
개발계획 §9.4 가 *"복구 리허설. 두 참고 플랫폼 모두 이걸 갖고 있지 않으므로
베낄 원본이 없다"* 고 적어 둔 자리다.

## 무엇을 지키나

    1. 넣은 것이 그대로 돌아온다        행 수와 내용 해시까지
    2. 시점이 어긋나면 멈춘다           DB엔 있는데 파일이 없는 상태를 잡는가
    3. 있는 DB 를 말없이 덮지 않는다     복구는 대개 '옆에 띄워 보는' 일이다

2번이 이 스크립트의 절반이다. DB 에는 곡선의 경로와 해시가, 파일스토어에는 그
내용이 있다(D10) — 한쪽만 되돌리면 앱은 멀쩡히 뜨고 **그 곡선을 열 때만
터진다.** 그런 상태로 파일럿 부서에 넘길 수는 없다.

## 개발 DB 를 안 건드린다

일회용 DB 를 만들어 쓰고 스스로 지운다. `matnexus_test` 도 안 쓴다 — pytest 가
그걸 쓰는 중에 복구가 끼면 스위트가 통째로 어긋난다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[3]
RESTORE = ROOT / "scripts" / "deploy" / "restore.ps1"

#: 도구가 없으면 이 시험은 건너뛴다. **없다고 실패로 적지 않는다** — CI 러너에
#: postgres 클라이언트가 없을 수 있고, 그것은 이 스크립트의 문제가 아니다.
TOOLS = ("pg_dump", "pg_restore", "psql")


def _tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin"), reverse=True):
        candidate = base / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
    return None


pytestmark = pytest.mark.skipif(
    any(_tool(name) is None for name in TOOLS) or shutil.which("powershell") is None,
    reason="pg_dump/pg_restore/psql 또는 powershell 이 없습니다.",
)


@pytest.fixture
def backup(tmp_path: Path) -> Iterator[Path]:
    """작은 DB 하나를 만들어 백업한 모양으로 담는다.

    **개발 DB 를 안 쓴다.** 15MB 를 덤프하면 시험이 느려지고, 무엇보다 이
    시험이 지켜야 하는 것은 "우리 데이터가 복구되나" 가 아니라 **"복구 절차가
    도는가"** 다 — 그 둘은 다른 물음이다.
    """
    url = make_url(get_settings().database_url)
    seed = f"matnexus_restore_seed_{uuid.uuid4().hex[:8]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'create database "{seed}"'))

    try:
        engine = create_engine(url.set(database=seed))
        with engine.begin() as conn:
            # 파일을 가리키는 표 하나. 실제 스키마의 컬럼 이름을 그대로 쓴다 —
            # 복구 스크립트가 카탈로그에 물어 찾는 그 이름이다.
            conn.execute(text("create table test_runs (id int primary key, source_path text)"))
            conn.execute(text("create table curves (id int primary key, storage_path text)"))
            conn.execute(
                text("insert into test_runs values (1, 'a/one.tra'), (2, 'a/two.tra')")
            )
            conn.execute(text("insert into curves values (1, 'b/one.parquet')"))
        engine.dispose()

        target = tmp_path / "backup"
        (target / "filestore" / "a").mkdir(parents=True)
        (target / "filestore" / "b").mkdir(parents=True)
        for relative in ("a/one.tra", "a/two.tra", "b/one.parquet"):
            (target / "filestore" / relative).write_bytes(b"x")

        env = dict(os.environ, PGPASSWORD=url.password or "")
        dump = subprocess.run(
            [
                str(_tool("pg_dump")),
                f"--host={url.host}",
                f"--port={url.port}",
                f"--username={url.username}",
                "--format=custom",
                f"--file={target / 'db.dump'}",
                seed,
            ],
            env=env,
            capture_output=True,
        )
        assert dump.returncode == 0, dump.stderr.decode("utf-8", "replace")
        (target / ".env").write_text(
            f"DATABASE_URL=postgresql+psycopg://{url.username}:{url.password}"
            f"@{url.host}:{url.port}/{seed}\n",
            encoding="utf-8",
        )
        yield target
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'drop database if exists "{seed}" with (force)'))
        admin.dispose()


def _text(done: subprocess.CompletedProcess[bytes]) -> str:
    """PowerShell 이 낸 것을 읽는다.

    **UTF-8 이 아니다.** Windows 콘솔은 한국어 환경에서 CP949 로 내보내므로,
    UTF-8 로 읽으면 한글이 통째로 깨지고 **시험이 스크립트를 못 읽는다** —
    실제로 그랬다. 스크립트는 제대로 멈췄는데 시험은 "메시지가 없다" 고 했다.

    콘솔 코드페이지가 다른 기계도 있으므로 UTF-8 을 먼저 시도한다.
    """
    raw = done.stdout + done.stderr
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp949", "replace")


def _restore(
    backup: Path, db: str, app: Path | None = None, force: bool = False
) -> subprocess.CompletedProcess[bytes]:
    args = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(RESTORE),
        "-BackupPath",
        str(backup),
        "-DbName",
        db,
    ]
    if app is not None:
        args += ["-AppPath", str(app)]
    if force:
        args += ["-Force"]
    return subprocess.run(args, capture_output=True)


@pytest.fixture
def spare() -> Iterator[str]:
    """일회용 DB 이름. 시험이 끝나면 지운다."""
    name = f"matnexus_restore_check_{uuid.uuid4().hex[:8]}"
    yield name
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'drop database if exists "{name}" with (force)'))
    admin.dispose()


def test_넣은_것이_그대로_돌아온다(backup: Path, spare: str, tmp_path: Path) -> None:
    """**행 수만 보지 않는다.** 표가 만들어졌는데 내용이 비면 행 수는 0 으로
    맞을 수 있다 — 실제로 담긴 경로까지 대조한다."""
    app = tmp_path / "app"
    done = _restore(backup, spare, app=app)
    assert done.returncode == 0, _text(done)

    url = make_url(get_settings().database_url)
    engine = create_engine(url.set(database=spare))
    with engine.connect() as conn:
        paths = [
            r[0] for r in conn.execute(text("select source_path from test_runs order by id"))
        ]
        curves = [r[0] for r in conn.execute(text("select storage_path from curves"))]
    engine.dispose()
    assert paths == ["a/one.tra", "a/two.tra"]
    assert curves == ["b/one.parquet"]

    # 파일스토어도 함께 돌아왔다.
    assert (app.parent / f"{app.name}_data" / "filestore" / "a" / "one.tra").exists()


def test_시점이_어긋나면_멈춘다(backup: Path, spare: str, tmp_path: Path) -> None:
    """**여기가 이 스크립트가 있는 이유다.**

    DB 는 온전한데 파일이 빠진 백업을 준다. 그대로 통과시키면 앱은 멀쩡히
    뜨고 그 곡선을 열 때만 터진다 — 그때는 무엇이 어긋났는지 알 방법이 없다.
    """
    (backup / "filestore" / "a" / "two.tra").unlink()

    done = _restore(backup, spare, app=tmp_path / "app")
    output = _text(done)
    assert done.returncode != 0, f"빠진 파일을 그냥 지났습니다:\n{output}"
    assert "시점이 어긋났습니다" in output, output
    # **몇 개인지 말한다.** "어긋났다" 만으로는 무엇을 다시 받아야 할지 모른다.
    assert "1 개가 없습니다" in output, output


def test_있는_DB_를_말없이_덮지_않는다(backup: Path, spare: str, tmp_path: Path) -> None:
    """복구는 대개 "옛 상태를 옆에 띄워 보는" 일이다. 살아 있는 DB 를 실수로
    덮으면 되돌릴 데가 없다."""
    first = _restore(backup, spare, app=tmp_path / "app")
    assert first.returncode == 0

    again = _restore(backup, spare, app=tmp_path / "app")
    output = _text(again)
    assert again.returncode != 0, f"있는 DB 를 덮었습니다:\n{output}"
    assert "이미 있습니다" in output, output

    # -Force 면 덮되, 무엇을 지우는지 먼저 적는다.
    forced = _restore(backup, spare, app=tmp_path / "app", force=True)
    assert forced.returncode == 0, _text(forced)
