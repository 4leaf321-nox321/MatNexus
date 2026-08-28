"""묶음 결과 — **여러 시험을 묶어 만든 것을 행으로 남긴다.**

## 왜 행으로 남기나

처리 결과와 같은 이유다. 「이 카드가 어느 시편들에서, 어떤 방법으로 나왔나」 를
**카드 밖에서도** 물을 수 있어야 통계·비교 화면이 그것을 쓴다. 그때 계산하고
버리면 그 물음에 답할 데가 카드 안뿐이다.

## 왜 일반형인가

점탄성이 `master_curves` 라는 전용 표로 이 일을 하고 있었다. 다음 물성이 오면
또 만들어야 했다 — 피로 S-N(시편 수십 개를 지나는 회귀), 크리프(조건별 여러
시험)가 전부 같은 모양이다.

무엇을 묶는지는 **플러그인이 정한다**(`matcore.groups`). 이 표는 「누구를 묶어
무엇이 나왔나」 만 안다.

## 불변이다

처리 결과와 같다. 방법을 바꿔 다시 묶으면 **새 행**이 생기고, 앞의 것은 그때의
방법과 구성원을 그대로 들고 남는다 — 「왜 이 값이 이래」 에 답하려면 그 스냅샷이
있어야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GroupResult(Base):
    """묶음 하나."""

    __tablename__ = "group_results"
    __table_args__ = (
        # 재료 화면이 「이 재료의 묶음」 을 최근 순으로 읽는다.
        Index("ix_group_results_material_created", "material_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("materials.id"), index=True
    )
    """**묶음은 재료에 붙는다.** 시편을 가로지르는 것이라 시편에는 못 붙고,
    시료로 좁히면 로트가 다른 시편을 못 묶는다 — 그런데 그것이 정상 작업이다."""

    plugin_id: Mapped[str] = mapped_column(String(80), index=True)
    """`viscoelastic.prony_group`. **무엇을 묶었는지는 이 이름이 말한다.**"""
    plugin_version: Mapped[str] = mapped_column(String(20), default="1")
    """계산이 바뀌면 올라간다. 옛 행이 어느 판으로 나온 것인지 남는다."""

    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """`{"method": "pooled", "terms": 0}`. **그때 무엇을 골랐는지 그대로.**"""

    members: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """묶은 것들. `[{"test_run_id": ..., "label": ..., "source_id": ...}]`.

    **이름을 함께 담는다.** id 만 두면 나중에 그 시험이 지워졌을 때 무엇이었는지
    알 수 없다 — 감사 기록이 이름을 함께 남기는 것과 같은 이유다."""

    used: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """**실제로 쓴 것.** 고른 것과 다를 수 있다 — 대표를 고르면 하나만 쓰고,
    조건이 안 맞아 빠진 것도 있다. 그 차이가 안 보이면 「셋을 묶었다」 가 거짓말이
    된다."""

    values: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict, server_default="{}")
    """나온 스칼라. 처리 결과의 그것과 같은 모양이라 카드가 구별 없이 받는다."""
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """숫자로 안 담기는 것(Prony 항 목록 등)."""
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """막지 않았지만 말한 것. **묶음에서 특히 많다** — 조건이 조금씩 다른 것을
    묶는 일이라, 무엇을 감수했는지가 남아야 한다."""

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
