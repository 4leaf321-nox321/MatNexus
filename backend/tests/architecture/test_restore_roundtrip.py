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
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[3]
RESTORE = ROOT / "scripts" / "deploy" / "restore.ps1"
BACKUP = ROOT / "scripts" / "deploy" / "backup.ps1"

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
def ascii_tmp() -> Iterator[Path]:
    """**ASCII 경로**의 임시 폴더.

    `tmp_path` 를 안 쓴다. pytest 는 시험 이름으로 폴더 이름을 만드는데 이
    저장소의 시험 이름은 한글이고, 그 경로를 `pg_dump.exe` 에 넘기면 **콘솔
    코드페이지가 한국어가 아닌 기계에서 물음표로 바뀌어** 파일을 못 연다.

    실측(2026-08-25): 로컬(CP949)에서는 3건 다 통과하고 CI 러너에서만 깨졌다.
    `.../test_??_??_???_????0/backup/db.dump: No such file or directory`.

    한글 이름 자체는 그대로 둔다 — 시험이 무엇을 지키는지 한국어로 읽히는 것이
    이 저장소의 규율이다. **새어 나가면 안 되는 것은 경로다.**
    """
    made = Path(tempfile.mkdtemp(prefix="matnexus_restore_"))
    # **되돌아가는 것을 여기서 막는다.** `tmp_path` 로 바꾸면 로컬(CP949)에서는
    # 통과하고 CI 에서만 깨진다 — 고친 사람이 그 사실을 볼 수 없는 자리다.
    assert str(made).isascii(), (
        f"임시 경로에 ASCII 밖 글자가 있습니다: {made}. 네이티브 pg_dump 가 "
        f"콘솔 코드페이지에 따라 이 경로를 못 엽니다."
    )
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def backup(ascii_tmp: Path) -> Iterator[Path]:
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

        target = ascii_tmp / "backup"
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
    backup: Path,
    db: str,
    app: Path | None = None,
    force: bool = False,
    port: int | None = None,
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
    if port is not None:
        args += ["-DbPort", str(port)]
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


def test_넣은_것이_그대로_돌아온다(backup: Path, spare: str, ascii_tmp: Path) -> None:
    """**행 수만 보지 않는다.** 표가 만들어졌는데 내용이 비면 행 수는 0 으로
    맞을 수 있다 — 실제로 담긴 경로까지 대조한다."""
    app = ascii_tmp / "app"
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


def test_DbPort_가_백업의_포트를_이긴다(backup: Path, spare: str, ascii_tmp: Path) -> None:
    """새 서버의 PostgreSQL 이 다른 포트일 때 — 백업 .env 는 옛 포트를 들고 온다.

    실측(2026-09-16): `-DbPort 5434` 를 줬는데 5432 로 붙었다. 매개변수 `$DbPort` 와
    스크립트 변수 `$dbPort` 가 PowerShell 에서는 **같은 변수**라 .env 값이 매개변수를
    덮었다. 여기서는 .env 에 엉뚱한 포트를 적어 두고 진짜 포트를 -DbPort 로 준다 —
    덮어쓰기가 안 되면 엉뚱한 포트로 붙다가 실패한다.
    """
    url = make_url(get_settings().database_url)
    env_file = backup / ".env"
    wrong = env_file.read_text(encoding="utf-8").replace(f":{url.port}/", ":1/")
    assert ":1/" in wrong
    env_file.write_text(wrong, encoding="utf-8")

    done = _restore(backup, spare, app=ascii_tmp / "app", port=int(url.port or 5432))
    output = _text(done)
    assert done.returncode == 0, output
    assert f"접속 포트를 바꿉니다: {url.port} (-DbPort)" in output, output
    # **어느 서버에 붙었는지 말한다** — PostgreSQL 이 둘인 서버에서 눈으로 확인하는 줄.
    assert "복구 대상 서버: PostgreSQL" in output and "data_directory=" in output, output


def test_시점이_어긋나면_멈춘다(backup: Path, spare: str, ascii_tmp: Path) -> None:
    """**여기가 이 스크립트가 있는 이유다.**

    DB 는 온전한데 파일이 빠진 백업을 준다. 그대로 통과시키면 앱은 멀쩡히
    뜨고 그 곡선을 열 때만 터진다 — 그때는 무엇이 어긋났는지 알 방법이 없다.
    """
    (backup / "filestore" / "a" / "two.tra").unlink()

    done = _restore(backup, spare, app=ascii_tmp / "app")
    output = _text(done)
    assert done.returncode != 0, f"빠진 파일을 그냥 지났습니다:\n{output}"
    assert "시점이 어긋났습니다" in output, output
    # **몇 개인지 말한다.** "어긋났다" 만으로는 무엇을 다시 받아야 할지 모른다.
    assert "1 개가 없습니다" in output, output


