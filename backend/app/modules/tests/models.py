"""시험 — 종류 정의, 실행 기록, 곡선, 요약값.

**시험 종류를 코드가 아니라 데이터로 둔다**(개발계획 ④ 수준 2). 어떤 시험이
있고, 어떤 채널·단위를 갖고, 어떤 조건을 입력받는지는 이 테이블들이 정한다.
새 시험(압축 등)을 받으려면 관리 화면에서 종류와 채널을 추가하고 파서 플러그인
하나만 붙이면 되고, 등록·목록·조회·곡선 표시는 배포 없이 동작한다.

**화면 레이아웃까지 데이터로 두지는 않는다.** 기존 앱(MaterialAppVer2)과 65는
탭 구성·필드 배치·ID 규칙까지 JSON 이었는데, 그러면 검색·검증·화면이 전부
'무엇이 있을지 모르는' 상태로 짜여야 한다. 65가 그 대가를 치렀다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 채널·조건이 가질 수 있는 물리 차원. 단위 변환이 이것을 기준으로 한다.
DIMENSIONS = (
    "length",
    "force",
    "stress",
    "strain",
    "strain_rate",
    "velocity",
    "time",
    "temperature",
    "frequency",
    "mass",
    "angle",
    "dimensionless",
)

#: 조건 입력 항목의 값 종류.
CONDITION_VALUE_TYPES = ("number", "text", "choice", "date", "boolean")

#: 시험 실행 상태.
RUN_STATUSES = ("uploaded", "parsing", "parsed", "failed")

#: 요약값의 출처. 이 구분이 없으면 '장비가 준 항복강도'와 '우리가 계산한
#: 항복강도'가 한 칸에 섞여, 나중에 계산식을 고쳤을 때 무엇이 바뀐 값인지 모른다.
SUMMARY_SOURCES = ("instrument", "matnexus")


class TestType(Base):
    """시험 종류 정의. 관리 화면에서 추가·수정한다."""

    __tablename__ = "test_types"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    """`tensile`, `dma_strain_sweep`. 코드가 참조하는 안정된 이름이다.

    기존 앱은 **라벨 문자열**로 필드를 찾았다(`label:contains(...)`). 라벨 문구를
    바꾸면 ID 생성이 조용히 깨졌다. 표시용 라벨과 참조용 키를 분리한다."""
    label: Mapped[str] = mapped_column(String(100))
    abbr: Mapped[str] = mapped_column(String(10))
    """시험 이름에 들어가는 약어(`TEN`). `matcore.naming.test_run_name` 이 쓴다."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """`matcore.registry` 에 등록된 파서 이름. 없으면 수동 입력만 받는다."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TestChannel(Base):
    """시험 종류가 갖는 데이터 채널(곡선의 열).

    `.tra` 를 열어 확인한 것: 인장 장비가 주는 것은 응력-변형률이 아니라
    **변위(mm)·하중(N)·시편폭(mm)** 이다. 공칭→진응력 변환과 n·r 값 계산은
    MatNexus 가 한다. 그래서 채널 정의는 원본 채널 기준으로 둔다.
    """

    __tablename__ = "test_channels"
    __table_args__ = (
        UniqueConstraint("test_type_id", "key", name="uq_test_channels_type_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    dimension: Mapped[str] = mapped_column(String(20))
    si_unit: Mapped[str] = mapped_column(String(20))
    """저장 단위. 곡선은 항상 이 단위로 정규화해 Parquet 에 넣는다.

    기존 앱은 단위를 라벨에 박아 뒀다(`Spec Thickness (mm)`). 그런데 ID 생성
    규칙이 그 라벨 문자열을 참조해서, 단위를 고치려면 라벨을 고쳐야 하고 라벨을
    고치면 ID 가 깨졌다. 라벨·단위·식별자를 한 문자열에 묶지 않는다."""
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class TestConditionField(Base):
    """시험 종류별 조건 입력 항목(온도·변형률속도·주파수 …).

    조건을 컬럼이 아니라 정의로 두는 이유: 지금 인장이 상온 고정인지 고온도
    하는지 확정되지 않았다. 나중에 고온 인장이 생겨도 관리 화면에서 항목만
    추가하면 된다 — 수준 2의 실질적 이득이 여기서 나온다.
    """

    __tablename__ = "test_condition_fields"
    __table_args__ = (
        UniqueConstraint("test_type_id", "key", name="uq_test_condition_fields_type_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    value_type: Mapped[str] = mapped_column(String(20))
    dimension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    si_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    choices: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class TestRun(Base):
    """시험 한 번. 시편 하나를 특정 종류로 시험한 회차."""

    __tablename__ = "test_runs"
    __table_args__ = (
        # 회차가 이름의 끝자리다. 기존 앱은 여기에 타임스탬프+6자리 난수를 붙여
        # 같은 파일을 다시 올리면 다른 이름이 나왔다 — 중복 판정이 불가능했다.
        UniqueConstraint(
            "specimen_id", "test_type_id", "seq_no", name="uq_test_runs_specimen_type_seq"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    specimen_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("specimens.id"), index=True
    )
    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), index=True
    )

    seq_no: Mapped[int] = mapped_column(Integer)
    record_name: Mapped[str] = mapped_column(String(400), index=True)

    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """`TestConditionField.key` → 값. 숫자는 SI 로 정규화해 넣는다."""
    input_units: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- 원본 파일 ---------------------------------------------------------
    # 원본은 항상 그대로 보관한다. 파서를 고쳐 다시 돌릴 수 있어야 하고, 장비가
    # 바뀌어 형식이 달라졌을 때 무엇이 왔었는지 확인할 수 있어야 한다.
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    source_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default="uploaded", server_default="uploaded", index=True
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """파서가 모르는 형식을 만나면 **명시적으로 실패**하고 이유를 여기 남긴다.
    조용히 잘못 읽는 것보다 낫다 — 잘못 읽힌 곡선은 나중에 찾아낼 수 없다."""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)

    registered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )


class Curve(Base):
    """정규화한 곡선 한 벌. 실데이터는 Parquet 파일에 있다.

    시험 하나가 수천~수만 행이다. DB 행으로 넣으면 금방 무너진다. 한 시험이
    곡선을 여러 개 가질 수 있어서(DMA 온도-주파수 스윕의 구간별) 별도 테이블로
    둔다.

    **불변이다.** 다시 처리하면 새 행을 만든다 — 표시 설정이나 라벨을 바꿨다고
    리비전이 찍히면 안 되지만, 데이터 자체는 덮어쓰지 않는다.
    """

    __tablename__ = "curves"
    __table_args__ = (UniqueConstraint("test_run_id", "key", name="uq_curves_run_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_runs.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(50))
    """`raw` 또는 구간 이름."""
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    storage_path: Mapped[str] = mapped_column(String(500))
    row_count: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    channels: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    """실제로 들어 있는 채널 키. 정의에 있어도 파일에 없을 수 있다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TestSummary(Base):
    """시험 한 번의 요약값(항복강도·최대하중·n값 …).

    `source` 로 **장비가 준 값**과 **우리가 계산한 값**을 나눈다. `.tra` 의 결과
    요약부에는 장비가 계산한 값이 이미 들어 있는데, 둘을 같은 칸에 섞으면
    나중에 계산식을 고쳤을 때 어느 값이 바뀐 것인지 알 수 없다. 둘을 나란히
    두면 검증도 된다 — 우리 계산이 장비 값과 크게 다르면 뭔가 잘못된 것이다.
    """

    __tablename__ = "test_summaries"
    __table_args__ = (
        UniqueConstraint("test_run_id", "key", "source", name="uq_test_summaries_run_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_runs.id"), index=True
    )
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20))

    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """`.tra` 에는 `"Unknown"` 같은 문자열이 실제로 들어온다. 숫자 칸에 억지로
    넣지 않고, 값 없음은 NULL 로 둔다 — 집계에서 `"Unknown"` 이 하나의 값으로
    잡히면 통계가 오염된다."""
    si_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
