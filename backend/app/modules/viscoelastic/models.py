"""마스터커브와 Prony 적합 — **여러 곡선이 하나가 되는 자리.**

## 왜 처리 결과가 아닌가

`ProcessingResult` 는 `source_curve_key` 가 **하나**다. 처리는 곡선 하나를 받아
곡선 하나를 낸다 — 파이프라인 전체가 그 모양이다.

마스터커브는 다르다. **온도가 다른 곡선 여섯을 받아 하나를 낸다.** 그것을 처리
파이프라인에 억지로 끼우려면 `Frame` 하나를 받는 규약을 통째로 넓혀야 하고,
그러면 곡선 하나만 쓰는 나머지 열 몇 개 단계가 다 그 비용을 낸다.

`statistics` 가 같은 자리에서 같은 판단을 했다 — 여러 시험을 묶는 일은 처리가
아니라 별개다. 여기도 그렇게 둔다.

## 겹친 곡선은 불변이다

만들고 나면 안 고친다. 기준 온도를 바꾸고 싶으면 **새로 만든다** — 같은 행을
고치면 그 계수로 이미 내보낸 카드가 무엇에서 나왔는지 알 수 없게 된다
(ADR 0007 의 결과 불변성과 같은 판단).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MasterCurve(Base):
    """시간-온도 중첩으로 겹친 곡선 한 벌."""

    __tablename__ = "master_curves"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True
    )
    source_curve_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """겹친 곡선들. **하나가 아니라 여럿이라 여기 있다.**"""

    reference_temperature_k: Mapped[float] = mapped_column(Float)
    """**이 곡선이 유효한 온도.** 카드 주석에 그대로 들어간다 — 다른 온도의
    해석에 쓰면 안 된다는 사실이 덱까지 따라가야 한다."""
    method: Mapped[str] = mapped_column(String(20))
    """`wlf` | `arrhenius` | `manual`."""
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    """`wlf` 면 `c1`·`c2`, `arrhenius` 면 활성화 에너지."""
    shifts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """온도별 이동인자. **맞춘 값과 관측값을 함께 담는다** — 둘이 벌어지면 그
    모델이 이 재료에 안 맞는다는 뜻이고, 그 판단은 사람이 한다."""
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """겹치면서 한 일과 경고. 화면이 그대로 보여 준다."""

    storage_path: Mapped[str] = mapped_column(String(500))
    """겹친 곡선의 Parquet. **DB 에 넣지 않는다**(ADR 0004) — 점이 수백이다."""
    point_count: Mapped[int] = mapped_column(Integer, default=0)
    minimum_frequency_hz: Mapped[float] = mapped_column(Float)
    maximum_frequency_hz: Mapped[float] = mapped_column(Float)
    """겹친 범위. 목록에서 "얼마나 넓어졌나" 를 보여 주는 데 쓴다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PronyFit(Base):
    """마스터커브에 맞춘 일반화 Maxwell 계수."""

    __tablename__ = "prony_fits"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    master_curve_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("master_curves.id", ondelete="CASCADE"), index=True
    )

    equilibrium_pa: Mapped[float] = mapped_column(Float)
    terms: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """`[{modulus_pa, relaxation_time_s}, ...]`. 완화시간이 커지는 순서."""
    normalized_rmse: Mapped[float] = mapped_column(Float)
    bic: Mapped[float] = mapped_column(Float)
    at_bound: Mapped[list[float]] = mapped_column(JSONB, default=list)
    """경계에 붙은 완화시간. 있으면 **관측 밖을 외삽하고 있다.**"""

    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """재 본 후보 전부. **고른 것만 남기면** "3항이면 충분한데 왜 6항이지" 를
    사람이 볼 수 없다 — 경화식 견주기와 같은 판단이다."""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
