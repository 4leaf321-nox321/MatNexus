"""물성 카드 — **해석에 들어가는 최종 산출물.**

앞 단계까지가 "이 재료가 이렇게 거동한다" 를 데이터로 보인 것이라면, 이것은 그
거동을 솔버가 읽는 모양으로 굳힌 것이다. 여기서 나온 값이 해석에 들어가고,
그 해석으로 설계가 정해진다.

## 상태 플래그만 둔다 (D8)

`draft → published → deprecated`. **리뷰 큐와 승인자는 두지 않는다** — 운영
규칙이 보이기 전에 절차를 만들면 그 절차가 일을 정의해 버린다. `published` 로
올리는 권한만 부서 관리자에게 준다(D12).

## 불변이 아니다 — 대신 상태가 바뀐다

처리 결과·앙상블과 다른 점이다. 카드는 **사람이 검토하고 승인하는 대상**이라
초안 상태에서 고쳐질 수 있어야 한다. 다만 `published` 로 올라간 뒤에는 값을
바꿀 수 없다 — 그 값으로 해석이 돌았을 수 있기 때문이다. 고치려면 `deprecated`
로 내리고 새 카드를 만든다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 카드의 생애. **리뷰 큐는 없다**(D8) — 상태만 둔다.
PROPERTY_STATUSES = ("draft", "published", "deprecated")


class PropertyCard(Base):
    """재료 하나의 물성 한 벌."""

    __tablename__ = "property_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("materials.id"), index=True
    )
    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), index=True
    )
    orientation: Mapped[str] = mapped_column(String(10), index=True)

    label: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", index=True
    )
    """`draft` | `published` | `deprecated`. `published` 전환은 부서 관리자만(D12)."""

    ensemble_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ensemble_results.id"), index=True, nullable=True
    )
    """어느 통계에서 나왔나. **근거의 뿌리다** — 통계가 지워져도 아래 스냅샷이 남는다."""

    source: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """쓴 시험·표본 수·적합 구간. 카드가 자기 근거를 들고 있어야 한다."""

    elastic: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """탄성: `youngs_modulus`(Pa) · `poisson_ratio` · `density`.

    **푸아송비와 밀도는 인장시험이 주지 않는다.** 사람이 넣거나 재료 DB 에서
    온다 — 값이 없으면 없는 채로 두고, 0 으로 채우지 않는다."""

    hardening: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """경화: `family` · `parameters` · `rmse` · `relative_rmse` · `r_squared` ·
    `strain_min` · `strain_max` · `notes`.

    **적합도를 함께 저장한다.** 파라미터만 남기면 그 값이 데이터와 얼마나 맞는지
    다시 알 수 없고, 그러면 카드를 믿을 근거가 사라진다."""

    table: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """tabulated plasticity — `[{plastic_strain, true_stress}]`.

    많은 솔버가 식보다 표를 그대로 받는다. 식이 안 맞는 재료에서는 표가 더 정확하다."""

    point_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """**누가 언제 올렸는지.** 이 값으로 해석이 돌았을 수 있어 흔적이 필요하다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
