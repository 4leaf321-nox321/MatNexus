"""물성 이름 사전 — **「항복응력」이 어느 물성인가에 답한다.**

MCP/AI 가 길을 찾으려면 사람이 부르는 말과 DB 의 키가 이어져야 한다. 지금은 물성
이름이 **세 곳에 따로** 산다:

    문헌 정의        catalog_definitions      271개   mechanical.yield_strength
    사내 선언 물성    기준정보 property_item     9개   「항복강도」(Rp, stress)
    처리 결과 키      matcore 레지스트리                proof_stress

ADR 0027 이 *"기준정보 `property_item` 축과도 매핑 표로 잇는다(통합하지 않는다)"*
고 미뤄 둔 그 표가 여기다.

## 왜 급한가 — 실측(2026-09-08)

「항복」이 붙은 문헌 정의가 일곱이고, **이름이 정확히 「항복응력」인 것은 유변학
물성**이다:

    rheological.yield_stress    「항복응력」      9건   8 ~ 20 Pa      ← 페이스트가 흐르는 응력
    mechanical.yield_strength   「항복강도」    486건   0.1 ~ 2310 MPa  ← 사람이 물은 것

사람이 「항복응력이 200MPa 근처인 재료」를 물으면 금속의 항복강도를 뜻하는데,
이름만 맞춰 찾으면 **9건짜리 엉뚱한 물성**을 준다. 조용히 틀린 답이다.

## 왜 이관물 옆에 따로 두는가

`catalog_definitions` 는 MaterialTwin 이관물이고 **배포마다 원본으로 덮인다**
(`deploy.ps1` 이 이관을 자동으로 돌린다). 거기에 별칭 칸을 더하면 다음 배포에
조용히 사라진다. `catalog_links` 가 사내 연결을 이관물 옆에 따로 둔 것과 같은
판단이다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 별칭이 어디서 왔나. **지어낸 것과 규격에서 온 것을 구별한다** — 규격 표현은
#: 근거가 있고, 사람이 손으로 더한 것은 그 사람의 판단이다.
ALIAS_SOURCES = ("standard", "vendor", "manual", "seed")

#: 두 물성이 어떤 사이인가.
#:
#: **`same_as` 를 함부로 쓰지 않는다.** 「항복강도」와 「변형률속도별 항복강도」는
#: 같지 않다 — 다른 것을 다르게 적는 것이 이 표의 값이다.
LINK_KINDS = ("same_as", "narrower", "related")


class PropertyAlias(Base):
    """물성 하나를 부르는 다른 이름.

    한글·영문·기호·규격 표현이 다 들어온다 — 「항복강도」·「yield strength」·
    「Rp0.2」·「0.2% proof stress」·「σy」.

    **정규화 열로 찾는다.** 사람은 「0.2% proof」·「0.2 % Proof Stress」 를 제각각
    친다. 기준정보의 `compare_key` 와 같은 규칙을 쓴다.
    """

    __tablename__ = "property_aliases"
    __table_args__ = (
        # 같은 물성에 같은 별칭이 둘일 이유가 없다.
        UniqueConstraint("property_key", "normalized", name="uq_property_aliases"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_key: Mapped[str] = mapped_column(String(120), index=True)
    """`catalog_definitions.key`. **FK 를 안 건다** — 이관이 정의를 지웠다 다시
    넣으면 FK 가 별칭을 함께 지운다. 끊어진 것은 점검이 센다."""

    alias: Mapped[str] = mapped_column(String(200))
    """사람에게 보이는 그대로."""
    normalized: Mapped[str] = mapped_column(String(200), index=True)
    """찾을 때 쓴다. `compare_key(alias)`."""

    source: Mapped[str] = mapped_column(String(20), default="manual")
    """`ALIAS_SOURCES` 중 하나."""
    note: Mapped[str | None] = mapped_column(Text)
    """어디서 온 이름인지 — 「ASTM E8 표기」 처럼."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PropertyLink(Base):
    """문헌 물성 정의 ↔ 사내 물성 항목. **ADR 0027 이 미뤄 둔 매핑이다.**

    통합하지 않고 잇기만 한다 — 단위 정본이 서로 다르기 때문이다(문헌은 원본
    taxonomy, 사내는 matcore 차원). 억지로 꿰면 값이 상한다.
    """

    __tablename__ = "property_links"
    __table_args__ = (
        UniqueConstraint("property_key", "term_id", "scale", name="uq_property_links"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_key: Mapped[str] = mapped_column(String(120), index=True)
    """`catalog_definitions.key`. 위와 같은 이유로 FK 를 안 건다."""

    term_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="CASCADE"),
        index=True,
    )
    """기준정보 `property_item` 축의 값. **이쪽은 FK 다** — 우리 표이고, 값이
    지워지면 매핑도 뜻이 없다."""

    kind: Mapped[str] = mapped_column(String(20), default="same_as")
    """`LINK_KINDS` 중 하나."""
    scale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """이 매핑이 **어느 눈금의 값에만** 해당하는가 — `HV`·`HRC`.

    사내 항목 「경도」 는 하나인데 문헌은 비커스·브리넬·로크웰이 다른 키다. 눈금 없이
    이으면 HRC 60 이 비커스 검색에 섞여 나오고, 숫자 크기가 비슷해 눈에 안 띈다
    (2026-09-12). 비어 있으면 눈금을 안 가린다 — 항복강도처럼 눈금이 없는 항목."""
    note: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
