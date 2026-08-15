"""시험 API 형태.

시험 종류 정의를 그대로 내려보낸다. 화면이 채널·조건 폼을 **정의에서 그려야**
새 시험 종류를 배포 없이 추가할 수 있다(수준 2). 화면이 항목을 하드코딩하면
정의를 데이터로 둔 이유가 사라진다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# --- 정의 -------------------------------------------------------------------


class TestChannelOut(BaseModel):
    key: str
    label: str
    dimension: str
    si_unit: str
    is_required: bool
    sort_order: int


class TestConditionFieldOut(BaseModel):
    key: str
    label: str
    value_type: str
    dimension: str | None
    si_unit: str | None
    choices: list[str] | None
    is_required: bool
    sort_order: int


class TestTypeOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    abbr: str
    description: str | None
    parser_key: str | None
    extensions: list[str]
    """이 종류가 읽을 수 있는 파일 확장자(소문자, 점 포함).

    파서 플러그인이 선언한 것을 그대로 내보낸다. 화면이 **파일만 보고 시험 종류를
    추정**하는 데 쓴다 — 종류가 열 개, 스무 개로 늘면 사람이 파일마다 고르는 것이
    일이 된다. 목록을 화면에 하드코딩하면 파서를 추가할 때 두 곳을 고쳐야 한다."""
    is_active: bool
    max_upload_bytes: int
    """정의에 없으면 전역 기본값이 채워져 나간다 — 화면이 두 곳을 보지 않게."""
    run_count: int
    """이 종류로 등록된 시험 수. 0 이 아니면 채널의 key·단위·차원이 잠긴다.

    화면이 **이유와 함께 잠가야** 사람이 납득한다. 눌러 보고 나서 409 를 받으면
    무엇이 문제인지 알기 어렵다."""
    channels: list[TestChannelOut]
    conditions: list[TestConditionFieldOut]


# --- 시험 -------------------------------------------------------------------


class TestRunOut(BaseModel):
    id: uuid.UUID
    record_name: str
    seq_no: int
    status: str
    parse_error: str | None

    specimen_id: uuid.UUID
    specimen_name: str | None
    orientation: str | None
    material_id: uuid.UUID | None
    material_name: str | None

    test_type_key: str
    test_type_label: str

    conditions: dict[str, Any]
    tested_at: datetime | None
    operator: str | None
    instrument: str | None

    source_filename: str | None
    source_bytes: int | None
    source_sha256: str | None
    note: str | None
    """등록 메모. 서버가 "내용이 같은 파일이 이미 N건 있습니다" 를 여기 적는다 —
    실을 곳이 없으면 서버만 알고 사용자는 끝내 모른다."""

    row_count: int | None
    channels: list[str]
    warnings: list[str]
    created_at: datetime


class TestSummaryOut(BaseModel):
    key: str
    label: str | None
    source: str
    """`instrument` = 장비가 계산한 값, `matnexus` = 우리가 계산한 값.

    나란히 두는 것이 목적이다. 우리 계산이 장비 값과 크게 다르면 뭔가 잘못됐다."""
    value: float | None
    text: str | None
    si_unit: str | None


class TestRunDetailOut(TestRunOut):
    summary: list[TestSummaryOut]
    source_metadata: dict[str, str]


class CurvePointsOut(BaseModel):
    x: str
    y: str
    row_count: int
    """원본 행 수. 축약 전이다."""
    returned: int
    points: list[tuple[float, float]]


class ReparseOut(BaseModel):
    status: str
    message: str


# --- 저장소 정리 ------------------------------------------------------------


class StorageItemOut(BaseModel):
    path: str
    bytes: int


class IncompleteOut(StorageItemOut):
    age_hours: float


class ExpiredOut(StorageItemOut):
    run_id: uuid.UUID
    record_name: str
    deleted_at: datetime


class StorageReportOut(BaseModel):
    """치울 것이 **세 종류**다. 하나만 다루면 나머지가 영원히 쌓인다."""

    root: str
    total_bytes: int
    retention_days: int
    live_count: int
    live_bytes: int
    orphans: list[StorageItemOut]
    """DB 에 행이 없는 폴더. 트랜잭션이 파일시스템까지 덮지 못해 생긴다."""
    incomplete: list[IncompleteOut]
    """쓰다 만 `.part`. 폴더는 살아 있어서 오펀 탐색에 안 걸린다."""
    expired: list[ExpiredOut]
    """보존기간 지난 소프트 삭제. **행이 있어서 오펀으로 영원히 안 잡힌다** —
    실측으로 확인한, 셋 중 가장 큰 구멍이다."""
    reclaimable_bytes: int


class CleanupRequest(BaseModel):
    dry_run: bool = True
    """기본이 안전한 쪽이다. 되돌릴 수 없는 작업이라 명시적으로 꺼야 지운다."""
    retention_days: int | None = Field(default=None, ge=0)


class CleanupQueuedOut(BaseModel):
    status: str
    message: str
    dry_run: bool


# --- 정의 편집 --------------------------------------------------------------
#
# **여기가 위험한 자리다.** 채널의 `key` 와 `si_unit` 은 이미 저장된 데이터의
# 해석을 바꾼다.
#
#   key       Parquet 컬럼 이름이자 `Curve.channels` 의 값이다. 바꾸면 저장된
#             곡선을 못 읽고, 조용히 "채널 없음" 이 된다.
#   si_unit   저장된 숫자는 그대로인데 뜻이 바뀐다. force 를 N → kN 으로 바꾸면
#             3466.4 N 이 3466.4 kN 으로 읽힌다. **숫자가 그대로라 티가 안 난다.**
#
# 그래서 그 종류로 등록된 시험이 하나라도 있으면 둘을 잠근다. 라벨·정렬·필수
# 여부는 언제든 바꿀 수 있다 — 그것들은 해석을 바꾸지 않는다.


class ParserOut(BaseModel):
    """`matcore.registry` 에 등록된 파서. 종류를 만들 때 여기서 고른다."""

    id: str
    label: str
    version: str
    extensions: list[str]
    applies_to: list[str]


class ChannelInput(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    """소문자·숫자·밑줄만. Parquet 컬럼 이름이 되므로 공백과 기호를 막는다."""
    label: str = Field(min_length=1, max_length=100)
    dimension: str = Field(min_length=1, max_length=20)
    si_unit: str = Field(min_length=1, max_length=20)
    is_required: bool = True
    sort_order: int = 0


class ConditionInput(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    value_type: str = Field(pattern="^(number|text|choice|date|boolean)$")
    dimension: str | None = Field(default=None, max_length=20)
    si_unit: str | None = Field(default=None, max_length=20)
    choices: list[str] | None = None
    is_required: bool = False
    sort_order: int = 0


class TestTypeSaveRequest(BaseModel):
    """정의 한 벌을 통째로 저장한다.

    항목별 엔드포인트를 늘어놓지 않는 이유: 화면은 폼 하나를 채워 저장한다.
    부분 갱신으로 쪼개면 "채널만 바꿨는데 조건이 사라졌다" 같은 어긋남이 생기고,
    무엇이 지워졌는지 판정하는 곳도 화면과 서버 둘로 갈라진다.
    """

    label: str = Field(min_length=1, max_length=100)
    abbr: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$")
    """시험 이름에 들어가는 약어. 이름에 쓰이므로 영숫자만."""
    description: str | None = None
    parser_key: str | None = None
    is_active: bool = True
    sort_order: int = 0
    max_upload_bytes: int | None = Field(default=None, gt=0)
    channels: list[ChannelInput]
    conditions: list[ConditionInput] = []


class TestTypeCreateRequest(TestTypeSaveRequest):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    """만든 뒤에는 바꿀 수 없다. 시험 종류를 가리키는 안정된 이름이다."""


class DefinitionLocksOut(BaseModel):
    """무엇을 왜 못 바꾸는지. 화면이 이유와 함께 잠가야 사람이 납득한다."""

    run_count: int
    locked: bool
    reason: str | None


# --- 형식 프로파일 ----------------------------------------------------------
#
# **장비가 늘 때마다 파서를 짜지 않으려고 만든 길이다.** 구조는 코드가 자동으로
# 읽고, "이 열이 무엇인가" 만 사람이 한 번 정해 저장한다. 그 저장물이 프로파일이다.
#
# 결정적인 점: **운영 서버에서 실제 파일을 보며 만든다.** 현장 파일이 개발자에게
# 갈 필요가 없다.


class TablePreviewOut(BaseModel):
    index: int
    name: str | None
    header: list[str]
    units: list[str]
    row_count: int
    column_count: int
    first_line: int
    sample_rows: list[list[str]]
    """앞 몇 행. **사람이 눈으로 확인하는 근거다.**

    자동 감지는 인코딩이 이중으로 깨진 파일도 '성공' 시킨다(실측). 숫자는 멀쩡하고
    글자만 깨지므로, 표를 직접 보지 않으면 알 수 없다."""


class StructurePreviewOut(BaseModel):
    """파일을 저장하지 않고 구조만 읽어 본 결과."""

    filename: str
    encoding: str
    delimiter: str
    line_count: int
    meta: list[tuple[str, str]]
    tables: list[TablePreviewOut]
    warnings: list[str]
    """**추측한 것**을 그대로 드러낸다. 인코딩을 UTF-8 이 아닌 것으로 골랐다면
    그 사실이 여기 있다."""
    matched_profile: str | None
    """이미 있는 프로파일이 이 파일을 잡는가. 있으면 새로 만들 필요가 없다."""


class FormatProfileOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    test_type_key: str
    test_type_label: str
    definition: dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FormatProfileSaveRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    description: str | None = None
    test_type_key: str = Field(min_length=1)
    definition: dict[str, Any]
    priority: int = 0
    is_active: bool = True


class FormatProfileCreateRequest(FormatProfileSaveRequest):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")


class TriedChannelOut(BaseModel):
    key: str
    label: str | None
    source_unit: str | None
    """파일에 적힌 단위. **환산이 맞았는지 사람이 판단할 유일한 근거다** —
    `°C → K` 는 값이 크게 바뀌므로, 원 단위가 안 보이면 틀렸는지 알 수 없다."""
    si_unit: str
    first: float | None
    last: float | None


class TriedCurveOut(BaseModel):
    key: str
    label: str | None
    row_count: int
    channels: list[TriedChannelOut]


class TriedSummaryOut(BaseModel):
    key: str
    label: str | None
    value: float | None
    text: str | None
    si_unit: str | None


class ProfileTryOut(BaseModel):
    """프로파일을 저장하기 전에 그 파일에 적용해 본 결과.

    저장하고 나서 틀린 것을 아는 것과, 저장 전에 아는 것은 다르다.
    """

    curves: list[TriedCurveOut]
    summary: list[TriedSummaryOut]
    metadata: dict[str, str]
    warnings: list[str]
