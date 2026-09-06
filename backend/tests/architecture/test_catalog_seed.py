"""동봉된 문헌 카탈로그 씨앗이 이관과 맞는가.

**핸드북과 같은 자리에서 같은 실수를 한다.** 코드 배포는 DB 에 행을 넣지 않으므로
씨앗이 따로 실려야 하는데, 씨앗은 릴리스와 따로 늙는다 — 실측(2026-08-31): 운영
가이드가 통째로 비어 있었고 씨앗 파일은 서버에 이미 가 있었다.

여기서 막는 것은 그 다음 판이다. 이관이 표를 하나 더 읽게 되거나 원본 스키마가
바뀌면, 씨앗만 옛것으로 남는다. 그러면 **배포는 성공하고** 카탈로그 절만
「원본에 그 표가 없습니다」 로 조용히 거절된다(실패해도 배포를 안 세우니까).
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.modules.catalog.importer import EXPECTED_COLUMNS as CATALOG_TABLES
from app.modules.metrology.importer import EXPECTED_COLUMNS as METROLOGY_TABLES
from app.shared.mt_import import check_schema

BACKEND = Path(__file__).resolve().parents[2]
SEED = BACKEND / "seeds" / "catalog" / "materialtwin.db.gz"
PACKAGER = BACKEND.parent / "scripts" / "ci" / "package_deploy.ps1"

EXPECTED = {**CATALOG_TABLES, **METROLOGY_TABLES}


def test_씨앗이_저장소에_있다() -> None:
    """없으면 `deploy.ps1` 의 카탈로그 절이 매번 실패한다."""
    assert SEED.exists(), (
        f"{SEED.relative_to(BACKEND)} 가 없습니다. "
        "`python scripts/make_catalog_seed.py --db <materialtwin.db>` 로 만드세요."
    )
    # 5MB 언저리다. 0바이트나 몇 KB 면 깎다 만 것이다.
    assert SEED.stat().st_size > 1_000_000, "씨앗이 너무 작습니다 — 깎다 말았습니까?"


@pytest.fixture(scope="module")
def unpacked(tmp_path_factory: pytest.TempPathFactory) -> Iterator[sqlite3.Connection]:
    """씨앗을 풀어 연다. 73MB 라 모듈에 한 번만 푼다."""
    plain = tmp_path_factory.mktemp("catalog-seed") / "materialtwin.db"
    with gzip.open(SEED, "rb") as packed, plain.open("wb") as out:
        shutil.copyfileobj(packed, out)
    con = sqlite3.connect(plain)
    try:
        yield con
    finally:
        con.close()


def test_씨앗이_이관이_아는_스키마다(unpacked: sqlite3.Connection) -> None:
    """이관이 시작 전에 하는 검사를 CI 가 미리 한다.

    `check_schema` 는 모르는 컬럼도, 빠진 컬럼도 거부한다. 그것이 배포 중에
    처음 터지면 사람은 로그 끝에서야 안다.
    """
    check_schema(unpacked, EXPECTED)  # 어긋나면 ImportRefused 를 던진다


def test_씨앗에_빈_표가_없다(unpacked: sqlite3.Connection) -> None:
    """표는 있는데 행이 없으면 이관은 조용히 성공한다 — 화면만 빈다."""
    empty = [
        table
        for table in EXPECTED
        if not unpacked.execute(f'select 1 from "{table}" limit 1').fetchone()
    ]
    assert not empty, f"씨앗의 {empty} 표가 비어 있습니다. 깎을 때 무엇이 빠졌습니다."


def test_패키지가_씨앗을_걷어내지_않는다() -> None:
    """`Copy-Item -Recurse .\\backend` 가 통째로 담으므로 저절로 따라간다.

    걷어내는 목록(`.venv`·`__pycache__`·`logs`…)에 `seeds` 가 들어가면 씨앗이
    조용히 사라지고, **서버에서 문헌 물성만 안 뜬다.** 빌드는 성공하고 릴리스도
    발행되므로 알아챌 길이 없다 — 확장 폴더와 같은 함정이다.
    """
    packager = PACKAGER.read_text(encoding="utf-8-sig")
    stripped = [
        line for line in packager.splitlines() if "foreach ($junk" in line and "seeds" in line
    ]
    assert not stripped, (
        "package_deploy.ps1 이 seeds 를 걷어냅니다. 그러면 핸드북·카탈로그 씨앗이 "
        "패키지에서 사라지고, 서버에서 그 화면만 빕니다."
    )
