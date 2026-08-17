"""재료·시료·시편 API 형태.

**API 는 사람의 단위로 말한다.** 저장은 SI 지만 화면이 0.00045 를 다루게 하지
않는다. 대신 값마다 단위를 함께 실어, 받는 쪽이 무엇을 본 것인지 명확하게 한다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

#: 화면이 기본으로 쓰는 단위. 저장은 SI 로 하되 주고받는 것은 이쪽이다.
LENGTH_UNIT = "mm"
DENSITY_UNIT = "kg/m3"


# --- 재료 -------------------------------------------------------------------


class MaterialOut(BaseModel):
    id: uuid.UUID
    record_name: str
    alias: str | None
    owner_workspace_id: uuid.UUID | None
    owner_workspace_name: str | None
    """NULL 이면 전역 재료다. 화면이 그 사실을 표시할 수 있어야 한다."""
    is_global: bool

    family: str
    category: str
    grade: str
    details: str | None
    spec_thickness: float | None
    spec_thickness_unit: str = LENGTH_UNIT

    note: str | None
    legacy_id: str | None
    sample_count: int
    created_at: datetime
    updated_at: datetime


class MaterialCreateRequest(BaseModel):
    family: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=50)
    grade: str = Field(min_length=1, max_length=100)
    details: str | None = Field(default=None, max_length=100)
    spec_thickness: float | None = Field(default=None, gt=0)
    spec_thickness_unit: str = LENGTH_UNIT
    alias: str | None = Field(default=None, max_length=200)
    note: str | None = None
    legacy_id: str | None = Field(default=None, max_length=200)
    workspace_slug: str | None = None
    """생략하면 내 소속 부서. 전역 재료를 만드는 경로는 따로 두지 않는다 —
    승격은 이미 있는 재료를 올리는 일이지 처음부터 전역으로 만드는 일이 아니다."""


class ClassificationOut(BaseModel):
    """실제로 쓰이고 있는 분류 한 쌍.

    **목록에 있는 것에서 만든다.** 고정 목록을 코드에 박아 두면 부서가 새 분류를
    쓰기 시작한 순간 화면에서 고를 수 없게 되고, 그때 사람은 "필터가 고장났다"
    가 아니라 "그 재료가 없다" 로 읽는다.
    """

    family: str
    category: str
    count: int


class MaterialUpdateRequest(BaseModel):
    family: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    grade: str | None = Field(default=None, min_length=1, max_length=100)
    details: str | None = Field(default=None, max_length=100)
    spec_thickness: float | None = Field(default=None, gt=0)
    spec_thickness_unit: str | None = None
    alias: str | None = Field(default=None, max_length=200)
    note: str | None = None


class NamePreviewRequest(BaseModel):
    """등록 폼이 입력 중에 부르는 것. 서버가 이름을 만드는 유일한 곳이므로,
    화면이 같은 규칙을 다시 구현하지 않게 한다."""

    grade: str | None = None
    details: str | None = None
    spec_thickness: float | None = None
    spec_thickness_unit: str = LENGTH_UNIT


class NamePreviewOut(BaseModel):
    record_name: str
    taken: bool
    """이미 쓰이고 있는 이름인가. 등록 버튼을 누르기 전에 알려 준다."""


# --- 시료 -------------------------------------------------------------------


class SampleOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str | None
    seq_no: int
    record_name: str
    alias: str | None

    lot_no: str | None
    manufacturer: str | None
    distributor: str | None
    primary_vendor: str | None
    sales_type: str | None
    applied_product: str | None
    applied_part: str | None
    production_date: date | None

    density: float | None
    density_unit: str = DENSITY_UNIT
    poisson_ratio: float | None

    note: str | None
    specimen_count: int
    created_at: datetime

    test_run_count: int = 0
    adopted_count: int = 0
    failed_count: int = 0
    """이 시료의 시편들에 걸린 시험 상태.

    **접힌 줄이 상태를 말해야 한다.** 접기만 하고 개수를 안 주면 "실패한 게
    있나" 를 알려고 시료·시편을 전부 펼쳐야 한다. 특히 `adopted_count` 는
    물성 탭의 n 이 왜 그 수인지를 설명한다 — 통계와 적합에 들어가는 것은
    채택된 것뿐이다(ADR 0007)."""


class SampleCreateRequest(BaseModel):
    lot_no: str | None = Field(default=None, max_length=100)
    alias: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=100)
    distributor: str | None = Field(default=None, max_length=100)
    primary_vendor: str | None = Field(default=None, max_length=100)
    sales_type: str | None = Field(default=None, max_length=50)
    applied_product: str | None = Field(default=None, max_length=100)
    applied_part: str | None = Field(default=None, max_length=100)
    production_date: date | None = None
    density: float | None = Field(default=None, gt=0)
    density_unit: str = DENSITY_UNIT
    poisson_ratio: float | None = Field(default=None, ge=0, lt=0.5)
    note: str | None = None
    workspace_slug: str | None = None


class SampleUpdateRequest(BaseModel):
    lot_no: str | None = Field(default=None, max_length=100)
    alias: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=100)
    distributor: str | None = Field(default=None, max_length=100)
    primary_vendor: str | None = Field(default=None, max_length=100)
    sales_type: str | None = Field(default=None, max_length=50)
    applied_product: str | None = Field(default=None, max_length=100)
    applied_part: str | None = Field(default=None, max_length=100)
    production_date: date | None = None
    density: float | None = Field(default=None, gt=0)
    density_unit: str | None = None
    poisson_ratio: float | None = Field(default=None, ge=0, lt=0.5)
    note: str | None = None


# --- 시편 -------------------------------------------------------------------


class SpecimenOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    workspace_id: uuid.UUID
    seq_no: int
    orientation: str
    record_name: str

    thickness: float | None
    width: float | None
    gauge_length: float | None
    length_unit: str = LENGTH_UNIT

    note: str | None
    created_at: datetime

    test_run_count: int = 0
    adopted_count: int = 0
    failed_count: int = 0
    """이 시편에 걸린 시험과 그 상태.

    **접힌 줄이 아무것도 말하지 않으면 접는 뜻이 없다.** 하나씩 펼쳐 봐야
    "시험이 있는지, 실패했는지, 채택됐는지" 를 알게 되기 때문이다. 목록에서
    한 번에 세어 넣는다 — 시편마다 물으면 N+1 이다."""


class SpecimenCreateRequest(BaseModel):
    orientation: str = Field(default="NA", max_length=10)
    seq_no: int | None = Field(default=None, ge=1)
    """생략하면 방향별로 이어서 채번한다."""
    thickness: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    gauge_length: float | None = Field(default=None, gt=0)
    length_unit: str = LENGTH_UNIT
    note: str | None = None


class SpecimenUpdateRequest(BaseModel):
    thickness: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    gauge_length: float | None = Field(default=None, gt=0)
    length_unit: str | None = None
    note: str | None = None
