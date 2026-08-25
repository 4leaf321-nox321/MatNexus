"""재료·시료·시편 API 형태.

**API 는 사람의 단위로 말한다.** 저장은 SI 지만 화면이 0.00045 를 다루게 하지
않는다. 대신 값마다 단위를 함께 실어, 받는 쪽이 무엇을 본 것인지 명확하게 한다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

#: 화면이 기본으로 쓰는 단위. **정본은 `app/shared/display`** 다 — 재료 모듈과
#: 적합 모듈이 같은 값을 보여 줘야 해서 모듈 밖에 둔다. 여기서는 이름만 다시
#: 내보낸다(이 이름으로 읽는 자리가 여럿이라).
from app.shared.display import DENSITY_UNIT as DENSITY_UNIT
from app.shared.display import LENGTH_UNIT as LENGTH_UNIT

MAX_USES = 20
"""한 재료에 붙일 수 있는 용도 수. 스무 개가 넘으면 그건 분류가 아니라 메모다."""

MAX_BULK = 200
"""한 번에 받는 줄 수의 상한.

**서버가 강제한다.** 화면이 200줄까지만 그린다고 해서 요청이 200줄이라는
보장은 없다. 상한이 없으면 붙여 넣기 한 번이 수만 줄짜리 요청이 된다.
"""


# --- 재료 -------------------------------------------------------------------


class DeclaredPointOut(BaseModel):
    """온도 하나에서의 값 하나."""

    temperature_k: float | None = None
    """이 값이 유효한 온도. **점이 하나면 비어 있을 수 있다** — 그때는 온도를
    안 타는 값이거나 상온값이라는 뜻이다."""
    value_si: float
    """**언제나 정본 SI.** 사람이 GPa 로 적어도 저장은 Pa 다."""
    value: float
    """`input_unit` 단위로 되돌린 값 — 화면이 그대로 그린다.

    **환산을 화면에서 안 한다.** 규칙이 두 곳에 있으면 언젠가 갈라지고
    (ADR 0004), 갈라진 쪽이 화면이면 사람은 자기가 적은 값과 다른 숫자를
    보면서 그것이 저장된 값이라고 믿는다."""


class DeclaredPropertyOut(BaseModel):
    """시험이 주지 않아 사람이 적은 물성 한 줄.

    **한 줄이 표를 든다.** 강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa
    쯤으로 떨어지고, 열간 성형·용접·화재 해석은 그 곡선이 필요하다. 그렇다고
    줄을 여럿 두면 카드가 어느 것을 쓸지 못 정한다 — **항목은 하나이고 그 하나가
    온도에 따라 변할 뿐**이므로 줄 안에 점을 넣는다.
    """

    item: str
    """기준정보 `property_item` 축의 값. 항목 목록을 **부서가 정한다**(D7)."""
    points: list[DeclaredPointOut]
    """온도-값 점들. **온도 오름차순이고 비지 않는다.**"""
    input_unit: str | None = None
    """사람이 적은 단위. 화면이 그대로 되돌려 보여 준다 — 206 GPa 를 넣었는데
    2.06e11 Pa 로 보이면 자기가 적은 값인지 알기 어렵다.

    **점마다 두지 않는다.** 한 물성을 GPa 와 MPa 로 섞어 적을 이유가 없고,
    섞을 수 있게 두면 표를 읽는 사람이 열마다 단위를 확인해야 한다.

    척도로 재는 물성(경도)에서는 비어 있다 — `scale` 이 그 자리다."""
    scale: str | None = None
    """시험 척도(`HV`·`HB`·`HRC`…). **단위가 아니다.**

    단위는 계수로 환산되지만(MPa → Pa) 척도는 안 된다 — `HV 200` 과 `HB 200` 은
    다른 값이고 환산식이 없다(ASTM E140 의 참고표는 재료마다 다르고 「대략」이라고
    명시한다). 그래서 **척도는 값의 일부**이고, 다른 척도끼리는 견주지 않는다.

    `input_unit` 과 **둘 중 하나만** 채워진다."""
    source: str
    """`literature` · `standard` · `datasheet` · `estimate`. **필수다** — 값만
    있고 어디서 왔는지 모르면 그 값으로 돌린 해석의 근거를 되짚을 수 없다."""
    reference: str
    """어느 문서인가. `'문헌'` 만으로는 어느 핸드북 몇 판인지 알 수 없다."""
    note: str | None = None


class DeclaredPointIn(BaseModel):
    temperature_k: float | None = None
    value: float


class DeclaredPropertyIn(BaseModel):
    """넣을 때. 값은 `input_unit` 단위이고 서버가 SI 로 바꾼다."""

    item: str
    points: list[DeclaredPointIn]
    """**비면 거절한다.** 값 없는 항목은 「이 물성이 있다」고 말하는 거짓말이다."""
    input_unit: str | None = None
    """비우면 그 항목의 정본 SI 단위로 본다. **척도로 재는 물성에서는 안 쓴다.**"""
    scale: str | None = None
    """시험 척도. 그 항목이 척도를 들면 **필수**이고, 안 들면 무시한다."""
    source: str
    reference: str
    note: str | None = None


class PropertyItemOut(BaseModel):
    """넣을 수 있는 물성 항목. 화면이 피커를 그리는 데 쓴다."""

    item: str
    dimension: str
    si_unit: str
    symbol: str | None
    level: str
    """`재료` | `시료`. **어디에 붙는가** — 화면이 이 값으로 피커를 가른다."""
    scales: list[str] = []
    """비어 있지 않으면 **단위 대신 척도를 고른다**(경도). 화면이 이 값으로
    단위 드롭다운을 척도 드롭다운으로 바꾼다."""
    units: list[str]
    """이 차원에서 고를 수 있는 단위.

    **항목이 자기 단위를 들고 온다.** 화면이 단위 표를 따로 읽어서 차원으로
    거르게 두면, 거르는 규칙이 화면에도 생긴다 — 그 규칙이 서버와 갈라지는
    날 비열 자리에 W/(m.K) 가 뜬다. 여기서 주면 화면은 그리기만 한다."""


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

    applied_products: list[str] = Field(default_factory=list)
    applied_parts: list[str] = Field(default_factory=list)
    """이 재료를 어디에 쓰는가. **여러 개다**(v1.89.0) — 한 재료가 여러 제품에
    들어간다. 적은 순서를 지킨다: 첫 번째가 대표값처럼 읽힌다."""
    """이 재료를 어디에 쓰는가. **재료의 용도이지 로트의 행선지가 아니다.**"""

    density: float | None
    density_unit: str = DENSITY_UNIT
    """공칭 밀도. 로트 실측은 시료에 있고, 카드는 실측을 먼저 본다."""
    poisson_ratio: float | None
    """인장시험이 주지 않는 값이다 — 대개 문헌값이고 재료 등급에 붙는다."""

    declared_properties: list[DeclaredPropertyOut] = []
    """**시험이 주지 않는 물성.** 탄성계수·열팽창계수·비열·열전도도처럼 핸드북·
    규격·밀시트에서 오는 값들이다. 밀도·푸아송비가 컬럼으로 있는 것과 같은
    성격인데, **항목을 부서가 정하므로** 컬럼이 아니라 목록이다."""

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
    applied_products: list[str] = Field(default_factory=list, max_length=MAX_USES)
    applied_parts: list[str] = Field(default_factory=list, max_length=MAX_USES)
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
    applied_products: list[str] | None = Field(default=None, max_length=MAX_USES)
    applied_parts: list[str] | None = Field(default=None, max_length=MAX_USES)
    """**통째로 바꾼다.** 줄 하나를 지운 것과 안 보낸 것을 구별할 방법이 없어서,
    안 보내면 그대로 두고 보내면 그 목록이 전부가 된다."""
    density: float | None = Field(default=None, gt=0)
    density_unit: str | None = None
    poisson_ratio: float | None = Field(default=None, ge=0, lt=0.5)
    declared_properties: list[DeclaredPropertyIn] | None = None
    """**통째로 갈아 끼운다.** 줄 하나만 고치는 길을 두면 "어느 줄인가" 를
    가리킬 열쇠가 필요한데, 항목 이름이 그 열쇠다 — 이름을 고치는 것과 값을
    고치는 것이 같은 요청에 섞이면 어느 쪽인지 알 수 없다."""
    alias: str | None = Field(default=None, max_length=200)
    note: str | None = None


class MaterialDeleteRequest(BaseModel):
    material_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)


class MaterialBlockedOut(BaseModel):
    """못 지운 것 하나. **이유를 함께 준다.**

    재료는 시료가 남아 있으면 안 지워진다 — 그것은 권한 문제와 다르고, 사람이
    해야 할 일도 다르다(하나는 관리자에게 말하는 것, 하나는 시료를 먼저 치우는
    것). 개수만 돌려주면 둘을 구별할 수 없다.
    """

    id: uuid.UUID
    name: str | None
    reason: str


class MaterialDeleteOut(BaseModel):
    deleted: int
    blocked: list[MaterialBlockedOut]


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
    registered_by: str | None = None
    """누가 등록했나. **이상한 값이 보일 때 물어볼 데가 여기다** —
    전에는 시험에만 있었고, 시료·시편은 상세를 열어도 알 수 없었다."""
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

    declared_properties: list[DeclaredPropertyOut] = []
    """밀시트가 준 값들(ADR 0016). **재료의 같은 칸과 층이 다르다** — 여기 것은
    로트마다 달라지는 값이고(항복강도·인장강도), 재료 것은 Grade 가 같으면 같은
    값이다(탄성계수·열물성)."""

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


class MillCheckRowOut(BaseModel):
    """밀시트가 말한 값 하나와 **우리가 잰 값.**

    밀시트는 「이 로트가 규격에 맞나」를 증명하는 문서다(EN 10204 3.1). 그
    증명이 맞는지 확인할 자리가 지금까지 없었다 — 값은 문서에, 시험 결과는
    시스템에 따로 있었다.
    """

    item: str
    label: str
    declared: float
    """밀시트가 말한 값. 정본 SI — 척도로 재는 물성이면 적은 그대로."""
    declared_unit: str
    """단위 또는 척도. 사람이 읽는 자리라 둘을 한 칸에 둔다."""
    reference: str
    measured: float | None = None
    """우리가 잰 값의 평균. 채택된 처리 결과에서만 온다(ADR 0007)."""
    measured_count: int = 0
    """몇 건을 평균했나. **0 이면 잰 적이 없다** — 값이 0 인 것과 다르다."""
    si_unit: str
    difference: float | None = None
    """`(잰 값 빼기 적은 값) ÷ 적은 값`. 둘 다 있을 때만 낸다.

    **판정을 안 한다.** 몇 %부터 문제인지는 규격과 용도가 정하고, 그것을 여기서
    상수로 박으면 그 숫자가 곧 규격 행세를 한다."""
    note: str | None = None
    """비교할 수 없을 때 그 이유. **조용히 빼지 않는다.**"""


class MillCheckOut(BaseModel):
    """이 시료의 밀시트 대조표."""

    sample_name: str
    rows: list[MillCheckRowOut]


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
    declared_properties: list[DeclaredPropertyIn] | None = None
    """**통째로 바꾼다.** 줄 하나를 지우는 것과 안 보낸 것을 구별할 방법이
    없어서, 안 보내면 그대로 두고 보내면 그 목록이 전부가 된다."""
    note: str | None = None


# --- 시편 -------------------------------------------------------------------


class SpecimenOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    workspace_id: uuid.UUID
    seq_no: int
    orientation: str
    record_name: str
    registered_by: str | None = None
    """누가 등록했나. **이상한 값이 보일 때 물어볼 데가 여기다** —
    전에는 시험에만 있었고, 시료·시편은 상세를 열어도 알 수 없었다."""

    standard: str | None
    """시편 규격. **자를 때 정해지고 아래 치수를 정하는 쪽이다.**

    전에는 시험 조건에 있었다 — 정해지는 값이 시편에, 정하는 값이 시험에 있어
    인과가 반대였다. 장비 파일에도 없다(사람이 아는 값이다)."""
    thickness: float | None
    width: float | None
    gauge_length: float | None
    length_unit: str = LENGTH_UNIT

    sizes: list[SpecimenBriefSizeOut] = []
    """이 시편의 실효 치수. **잰 값이 이기고 빈 칸은 규격에서 온다.**

    목록이 시편마다 읽으면 N+1 이라 **규격별로 한 번에** 읽는다
    (`specimen_size.sizes_for`)."""

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


class SpecimenBriefSizeOut(BaseModel):
    """목록의 접힌 줄에 적는 치수 하나.

    **이름을 함께 낸다.** 전에는 두께·폭·게이지 세 값을 `1.0 / 12.5 / 50` 처럼
    이름 없이 늘어놓았다. 칸이 규격마다 다른 지금은 자리로 외울 수가 없다 —
    환봉 규격의 첫 값은 직경이고 평판 규격의 첫 값은 폭이다.

    그리고 **어디서 온 값인지도 낸다.** 규격의 공칭과 사람이 잰 값을 합쳐서
    보여 주면 전부 실측으로 읽힌다.
    """

    key: str
    label: str
    symbol: str | None = None
    value: float
    """SI. 화면이 실무 단위로 바꿔 보여 준다."""
    si_unit: str
    dimension: str = "length"
    source: str
    """`measured` 사람이 잰 것 · `nominal` 규격이 정한 것."""


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


# --- 여러 개 한꺼번에 -------------------------------------------------------


class BulkSpecimenRequest(SpecimenCreateRequest):
    row: int = 0
    """표의 몇 번째 줄이 이것을 만들었나. **화면이 그 줄을 짚을 수 있어야 한다** —
    「3건 실패」만 돌려주면 스무 줄 중 어디를 고쳐야 하는지 알 수 없다."""


class BulkSampleRequest(SampleCreateRequest):
    row: int = 0
    specimens: list[BulkSpecimenRequest] = Field(default_factory=list)


class BulkMaterialRequest(MaterialCreateRequest):
    row: int = 0
    samples: list[BulkSampleRequest] = Field(default_factory=list)


class BulkRequest(BaseModel):
    """여러 개를 한꺼번에 — **평평한 표가 아니라 나무로 받는다.**

    화면의 표는 평평하다. 재료 칸이 빈 줄은 위 줄의 재료에 붙는다 — 엑셀에서
    늘 하는 방식이다. 그 「빈 칸은 위와 같다」를 서버가 다시 해석하게 하면
    규칙이 두 곳에 살고, 언젠가 갈라진다. 화면이 한 번 묶어서 보낸다.
    """

    materials: list[BulkMaterialRequest] = Field(min_length=1, max_length=MAX_BULK)

    @model_validator(mode="after")
    def _within_limit(self) -> BulkRequest:
        total = sum(
            1 + len(sample.specimens)
            for material in self.materials
            for sample in material.samples
        ) + len(self.materials)
        if total > MAX_BULK:
            # 표의 한 줄이 마디 하나다. 재료만 세면 시편 수천 개짜리 요청이 통과한다.
            raise ValueError(f"한 번에 {MAX_BULK}줄까지 넣을 수 있습니다 (지금 {total}줄)")
        return self


class BulkMadeOut(BaseModel):
    row: int
    kind: Literal["material", "sample", "specimen"]
    name: str
    reused: bool = False
    """있던 것을 찾아 쓴 것인가. **말해 주지 않으면 놀란다** — 같은 이름을
    적었을 때 조용히 남의 재료 밑에 시료가 붙을 수 있다."""


class BulkBlockedOut(BaseModel):
    row: int
    reason: str


class BulkOut(BaseModel):
    materials: int
    samples: int
    specimens: int
    made: list[BulkMadeOut]
    blocked: list[BulkBlockedOut]
