"""카탈로그 API 스키마."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CatalogSummaryOut(BaseModel):
    materials: int
    values: int
    sources: int
    definitions: int
    subsystems: dict[str, int]
    categories: dict[str, int]
    domains: dict[str, int]
    tiers: dict[int, int]


class CatalogMaterialOut(BaseModel):
    id: uuid.UUID
    name: str
    material_code: str | None
    category: str
    origin: str = "catalog"
    """`catalog`(MaterialTwin 이관) · `local`(MatNexus 에서 직접 넣음)."""
    subsystem: str | None
    role: str | None
    manufacturer: str | None
    material_class: str | None
    grade: str | None
    value_count: int = 0


class CatalogMaterialPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CatalogMaterialOut]


class CatalogSourceOut(BaseModel):
    id: uuid.UUID
    kind: str
    doi: str | None
    url: str | None
    title: str | None
    year: int | None
    publisher: str | None
    license: str | None


class CatalogValueOut(BaseModel):
    id: uuid.UUID
    property_key: str
    property_name: str
    domain: str
    symbol: str | None
    value_num: float | None
    value_text: str | None
    unit: str | None
    term: str | None = None
    """**어느 변수인가**(ADR 0029). 한 이름에 여럿이 든 물성에서만 온다 —
    「Anand 점소성 상수」 의 `h0`."""
    term_unit: str | None = None
    """그 변수의 진짜 단위. 정의가 말하는 단위가 아니다 — 대개 정의는 `1` 이라고
    적혀 있고 실제로는 `MPa`·`1/s`·`K` 다."""
    uncertainty: float | None
    conditions: dict[str, Any] | None
    method: str | None
    quality_tier: int
    summary: dict[str, Any] | None = None
    """**조건이 완전히 같은 중복**일 때만 오는 종합 — `{n, median, min, max}`.

    대표 줄에만 실린다. 이것이 있으면 「같은 조건에서 잰 값이 N개」 라는 뜻이라
    중앙값을 담는 선택지가 생긴다. 없으면(대부분) 조건이 다른 값들이라 종합하면
    안 된다 — 실측상 98%가 그쪽이다."""
    distinguishing: dict[str, Any] = {}
    """**후보들 사이에서 값이 갈리는 조건**만 — 이 값의 것.

    조건 전체는 `conditions` 에 있다. 후보가 넷이면 사람이 넷을 눈으로 대조해야
    무엇이 다른지 아는데, 그 대조를 서버가 대신한다. 실측(2026-09-09): 값이 둘
    이상인 조합의 98%가 조건이 서로 다르다."""
    source: CatalogSourceOut | None
    source_detail: str | None
    notes: str | None
    representative: bool = False
    origin: str = "catalog"
    """`catalog`(이관) · `local`(직접 넣음). local 은 지울 수 있고 원본 검산에 안 든다."""
    created_by: str | None = None
    """직접 넣은 값이면 넣은 사람."""
    """같은 물성의 후보 중 대표로 뽑힌 값인가. **진 후보도 함께 온다** — 화면이
    이유와 같이 보여 준다."""
    n_candidates: int = 1
    separated_by: str | None = None
    """대표에게 밀린 자리(상태·등급·수치·온도·조건 수·입력 순서). 대표는 None."""


class CatalogLinkIn(BaseModel):
    catalog_material_id: uuid.UUID


class CatalogLinkOut(BaseModel):
    """사내 재료의 문헌 연결 — 비면 전부 None. 화면이 한 번에 그릴 요약까지."""

    catalog_material_id: uuid.UUID | None = None
    name: str | None = None
    category: str | None = None
    subsystem: str | None = None
    value_count: int = 0


class DeckMatchIn(BaseModel):
    text: str
    """붙여넣은 줄들 — `MID, 이름` 또는 `이름`."""


class DeckCandidateOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    value_count: int
    score: int
    """정확 일치 3 > 앞부분 2 > 포함 1. 고르는 것은 사람이다."""


class DeckMatchRowOut(BaseModel):
    query: str
    mid: int | None
    candidates: list[DeckCandidateOut]


class DeckBuildItemIn(BaseModel):
    mid: int
    catalog_material_id: uuid.UUID


class DeckBuildIn(BaseModel):
    items: list[DeckBuildItemIn]
    format: str = "dyna_elastic"
    units: str | None = None
    """단위계 key. 비우면 SI."""


class DeckSkippedOut(BaseModel):
    mid: int
    name: str
    missing: list[str]


class DeckBuiltOut(BaseModel):
    filename: str
    text: str
    material_count: int
    skipped: list[DeckSkippedOut]
    notes: list[str]


class CatalogCompareCellOut(BaseModel):
    """비교 표의 칸 하나 — 그 재료의 그 물성 대표값. 없으면 None 칸."""

    value_num: float | None = None
    value_text: str | None = None
    quality_tier: int | None = None
    n_candidates: int = 0
    conditions: dict[str, Any] | None = None


class CatalogCompareRowOut(BaseModel):
    property_key: str
    name: str
    domain: str
    symbol: str | None
    unit: str | None
    cells: list[CatalogCompareCellOut]


class CatalogCompareOut(BaseModel):
    materials: list[CatalogMaterialOut]
    rows: list[CatalogCompareRowOut]
    """도메인·키 차례. ≥1 재료가 값을 가진 물성만."""


class AshbyAxisOut(BaseModel):
    key: str
    name: str
    domain: str
    unit: str | None
    material_count: int
    """이 물성의 수치 대표값을 가진 재료 수 — 축으로 쓸 만한지의 근거."""


class AshbyPointOut(BaseModel):
    id: uuid.UUID
    name: str
    group: str
    x: float
    y: float


class AshbyOut(BaseModel):
    x_unit: str | None
    y_unit: str | None
    points: list[AshbyPointOut]


class CatalogCoverageOut(BaseModel):
    """계통-도메인 값 수 격자. 빈 계통은 「미분류」("") 로 온다."""

    domains: list[str]
    subsystems: list[str]
    cells: dict[str, dict[str, int]]
    """subsystem → domain → 값 수."""


class CatalogMaterialDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    material_code: str | None
    category: str
    description: str | None
    subsystem: str | None
    role: str | None
    manufacturer: str | None
    material_class: str | None
    grade: str | None
    attributes: dict[str, Any] | None
    origin: str = "catalog"
    created_by: str | None = None
    values: list[CatalogValueOut]


# --- 직접 넣기 (contribute.py) ------------------------------------------------


class CatalogPropertyCreate(BaseModel):
    """물성 정의 하나. 키는 서버가 `local.<domain>.<slug>` 로 만든다."""

    name: str = Field(min_length=1, max_length=200)
    """사람이 부르는 이름 — 「습윤 굴곡탄성률」."""
    domain: str = Field(min_length=1, max_length=30)
    """카탈로그 도메인 — mechanical · thermal · physical · electrical …"""
    slug: str = Field(min_length=2, max_length=60)
    """키의 마지막 조각. 영문 snake_case — flexural_modulus_wet."""
    si_unit: str | None = Field(default=None, max_length=50)
    """SI 정본 단위(Pa · J/(kg.K) · 1). 수치 물성이면 필수."""
    symbol: str | None = Field(default=None, max_length=50)
    value_type: str = "numeric"
    description: str | None = None
    test_standard: str | None = Field(default=None, max_length=200)
    condition_axes: list[str] | None = None
    """조건 없이는 무의미해지는 축 — 예: ["temperature_k"]."""


class CatalogDefinitionOut(BaseModel):
    key: str
    name: str
    domain: str
    symbol: str | None
    si_unit: str | None
    value_type: str
    description: str | None
    test_standard: str | None
    condition_axes: list[str] | None
    origin: str
    created_by: str | None = None
    deprecated: bool = False
    superseded_by: str | None = None
    deprecation_note: str | None = None


class CatalogPropertyMigrateIn(BaseModel):
    """폐기된 키에 걸린 것을 후속 키로 옮긴다 — 관리자가 누르는 동작이지 자동이 아니다."""

    to: str | None = Field(default=None, max_length=100)
    """옮길 곳. 비우면 폐기 때 적어 둔 후속 키."""
    dry_run: bool = True


class CatalogPropertyMigrateOut(BaseModel):
    from_key: str
    to_key: str
    dry_run: bool
    values: int
    """옮긴(옮길) 값 — MatNexus 에서 직접 넣은 것만."""
    values_imported: int
    """못 옮기는 값 — 이관해 온 것. 원본(MaterialTwin)이 정본이라 다시 이관하면 돌아온다."""
    links: int
    """옮긴(옮길) 사내 항목 매핑. 후속 키에 같은 것이 있으면 겹치는 것은 지운다."""
    aliases: int
    converted: str | None = None
    """단위가 달라 환산했으면 그 내역."""


class CatalogPropertyDeprecate(BaseModel):
    """키를 폐기한다 — 지우지 않는다. 후속 키가 있으면 그것을 가리킨다."""

    superseded_by: str | None = Field(default=None, max_length=100)
    note: str | None = None


class CatalogMaterialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=30)
    """metal · polymer · ceramic · composite · foam · rubber · molecular."""
    material_code: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = None
    grade: str | None = None
    material_class: str | None = None
    subsystem: str | None = Field(default=None, max_length=50)
    description: str | None = None


class CatalogSourceIn(BaseModel):
    """값의 출처. **제목·DOI·URL 중 하나는 있어야 한다** — 출처 없는 값은 안 받는다."""

    kind: str = Field(min_length=1, max_length=30)
    """journal · book · database · datasheet · standard · web · other."""
    title: str | None = None
    authors: str | None = None
    year: int | None = Field(default=None, ge=1800, le=2100)
    doi: str | None = Field(default=None, max_length=200)
    url: str | None = None
    publisher: str | None = Field(default=None, max_length=300)


class CatalogValueCreate(BaseModel):
    property_key: str = Field(min_length=1, max_length=100)
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = Field(default=None, max_length=50)
    """값의 단위. 정의 단위와 같은 차원이면 서버가 정의 단위로 환산한다."""
    uncertainty: float | None = None
    conditions: dict[str, Any] | None = None
    """조건 — temperature_k · strain_rate_1_s · state …"""
    method: str = "handbook"
    """measured · handbook · digitized · computed · estimated."""
    quality_tier: int = Field(ge=1, le=4)
    """1 실측 인쇄 · 2 핸드북·규격 · 3 계열 대표값·2차 인용 · 4 계산·추정·가정."""
    source: CatalogSourceIn
    source_detail: str | None = None
    """출처 안의 위치 — 페이지·표·그림."""
    notes: str | None = None


class CatalogValueCreatedOut(BaseModel):
    value: CatalogValueOut
    converted: str | None = None
    """단위를 환산했으면 그 내역 — "310 MPa → 3.1e+08 Pa"."""


class PropertyCandidateOut(BaseModel):
    """물성 후보 하나 — **값을 묻기 전에 필요한 것을 다 들고 있다.**

    단위를 필드 이름에 박지 않고 값으로 싣는다(`si_unit`). 알루미늄 밀도가
    `2.68e-09 kg/m3` 로 나간 적이 있다 — 이름에 단위를 박은 탓이었다.
    """

    key: str
    name: str
    domain: str
    si_unit: str
    symbol: str | None
    value_count: int
    """값이 몇 건인가. 0이면 이 물성으로는 아무것도 못 찾는다."""
    internal_items: list[str]
    measured_keys: list[str] = Field(default_factory=list)
    deprecated: bool = False
    """폐기된 키 — 그만 쓰고 `superseded_by` 를 쓴다. 뒤로 밀려 선다."""
    superseded_by: str | None = None
    """시험 처리가 이 물성으로 내는 값 이름(`proof_stress`…). 비면 잰 값은 안 찾는다."""
    """이어진 사내 물성 항목. 있으면 우리가 실제로 쓰는 물성이다."""
    parameterized: bool = False
    """**한 키에 여러 변수가 들어 있나**(ADR 0029). 참이면 값을 묻기 전에 어느
    변수인지(`term`) 정해야 한다 — Anand 하나에 9개 상수가 들어 있다."""
    terms: list[str] = []
    """그 변수들(앞의 몇 개)."""
    matched_by: str
    """`alias` · `name` · `symbol` · `key` · `alias_partial` · `partial`."""
    matched_text: str | None
    notes: list[str]


class PropertyResolveOut(BaseModel):
    query: str
    ambiguous: bool
    """**참이면 하나를 고르면 안 된다.** 도메인이 다른 후보가 나란히 섰다는 뜻이다."""
    candidates: list[PropertyCandidateOut]


class PropertyAliasOut(BaseModel):
    id: uuid.UUID
    property_key: str
    alias: str
    source: str
    note: str | None

    model_config = {"from_attributes": True}


class PropertyAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    source: str = "manual"
    note: str | None = None


class PropertyLinkOut(BaseModel):
    id: uuid.UUID
    property_key: str
    term_id: uuid.UUID
    item: str
    """사내 물성 항목 이름 — 화면이 기준정보를 따로 안 부르게."""
    kind: str
    scale: str | None = None
    """이 매핑이 해당하는 눈금(`HV`·`HRC`). 비면 눈금을 안 가린다."""
    note: str | None


class PropertyLinkCreate(BaseModel):
    property_key: str
    item: str
    """사내 물성 항목 **이름**으로 받는다 — 사람이 폼에 id 를 적지 않는다."""
    kind: str = "same_as"
    scale: str | None = Field(default=None, max_length=20)
    """항목이 눈금을 갖는 것(경도)이면 **어느 눈금의 값이 이 물성인가.** 항목이
    선언한 눈금(`scales`) 중 하나여야 한다."""
    note: str | None = None


class PropertyDictionaryEntryOut(BaseModel):
    """물성 키 사전의 한 줄 — **다른 시스템이 자기 매핑의 키를 검사하는 데 쓴다.**"""

    key: str
    name: str
    domain: str
    origin: str = "catalog"
    """`catalog`(MaterialTwin 키) · `local`(MatNexus 가 만든 키, `local.` 접두어)."""
    deprecated: bool = False
    """**폐기된 키.** 받아 간 쪽은 이 키로 새로 잇지 말고 `superseded_by` 로 옮긴다."""
    superseded_by: str | None = None
    si_unit: str | None
    symbol: str | None
    test_standard: str | None
    aliases: list[str]
    internal_items: list[str]
    """사내 항목 이름(눈금이 있으면 「경도 (HV)」)."""
    measured_keys: list[str]


class PropertyDictionaryOut(BaseModel):
    """물성 키 사전 — 허브 키의 정본.

    시스템이 여럿(MaterialTwin · MatNexus · TestScope …)이면 쌍마다 표를 두지 않고
    **키 하나를 허브로** 두고 각자 자기 개념을 그 키에 잇는다(2026-09-12). 이 파일이
    그 허브다. 폐쇄망이라 API 보다 파일이 낫다 — 받아서 자기 검사에 쓴다.

    **키는 안 바뀐다.** 틀렸으면 새 키를 만들고 옛 키는 폐기 표시만 한다 — 바꾸면
    스포크 전부가 같은 날 깨진다.
    """

    version: str
    """MatNexus 버전. 사전이 어느 배포에서 나왔는지."""
    generated_at: datetime
    count: int
    properties: list[PropertyDictionaryEntryOut]


class PropertyAdoptableOut(BaseModel):
    """문헌값 하나를 **사내 어디에 담을 수 있는가.** 채우기 화면과 MCP 가 이것만 본다.

    전에는 이 표가 화면·MCP·백엔드에 세 벌로 박혀 있었고, 매핑 화면에서 항목을
    이어도 채우기에는 아무 일도 안 일어났다(2026-09-12). 지금은 `property_links`
    (사람이 잇는 것)와 재료 기본 칸(코드)에서 만든다.
    """

    property_key: str
    place: str
    """`declared`(선언 물성 항목) · `column`(재료 기본 칸 — 밀도·푸아송비)."""
    item: str | None = None
    """`declared` 면 항목 이름."""
    scale: str | None = None
    """`declared` 에 눈금이 붙었으면(경도 HV) 담을 때 그 눈금으로."""
    field: str | None = None
    """`column` 이면 재료 칸 이름(`density` · `poisson_ratio`)."""


class PropertyMeasuredOut(BaseModel):
    """시험 처리가 이 물성으로 내는 값 하나 — 어느 계산의 어느 값."""

    plugin_id: str
    plugin_label: str
    scalar_key: str


class PropertyMappingRowOut(BaseModel):
    """물성 하나가 세 층에서 어떻게 불리는가 — 매핑 화면의 한 줄."""

    origin: str = "catalog"
    """`local` 이면 MatNexus 에서 만든 물성 — 값·매핑이 없으면 지울 수 있다."""
    deprecated: bool = False
    superseded_by: str | None = None
    deprecation_note: str | None = None
    key: str
    name: str
    domain: str
    si_unit: str | None
    symbol: str | None
    test_standard: str | None
    value_count: int
    """문헌값 수. 0 이면 문헌에도 값이 없는 정의다."""
    links: list[PropertyLinkOut]
    """사내 항목과의 매핑 — 사람이 잇고 푼다."""
    measured: list[PropertyMeasuredOut]
    """시험 처리가 이 물성으로 내는 값 — 코드가 정한다."""


class PropertyUnlinkedItemOut(BaseModel):
    """사내 항목인데 문헌 키에 안 이어진 것. **표시가 없으면 조용히 빠진다** —
    값으로 찾기·다른 시스템과의 매핑에서."""

    term_id: uuid.UUID
    item: str
    dimension: str | None
    scales: list[str]


class PropertySuggestionOut(BaseModel):
    """사내 항목 하나에 **이을 만한 문헌 키** 하나. 잇지는 않는다 — 사람이 누른다."""

    term_id: uuid.UUID
    item: str
    property_key: str
    name: str
    domain: str
    si_unit: str | None
    value_count: int
    matched_by: str
    """`alias` · `name` · `symbol` · `partial` — 왜 걸렸나."""
    scale: str | None = None
    """눈금 있는 항목이면 어느 눈금으로 이어야 하나(「경도」 + 비커스 → HV)."""


class PropertyMappingOut(BaseModel):
    axis_slug: str
    """사내 항목이 사는 기준정보 축. 화면이 이 축의 탭에 매핑을 붙인다 — 이름을
    화면이 외우지 않게."""
    rows: list[PropertyMappingRowOut]
    items: list[PropertyUnlinkedItemOut]
    """사내 항목 전부(잇는 창의 후보). 눈금이 있으면 `scales` 에 든다."""
    unlinked_items: list[PropertyUnlinkedItemOut]
    suggestions: list[PropertySuggestionOut] = Field(default_factory=list)
    """이을 만한 것 — 차원이 맞고 아직 안 이어진 쌍만. 271종을 눈으로 훑지 않게."""
    kinds: list[str]
    summary: dict[str, int]
    """`keys` · `linked_keys` · `measured_keys` · `unlinked_items`."""


class PropertyHitOut(BaseModel):
    """값 하나와 그것을 든 재료. **값과 단위를 함께 싣는다.**"""

    world: str
    """`catalog`(문헌) · `internal`(사내 선언) · `measured`(시험으로 잰 값 — 채택된
    처리 결과)."""
    material_id: uuid.UUID
    material_name: str
    value: float
    """**물어본 단위로 되돌린 값.** SI 원본은 `value_si`."""
    unit: str
    value_si: float
    quality_tier: int | None = None
    source_detail: str | None = None
    category: str | None = None
    count: int = 1
    """이 줄에 묶인 값의 수. `measured` 는 재료·방법별로 묶여 오므로 시편 3장이면 3."""
    spread: float | None = None
    """묶인 값들의 표준편차(**물어본 단위**). 하나면 비어 있다."""
    method: str | None = None
    """`measured` 가 어떻게 쟀나 — 「항복강도 · offset_strain=0.002」. 같은 물성이라도
    방법이 다르면 값이 다르다."""


class PropertySearchOut(BaseModel):
    """값 검색 결과.

    **후보가 갈렸으면 값을 안 찾고 되묻는다** — 어느 물성인지 모른 채 찾은 값은
    엉뚱한 물성의 정답이다.
    """

    query: str
    resolved: PropertyCandidateOut | None = None
    ambiguous: bool = False
    candidates: list[PropertyCandidateOut] = Field(default_factory=list)
    """`ambiguous` 일 때만 채워진다 — 사용자가 고를 것들."""

    unit: str | None = None
    range_si: list[float] | None = None
    """실제로 건 범위(SI). **AI 가 자기가 무엇을 물었는지 되짚을 수 있어야 한다.**"""
    total: int = 0
    hits: list[PropertyHitOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CatalogParameterTermOut(BaseModel):
    term: str
    value: float | None = None
    text: str | None = None
    unit: str = ""


class CatalogParameterSetOut(BaseModel):
    """문헌 재료가 가진 모델 파라미터 한 벌(ADR 0029).

    **한 벌이 채택의 단위다** — `A` 만 떼어 가면 모델이 못 쓴다.
    """

    property_key: str
    label: str
    model: str
    set_id: str
    quality_tier: int | None = None
    source_detail: str | None = None
    variant: str = ""
    """같은 `set_id` 안에서 이 벌을 형제와 가르는 조건. 안 갈렸으면 빈 값.

    **채택할 때 이것으로 고른다** — 출처가 한 벌 이름 아래 온도별·계열별로 여러
    벌을 담는 일이 흔해서, `set_id` 만으로는 못 집는다."""

    distinguishing: dict[str, Any] = {}
    duplicated: list[str] = []
    """그래도 남은 겹친 항. **비어 있어야 정상이다** — 있으면 그 벌은 채택이
    거절된다(어느 값이 쓰일지 알 수 없어서다)."""

    terms: list[CatalogParameterTermOut] = []
