"""DB 가 코드보다 뒤처졌는지 — **기동할 때 말한다.**

실제로 겪은 일이 이 파일의 이유다. 마이그레이션을 만들고 개발 서버를 그대로 둔
채 화면을 열었더니 기준정보 화면이 통째로 `MNX-COMMON-0500` 이었다. 원인은 ORM 이
없는 컬럼을 SELECT 한 것인데, **오류 어디에도 "DB 가 한 리비전 뒤에 있다" 는 말이
없었다.** 옆의 어긋남 점검 패널만 멀쩡해서 더 헷갈렸다 — 그건 새 컬럼을 안
건드리는 쿼리였다.

운영은 배포가 `alembic upgrade head` 를 돌리므로 이 문제가 없다. 이건 개발
서버를 위한 안내다.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine

from app import schema_version


def test_코드의_head_를_읽는다() -> None:
    """마이그레이션 폴더에서 읽는다. 못 읽으면 안내 자체가 성립하지 않는다."""
    head = schema_version.code_head()
    assert head is not None
    assert len(head) >= 8


def test_붙지_못하면_조용히_넘어간다() -> None:
    """**기동을 막지 않는다.** DB 에 못 붙는 상황에서 서버가 안 뜨면 원인을 볼
    화면조차 없다."""
    dead = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    assert schema_version.db_revision(dead) is None
    assert schema_version.warn_if_behind(dead) is None


def test_같으면_아무_말도_안_한다(caplog: pytest.LogCaptureFixture) -> None:
    """맞는 상태에서 매번 경고가 뜨면 그 경고를 아무도 안 읽게 된다."""
    head = schema_version.code_head()
    monkey = _FakeEngine(head)
    with caplog.at_level(logging.WARNING):
        assert schema_version.warn_if_behind(monkey) is None  # type: ignore[arg-type]
    assert caplog.records == []


def test_뒤처지면_무엇을_하면_되는지_말한다(caplog: pytest.LogCaptureFixture) -> None:
    """**"뒤처졌다" 만으로는 부족하다.** 어느 리비전에서 어디로 가야 하는지와,
    무엇을 치면 되는지가 같이 있어야 한다."""
    head = schema_version.code_head()
    assert head is not None
    with caplog.at_level(logging.WARNING):
        found = schema_version.warn_if_behind(_FakeEngine("e96990a6b281"))  # type: ignore[arg-type]

    assert found == head
    message = caplog.records[0].getMessage()
    assert "e96990a6b281" in message
    assert head in message
    assert "alembic upgrade head" in message


class _FakeEngine:
    """`alembic_version` 만 흉내 낸다. 진짜 DB 를 쓰면 이 시험이 리비전을
    갈아 끼워야 하는데, 그건 다른 시험을 깨뜨린다."""

    def __init__(self, revision: str | None) -> None:
        self._revision = revision

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self._revision)


class _FakeConnection:
    def __init__(self, revision: str | None) -> None:
        self._revision = revision

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def scalar(self, *_: object) -> str | None:
        return self._revision
