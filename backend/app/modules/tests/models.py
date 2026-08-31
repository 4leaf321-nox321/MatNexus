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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
#:
#: **`imported` 는 파일 처리 상태가 아니다.** 나머지 넷은 올린 원본을 읽는 과정
#: (올림 → 읽는 중 → 읽음/실패)인데, 표로 들어온 시험은 그 길을 아예 안 지난다 —
#: 원본 파일이 없다. `parsed` 로 두면 "읽었다" 는 거짓말이 되고, `uploaded` 로
#: 두면 영영 처리를 기다리는 것처럼 보인다.
#:
#: **모자란 상태가 아니다.** 곡선이 있는 시험은 비선형 물성까지 가고, 표로 들어온
#: 시험은 요약값이 답할 수 있는 데까지 간다 — 낼 수 있는 물성의 범위가 다를 뿐이다.
RUN_STATUSES = ("uploaded", "parsing", "parsed", "failed", "imported")

#: 요약값의 출처. 이 구분이 없으면 '장비가 준 항복강도'와 '우리가 계산한
#: 항복강도'가 한 칸에 섞여, 나중에 계산식을 고쳤을 때 무엇이 바뀐 값인지 모른다.
SUMMARY_SOURCES = ("instrument", "matnexus")


class TestType(Base):
    """시험 종류 정의. 부서 관리자와 시스템 관리자가 추가·수정한다."""

    __tablename__ = "test_types"
    __table_args__ = (
        # **지운 행은 key 를 잡아 두지 않는다**(재료와 같은 판단, 2026-08-28).
        # 그냥 유니크면 지운 종류의 key 로 다시 만들 수 없는데, 화면 어디에도
        # 그 종류가 없어서 빠져나갈 길이 없다.
        Index(
            "uq_test_types_key",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

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
    key: Mapped[str] = mapped_column(String(50), index=True)
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
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    """저장할 때마다 오르는 번호. **덮어쓰기를 막는 근거다**(ADR 0015).

    `updated_at` 을 쓰지 않은 이유를 실측으로 확인했다(2026-08-24): `onupdate` 는
    **부모 행이 더러울 때만** 걸린다. 채널 라벨만 고치면 부모는 안 바뀌므로
    `updated_at` 이 그대로다 — 바뀌었는데 안 바뀐 것처럼 보인다.

    이 정의는 **한 벌 통째로 갈아 끼운다.** 그래서 뒤에 저장한 쪽이 앞을 덮는
    것이 아니라 **지운다** — 자식까지 통째로. 그 사고를 막는 자리다.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    """지운 때. **행은 남는다** — 휴지통에서 되살린다(재료와 같은 모델).

    이것이 있으면 위의 유니크는 **부분 인덱스**여야 한다. 그냥 두면 지운 행이
    key 를 붙들어, 같은 key 로 다시 만들 때 「이미 있습니다」 가 나오는데 화면
    어디에도 그것이 없다 — 재료에서 그대로 터졌다(2026-08-28 이관 사고).
    """


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
    instrument_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    """장비 기준정보(ADR 0010). 같은 장비를 'Zwick Z100'·'zwick z100' 으로 적으면
    장비별 비교가 갈린다."""

    division: Mapped[str | None] = mapped_column(String(100), nullable=True)
    division_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    """**어느 사업부가 등록한 시험인가.** 기준정보를 거친다(ADR 0010).

    부서(`workspace_id`)와 다르다. 부서는 **누가 볼 수 있는가**를 정하는 권한의
    축이고, 이것은 **누가 낸 데이터인가**를 적는 이름표다. 한 부서 계정으로 여러
    사업부의 판을 올리는 일이 실제로 있고, 그때 부서로는 그 둘을 못 가른다.

    자유 문자열로 두면 `전장`·`전장사업부`·`전장 사업부` 가 갈려서 「사업부별로
    몇 건」이 답이 셋 나온다 — 축을 둔 이유 그대로다.
    """

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

    dimensions: Mapped[dict[str, float]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """**이 시험에서 잰** 시편 치수. 키는 시편 규격이 정한 칸 이름, 값은 SI.

    ## 왜 시편이 아니라 여기에도 두나

    실사용에서 나왔다 — *"시편 하나에 여러 시험으로 넣으니까, 그 시험은 다 같은
    두께, 폭을 가지게 되어 버린다"*.

    치수는 **그 시험에서 잰 값**이다. 장비 파일마다 `a0`·`b0` 가 들어 있고, 같은
    시편으로 여러 번 재면(비파괴 시험) 그 값이 달라질 수 있다. 시편 행 한 곳에만
    두면 시험 N개가 한 벌을 나눠 쓰게 되고, 두 번째 파일이 들고 온 값은 갈 자리가
    없다.

    ## 시편을 없애지 않는 이유

    비파괴 시험은 한 시편으로 여러 번 잰다(DMA 주파수 스윕 + 온도 스윕). 통계는
    **시편 n개의 흩어짐**을 본다(ADR 0008) — 시험=시편이면 스윕 둘이 시편 둘로
    세어져 n 이 부푼다. 그리고 안 시험한 시편도 기록으로 남아야 한다.

    그래서 엔티티가 아니라 **치수만 내렸다.** 읽는 순서는 셋이다:

        ① 이 시험이 잰 값       여기
        ② 시편이 잰 값          `Specimen.dimensions`
        ③ 규격이 정한 공칭      규격 값의 속성

    밀도가 이미 같은 모양이다(시료 실측 → 재료 공칭). 그리고 그 셋 중 **어느
    것을 썼는지 화면이 말한다** — 값이 두 곳에 살면 "어느 게 맞느냐" 를 묻게
    되고, 답이 안 보이면 그 자리가 조용히 틀리는 자리가 된다."""

    parse_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("format_profiles.id"), index=True, nullable=True
    )
    """**이 파일은 이 형식으로 읽는다** — 사람이 고른 것.

    비어 있으면 지문으로 자동으로 고른다(`_pick_reader`). 자동이 틀리는 자리가
    실제로 있다: 같은 장비의 형식이 조금 달라져 프로파일을 하나 더 만들면 지문이
    겹치고, 우선순위가 높은 쪽이 이겨서 **엉뚱한 것으로 읽거나 아예 실패한다.**

    그때 「다시 읽기」 만 있으면 같은 선택을 그대로 반복한다 — 고칠 자리가
    없었다. 고른 것을 여기 남겨 두는 이유는, 나중에 누가 다시 읽어도 **그 결정이
    이어져야** 하기 때문이다. 큐 페이로드에만 실으면 재시도에서 사라진다.
    """

    temperature_step_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """**겹칠 수 있는 온도 단이 몇이었나.** 읽을 때 세어 둔다. 안 세어 본 것은 `None`.

    DMA 는 같은 시험종류 아래 성격이 다른 두 가지가 온다.

        주파수-온도 스윕   온도 여러 단 → 겹쳐서 마스터커브를 만든다
        변형률 스윕        온도 한 단   → 겹칠 것이 없다(선형 구간을 본다)

    시험종류 키로는 못 가른다. 그런데 재료 화면이 「마스터커브가 없는 DMA 3건」
    이라고 재촉할 때 변형률 스윕이 섞여 있으면 **할 수 없는 일을 남은 일로 적는
    셈**이다. 그래서 읽는 김에 세어 둔다 — 목록에서 이걸 다시 재려면 시험마다
    Parquet 을 열어야 한다.

    **`None` 은 0 이 아니다.** 이 칸이 생기기 전에 읽은 시험이라 「모른다」 는
    뜻이고, 모르는 것을 「못 한다」 로 세면 그 시험은 화면에서 조용히 빠진다.
    `scripts/backfill_temperature_steps.py` 가 채운다."""

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
    dimension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """**단위만으로는 못 가르는 것이 있다.**

    항복 변형률 0.0686 과 네킹 후보 위치 14 는 저장 단위가 둘 다 `1` 이다. 앞은
    6.86% 로 읽어야 하고 뒤는 14 그대로다 — 차원이 없으면 화면이 둘을 같게
    다루고 변형률이 소수로 나온다. 채널에서 이미 겪은 문제다.

    장비가 준 값(`instrument`)은 비어 있다 — 파서가 차원을 알려 주지 않는다.
    그건 그대로 두고 우리가 계산한 값부터 채운다."""

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
        Index(
            "uq_format_profiles_scope_key",
            "owner_workspace_id",
            "key",
            unique=True,
            # PG15+. 없으면 NULL != NULL 이라 **전역 프로파일끼리 같은 키가 허용된다.**
            # 재료가 같은 문제를 겪어 같은 방식으로 막았다(ADR 0004).
            postgresql_nulls_not_distinct=True,
            # **지운 행은 key 를 잡아 두지 않는다.** 그냥 유니크면 지운 프로파일의
            # key 로 다시 만들 수 없는데 화면 어디에도 그것이 없다(2026-08-28 재료).
            postgresql_where=text("deleted_at IS NULL"),
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

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    """지운 때. **행은 남는다** — 휴지통에서 되살린다(재료와 같은 모델).

    이것이 있으면 위의 유니크는 **부분 인덱스**여야 한다. 그냥 두면 지운 행이
    key 를 붙들어, 같은 key 로 다시 만들 때 「이미 있습니다」 가 나오는데 화면
    어디에도 그것이 없다 — 재료에서 그대로 터졌다(2026-08-28 이관 사고).
    """
