"""측정법 — **「그 물성은 무엇으로 어떻게 재는가」** (MaterialTwin 이식 4단계).

문헌 물성 카탈로그가 「무엇이 얼마인가」 에 답한다면, 여기는 그 옆에 서는
답이다: 물성 → 측정 기법·시험 규격 → 장비(제조사·모델 + **카탈로그에 인쇄된**
사양). 빈 물성칸을 만난 사용자가 다음에 무엇을 할지(무슨 장비로 재면 되는지)
알게 하는 것이 목적이다.

원본 규율 그대로다: 지어내지 않는다 · 빈 칸이 틀린 값보다 낫다 · 벤더 문구
(`up to …`)를 값으로 읽지 않는다(상한만 확정, 하한은 빈 칸) · **장비 카탈로그에
있는 것과 우리가 보유한 것을 가른다**(`owned`) — "장비 218대" 가 보유 능력으로
읽히면 안 된다.

이관은 카탈로그와 같은 무늬다 — `mt_id` 멱등, 모르는 컬럼 거부, 원본 그대로.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Instrument(Base):
    """계측 장비 하나 — 장비 카탈로그(PDF)에서 온 제조사·모델."""

    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("vendor", "model", name="uq_instruments_vendor_model"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: 원본 instrument.id — 멱등의 열쇠.
    mt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    vendor: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), index=True)
    """thermal·mechanical·surface·chemical·particle·optical·electrical·ndt·reliability."""
    technique: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    doc_path: Mapped[str | None] = mapped_column(Text)
    """원본 수집 환경의 장비 카탈로그 PDF 경로 — 참고 문자열이다(원문은 없다)."""
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("catalog_sources.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    owned: Mapped[bool] = mapped_column(Boolean, default=False)
    """**보유 여부 — 이 표에서 가장 중요한 한 칸.** 카탈로그에 있는 것과 우리가
    가진 것을 가르지 않으면 「잴 수 있다」 가 거짓말이 된다."""
    owned_note: Mapped[str | None] = mapped_column(Text)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    owner_contact: Mapped[str | None] = mapped_column(String(200))
    owned_checked_at: Mapped[datetime | None] = mapped_column(DateTime())

    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InstrumentCapability(Base):
    """장비 하나가 물성 하나를 어떤 기법으로 재는가 — 인쇄된 사양과 함께.

    물성 매핑은 사람의 판단이라 `mapping_confidence` 를 든다 — 애매하면 잇지
    않는 것이 원본 규율이었다.
    """

    __tablename__ = "instrument_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "property_key", "technique", name="uq_capabilities_triple"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        index=True,
    )
    property_key: Mapped[str] = mapped_column(
        String(100), ForeignKey("catalog_definitions.key"), index=True
    )
    technique: Mapped[str | None] = mapped_column(Text)
    standard: Mapped[str | None] = mapped_column(String(200))
    """시험 규격 — 규격 번호가 기법을 정한다(원본 규율)."""
    range_min: Mapped[float | None] = mapped_column(Float)
    range_max: Mapped[float | None] = mapped_column(Float)
    """측정 범위. `up to` 문구는 상한만 확정한 것이라 하한이 빈 칸일 수 있다."""
    range_unit: Mapped[str | None] = mapped_column(String(50))
    resolution: Mapped[str | None] = mapped_column(String(200))
    accuracy: Mapped[str | None] = mapped_column(String(200))
    temperature_min_k: Mapped[float | None] = mapped_column(Float)
    temperature_max_k: Mapped[float | None] = mapped_column(Float)
    """**시편 온도 범위다** — 장비 내부 온도계 범위가 아니다(원본 함정 대장)."""
    specimen: Mapped[str | None] = mapped_column(Text)
    mapping_confidence: Mapped[str | None] = mapped_column(String(10))
    """high·medium·low — 물성↔장비 매핑은 우리 판단이라 확신도를 남긴다."""
    source_detail: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
