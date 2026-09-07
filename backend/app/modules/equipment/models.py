"""보유 장비 — **우리가 실제로 가진 설비 한 대 한 대.**

측정법(`metrology`)이 *"이 물성은 무엇으로 재는가"* 라는 **지식**이라면, 여기는
*"그중 우리 것은 어디 있고 언제 교정했나"* 라는 **자산**이다. 둘을 한 표에 두지
않는 이유가 셋이다.

1. **이관물은 사람이 못 고친다.** `metrology.instruments` 는 MaterialTwin 에서
   이관한 218대이고, 이관기가 `owned`·`owner_name` 까지 원본 값으로 덮어쓴다.
   그리고 `deploy.ps1` 이 배포마다 이관을 자동으로 돌린다 — 거기에 사내 위치를
   적으면 **다음 배포에 조용히 되돌아간다.**
2. **모델과 개체는 다르다.** `instruments` 에는 `UNIQUE(vendor, model)` 이 걸려
   있다. 같은 모델 세 대가 각각 다른 방에 있고 교정 이력이 다른데, 그 표는
   카탈로그에 인쇄된 **모델** 한 줄만 담는다.
3. **불변과 가변을 섞지 않는다**(AGENTS.md). 벤더 사양은 안 바뀌고, 위치·상태·
   담당자는 매달 바뀐다.

## 얼굴은 장비명, 자산번호는 대조용이다

사람이 장비를 부르는 말은 「생기연 DMA」·「대형 챔버」 다 — 자산번호로도
관리번호로도 부르지 않는다(2026-09-07 확인). 그래서 목록과 상세에서 큰 글씨는
`name` 이고, 자산번호는 **「그 장비가 이 장비 맞나」 를 스티커와 대조할 때** 쓴다.

둘 다로 찾힌다. 이름은 부분 일치(「DMA」 → 「생기연 DMA」), 자산번호는 정확 일치다.

**우리가 채번하지 않는다.** 재료번호(`materials.code`)는 DB 시퀀스가 만들지만
자산번호는 이미 물리적으로 존재하는 것을 받아 적는 것이다. 그래서 형식을 강제하지
않고, **비워 둘 수도 있다** — 스티커 없는 장비를 못 넣게 하면 사람들이 가짜
번호를 지어낸다. PostgreSQL 은 `NULL` 을 유일 제약에서 빼 주므로 그대로 된다.

대신 `asset_key` 로 정규화해 둔다. 스티커를 보고 치는 것이라 `A-2019-0142` ·
`a20190142` · `A 2019 0142` 가 섞이는데, 어떻게 쳐도 같은 장비에 닿아야 한다.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 장비가 지금 어떤 상태인가.
#:
#: **폐기는 삭제가 아니다.** 지난 시험이 그 장비를 가리키고 있고, 그 provenance 가
#: 끊기면 "이 물성값을 무엇으로 쟀나" 에 답할 수 없다. 목록에서 빠질 뿐 행은 산다.
STATUSES = ("active", "maintenance", "idle", "retired")

#: 교정 결과. **「조건부」 가 필요하다** — 일부 범위만 합격인 성적서가 실제로 있다.
CALIBRATION_RESULTS = ("pass", "conditional", "fail")

#: 부속 종류. 늘어날 수 있으므로 화면이 목록을 정하지 않는다.
PART_KINDS = ("load_cell", "extensometer", "chamber", "sensor", "fixture", "other")

#: 우리 것인가, 남의 것을 쓰는가.
#:
#: **위탁 시험도 우리 물성을 만든다.** 남의 장비로 낸 값이라고 데이터가 덜 중요한
#: 것이 아니라, 「그 값이 어디서 나왔나」 에 답하려면 그 장비도 적혀 있어야 한다.
#: 다만 위치·교정을 우리가 관리하지는 않으므로 목록에서 갈라 볼 수 있어야 한다.
OWNERSHIPS = ("internal", "external")


def asset_key(raw: str | None) -> str | None:
    """자산번호를 찾기용으로 정규화한다 — 영숫자만 남기고 대문자로.

    `A-2019-0142` · `a20190142` · `A 2019 0142` 가 모두 `A20190142` 가 된다.
    기준정보의 `normalized` 와 같은 판단이되 **구두점을 지운다** — 거래처 이름과
    달리 자산번호의 하이픈은 뜻을 나르지 않고 사람마다 다르게 친다.
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    return cleaned or None


