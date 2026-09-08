"""재료가 가진 **모델 파라미터 집합** — 문헌에서 받아 온 한 벌(ADR 0029).

Anand 9개, Prony 항, Ogden 계수처럼 **여럿이 한 벌이어야 뜻이 있는** 값들이 산다.
값 하나짜리(항복강도·밀도)는 선언 물성이 담고, 이쪽은 묶음이 담는다.

## 왜 카드가 아니라 재료에 두나 (ADR 0029 D3)

카드에 바로 넣으면 넷이 깨진다:

1. **물성 탭에서 안 보인다.** 사람은 「이 재료가 무엇을 가졌나」 를 거기서 본다 —
   카드를 만들기 전까지 안 보이면 없는 것과 같다.
2. **후보를 여럿 못 둔다.** 같은 재료에 논문마다 다른 Anand 벌이 있다.
3. **불변과 가변을 섞는다.** 카드는 확정·폐기되는 가변물이고, 근거는 더 오래 남아야
   한다(AGENTS.md 가 「모델 파라미터」 를 불변 목록에 적어 뒀다).
4. 이미 같은 모양이 있다 — 처리 결과가 남고 카드가 **채택**한다(ADR 0007).

## 단위를 환산하지 않는다

문헌의 이 값들은 SI 가 아니라 **그 항의 원래 단위**다(h0 = 150000 MPa 이지
1.5e11 Pa 가 아니다). 받아 올 때도 그대로 둔다 — 환산하면 모델이 기대하는 값과
달라지고, 그 사실은 숫자만 봐서는 안 드러난다. 대신 **단위를 항마다 함께 적는다.**
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 어디서 왔나. 선언 물성의 출처 목록과 뜻을 맞춘다.
ORIGINS = ("catalog", "literature", "fitted", "manual")


class MaterialParameterSet(Base):
    """한 벌. **`A` 만 떼어 가면 뜻이 없으므로 이것이 최소 단위다.**"""

    __tablename__ = "material_parameter_sets"
    __table_args__ = (
        # 같은 재료에 같은 출처의 같은 벌을 두 번 담지 않는다. 논문이 다르면
        # `source_ref` 가 달라 둘 다 남는다 — **후보를 여럿 두는 것이 목적이다.**
        UniqueConstraint(
            "material_id", "model", "source_ref", name="uq_material_parameter_sets"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), index=True
    )

    model: Mapped[str] = mapped_column(String(80), index=True)
    """모델 이름 — `anand` · `prony` · `ogden`. 이것이 파라미터의 뜻을 정한다."""

    label: Mapped[str] = mapped_column(String(200))
    """사람에게 보일 이름 — 「Anand 점소성 상수」."""

    property_key: Mapped[str | None] = mapped_column(String(120), index=True)
    """어느 문헌 물성에서 왔나. **FK 를 안 건다** — 이관이 정의를 지웠다 넣으면
    함께 지워진다(`property_aliases` 와 같은 판단)."""

    origin: Mapped[str] = mapped_column(String(20), default="catalog")
    """`ORIGINS` 중 하나."""
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    """출처를 가리키는 손잡이 — 문헌이면 `set_id`, 손으로 적었으면 사람이 준 이름.
    **같은 재료의 두 벌을 가르는 열쇠**라 빈 문자열도 값으로 쓴다."""
    source_detail: Mapped[str | None] = mapped_column(Text)
    """어느 논문·데이터시트인가. 값만 있고 근거가 없으면 나중에 되짚을 수 없다."""
    quality_tier: Mapped[int | None] = mapped_column()

    terms: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """`[{term, value, unit, text}]`. **단위를 항마다 든다** — 한 벌 안에서
    `1`·`1/s`·`MPa`·`K` 가 섞이기 때문이다."""

    notes: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
