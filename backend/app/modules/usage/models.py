"""사용 집계 — **얼마나, 무엇을, 어느 길로 쓰나**(2026-10-02).

접근 로그(`audit.AccessLog`)는 사람 지원용이라 쓰기 요청과 로그인만 남긴다 — 조회는 양이 많고
행마다 남기면 정작 찾을 것을 못 찾는다. 그래서 「얼마나 잘 쓰고 있나」 에는 답하지 못했다:
조회가 0 으로 보이고, MCP 로 왔는지도 안 남았다.

여기는 **행을 남기지 않고 센다.** 날 · 사람 · 길(화면 · MCP) · 라우트마다 한 줄이고, 같은
줄이 오면 수만 더한다. 그래서 조회까지 다 세도 표가 요청 수만큼 자라지 않는다.

    usage_daily         API 요청 — 라우트 틀(`/materials/{material_id}`) · 메서드 · 오류 수
    usage_views_daily   상세 조회 — 어느 재료 · 문헌 재료 · 시험 · 카드 · 가이드를 몇 번 봤나
    mcp_tool_daily      MCP 도구 호출 — 도구 이름 · 실패 · 걸린 시간(MCP 서버가 알린다)

**사용자 열에 외래키를 안 건다.** 계정을 지워도 그 사람이 쓴 양은 집계에 남아야 한다 —
「지난 분기에 몇 명이 썼나」 는 지금 계정 수와 다른 물음이다.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import BigInteger, Date, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageDaily(Base):
    """API 요청 수 — 하루 · 사람 · 길 · 메서드 · 라우트마다 한 줄."""

    __tablename__ = "usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    client: Mapped[str] = mapped_column(String(10), primary_key=True)
    """`web`(화면) · `mcp` · `pylon` · `script` — 요청의 `X-Client` 표식(인증이 아니다)."""
    method: Mapped[str] = mapped_column(String(8), primary_key=True)
    route: Mapped[str] = mapped_column(String(200), primary_key=True)
    """라우트 틀 — `/materials/{material_id}`. 주소를 그대로 적으면 재료마다 줄이 갈린다."""
    requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """응답 4xx · 5xx 수. 잘 안 되는 기능을 가리킨다."""


class UsageViewDaily(Base):
    """상세 조회 — 하루 · 종류 · 대상 · 사람마다 한 줄. 「무엇을 보나」 의 답."""

    __tablename__ = "usage_views_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    """`material` · `catalog_material` · `test_run` · `card` · `guide`."""
    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    client: Mapped[str] = mapped_column(String(10), primary_key=True)
    views: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class McpToolDaily(Base):
    """MCP 도구 호출 — 하루 · 사람 · 도구마다 한 줄.

    API 요청 수로는 도구 수를 못 센다 — 도구 하나가 백엔드를 여러 번 부르고
    (`property_coverage`), 파일만 읽고 백엔드를 안 부르는 도구도 있다(`get_guide`). 그래서 MCP
    서버가 도구가 끝날 때마다 직접 알린다(`POST /usage/mcp-calls`).
    """

    __tablename__ = "mcp_tool_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    tool: Mapped[str] = mapped_column(String(80), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """오류를 돌려준 호출 — 도구가 `{"error": …}` 로 끝났거나 예외로 끝났다."""
    elapsed_ms: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    """걸린 시간의 합. 평균은 `elapsed_ms / calls`."""
