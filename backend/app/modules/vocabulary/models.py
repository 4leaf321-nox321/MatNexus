"""기준정보 — **축과 값과 표기.**

사람이 타이핑하는 짧은 문자열(제조사·강종·시편 규격 …)을 표로 올리고, 쓰는
쪽은 외래키로 가리킨다(ADR 0010). 그래야 두 표기를 묶는 것이 `UPDATE` 한
문장이 되고, 값 이름을 바꾸는 것이 한 행이 된다.

    vocabularies         축    manufacturer · grade · specimen_standard …
    vocabulary_terms     값    포스코 · 현대제철
    vocabulary_aliases   표기  '포스코(주)' → 포스코

## 왜 세 표인가

**축과 값을 나누는 이유**: 축마다 성질이 다르다. 입력 정책(`open`/`closed`)도,
부모 축이 무엇인지도 축에 붙는다 — `category` 의 부모는 `family` 다. 값마다
그것을 물으면 같은 답을 수만 번 저장하는 셈이다.

**별칭을 나누는 이유**: 별칭은 **예방**이다. `'POSCO'` 를 `'포스코'` 의 별칭으로
등록해 두면 값을 만들 때 그것까지 뒤져서 애초에 중복이 안 생긴다 — 사후에
합치는 것보다 싸다.

## 기준정보는 전사 공용이다

제조사가 부서마다 다를 이유가 없다. 시험 종류를 부서가 만드는 것(ADR 0006)과는
다르다 — 그건 장비가 부서마다 달라서지 기준정보가 달라서가 아니다. 필요해지면
`owner_workspace_id` 한 컬럼을 더하면 된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 입력 정책. 값이 아니라 **축**에 붙는다.
#:
#:   open   — 누구나 피커에서 새 값을 추가할 수 있다. 강종·제조사처럼 계속
#:            늘어나는 축. 승인 대기를 두지 않는다 — 기다리게 하면 피커가 멈추고,
#:            그러면 사람은 시스템 밖에서 일한다. 드리프트는 사후 병합으로 푼다.
#:   closed — 관리자가 등록한 값만 고른다. **지금은 아무 축도 안 쓴다.**
#:            막았을 때 사람이 어디로 가는지가 문제다 — 목록에 없으면 관리자를
#:            찾아가거나, 더 흔하게는 비슷한 것을 대충 고르고 넘어간다. 그러면
#:            분류가 지켜진 것이 아니라 조용히 틀린 것이다.
#:
#:            값을 하는 자리는 **외부 시스템이 정본을 주는 축**이다(ReportArchive
#:            는 모델·BOM 코드에 쓴다). Phase 6 에서 장비 커넥터가 붙으면 켠다.
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
    parent_slug: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """이 축의 값이 어느 축 아래 사는가. `category` 의 부모는 `family` 다.

    **계약을 축 수준에 한 번만 적는다.** 값마다 "이건 어느 축의 부모냐" 를 물으면
    같은 답을 수만 번 저장하는 셈이고, 잘못된 축을 가리키는 값이 생긴다."""
    attribute_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """이 축의 값이 **속성을 갖는가, 기본 칸을 누가 정하는가.**

    `parent` 면 값의 **상위 값**(`parent_term_id`)이 기본 칸을 갖는다. 시편
    규격의 상위는 시편 분류이고, 분류가 "이 종류의 시편이면 늘 필요한 치수" 를
    선언한다(`SpecimenField`). 지금 이걸 쓰는 축은 `specimen_standard` 하나다.

    규격은 거기에 **자기만의 칸을 더할 수 있다**(`VocabularyTerm.extra_fields`) —
    `ASTM E8 R1` 은 환봉이라 직경이 필요하고, `JIS 5호` 는 평판이라 필요 없다.
    분류의 기본 칸만으로 둘을 담으면 절반이 늘 비고, 그 빈 칸이 "안 쟀다" 인지
    "이 규격에 없는 값" 인지 구별되지 않는다.

    **왜 축에 적는가:** 값마다 물으면 같은 답을 수만 번 저장하는 셈이다
    (`parent_slug` 와 같은 판단)."""
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
        # 기준정보가 수만 개가 되면 피커 검색이 `ILIKE '%낱말%'` 이다. B-tree 는 못
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
    parent_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    """상위 축의 값. `SECC` 의 부모는 `Steel`, `Steel` 의 부모는 `Metal`.

    **비워 둘 수 있다.** 부모를 모르는 값이 있어도 시스템이 멈추면 안 된다 —
    `closed` 를 안 켠 것과 같은 판단이다. 부모가 없으면 좁히기가 안 될 뿐이다.

    부모가 지워지면 `NULL` 이 된다. 값 자체는 살아 있어야 한다 — 가리키던 재료가
    무엇이었는지는 그대로여야 하기 때문이다."""

    extra_fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """이 값**만** 갖는 치수 칸. 상위 분류의 기본 칸에 더해진다.

    `ASTM E8 R1` 은 환봉이라 직경이 필요하고 `JIS 5호` 는 평판이라 필요 없다.
    규격은 계속 늘어나는데 그때마다 분류의 기본 칸을 늘리면, 안 쓰는 규격에도
    빈 칸이 하나씩 쌓인다.

    모양은 기본 칸과 같다(`key`·`label`·`dimension`·`si_unit`·`is_required`·
    `help`). **기본 칸과 같은 키는 못 쓴다** — 서버가 거절한다."""
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """치수 등 이 값이 갖는 속성. **언제나 SI 로 담는다** — 규격서가 mm 로 적혀
    있어도 저장은 m 다. 화면이 실무 단위로 바꿔 보여 준다.

    키는 그 시험 종류가 선언한 칸(`test_specimen_fields.key`)이다. 스키마에 없는
    키는 서버가 거절한다 — 오타 하나가 조용히 새 속성이 되면 아무도 못 찾는다."""

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


class SpecimenField(Base):
    """시편 **분류**가 선언하는 기본 치수 칸.

    "인장 시편이면 늘 게이지 길이가 필요하다" 처럼, 그 분류에 속한 규격 전부가
    갖는 값이다. 규격마다 다른 것은 규격이 따로 더한다
    (`VocabularyTerm.extra_fields`).

    ## 왜 시험 종류가 아니라 분류인가

    처음에는 시험 종류에 매달았다. 그런데 **같은 시험 안에서도 시편에 따라 칸이
    갈린다** — 인장은 평판(폭·두께)과 환봉(직경)이 다르고, DMA 는 3점 굽힘
    (지지 간격 있음)과 인장 필름(없음)이 다르다. 실측: DMA 실파일 172개 전부에
    장비가 적은 `Geometry name` 이 있고 155개가 `3 Point Bending Clamp` 였다.

    시험 종류는 "무엇을 쟀나" 이고 분류는 "무엇을 잘랐나" 다. 둘은 자주 겹치지만
    같은 것이 아니다.
    """

    __tablename__ = "specimen_fields"
    __table_args__ = (
        UniqueConstraint("category_term_id", "key", name="uq_specimen_fields_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_term_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="CASCADE"),
        index=True,
    )
    """시편 분류 축의 값. 이 분류에 속한 규격 전부가 이 칸을 갖는다."""
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    dimension: Mapped[str] = mapped_column(String(20))
    si_unit: Mapped[str] = mapped_column(String(20))
    """**저장 단위.** 값은 언제나 SI 로 담는다 — 규격서가 mm 로 적혀 있어도."""
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    help: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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


class VocabularyMerge(Base):
    """병합 기록. **없어진 값의 스냅샷.**

    병합하면 `src` 가 사라진다. 되돌리기는 안 하지만 — 되돌리려면 참조를 다시
    갈라야 하는데 어느 행이 어느 쪽이었는지 알 수 없다 — **무엇을 무엇으로
    합쳤는지는 답할 수 있어야 한다.** 반년 뒤 "포스코(주) 는 어디 갔나" 를
    묻는 사람에게 줄 답이 이것뿐이다.
    """

    __tablename__ = "vocabulary_merges"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabularies.id", ondelete="CASCADE"), index=True
    )
    source_value: Mapped[str] = mapped_column(String(200))
    """사라진 값의 표기."""
    target_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    target_value: Mapped[str] = mapped_column(String(200))
    moved_count: Mapped[int] = mapped_column(Integer, default=0)
    """옮긴 참조 수. 병합이 실제로 무엇을 건드렸는지."""
    merged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VocabularyDismissal(Base):
    """ "이 둘은 다른 값이다" 라고 사람이 판정한 쌍.

    병합 후보 탐지는 넓게 건진다 — `'포스코'` 와 `'포스코특수강'` 이 후보로 뜬다.
    **기각한 쌍을 기억하지 않으면 같은 것을 매번 다시 묻는다.** 그러면 목록을
    아무도 안 본다.
    """

    __tablename__ = "vocabulary_dismissals"
    __table_args__ = (
        UniqueConstraint("low_term_id", "high_term_id", name="uq_vocabulary_dismissals"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: 쌍을 **정렬해 저장한다** — (a,b) 와 (b,a) 가 다른 행이 되면 유니크가 무의미하다.
    low_term_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id", ondelete="CASCADE")
    )
    high_term_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id", ondelete="CASCADE")
    )
    dismissed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VocabularyDriftCheck(Base):
    """어긋남 점검 한 번의 결과. **"지금 0" 이 아니라 "언제부터 0" 을 답한다.**

    문자열 컬럼을 지우는 조건(ADR 0010 Contract 4-2)이 "한 릴리스 동안 0" 이다.
    그런데 점검이 사람이 누를 때만 돌면 일주일 뒤에 그 질문에 답할 수가 없다 —
    눌렀을 때만 0 이었는지, 내내 0 이었는지 알 방법이 없다.

    **지켜보는 게이트가 아니면 게이트가 아니다.** 그래서 워커가 스스로 돌리고
    여기 남긴다.
    """

    __tablename__ = "vocabulary_drift_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), index=True
    )
    """**`now()` 가 아니라 `clock_timestamp()` 다.** 포스트그레스의 `now()` 는
    트랜잭션 시작 시각이라, 한 트랜잭션에 넣은 두 줄이 같은 시각을 받는다.
    고치기는 한 번에 두 줄을 남기므로(고치기 전·후) 그러면 순서가 사라지고
    "언제부터 0" 이 틀린 답을 낸다."""
    total: Mapped[int] = mapped_column(Integer, default=0)
    """어긋난 행 수. **0 이 정상이다.**"""
    detail: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """어느 칸이 몇 건인지와 예시 몇 개. 수만 남기면 나중에 무엇이 벌어졌는지
    알 수 없다 — 그때 그 행은 이미 고쳐졌을 수 있다."""
    source: Mapped[str] = mapped_column(String(20), default="worker")
    """`worker` | `manual`. 사람이 눌러 본 것과 저절로 돈 것을 가른다.

    연속 0 은 둘 다 센다 — 사람이 눌러서 잰 0 도 그 시점에 0 이었다는 증거다.
    가르는 이유는 나중에 "저절로 돌긴 했나" 를 물을 수 있어야 해서다."""
