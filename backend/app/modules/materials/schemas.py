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
    """**규격 두께다.** 계산에 쓰는 것은 시편의 실측 두께다."""

    applied_product: str | None
    applied_part: str | None
    """이 재료를 어디에 쓰는가. **재료의 용도이지 로트의 행선지가 아니다.**"""

    density: float | None
    density_unit: str = DENSITY_UNIT
    """공칭 밀도. 로트 실측은 시료에 있고, 카드는 실측을 먼저 본다."""
    poisson_ratio: float | None
    """인장시험이 주지 않는 값이다 — 대개 문헌값이고 재료 등급에 붙는다."""

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
    applied_product: str | None = Field(default=None, max_length=100)
    applied_part: str | None = Field(default=None, max_length=100)
    density: float | None = Field(default=None, gt=0)
    density_unit: str = DENSITY_UNIT
    poisson_ratio: float | None = Field(default=None, ge=0, lt=0.5)
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
    applied_product: str | None = Field(default=None, max_length=100)
    applied_part: str | None = Field(default=None, max_length=100)
    density: float | None = Field(default=None, gt=0)
    density_unit: str | None = None
    poisson_ratio: float | None = Field(default=None, ge=0, lt=0.5)
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
    production_date: date | None

    density: float | None
    density_unit: str = DENSITY_UNIT
    """**이 로트에서 잰 값이다.** 공칭은 재료에 있다."""

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
    production_date: date | None = None
    density: float | None = Field(default=None, gt=0)
    density_unit: str = DENSITY_UNIT
    note: str | None = None
    workspace_slug: str | None = None


class SampleUpdateRequest(BaseModel):
    lot_no: str | None = Field(default=None, max_length=100)
    alias: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=100)
    distributor: str | None = Field(default=None, max_length=100)
    primary_vendor: str | None = Field(default=None, max_length=100)
    sales_type: str | None = Field(default=None, max_length=50)
    production_date: date | None = None
    density: float | None = Field(default=None, gt=0)
    density_unit: str | None = None
    note: str | None = None


# --- 시편 -------------------------------------------------------------------


class SpecimenOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    workspace_id: uuid.UUID
    seq_no: int
    orientation: str
    record_name: str

    standard: str | None
    """시편 규격. **자를 때 정해지고 아래 치수를 정하는 쪽이다.**

    전에는 시험 조건에 있었다 — 정해지는 값이 시편에, 정하는 값이 시험에 있어
    인과가 반대였다. 장비 파일에도 없다(사람이 아는 값이다)."""
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


class SpecimenSizeOut(BaseModel):
    """시편 치수 칸 하나 — **잰 값과 규격값을 나란히 낸다.**

    둘을 합쳐 하나로 내면 사람은 전부 실측으로 읽는다. 규격을 고쳐도 안 따라오는
    옛 값과, 규격이 정한 값을 구별할 수 없게 된다.
    """

    key: str
    label: str
    dimension: str
    si_unit: str
    is_required: bool
    help: str | None
    inherited: bool
    """분류가 준 칸인가. 아니면 이 규격만의 칸이다."""
    nominal: float | None
    """규격이 정한 공칭(SI). 시편 행에는 복사돼 있지 않다."""
    measured: float | None
    """이 시편에서 실제로 잰 값(SI)."""
    source: str | None
    """실제로 쓰이는 값이 어디서 왔는가 — `measured` 또는 `nominal`, 없으면 빈 칸."""


class SpecimenWarningOut(BaseModel):
    """규격이 요구하는 비율을 어겼다 — **막지는 않는다.**

    규격이 권장값을 주는데 장비가 못 맞추는 일이 실제로 있다. ISO 6721-4 는
    클램프 간 50~100 mm 를 권하지만 어느 DMA 장비도 그 값을 못 준다(Netzsch 15 ·
    Mettler 20 · TA 30). 막으면 실제로 잰 데이터를 못 넣고, 그러면 사람은 시스템
    밖에서 일한다. 대신 어긴 채로 쟀다는 것이 눈에 보여야 한다 — 규격 이름만 적힌
    보고서는 재현이 안 된다.
    """

    condition: str
    """사람이 읽는 조건. `게이지 길이 / 두께 >= 50`"""
    actual: float
    """실제 비. **값이 없으면 무엇을 고쳐야 할지 모른다.**"""
    help: str | None = None


class SpecimenSizesOut(BaseModel):
    """시편 하나의 치수 한 벌과 단면적."""

    standard: str | None
    cross_section: str | None
    cross_section_label: str | None
    area: float | None
    """초기 단면적(m^2). 못 내면 `None` 이고 이유가 `area_problem` 에 있다."""
    area_problem: str | None
    fields: list[SpecimenSizeOut]
    warnings: list[SpecimenWarningOut] = []
    """규격이 요구하는 비율을 어긴 것. **저장은 막지 않는다.**"""


class SpecimenSizesRequest(BaseModel):
    """잰 값만 보낸다(SI). **키를 빼면 그 칸을 안 잰 것이 된다.**"""

    dimensions: dict[str, float]


class SpecimenCreateRequest(BaseModel):
    orientation: str = Field(default="NA", max_length=10)
    seq_no: int | None = Field(default=None, ge=1)
    """생략하면 방향별로 이어서 채번한다."""
    standard: str | None = Field(default=None, max_length=100)
    thickness: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    gauge_length: float | None = Field(default=None, gt=0)
    length_unit: str = LENGTH_UNIT
    note: str | None = None


class SpecimenUpdateRequest(BaseModel):
    standard: str | None = Field(default=None, max_length=100)
    thickness: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    gauge_length: float | None = Field(default=None, gt=0)
    length_unit: str | None = None
    note: str | None = None


class ValueSourceOut(BaseModel):
    """값 하나가 **어디서 와서 어디에 쓰이는가.**

    이 정보가 없으면 사람은 화면을 옮겨 다니며 재료·시료·시편을 하나씩 열어
    봐야 한다. 그러고도 "이게 계산에 쓰이는 값인지" 는 알 수 없다 — 규격 두께와
    실측 두께가 나란히 있는데 계산에 들어가는 것은 하나뿐이다.
    """

    key: str
    label: str
    value: float | None
    display_unit: str
    """표시 단위. 값은 이 단위로 이미 환산돼 있다."""
    level: str
    """`material` | `sample` | `specimen` | `result`. **어디에 적는 값인가.**"""
    origin: str | None
    """사람이 읽는 출처 한 줄. 갈렸으면 무엇과 무엇이 갈렸는지."""
    status: str
    """`ok` | `missing` | `conflict`."""
    used_for: str
    """이 값이 무엇에 쓰이는가. 없을 때 무엇이 막히는지가 여기서 나온다."""
    edit_hint: str | None = None
    """비었을 때 어디서 채우는지."""


class PropertySourcesOut(BaseModel):
    material_id: uuid.UUID
    material_name: str
    rows: list[ValueSourceOut]
