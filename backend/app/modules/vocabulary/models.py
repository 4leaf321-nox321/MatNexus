"""어휘 — **축과 값과 표기.**

사람이 타이핑하는 짧은 문자열(제조사·강종·시편 규격 …)을 표로 올리고, 쓰는
쪽은 외래키로 가리킨다(ADR 0010). 그래야 두 표기를 묶는 것이 `UPDATE` 한
문장이 되고, 값 이름을 바꾸는 것이 한 행이 된다.

    vocabularies         축    manufacturer · grade · specimen_standard …
    vocabulary_terms     값    포스코 · 현대제철
    vocabulary_aliases   표기  '포스코(주)' → 포스코

## 왜 세 표인가

**축과 값을 나누는 이유**: 축마다 입력 정책이 다르다. 강종은 계속 새로 생기니
사용자가 즉석에서 추가할 수 있어야 하고(`open`), Family 는 관리자가 정하는
분류라 아무나 늘리면 안 된다(`closed`). 하나로 합치면 그 차이를 둘 데가 없다.

**별칭을 나누는 이유**: 별칭은 **예방**이다. `'POSCO'` 를 `'포스코'` 의 별칭으로
등록해 두면 값을 만들 때 그것까지 뒤져서 애초에 중복이 안 생긴다 — 사후에
합치는 것보다 싸다.

## 어휘는 전사 공용이다

제조사가 부서마다 다를 이유가 없다. 시험 종류를 부서가 만드는 것(ADR 0006)과는
다르다 — 그건 장비가 부서마다 달라서지 어휘가 달라서가 아니다. 필요해지면
`owner_workspace_id` 한 컬럼을 더하면 된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 입력 정책. 값이 아니라 **축**에 붙는다.
#:
#:   open   — 누구나 피커에서 새 값을 추가할 수 있다. 강종·제조사처럼 계속
#:            늘어나는 축. 승인 대기를 두지 않는다 — 기다리게 하면 피커가 멈추고,
#:            그러면 사람은 시스템 밖에서 일한다. 드리프트는 사후 병합으로 푼다.
#:   closed — 관리자가 등록한 값만 고른다. Family·Category 처럼 **미리 정해야
#:            하는 분류**. 실제로 `'Family'` 라는 값이 입력된 적이 있다.
ENTRY_POLICIES = ("open", "closed")

#: 값의 상태.
#:
#:   active     — 피커에 뜬다.
#:   deprecated — 피커에서 숨기되 **이미 가리키고 있는 것은 그대로 둔다.**
#:                지우면 그 재료·시료가 무엇이었는지 알 수 없게 된다.
TERM_STATUSES = ("active", "deprecated")


class Vocabulary(Base):
    """축 하나. 마이그레이션으로 심고 API 로는 안 만든다 — 축이 늘어나는 것은
    스키마가 바뀌는 일이지 데이터가 늘어나는 일이 아니다."""

    __tablename__ = "vocabularies"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    """코드가 거는 이름. `manufacturer` 처럼 안 바뀌는 것."""
    label: Mapped[str] = mapped_column(String(100))
    entry_policy: Mapped[str] = mapped_column(String(10), default="open")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VocabularyTerm(Base):
    """값 하나."""

    __tablename__ = "vocabulary_terms"
    __table_args__ = (
        # **유일성은 비교키로 건다.** `value` 로 걸면 '포스코' 와 '포스코 ' 가
        # 둘 다 들어간다 — 눈에 같아 보이는데 DB 는 다르게 본다.
        UniqueConstraint("vocabulary_id", "normalized", name="uq_vocabulary_terms_norm"),
        # 어휘가 수만 개가 되면 피커 검색이 `ILIKE '%낱말%'` 이다. B-tree 는 못
        # 타므로 trigram 인덱스를 둔다(0단계에서 재료 검색에 한 것과 같은 이유).
        Index(
            "ix_vocabulary_terms_norm_trgm",
            "normalized",
            postgresql_using="gin",
            postgresql_ops={"normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabularies.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[str] = mapped_column(String(200))
    """보여 주는 값. 사람이 적은 표기를 정리만 해서(`clean`) 그대로 담는다."""
    normalized: Mapped[str] = mapped_column(String(200), index=True)
    """비교키(`compare_key`). 유일성과 조회가 이걸로 돈다.

    구두점은 안 지운다 — `'포스코(주)'` 가 계열사 구분일 수 있다. 그런 것을
    묶는 것은 병합 후보 탐지의 몫이고, 거기서는 **사람에게 묻는다.**"""
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """이 값을 가리키는 행 수. **분류 목록이 재료 수와 무관해지는 지점이다** —
    지금은 화면을 열 때마다 재료 전체를 `GROUP BY` 한다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VocabularyAlias(Base):
    """같은 대상의 다른 표기 → 정규 값.

    `vocabulary_id` 는 비정규화다(= term 의 축). 한 축 안에서 같은 표기가 두
    값에 매핑되는 것을 유니크 제약으로 막으려면 여기 있어야 한다.
    """

    __tablename__ = "vocabulary_aliases"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", "normalized", name="uq_vocabulary_aliases_norm"),
        Index(
            "ix_vocabulary_aliases_norm_trgm",
            "normalized",
            postgresql_using="gin",
            postgresql_ops={"normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabularies.id", ondelete="CASCADE"), index=True
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="CASCADE"),
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(200))
    normalized: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
