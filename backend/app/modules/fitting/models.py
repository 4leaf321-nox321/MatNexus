"""물성 카드 — **해석에 들어가는 최종 산출물.**

앞 단계까지가 "이 재료가 이렇게 거동한다" 를 데이터로 보인 것이라면, 이것은 그
거동을 솔버가 읽는 모양으로 굳힌 것이다. 여기서 나온 값이 해석에 들어가고,
그 해석으로 설계가 정해진다.

## 상태 플래그만 둔다 (D8)

`draft → published → deprecated`. **리뷰 큐와 승인자는 두지 않는다** — 운영
규칙이 보이기 전에 절차를 만들면 그 절차가 일을 정의해 버린다. `published` 로
올리는 권한만 부서 관리자에게 준다(D12).

## 물성의 갈래는 데이터다

전에는 `elastic`·`hardening`·`table` 이라는 **컬럼 셋**이었다. 점탄성을 더하려면
네 번째 컬럼이, 초탄성이면 다섯 번째가 필요했고 그때마다 마이그레이션·스키마·
화면이 딸려 왔다 — 폴리머 점탄성에서 D7 이 못 미친 45% 의 정체가 그것이다.

셋 다 **이미 JSONB 였다.** 안은 형식이 없는데 바깥의 컬럼 이름만 굳어 있었다.
지금은 `blocks` 한 칸이고, 무엇이 들어갈 수 있는지는 `matcore.cards` 레지스트리가
안다. 새 물성 1종에 드는 것은 `BlockSpec` 하나이고 마이그레이션은 0 이다.

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
    test_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), index=True, nullable=True
    )
    """어느 시험에서 나왔나. **빌 수 있다** — 시험이 하나도 없는 재료의 카드다.

    선언 물성만으로 만든 카드가 그렇다(ADR 0016). 여기에 아무 시험종류나 채워
    넣으면 그 카드가 인장시험에서 나온 것처럼 보이고, **덱을 받은 사람은 그
    숫자를 잰 값으로 읽는다.** 비어 있는 것이 사실이므로 비워 둔다."""

    orientation: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    """압연 방향 등. `test_type_id` 와 함께 빈다 — 시험을 안 했으면 방향도 없다.

    `"—"` 같은 자리표시를 넣지 않는 이유는 같다: 목록이 그것을 방향 이름으로
    줄 세우고, 나중에 그 값을 거르는 코드가 생긴다."""

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

    blocks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """물성 블록 묶음 — `{블록 key: {values, rows, notes}}`.

    무엇이 들어갈 수 있는지는 **`matcore.cards` 레지스트리가 안다.** 여기서는
    이름을 하나도 모른다 — 그것이 새 물성을 더하는 값을 마이그레이션 0 으로
    만드는 자리다.

    지금 등록된 것: `elastic` · `hardening` · `table` · `viscoelastic`.

    **적합도를 값과 함께 담는다.** 파라미터만 남기면 그 값이 데이터와 얼마나
    맞는지 다시 알 수 없고, 그러면 카드를 믿을 근거가 사라진다."""

    point_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """소성 표의 점 수. **목록이 표를 안 읽고도 보여 줄 수 있어야 한다** —
    카드 하나의 표가 수천 점이다."""
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
