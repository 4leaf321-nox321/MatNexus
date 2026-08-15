"""시험 API 형태.

시험 종류 정의를 그대로 내려보낸다. 화면이 채널·조건 폼을 **정의에서 그려야**
새 시험 종류를 배포 없이 추가할 수 있다(수준 2). 화면이 항목을 하드코딩하면
정의를 데이터로 둔 이유가 사라진다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

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