def test_있는_DB_를_말없이_덮지_않는다(backup: Path, spare: str, ascii_tmp: Path) -> None:
    """복구는 대개 "옛 상태를 옆에 띄워 보는" 일이다. 살아 있는 DB 를 실수로
    덮으면 되돌릴 데가 없다."""
    first = _restore(backup, spare, app=ascii_tmp / "app")
    assert first.returncode == 0

    again = _restore(backup, spare, app=ascii_tmp / "app")
    output = _text(again)
    assert again.returncode != 0, f"있는 DB 를 덮었습니다:\n{output}"
    assert "이미 있습니다" in output, output

    # -Force 면 덮되, 무엇을 지우는지 먼저 적는다.
    forced = _restore(backup, spare, app=ascii_tmp / "app", force=True)
    assert forced.returncode == 0, _text(forced)


# ── 파일스토어의 자리 — 앱이 보는 곳(`backend\.env` 의 FILESTORE_DIR) ─────────────────
#
# 실측(2026-09-25): 운영에서 저장소를 다른 드라이브로 옮기려고 .env 만 고치면, 백업은
# `<AppPath>_data\filestore` 를 박아 두고 있어 **옛 폴더를 뜨거나 건너뛰었다** — 새 시험
# 파일이 조용히 백업에서 빠진다. 복구도 옛 자리에 되돌렸고, 이미 있는 폴더에는 그 안에
# `filestore\` 를 한 겹 더 만들었다.


def _app_with_env(app: Path, **lines: str) -> Path:
    """`<app>\backend\.env` 를 적는다 — 스크립트가 읽는 앱의 설정."""
    (app / "backend").mkdir(parents=True, exist_ok=True)
    env = app / "backend" / ".env"
    env.write_text(
        "".join(f"{key}={value}\n" for key, value in lines.items()), encoding="utf-8"
    )
    return env


def test_앱이_보는_저장소로_되돌린다(backup: Path, spare: str, ascii_tmp: Path) -> None:
    """.env 의 FILESTORE_DIR 이 설치의 기본 자리가 아니면 **그쪽으로** 되돌린다."""
    app = ascii_tmp / "app"
    moved = ascii_tmp / "d_drive" / "filestore"
    _app_with_env(app, FILESTORE_DIR=str(moved))

    done = _restore(backup, spare, app=app)
    assert done.returncode == 0, _text(done)
    assert (moved / "a" / "one.tra").exists(), "앱이 보는 자리로 안 돌아왔다"
    assert not (ascii_tmp / "app_data" / "filestore").exists(), "옛 기본 자리에 되돌렸다"


def test_있는_저장소_안에_한_겹_더_넣지_않는다(
    backup: Path, spare: str, ascii_tmp: Path
) -> None:
    """운영 중인 서버에 되돌리는 경우 — 저장소 폴더가 이미 있다. `Copy-Item -Recurse` 는 그
    **안에** `filestore\` 를 만들어 파일이 엉뚱한 자리로 갔고, 검사는 원래 있던 파일을 보고
    통과시켰다. 원래 있던 파일은 지우지 않는다(백업에 없는 것을 지우는 판단은 복구의 일이
    아니다)."""
    app = ascii_tmp / "app"
    store = ascii_tmp / "app_data" / "filestore"
    store.mkdir(parents=True)
    (store / "keep.tra").write_bytes(b"k")

    done = _restore(backup, spare, app=app)
    assert done.returncode == 0, _text(done)
    assert (store / "a" / "one.tra").exists()
    assert (store / "b" / "one.parquet").exists()
    assert not (store / "filestore").exists(), "저장소 안에 filestore 를 한 겹 더 만들었다"
    assert (store / "keep.tra").exists(), "있던 파일을 지웠다"


def test_백업은_앱이_보는_저장소를_뜬다(backup: Path, ascii_tmp: Path) -> None:
    """.env 의 FILESTORE_DIR 을 따라간다 — 옛 기본 자리에 옛 파일이 남아 있어도 그쪽을 안
    본다."""
    dsn = next(
        line
        for line in (backup / ".env").read_text(encoding="utf-8").splitlines()
        if line.startswith("DATABASE_URL=")
    ).removeprefix("DATABASE_URL=")
    app = ascii_tmp / "app"
    moved = ascii_tmp / "d_drive" / "filestore"
    (moved / "a").mkdir(parents=True)
    (moved / "a" / "new.tra").write_bytes(b"n")
    # 옮기기 전의 자리 — 여기를 뜨면 새 파일이 빠진다.
    stale = ascii_tmp / "app_data" / "filestore"
    stale.mkdir(parents=True)
    (stale / "old.tra").write_bytes(b"o")
    _app_with_env(app, DATABASE_URL=dsn, FILESTORE_DIR=str(moved))
    root = ascii_tmp / "backup_root"

    done = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(BACKUP),
            "-AppPath",
            str(app),
            "-BackupRoot",
            str(root),
            "-PgDumpExe",
            str(_tool("pg_dump")),
        ],
        capture_output=True,
    )
    assert done.returncode == 0, _text(done)
    assert (root / "filestore" / "a" / "new.tra").exists(), "앱이 보는 저장소를 안 떴다"
    assert not (root / "filestore" / "old.tra").exists(), "옛 기본 자리를 떴다"
    assert str(moved) in (root / "LAST_BACKUP.txt").read_text(encoding="utf-8-sig")
