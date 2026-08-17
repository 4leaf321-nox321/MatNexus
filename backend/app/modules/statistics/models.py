"""앙상블 통계 결과 — **불변이다.**

시험이 하나 더 붙으면 평균이 달라진다. 그런데 어제 보고서에 적은 값은 어제의
표본으로 나온 것이다. 그래서 처리 결과와 같은 모델을 쓴다(ADR 0007):

    계산은 언제나 최신으로 보여 주고, **저장은 사람이 명시적으로** 한다.
    저장된 것은 그때의 표본과 값을 통째로 들고 있다.

`ProcessingResult` 가 단계를 스냅샷하는 것과 같은 이유다 — 나중에 "이 평균이
어느 시험 15건에서 나왔나" 를 답할 수 없으면 그 숫자는 근거가 없다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EnsembleResult(Base):
    """반복 시편 통계 한 벌.

    **묶음 키는 재료 + 시험종류 + 방향이다.** 인장은 압연 방향에 따라 물성이
    다르다 — MD 5개와 TD 5개를 한 통계로 묶으면 CV 가 15% 로 나오는데, 그것은
    산포가 아니라 다른 것을 섞은 것이다. 시료(lot)까지 나누지 않는 이유는 보통
    같은 재료로 취급하기 때문이다.
    """

    __tablename__ = "ensemble_results"

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

    sample_count: Mapped[int] = mapped_column(Integer)
    test_run_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """**어느 시험으로 냈는지.** 이것이 없으면 평균의 근거가 사라진다."""
    result_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """각 시험에서 채택돼 있던 처리 결과. 나중에 채택이 바뀌어도 이 값은 그대로다."""

    scalars: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """항목별 n·평균·SD·중앙값·MAD·IQR·min·max·CV·95%CI 와 이상치 후보."""
    curve: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """평균·중앙값 곡선과 점별 산포. 점 수가 많지 않아(재샘플 뒤) JSONB 로 둔다 —
    곡선 하나에 Parquet 파일을 만들 만큼 크지 않다."""
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
