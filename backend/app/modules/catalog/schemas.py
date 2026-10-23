"""카탈로그 API 스키마."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CatalogSummaryOut(BaseModel):
    materials: int
    values: int
    sources: int
    definitions: int
    subsystems: dict[str, int]
    categories: dict[str, int]
    domains: dict[str, int]
    """분야마다 **값** 수."""
    materials_by_domain: dict[str, int] = Field(default_factory=dict)
    """분야마다 그 분야의 값이 있는 **재료** 수 — 목록의 분야 거르개가 이것을 센다."""
    manufacturers: dict[str, int] = Field(default_factory=dict)
    """제조사마다 재료 수. 대소문자만 다른 표기는 하나로 센다."""
    tiers: dict[int, int]


class CatalogMatchedOut(BaseModel):
    """값 범위에 걸린 값 — 몇 건이고 어디서 어디까지인가. 물은 단위로 싣는다."""

    count: int
    low: float
    high: float
    unit: str


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
    source_missing_at: datetime | None = None
    """원본 스냅샷에서 빠진 것을 본 때 — 비어 있으면 원본에 있다. 이관은 지우지 않고
    표시만 하며, 빠진 값은 대표값 · 값 검색 · 커버리지에서 빠진다(2026-10-04)."""
    matched: CatalogMatchedOut | None = None
    """값 범위로 걸렀을 때만 — 이 재료에서 걸린 값들."""


class SyntheticInputOut(BaseModel):
    item: str
    """사내 물성 항목 이름 — 덱 각주와 같은 이름."""
    value_si: float
    reference: str
    si_unit: str = ""
    """그 물성 정의의 단위 — 강도는 Pa, 연신율은 1(변형률)."""


class SyntheticCurvePreviewOut(BaseModel):
    """문헌 재료의 **합성** σ-ε 곡선 — 실측이 아니다. 덱의 「곡선 합성」 과 같은 계산이다."""

    ok: bool
    why: str | None = None
    """못 지었으면 그 이유 — 덱이 하는 말과 같다."""
    model: str | None = None
    note: str | None = None
    """어떤 근사이고 무엇을 과대 · 과소평가하는지."""
    inconsistent: bool = False
    youngs_modulus: float | None = None
    strain: list[float] = Field(default_factory=list)
    """공칭 변형률."""
    stress: list[float] = Field(default_factory=list)
    """공칭 응력(Pa)."""
    table_points: int = 0
    """덱에 실릴 소성 표의 점 수 — 0 이면 소성 표가 안 나오는 재료다(취성)."""
    inputs: list[SyntheticInputOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
    attribution: str | None = None
    """귀속 문구 — CC BY 처럼 표기를 조건으로 하는 라이선스가 요구하는 글(ADR 0068)."""


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
    formula_term: bool = False
    """**식의 변수 값인가**(`representative.is_term`) — 그 물성 자리에 담을 값이 아니다.
    `term` 이 있어도 「단기 · 장기」 같은 구분이면 거짓이다. 화면이 따로 가르지 않는다."""
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
    source_missing_at: datetime | None = None
    """원본 스냅샷에서 빠진 것을 본 때 — 비어 있으면 원본에 있다. 이관은 지우지 않고
    표시만 하며, 빠진 값은 대표값 · 값 검색 · 커버리지에서 빠진다(2026-10-04)."""
    created_by: str | None = None
    """직접 넣은 값이면 넣은 사람."""
    series_id: uuid.UUID | None = None
    """이어진 값 한 벌(곡선 · 계수 묶음)의 점이면 그 벌(ADR 0067). 상세의 `series` 에 머리가
    있다."""
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


class LinkCandidateOut(BaseModel):
    """사내 재료 하나에 **이을 만한 문헌 재료** 하나. 잇지는 않는다 — 사람이 누른다."""

    catalog_material_id: uuid.UUID
    name: str
    category: str
    manufacturer: str | None = None
    subsystem: str | None = None
    role: str | None = None
    value_count: int
    matched_by: str
    """`code`(코드 · 등급이 같다) · `name`(이름 전체가 같다) · `prefix`(이름이 그것으로
    시작한다 — 열처리 · 충전재 꼬리가 다를 수 있다)."""
    matched_on: str
    """사내 재료의 어느 칸이 걸렸나 — `grade` · `alias`."""
    matched_text: str


class MaterialLinkCandidatesOut(BaseModel):
    """아직 문헌과 안 이어진 사내 재료 하나와 그 후보."""

    material_id: uuid.UUID
    code: str
    record_name: str
    family: str
    category: str
    grade: str
    alias: str | None = None
    can_edit: bool
    """잇는 권한이 있나 — 재료 편집과 같은 판정(ADR 0035). 없으면 화면이 단추를 잠근다."""
    candidates: list[LinkCandidateOut]


class LinkCandidatesPageOut(BaseModel):
    items: list[MaterialLinkCandidatesOut]
    """후보가 **있는** 재료만, 이름순. 상한은 서버가 정한다."""
    unlinked: int
    """보이는 사내 재료 중 문헌과 안 이어진 것."""
    with_candidates: int
    """그중 후보가 하나라도 있는 것. `items` 가 상한에 잘렸으면 이것이 더 크다."""


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
    """문헌 재료로 낼 형식 — `GET /catalog/deck/formats` 의 key."""
    units: str | None = None
    """단위계 key. 비우면 mm·N·tonne(ADR 0036)."""


class DeckFormatOut(BaseModel):
    """문헌 재료로 낼 수 있는 형식 하나 — 카드 내보내기와 같은 목록에서 골랐다."""

    key: str
    label: str
    solver: str
    """솔버 — 한 파일에는 한 솔버만 선다."""
    extension: str
    describe: str


class DeckSkippedOut(BaseModel):
    mid: int
    name: str
    missing: list[str]


class DeckBuiltOut(BaseModel):
    filename: str
    text: str
    material_count: int
    solver: str = "dyna"
    """이 파일의 솔버 — 받는 쪽이 확장자로 짐작하지 않게."""
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


class CatalogSeriesColumnOut(BaseModel):
    property_key: str
    property_name: str
    unit: str | None
    """저장된 단위 — 정의의 단위."""
    domain: str | None = None
    symbol: str | None = None
    count: int = 0
    """이 열의 점 수. 점 자체는 상세에 안 실린다 — `GET /catalog/series/{id}/points`."""
    low: float | None = None
    high: float | None = None
    """이 열의 값 범위(저장 단위). 요약 화면이 점을 받지 않고 「몇 ~ 몇」 을 쓴다."""


class CatalogSeriesOut(BaseModel):
    """이어진 값 한 벌의 머리(ADR 0067) — 곡선 · 표 또는 계수 묶음."""

    id: uuid.UUID
    kind: str
    """`curve` · `parameter_set`."""
    label: str
    x_key: str | None
    """곡선의 축 — 점의 조건 칸 이름(예: temperature_k · strain_pct)."""
    x_unit: str | None = None
    """축의 단위 — 키에서 안다(temperature_k → K). 모르는 축이면 비어 있다."""
    x_min: float | None = None
    x_max: float | None = None
    """점들의 축 범위(축 단위)."""
    columns: list[CatalogSeriesColumnOut]
    model: str | None
    point_count: int
    conditions: dict[str, Any] | None
    method: str
    quality_tier: int
    source: CatalogSourceOut | None
    source_detail: str | None
    notes: str | None
    created_by: str | None = None
    created_at: datetime
    batch_key: str | None = None
    """반입 묶음으로 들어왔으면 그 묶음(ADR 0068)."""


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
    source_missing_at: datetime | None = None
    """원본 스냅샷에서 빠진 것을 본 때 — 비어 있으면 원본에 있다. 이관은 지우지 않고
    표시만 하며, 빠진 값은 대표값 · 값 검색 · 커버리지에서 빠진다(2026-10-04)."""
    created_by: str | None = None
    values: list[CatalogValueOut]
    """낱값과 계수 묶음의 항. **곡선 · 산점의 점은 대표값으로 뽑힌 것만** 온다(ADR 0072) —
    벌의 점은 `GET /catalog/series/{id}/points` 로 따로 받는다."""
    series: list[CatalogSeriesOut] = Field(default_factory=list)
    """직접 넣은 **이어진 값 한 벌**들(ADR 0067). 점 수 · 값 범위는 머리에 있다. 값 검색 ·
    대표값은 여전히 그 점을 낱값처럼 읽는다."""


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
    """SI 정본 단위(Pa · J/(kg.K) · 1) 또는 눈금(HV · ShoreA · IRHD …). 수치 물성이면 필수."""
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
    is_span: bool = False
    """값이 **절대값이 아니라 폭**인가(WLF C₂ 처럼). 단위는 같은데 환산이 다르다 —
    폭은 섭씨로 바꿔도 크기가 그대로다. 화면이 이것으로 배지를 세운다."""


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


class CatalogPropertyUpdate(BaseModel):
    """물성 정의 고치기 — 지금은 **정의문** 하나(ADR 0050).

    부분 수정이다. 안 보낸 칸은 그대로, `description: null`(또는 빈 글)은 정의문을 비운다.
    """

    description: str | None = Field(default=None, max_length=2000)


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
    attributes: dict[str, Any] | None = None
    """규격명 · 형태 · 상태 같은 재료의 정체(ADR 0068) — `contribute.MATERIAL_ATTRIBUTES` 의
    칸만 받는다. 모르는 칸은 거절한다(아무 칸이나 받으면 같은 뜻이 이름 둘로 갈린다)."""


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
    license: str | None = Field(default=None, max_length=100)
    """SPDX 식별자(`CC-BY-4.0`) 또는 `LicenseRef-…`. 상업 이용이 안 되는 것(NC)은 거절한다."""
    attribution: str | None = None
    """귀속 문구 — 라이선스가 표기를 조건으로 하면 그 글."""


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


class CatalogSeriesColumnIn(BaseModel):
    property_key: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    """이 열 값의 단위. 정의 단위와 같은 차원이면 서버가 정의 단위로 환산한다."""


class CatalogSeriesTermIn(BaseModel):
    term: str = Field(min_length=1, max_length=50)
    value: float
    unit: str | None = Field(default=None, max_length=50)
    """항의 단위. 정의가 무차원(`1`)인 계수 묶음 키면 환산하지 않고 그대로 둔다(ADR 0029)."""
    property_key: str | None = Field(default=None, max_length=100)
    """비우면 벌의 `property_key`. Prony 처럼 두 키에 걸친 벌이면 항마다 적는다."""


class CatalogSeriesCreate(BaseModel):
    """**이어진 값 한 벌**을 한 번에 넣는다(ADR 0067) — 점마다 값 하나를 넣을 때와 같은 검사.

    곡선(`curve`): `x_key`(정의의 조건축) · `columns`(물성 열) · `rows`(`[x, y1, y2 …]`, 빈
    칸은 null). 계수 묶음(`parameter_set`): `model` · `property_key` · `terms`. 출처 · 등급 ·
    방법 · 조건은 벌 전체가 하나다.
    """

    kind: Literal["curve", "scatter", "parameter_set"]
    label: str = Field(min_length=1, max_length=200)
    x_key: str | None = Field(default=None, max_length=100)
    x_unit: str | None = Field(default=None, max_length=50)
    """축 값의 단위. 비우면 키의 단위로 적은 것으로 본다(temperature_k 면 K)."""
    columns: list[CatalogSeriesColumnIn] = Field(default_factory=list, max_length=8)
    rows: list[list[float | None]] = Field(default_factory=list, max_length=5000)
    row_conditions: list[dict[str, Any]] | None = None
    """줄마다 점에 더할 조건 — `rows` 와 같은 길이. `runout`(bool) · `specimen` ·
    `failure_mode` 만 받는다(ADR 0068). S-N 의 런아웃 표시가 여기 든다."""
    model: str | None = Field(default=None, max_length=50)
    property_key: str | None = Field(default=None, max_length=100)
    terms: list[CatalogSeriesTermIn] = Field(default_factory=list, max_length=500)
    conditions: dict[str, Any] | None = None
    """벌 전체가 함께 가진 조건 — 점마다 같이 들어간다."""
    method: str = "handbook"
    quality_tier: int = Field(ge=1, le=4)
    source: CatalogSourceIn
    source_detail: str | None = None
    notes: str | None = None


class CatalogSeriesPointOut(BaseModel):
    property_key: str
    value: float
    unit: str | None
    x: float | None = None
    """곡선의 축 값(축 단위)."""
    term: str | None = None
    term_unit: str | None = None
    row_conditions: dict[str, Any] | None = None
    """줄마다 붙은 조건 — `runout` · `specimen` · `failure_mode`(ADR 0068). 벌 공통 조건은
    머리에 있다."""


class CatalogSeriesPointsOut(BaseModel):
    """벌 하나의 점 — 상세에 안 싣고 화면이 그 벌을 열 때 받는다(ADR 0072)."""

    series: CatalogSeriesOut
    points: list[CatalogSeriesPointOut]
    """축 차례. 출처 · 등급 · 방법은 벌 전체가 하나라 점마다 되풀이하지 않는다."""


class CatalogSeriesCreatedOut(BaseModel):
    series: CatalogSeriesOut
    points: list[CatalogSeriesPointOut]
    """저장된(미리보기면 저장될) 점 — 정의 단위로 환산한 값."""
    converted: list[str] = Field(default_factory=list)
    """열마다 환산 내역 — "MPa → Pa(12점)"."""


class CatalogPropertyPreviewOut(BaseModel):
    """만들면 **이렇게 된다** — 만들 때와 같은 검사를 지났다(2026-10-20).

    AI 의 미리보기가 서버에 묻지 않고 입력을 그대로 돌려줘서, 미리보기는 통과하고 실제 생성에서
    「단위표에 없습니다」 로 거절되는 일이 있었다(사용자 보고). 이 응답은 생성 코드를 그대로
    돌리고 되돌린 결과다.
    """

    key: str
    name: str
    domain: str
    si_unit: str | None
    """정본 표기로 고친 단위 — `irhd` 를 적었으면 `IRHD`."""
    scale: bool
    """눈금인가 — 환산하지 않고 그 기호로만 값을 받는다."""
    symbol: str | None


class CatalogValuePreviewOut(BaseModel):
    """넣으면 **이렇게 저장된다** — 넣을 때와 같은 검사(단위 환산 · 눈금 일치 · 출처)를
    지났다."""

    property_key: str
    property_name: str
    value_num: float | None
    value_text: str | None
    unit: str | None
    """저장될 단위 — 정의의 단위."""
    uncertainty: float | None
    converted: str | None = None
    """환산했으면 그 내역 — "310 MPa → 3.1e+08 Pa"."""


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
    description: str | None = None
    """**정의문** — 이 물성이 무엇인가(ADR 0050). 이름이 비슷한 후보를 뜻으로 가른다."""
    test_standard: str | None = None
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
    condition_axes: list[str] = []
    """이 물성의 값이 무엇을 따라 갈리나 — 곡선을 넣을 때 축 후보(ADR 0067)."""


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


class AliasSuggestionOut(BaseModel):
    """「이것 아닐까」 — 못 푼 이름에 뜻이 가까운 물성(2026-09-18).

    **고르는 것은 사람이다.** 자동으로 이으면 「UTS」 가 엉뚱한 물성의 별칭이 되고, 그
    잘못은 그 뒤 모든 검색에 실린다 — 별칭은 사람이 못 박아 두는 것이라는 뜻이 사라진다.
    """

    key: str
    name: str
    si_unit: str
    value_count: int
    matched_by: str
    """`meaning` 이면 뜻으로 찾은 것 — 이름이 안 비슷해도 걸린다."""


class AliasCandidateOut(BaseModel):
    """못 푼 이름 하나 — 관리자가 별칭으로 받아들이거나 무시한다(2026-09-16)."""

    id: uuid.UUID
    kind: str
    text: str
    source: str
    count: int
    status: str
    resolved_to: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    suggestions: list[AliasSuggestionOut] = []
    """물성 이름 해소가 낸 후보 — 뜻이 가까운 것 포함. 비어 있으면 짐작할 것이 없다."""

    model_config = {"from_attributes": True}


class AliasCandidateAccept(BaseModel):
    property_key: str = Field(min_length=1, max_length=120)
    """이 물성의 별칭이 된다."""


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
    description: str | None = None
    """**정의문**(ADR 0050) — 받아 간 시스템이 이 키의 뜻을 자기 개념과 견줄 때 읽는다."""
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
    description: str | None = None
    """**정의문**(ADR 0050) — 매핑 화면이 이 줄의 뜻을 보이고, 자료 관리자가 그 자리에서
    고친다."""
    is_span: bool = False
    """값이 **절대값이 아니라 폭**인가(WLF C₂ 처럼). 단위는 같은데 환산이 다르다."""
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
    low: float | None = None
    high: float | None = None
    """묶인 값의 범위(**물어본 단위**). 문헌 벌의 점을 한 줄로 묶었을 때만(ADR 0072) —
    `value` 는 그중 기준에 가장 가까운 점이다."""
    series: str | None = None
    """문헌 벌(곡선 · 산점)의 점을 묶은 줄이면 그 벌의 이름. `count` 가 그 벌에서 창에 든
    점 수다."""


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
    """**보여 준 수**다 — 세계마다 `limit` 으로 자르고 합친 것이라 전체 수가 아니다.
    전부인지는 `truncated` 가 말한다."""
    truncated: bool = False
    """어느 세계든 `limit` 에 걸려 잘렸으면 참. **거짓이면 이것이 전부다** — 창을 좁혀
    다시 물을 이유가 없다(2026-09-20, 「없다」 규약)."""
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


# --- 반입 묶음 (ADR 0068) ----------------------------------------------------------


class CatalogMaterialPreviewOut(BaseModel):
    """재료를 만들면 **이렇게 된다** — 만들 때와 같은 검사를 지났다. 비슷한 기존 재료를
    함께 준다."""

    name: str
    category: str
    attributes: dict[str, Any] | None
    similar: list[CatalogMaterialOut]
    """이름 낱말이 겹치는 기존 문헌 재료(최대 10) — 같은 재료를 또 만들지 않게."""


class CatalogBatchMetaIn(BaseModel):
    key: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9][a-z0-9._/-]{2,159}$")
    """`materialcollector/fatigue-literature/2026-10-23` 꼴 — 소문자 · 숫자 · `._/-`."""
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


_ITEM_KEY = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,38}$"


class CatalogBatchSourceIn(CatalogSourceIn):
    key: str = Field(pattern=_ITEM_KEY)
    """묶음 안의 출처 키 — 값 · 벌이 이 키로 출처를 가리킨다."""


class CatalogBatchMaterialIn(BaseModel):
    """새 문헌 재료, 또는 **이미 있는 문헌 재료**(`existing_mt_id` · `existing_id`)를 가리킨다
    — 둘 중 하나."""

    key: str = Field(pattern=_ITEM_KEY)
    existing_id: uuid.UUID | None = None
    """이미 있는 문헌 재료에 붙일 때. 그 재료는 묶음의 것이 아니라 묶음을 지워도 남는다.
    uuid 는 서버마다 달라 개발에서 만든 파일이 운영에서는 「없는 재료」 가 된다."""
    existing_mt_id: int | None = Field(default=None, ge=1)
    """이관 원본 번호(`mt_id`)로 가리킨다 — 개발 · 운영이 같은 원본을 들여 같은 번호다.
    같은 파일을 두 서버에 쓰려면 이쪽을 쓴다."""
    name: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=30)
    material_code: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = None
    grade: str | None = None
    material_class: str | None = None
    subsystem: str | None = Field(default=None, max_length=50)
    description: str | None = None
    attributes: dict[str, Any] | None = None


class CatalogBatchValueIn(BaseModel):
    """낱값 하나 — 출처는 묶음의 출처 키로 가리킨다."""

    key: str = Field(pattern=_ITEM_KEY)
    material: str
    """묶음의 재료 키."""
    source: str
    """묶음의 출처 키."""
    property_key: str = Field(min_length=1, max_length=100)
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = Field(default=None, max_length=50)
    uncertainty: float | None = None
    conditions: dict[str, Any] | None = None
    method: str = "handbook"
    quality_tier: int = Field(ge=1, le=4)
    source_detail: str | None = None
    notes: str | None = None


class CatalogBatchSeriesIn(BaseModel):
    """이어진 값 한 벌(ADR 0067) — 출처는 묶음의 출처 키로."""

    key: str = Field(pattern=_ITEM_KEY)
    material: str
    source: str
    kind: Literal["curve", "scatter", "parameter_set"]
    label: str = Field(min_length=1, max_length=200)
    x_key: str | None = Field(default=None, max_length=100)
    x_unit: str | None = Field(default=None, max_length=50)
    columns: list[CatalogSeriesColumnIn] = Field(default_factory=list, max_length=8)
    rows: list[list[float | None]] = Field(default_factory=list, max_length=5000)
    row_conditions: list[dict[str, Any]] | None = None
    model: str | None = Field(default=None, max_length=50)
    property_key: str | None = Field(default=None, max_length=100)
    terms: list[CatalogSeriesTermIn] = Field(default_factory=list, max_length=500)
    conditions: dict[str, Any] | None = None
    method: str = "handbook"
    quality_tier: int = Field(ge=1, le=4)
    source_detail: str | None = None
    notes: str | None = None


class CatalogBatchBundleIn(BaseModel):
    """**묶음 파일 하나**(ADR 0068) — 서버가 한 번에 받아 전부 되거나 전부 안 된다."""

    batch: CatalogBatchMetaIn
    sources: list[CatalogBatchSourceIn] = Field(default_factory=list, max_length=2000)
    materials: list[CatalogBatchMaterialIn] = Field(default_factory=list, max_length=2000)
    values: list[CatalogBatchValueIn] = Field(default_factory=list, max_length=10000)
    series: list[CatalogBatchSeriesIn] = Field(default_factory=list, max_length=2000)


class CatalogBatchCountOut(BaseModel):
    created: int = 0
    existing: int = 0
    """같은 외부 키 · 같은 내용으로 이미 있어 그대로 둔 것."""


class CatalogBatchProblemOut(BaseModel):
    kind: str
    """`source` · `material` · `value` · `series`."""
    key: str
    code: str
    message: str


class CatalogBatchAttachedOut(BaseModel):
    """이미 있는 문헌 재료를 가리킨 항목이 어느 재료로 풀렸나."""

    key: str
    id: uuid.UUID
    mt_id: int | None
    name: str


class CatalogBatchWarningOut(BaseModel):
    """막지는 않는 것 — 정의의 조건축 · 문헌 조건 칸 목록에 없는 조건 칸(ADR 0071)."""

    key: str
    count: int
    example: str
    """처음 본 항목 키."""
    message: str


class CatalogBatchImportOut(BaseModel):
    """들이기의 결과 — 미리보기면 **들였을 때의 결과**이고 아무것도 남지 않는다."""

    batch_key: str
    dry_run: bool
    applied: bool
    """실제로 적었나. 문제가 하나라도 있으면 아무것도 적지 않는다."""
    sources: CatalogBatchCountOut
    materials: CatalogBatchCountOut
    values: CatalogBatchCountOut
    series: CatalogBatchCountOut
    points: int
    """새로 생긴 벌의 점 수."""
    licenses: dict[str, int]
    """이 묶음 출처의 라이선스별 수 — 빈 것은 `(없음)`."""
    attached: list[CatalogBatchAttachedOut] = Field(default_factory=list)
    """이미 있는 재료에 붙는 항목과 그 재료 이름. 번호가 하나 어긋나면(SUS304 ↔ SUS304L)
    남의 재료에 조용히 붙으므로 미리보기에서 이름을 대 본다."""
    problems: list[CatalogBatchProblemOut]
    warnings: list[CatalogBatchWarningOut] = Field(default_factory=list)
    """막지 않는 경고 — 조건 칸 이름이 정의의 축 · 문헌 조건 칸 목록 밖이다."""


class CatalogBatchOut(BaseModel):
    key: str
    title: str
    description: str | None
    manifest_sha256: str | None
    created_by: str | None
    created_at: datetime
    retired_at: datetime | None
    materials: int
    sources: int
    values: int
    series: int
    adopted: int
    """사내 재료 · 시료가 선언 물성으로 받아 간 이 묶음의 값 수 — 0 이 아니면 지울 수 없다."""
    licenses: dict[str, int]


class CatalogBatchDeleteOut(BaseModel):
    batch_key: str
    dry_run: bool
    series: int
    values: int
    sources: int
    materials: int


class CatalogConditionFieldOut(BaseModel):
    """문헌 조건 칸 하나 — 반입 묶음 · 낱값의 조건에 쓰는 이름(ADR 0071)."""

    key: str
    group: str
    label: str
    unit: str | None = None
    values: list[str] = Field(default_factory=list)
    note: str | None = None
