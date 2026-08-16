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
    """시험 종류 정의. 부서 관리자와 시스템 관리자가 추가·수정한다."""

    __tablename__ = "test_types"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True, index=True
    )
    """누구 것인가. `NULL` 이면 전역(재료·프로파일과 같은 모델, ADR 0004·0006).

    **처음에는 시스템 관리자 전용이었다.** 그런데 형식 프로파일을 부서 소유로
    연 순간 막다른 길이 생겼다 — 부서 관리자가 새 장비를 붙이려면 시험 종류가
    먼저 있어야 하는데, 그것을 만들 권한이 없었다. 새 장비란 대개 **없는 종류**를
    재는 장비다. 문을 반쪽만 연 셈이었다(ADR 0006)."""
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    """`tensile`, `dma_strain_sweep`. 코드가 참조하는 안정된 이름이다.

    기존 앱은 **라벨 문자열**로 필드를 찾았다(`label:contains(...)`). 라벨 문구를
    바꾸면 ID 생성이 조용히 깨졌다. 표시용 라벨과 참조용 키를 분리한다.

    **소유가 부서로 갈려도 키는 전사에서 유일하다.** 프로파일과 다른 점이다.
    두 부서가 같은 DMA 를 하면 종류를 둘로 만들 것이 아니라 하나를 같이 써야
    하고, 키 유일성이 그것을 강제한다 — 중복을 만들려는 순간 이름이 부딪혀
    "이미 ○○부서가 만들어 뒀다" 를 보게 된다."""
    label: Mapped[str] = mapped_column(String(100))
    abbr: Mapped[str] = mapped_column(String(10))
    """시험 이름에 들어가는 약어(`TEN`). `matcore.naming.test_run_name` 이 쓴다."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """`matcore.registry` 에 등록된 파서 이름. 없으면 수동 입력만 받는다."""
    max_upload_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    """이 종류의 업로드 한도. NULL 이면 전역 기본값(`settings.max_upload_bytes`).

    종류마다 두는 이유: DMA 온도-주파수 스윕은 인장보다 한 자릿수 크다. 하나로
    맞추면 큰 쪽에 맞춰야 하고, 그러면 인장에 100MB 파일이 올라와도 안 막힌다."""

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

    adopted_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        # **`use_alter` 가 필요하다.** `test_runs → processing_results → test_runs`
        # 로 순환하는 FK 라, 한쪽을 테이블 생성문 안에 넣으면 어느 것을 먼저
        # 만들어도 상대가 아직 없다. 별도 ALTER 로 미루면 둘 다 만든 뒤에 건다.
        # 이것 없이 만들었더니 `create_all` 은 통과하는데 `drop_all` 이 "없는
        # 제약을 지우려" 해서 테스트 DB 정리가 통째로 깨졌다.
        ForeignKey(
            "processing_results.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_test_runs_adopted_result_id_processing_results",
        ),
        nullable=True,
        index=True,
    )
    """**이 시험의 물성은 이것 하나다.**

    처리 결과는 여러 벌 쌓인다 — 탄성계수를 회귀로도 재 보고 현으로도 재 보고,
    네킹 후보로 잘라도 보는 것이 정상 작업이다. 그런데 통계·비교·내보내기는
    시험당 값 하나가 필요하다. 저장된 결과가 전부 동등하면 "이 시험의 항복강도는
    얼마인가" 에 답할 수가 없다.

    대안 둘을 재 봤다(ADR 0007):
      최신이 곧 대표   실험 삼아 마지막에 돌린 것이 대표가 된다 — 조용히 틀리는 계열
      저장 = 확정      시행착오를 남길 수 없어 방법 간 비교가 불가능해진다

    그래서 **명시적 채택**이다. 시도는 자유롭게 쌓이고, 대표는 사람이 한 번 정한다.

    이 컬럼이 이 계층에서 **유일한 가변**이다. 원본·측정 곡선·처리 결과는 전부
    불변이고, 바뀌는 것은 이 포인터 하나뿐이다. 결과가 지워지면 NULL 이 된다."""

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

    source_metadata: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """파서가 원본에서 읽어낸 부가 정보를 **원문 그대로** 담는다.

    `.tra` 의 `Specimen thickness a0` 처럼 시험 결과가 아니라 **입력**인 값들이
    여기 온다. 자동으로 시편 실측치를 덮어쓰지 않는다 — 사람이 이미 재어 넣은
    값을 장비 파일이 조용히 바꾸면, 어느 것이 맞는지 나중에 알 수 없다.
    화면이 "이 값으로 채울까요?" 를 물어보는 데 쓴다."""
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    """무엇으로 읽었는가(`profile:ta_dma850` · `zwick_tra:1`).

    20자였는데 `profile:dma_e2e_profile` 이 `profile:dma_e2e_prof` 로 잘렸다.
    **어느 프로파일이 읽었는지 알 수 없으면 이 값을 남기는 뜻이 없다** — 곡선이
    이상할 때 가장 먼저 보는 값이다."""
    """어느 버전 파서가 읽었는지. 파서를 고쳐 다시 돌릴 대상을 고를 때 쓴다."""

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

    kind: Mapped[str] = mapped_column(
        String(20), default="measured", server_default="measured"
    )
    """`measured`(측정) | `derived`(장비가 계산한 것).

    **한 파일에 성격이 다른 곡선이 섞여 온다.** 실측(TA DMA850 주파수-온도 스윕):

        Temperature Sweep - 2..7      측정 구간 6벌
        TTS - shift factors           장비가 맞춘 이동인자 aT·bT
        TTS - master curve (20.0 °C)  겹쳐 만든 마스터 곡선

    처음에는 뒤의 둘을 규칙에 안 맞다고 **버렸다.** 그러면 장비가 계산해 준 결과를
    잃는다. 그렇다고 섞어 두면 Phase 3 의 처리가 마스터 곡선을 원본으로 착각한다.

    요약값에서 `장비 / MatNexus` 를 나란히 두는 것과 같은 판단이다 — 버리지도
    섞지도 않고, **무엇인지 적어 둔다.**"""

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


class FormatProfile(Base):
    """장비 파일을 **어떻게 읽을지**를 담은 규칙. 코드가 아니라 데이터다.

    이 테이블이 있는 이유가 이 프로젝트의 확장성 전부다. 장비가 늘 때마다 파서를
    짜면 개발 비용도 문제지만, 더 큰 것은 **현장 파일이 개발자에게 오지 않는다**는
    점이다. 폐쇄망이면 더 그렇다 — 파일을 받아야 파서를 만들고, 만들면 배포해야
    하고, 그 왕복 동안 데이터는 안 들어온다.

    구조는 `matcore/readers/tabular` 가 자동으로 읽는다(인코딩·구분자·표·헤더·
    단위). 자동으로 안 되는 것은 **"이 열이 무엇인가"** 하나뿐이고, 그것을 사람이
    운영 서버에서 실제 파일을 보며 한 번 정해 여기에 저장한다.

    `definition` 의 모양은 `matcore/readers/profile` 이 정의한다. JSONB 로 두는
    이유: 규칙의 항목이 장비를 겪으면서 늘어난다. 컬럼으로 쪼개면 새 규칙이
    필요할 때마다 마이그레이션을 해야 하는데, 그러면 배포 없이 대응한다는 목적이
    무너진다.
    """

    __tablename__ = "format_profiles"
    __table_args__ = (
        UniqueConstraint(
            "owner_workspace_id",
            "key",
            name="uq_format_profiles_scope_key",
            # PG15+. 없으면 NULL != NULL 이라 **전역 프로파일끼리 같은 키가 허용된다.**
            # 재료가 같은 문제를 겪어 같은 방식으로 막았다(ADR 0004).
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(50), index=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), index=True
    )
    """어느 시험 종류로 읽는가. 매핑의 목적지가 그 종류의 채널이다."""

    owner_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True, nullable=True
    )
    """만든 부서. **`NULL` 이면 전역이다** — 재료와 같은 모델(ADR 0004).

    관리자 전용으로 두었더니 실무가 막혔다: **장비는 부서마다 다른데, 남의 부서
    파일을 어떻게 읽을지를 시스템 관리자가 알 리 없다.** 그 지식은 사업부에 있다.

    그래서 부서 관리자가 자기 부서 프로파일을 만든다. 여러 부서가 같은 장비를
    쓰게 되면 관리자가 전역으로 올린다(이 컬럼을 NULL 로 — 승격은 UPDATE 한 줄).

    읽을 때는 **내 부서 것이 전역보다 먼저다.** 같은 장비라도 부서마다 소프트웨어
    설정이 달라 열 이름이 조금씩 다른 일이 실제로 있다."""

    definition: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """지문·표 선택·열 매핑·요약값·시편 정보. `readers/profile` 참조."""

    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """여러 프로파일이 한 파일에 맞을 때 높은 것이 이긴다.

    실제로 생긴다 — 같은 장비의 형식이 조금 달라져 프로파일을 하나 더 만들면,
    둘 다 `.csv` 에 `Angular frequency` 를 지문으로 갖는다."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
