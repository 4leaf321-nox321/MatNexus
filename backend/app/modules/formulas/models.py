"""계산식 — **화면에서 적은 식이 적합식·처리 단계가 된다** (ADR 0030).

파이썬 폴더 없이, 배포 없이. 행 하나가 `matcore.formulas.FormulaSpec` 하나이고,
기동할 때와 저장할 때 레지스트리에 `formula.<key>` 로 들어간다.

## 판이 있고 저장된 것은 안 바뀐다 (D4)

식을 고치면 `version` 이 오른다. 이미 저장된 레시피·처리 결과·카드는 옛 판을 들고
있으므로 그대로다 — 다시 돌리면 새 판으로 돈다. 옛 판의 식 본문은 남기지 않는다:
그 대신 화면이 「편집」 보다 「새 키로 만들고 옛 것을 비활성화」 를 먼저 권한다.

## 지우기는 참조가 없을 때만

저장된 레시피가 이 단계를 쓰거나 카드가 이 식을 인용하면 못 지우고 `enabled=false` 로
끈다 — 물성 키 폐기와 같은 규칙. 끈 식은 목록에서 빠지되 옛 결과는 그대로 읽힌다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 자리 셋 — `matcore.formulas.KINDS` 와 같다.
KINDS = ("family", "scalar_step", "column_step")
KIND_LABELS = {"family": "적합식", "scalar_step": "값 단계", "column_step": "열 단계"}


class Formula(Base):
    __tablename__ = "formulas"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    """레지스트리 키의 뒷부분 — `formula.<key>`. 한 번 나가면 안 바뀐다."""
    kind: Mapped[str] = mapped_column(String(20), index=True)
    label: Mapped[str] = mapped_column(String(120))
    expression: Mapped[str] = mapped_column(Text)
    describe: Mapped[str | None] = mapped_column(Text)

    variables: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """`[{"name": "x", "unit": "1", "label": "…"}]` — 입력."""
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """`[{"name": "K", "unit": "Pa", "initial": 5e8, "lower": 0, "upper": 5e9}]` — 적합식만."""
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """`{"key": "yield_ratio", "label": "항복비", "si_unit": "1"}` — 단계만."""

    x_column: Mapped[str | None] = mapped_column(String(60))
    y_column: Mapped[str | None] = mapped_column(String(60))
    block: Mapped[str | None] = mapped_column(String(40))
    applies_to: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def registry_key(self) -> str:
        return f"formula.{self.key}"