class EquipmentUnit(Base):
    """장비 한 대. **모델이 아니라 개체다.**"""

    __tablename__ = "equipment_units"
    __table_args__ = (
        # 자산번호는 사내 유일하다. NULL 은 여러 개여도 된다(스티커 없는 장비).
        UniqueConstraint("asset_key", name="uq_equipment_units_asset_key"),
        # **장비명이 주 검색 수단이다.** 사람은 「DMA」 를 치고 「생기연 DMA」 를
        # 찾으므로 부분 일치가 필요하다. 재료 검색이 `ILIKE` 가지를 늘리는 것을
        # 경계한 것은 5만 행 기준이고(118ms 대 4.6ms), 장비는 많아야 수백 대다 —
        # 같은 저울이 아니다. 그래도 정렬·정확 일치가 색인을 타게 걸어 둔다.
        Index("ix_equipment_units_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    asset_no: Mapped[str | None] = mapped_column(String(80))
    """스티커에 적힌 그대로. 사람에게 보이는 것은 이 값이다."""
    asset_key: Mapped[str | None] = mapped_column(String(80), index=True)
    """`asset_no` 를 정규화한 것. 찾을 때만 쓴다 — 화면에 보이지 않는다."""

    name: Mapped[str] = mapped_column(String(120))
    """**사람이 부르는 이름.** 「생기연 DMA」·「대형 챔버」 처럼 쓴다.

    관리번호(`UTM-003`)가 아니다 — 실제로 그렇게 부르지 않는다(2026-09-07 확인).
    자유 문장이라 장소·크기 같은 단서가 섞여 들어오는데, 그대로 둔다. 사람이
    부르는 말을 우리가 교정하면 아무도 안 찾는 이름이 된다.

    **거르기는 이 문자열이 아니라 기준정보로 한다.** 「생기연에 있는 장비 전부」 는
    이름에 「생기연」 이 든 것을 훑어서는 안 나온다 — 시험실 축이 그 답을 낸다."""

    #: 문헌 장비 카탈로그의 모델. **선택이다** — 문헌에 없는 사내 장비가 당연히 있다.
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("instruments.id", ondelete="SET NULL"), index=True
    )
    #: 기준정보 값의 **문자열 짝.** FK 만 두면 `apply_bindings` 기계를 못 탄다 —
    #: 그러면 사용수 집계·개명 전파·어긋남 검사가 이 표만 비껴간다(피커의
    #: 「쓰는 곳 N건」 이 조용히 틀려진다). 재료·시료·시편이 전부 이 모양이다.
    instrument_type: Mapped[str | None] = mapped_column(String(120))
    instrument: Mapped[str | None] = mapped_column(String(120))
    lab: Mapped[str | None] = mapped_column(String(120))

    #: 기준정보 「장비」 값. **`TestRun.instrument_term_id` 와 이어지는 고리다** —
    #: 시험 기록을 한 줄도 안 고치고 「이 물성을 낸 장비가 어느 방 몇 번인가」 가 풀린다.
    instrument_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
    )
    #: 기준정보 「장비 유형」. 유형이 `base_fields` 로 이 장비의 추가 칸을 정한다.
    type_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
    )

    #: 모델 참조가 없을 때 직접 적는다. 있으면 비워 두고 그쪽을 읽는다.
    #:
    #: **`vendor` 가 아니라 `manufacturer` 다.** 기준정보에는 축이 둘 있고 뜻이
    #: 다르다 — 「제조사」(만든 회사)와 「거래처」(사고파는 회사). 장비를 만든 곳은
    #: 제조사이고, 이름을 `vendor` 로 두면 재료 쪽 거래처 축과 헷갈린다.
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    serial_no: Mapped[str | None] = mapped_column(String(120))

    #: 기준정보 「제조사」. 재료·시료가 쓰는 그 축이다 — 같은 회사가 재료도 팔고
    #: 장비도 만든다(3M·듀폰). 축을 나누면 같은 이름이 두 목록에 쌓인다.
    manufacturer_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
    )

    #: 기준정보 「시험실」.
    lab_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id", ondelete="SET NULL"),
        index=True,
    )
    location_detail: Mapped[str | None] = mapped_column(String(200))
    """방 안 어디인가 — 「3번 벤치」. 시험실만으로는 큰 방에서 못 찾는다."""

    ownership: Mapped[str] = mapped_column(String(20), default="internal", index=True)
    """`OWNERSHIPS` 중 하나. 사내 장비인가, 위탁 기관 장비인가."""

    #: **장비를 들고 있는 조직.**
    #:
    #: 기준정보에 조직 축을 따로 두려다 걷어냈다(2026-09-07) — 부서가 이미 조직
    #: 트리다(`Workspace.parent_id`: *"조직은 평면이 아니다 — 본부 아래 팀이 있고,
    #: 같은 이름의 팀이 본부마다 있을 수 있다"*). 축을 하나 더 두면 같은 조직이 두
    #: 목록에 쌓이고 합칠 방법이 없다.
    #:
    #: 그래서 **사업부별 현황은 이 트리를 타고 올라가서** 낸다. 장비에 상위 조직을
    #: 따로 적지 않는다 — 같은 답을 두 번 저장하면 언젠가 갈린다.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    owner_name: Mapped[str | None] = mapped_column(String(120))
    owner_contact: Mapped[str | None] = mapped_column(String(120))

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    """`STATUSES` 중 하나."""

    commissioned_on: Mapped[date | None] = mapped_column(Date)
    retired_on: Mapped[date | None] = mapped_column(Date)

    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """장비 유형이 정한 칸의 값(`type_term_id` → 축의 `base_fields`).

    **아무 칸이나 넣지 않는다.** 유형이 선언한 칸만 화면이 그리고 서버가 받는다 —
    자유 JSON 이 되면 같은 것을 사람마다 다른 키로 적는다."""

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EquipmentPart(Base):
    """부속·센서 — **개체의 실제 측정 범위를 정하는 것.**

    문헌 capability 의 「±50kN」 은 모델 사양이다. 실제로는 5kN 로드셀이 물려 있을
    수 있고, 그러면 그 장비로 잰 값의 범위는 5kN 이다. 로드셀·신율계·챔버가 각각
    따로 교정되므로 교정 이력도 부속에 붙을 수 있어야 한다.
    """

    __tablename__ = "equipment_parts"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("equipment_units.id", ondelete="CASCADE"),
        index=True,
    )
    """**개체가 지워지면 함께 지워진다.** 부속은 장비를 떠나 따로 살지 않는다."""

    kind: Mapped[str] = mapped_column(String(40), index=True)
    """`PART_KINDS` 중 하나."""
    label: Mapped[str] = mapped_column(String(120))

    asset_no: Mapped[str | None] = mapped_column(String(80))
    """부속에도 스티커가 붙는다. 다만 **유일 제약을 걸지 않는다** — 부속 번호 규칙이
    장비와 다른 곳이 있고, 없는 규칙을 강제하면 입력이 막힌다."""
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    serial_no: Mapped[str | None] = mapped_column(String(120))

    capacity: Mapped[str | None] = mapped_column(String(120))
    """「50 kN」·「±5 mm」. **숫자로 쪼개지 않는다** — 부속 종류마다 차원이 다르고,
    지금은 사람이 읽는 것이 목적이다. 범위로 거르는 요구가 생기면 그때 쪼갠다."""

    installed_on: Mapped[date | None] = mapped_column(Date)
    removed_on: Mapped[date | None] = mapped_column(Date)
    """뗀 날. **행을 지우지 않는다** — 그때 그 부속으로 잰 시험이 있다."""

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EquipmentCalibration(Base):
    """교정 한 건 — **유효기간이 있어야 나중에 물을 수 있다.**

    「이 물성값은 교정 만료된 장비로 잰 것인가」 는 값을 만들 때가 아니라 **물을 때**
    판정한다. 시험일과 유효기간을 대조하는 것이라, 지금 경고를 붙이지 않아도 기록만
    남으면 나중에 답할 수 있다.
    """

    __tablename__ = "equipment_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("equipment_units.id", ondelete="CASCADE"),
        index=True,
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("equipment_parts.id", ondelete="CASCADE"), index=True
    )
    """부속만 교정한 건이면 여기가 찬다. **장비는 항상 적는다** — 부속에만 매달면
    "이 장비의 교정 이력" 을 부속을 거쳐야만 찾게 된다."""

    performed_on: Mapped[date] = mapped_column(Date, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, index=True)
    """**비워 둘 수 있다.** 유효기간이 안 적힌 성적서가 있고, 그때 우리가 1년을
    지어내면 안 된다 — 빈 칸이 틀린 값보다 낫다."""

    agency: Mapped[str | None] = mapped_column(String(200))
    certificate_no: Mapped[str | None] = mapped_column(String(120))
    result: Mapped[str] = mapped_column(String(20), default="pass")
    """`CALIBRATION_RESULTS` 중 하나."""

    storage_path: Mapped[str | None] = mapped_column(Text)
    """성적서 파일(filestore). 원본이 있어야 「정말 그런가」 를 되짚을 수 있다."""

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
