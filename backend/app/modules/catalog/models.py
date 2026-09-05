"""물성 카탈로그 — 문헌·데이터시트에서 채굴된 물성값의 보관소 (ADR 0027).

MaterialTwin 스냅샷(`materialtwin.db`)에서 이관해 온다. 사내 재료
(`materials`)와는 **별도 표**다 — 카탈로그 재료는 문헌상의 등급/제품이고 사내
재료는 실물 lot 이라 수명주기가 다르다. 기존 표는 건드리지 않는다.

## 무손실 원칙

원본 컬럼 전부가 여기 1:1 로 온다. `attributes`·`conditions` JSON 은 정정 이력
(`*_before_correction`)·판정(`verdict_*`)·부재 판정(`core_*`)까지 **그대로**다.
검색에 쓰는 발췌 컬럼(subsystem 등)은 attributes 의 사본이며 **정본은 언제나
JSON 쪽**이다.

## 멱등의 열쇠 — `mt_id`

각 행이 원본 id 를 `mt_id` 로 보존한다. 이관을 다시 돌리면 이 열쇠로 대응행을
찾아 갱신하고, 지우지 않는다. 데이터는 어느 환경이든 「이관 스크립트 + 원본
파일」로만 들어온다(개발 DB → 운영 복사 경로는 없다 — 개발 DB 에는 테스트
데이터가 섞여 있다).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 품질 등급 — 원본 독트린 그대로. **4는 근거 없는 값이다**(계산·추정·가정,
#: `conditions.assumption` 표지). 신뢰가 필요한 경로(통계·카드)는 4를 뺀다.
QUALITY_TIERS = {
    1: "그 제품 문서에 인쇄된 실측",
    2: "핸드북·규격·공인 DB",
    3: "계열 대표값·2차 인용",
    4: "계산·추정·가정",
}


class CatalogMaterial(Base):
    """카탈로그 재료 — 문헌상의 등급/제품. 사내 재료와 다른 것이다."""

    __tablename__ = "catalog_materials"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: 원본 material.id — 멱등의 열쇠.
    mt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    name: Mapped[str] = mapped_column(String(300), index=True)
    material_code: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30), index=True)
    """metal·polymer·ceramic·composite·rubber·foam·molecular."""
    description: Mapped[str | None] = mapped_column(Text)

    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """원본 그대로 — 제조사·grade·계통·역할 판정과 그 근거·부재 판정 전부.
    아래 발췌 컬럼의 정본이다."""

    # ── 검색용 발췌 (정본은 attributes) ────────────────────────────────────
    subsystem: Mapped[str | None] = mapped_column(String(50), index=True)
    """스마트폰 부품 계통 — pcb·housing·display·battery… 비면 「미분류」."""
    role: Mapped[str | None] = mapped_column(String(30))
    """product(실제 제품) · evidence(근거용) · out_of_scope."""
    # 아래 셋은 자유 문장이다(실측: 100자 넘는 material_class 가 실재) — 자르면
    # 무손실이 깨지므로 길이 제한을 두지 않는다.
    manufacturer: Mapped[str | None] = mapped_column(Text)
    material_class: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(Text)

    #: 원본의 시각. 시간대 정보가 원본에 없어 **그대로**(naive) 둔다 — 붙여
    #: 꾸미면 그것이 왜곡이다.
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CatalogSource(Base):
    """출처 — 논문·데이터시트·핸드북. **출처 없는 값은 원본에 0건이다.**"""

    __tablename__ = "catalog_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    kind: Mapped[str] = mapped_column(String(30))
    """journal·datasheet·database·book·standard·web·computed·other."""
    doi: Mapped[str | None] = mapped_column(String(200), index=True)
    isbn: Mapped[str | None] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(300))
    license: Mapped[str | None] = mapped_column(String(100))
    local_path: Mapped[str | None] = mapped_column(Text)
    """원본 수집 환경의 파일 경로 — **여기서는 참고 문자열이다.** 원문 파일은
    스냅샷에 없고, 재배포 라이선스가 불명이라 원본도 경로만 기록했다."""
    content_hash: Mapped[str | None] = mapped_column(String(100))
    source_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime())
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CatalogDefinition(Base):
    """물성 정의 — 원본 taxonomy 271종이 정본이다.

    단위는 원본 그대로다. matcore 단위표에 없는 것(HV·ShoreA 등)이 있어
    억지로 꿰지 않는다 — matcore 차원·기준정보 property_item 과는 필요해질 때
    매핑 표로 잇는다 (ADR 0027).
    """

    __tablename__ = "catalog_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mt_id: Mapped[int] = mapped_column(Integer, unique=True)

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    """`domain.name` 꼴 안정 id — 예: mechanical.youngs_modulus."""
    domain: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    symbol: Mapped[str | None] = mapped_column(String(50))
    si_unit: Mapped[str | None] = mapped_column(String(50))
    value_type: Mapped[str] = mapped_column(String(20))
    """numeric·vector·categorical·boolean."""
    description: Mapped[str | None] = mapped_column(Text)
    test_standard: Mapped[str | None] = mapped_column(String(200))
    condition_axes: Mapped[list[str] | None] = mapped_column(JSONB)
    """이 물성이 조건 없이는 무의미해지는 축 — 예: temperature_k."""
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CatalogValue(Base):
    """물성값 하나 — 값 + 조건 + 방법 + 등급 + 출처가 한 몸이다.

    `conditions` 안에 정정 이력(`*_before_correction`)·판정(`verdict_*`)이
    보존돼 있다 — 원본은 값을 지우지 않고 표시했고, 우리도 그대로 나른다.
    """

    __tablename__ = "catalog_values"
    __table_args__ = (Index("ix_catalog_values_material_key", "material_id", "property_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    material_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_materials.id", ondelete="CASCADE"),
        index=True,
    )
    property_key: Mapped[str] = mapped_column(
        String(100), ForeignKey("catalog_definitions.key"), index=True
    )

    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(50))
    """정의의 단위와 같다(원본 적재 관문이 검사했다). 그래도 값 옆에 둔다 —
    값과 단위가 떨어져 있으면 언젠가 어긋난다."""
    uncertainty: Mapped[float | None] = mapped_column(Float)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    method: Mapped[str | None] = mapped_column(String(20))
    """measured·handbook·computed·estimated·digitized — digitized(그래프
    판독)는 실측과 다른 주장이라 원본이 어휘를 갈랐다."""
    quality_tier: Mapped[int] = mapped_column(SmallInteger, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("catalog_sources.id", ondelete="SET NULL")
    )
    source_detail: Mapped[str | None] = mapped_column(Text)
    """출처 안의 위치 — 페이지·표·그림."""
    notes: Mapped[str | None] = mapped_column(Text)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
