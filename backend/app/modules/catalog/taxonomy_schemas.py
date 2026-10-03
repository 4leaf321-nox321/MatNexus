"""물성 분류(분야 ⊃ 물성군 ⊃ 물성)의 요청 · 응답 모양 (ADR 0054).

바깥(SP)이 읽어 가는 목록(`Feed*`)은 SP 연동 지침 §3.1 의 모양이다 — **평평한 행**, 행마다
안 바뀌는 식별자(`key`)와 `updated_at`, 폐기한 것도 행으로(`is_active: false`), 여럿인 값은
`;` 로 이어서(SP 가 여러 값을 가르는 글자다 — `objects/bulk.MULTI_SEP`). **열 이름을 바꾸지
않는다**(SP 의 칸 대응이 열 이름에 물려 있다) — 늘리는 것은 자유다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── 화면이 읽는 트리 ────────────────────────────────────────────────────────


class PropertyFieldOut(BaseModel):
    key: str
    name: str
    description: str | None
    sort_order: int
    retired: bool
    group_count: int
    """쓰는 중인 물성군 수."""
    property_count: int
    """이 분야의 물성군에 든 물성 수."""


class PropertyGroupOut(BaseModel):
    key: str
    field_key: str
    name: str
    description: str | None
    sort_order: int
    retired: bool
    property_count: int


class TaxonomyPropertyOut(BaseModel):
    """분류 화면의 물성 한 줄 — 고르고 옮기는 데 필요한 것만."""

    key: str
    name: str
    symbol: str | None
    si_unit: str | None
    domain: str
    """키 앞머리. **분류가 아니다** — 식별자의 일부다(ADR 0054)."""
    local: bool
    """MatNexus 에서 만든 물성(`local.`)인가."""
    deprecated: bool
    group_key: str | None
    """든 물성군. 비었으면 미분류."""
    value_count: int
    """문헌 값 건수 — 무엇부터 분류할지 고르는 근거."""


class TaxonomyOut(BaseModel):
    fields: list[PropertyFieldOut]
    groups: list[PropertyGroupOut]
    properties: list[TaxonomyPropertyOut]
    truncated: bool = False
    """물성이 상한(`MAX_TREE_PROPERTIES`)을 넘어 잘렸나 — 조용히 자르지 않는다."""


# ── 고치기 ──────────────────────────────────────────────────────────────────


class PropertyFieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    key: str | None = Field(default=None, max_length=100)
    """비우면 `pf-0001` 꼴로 만든다. **나중에 못 바꾼다.**"""
    description: str | None = Field(default=None, max_length=2000)


class PropertyFieldUpdate(BaseModel):
    """부분 수정 — 안 보낸 칸은 그대로. `description: null` 은 설명을 비운다.

    `retired` 는 폐기(true) · 되살리기(false). 키는 못 바꾼다(바깥이 키로 잇는다).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    retired: bool | None = None


class PropertyGroupCreate(BaseModel):
    field_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    key: str | None = Field(default=None, max_length=100)
    """비우면 `pg-0001` 꼴로 만든다. **나중에 못 바꾼다** — 다른 분야로 옮겨도 그대로다."""
    description: str | None = Field(default=None, max_length=2000)


class PropertyGroupUpdate(BaseModel):
    """부분 수정. `field_key` 를 보내면 다른 분야로 옮긴다(든 물성은 함께 간다)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    field_key: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    retired: bool | None = None


class TaxonomyAssignIn(BaseModel):
    """물성 여럿을 한 물성군에 넣는다. `group_key: null` 이면 군에서 뺀다(미분류)."""

    group_key: str | None
    property_keys: list[str] = Field(min_length=1, max_length=500)


class TaxonomyAssignOut(BaseModel):
    group_key: str | None
    changed: list[str]
    """소속이 실제로 바뀐 물성 키. 이미 거기 있던 것은 안 든다."""
    unchanged: list[str]


# ── 밀어 넣기 ───────────────────────────────────────────────────────────────


class TaxonomyImportRow(BaseModel):
    """한 줄 = 분야 > 물성군 > 물성 한 갈래.

    물성 칸이 비면 그 줄은 분야 · 물성군만 만든다(빈 군). 각 칸은 **이름이나 키** 어느 것을
    적어도 된다 — 키 칸을 따로 주면 그 키로 찾고, 없으면 그 키로 만든다(SP 의 키를 그대로
    가져오면 두 시스템의 키가 같아진다. SP 는 첫 연동에서 **이름**으로 잇는다).
    """

    field: str | None = Field(default=None, max_length=200)
    field_key: str | None = Field(default=None, max_length=100)
    field_description: str | None = Field(default=None, max_length=2000)
    group: str | None = Field(default=None, max_length=200)
    group_key: str | None = Field(default=None, max_length=100)
    group_description: str | None = Field(default=None, max_length=2000)
    property: str | None = Field(default=None, max_length=200)
    """물성 키(`mechanical.yield_strength`) · 이름(「항복강도」) · 별칭. **정확히 맞는 것만** —
    비슷한 것을 골라 주지 않는다."""


class TaxonomyImportIn(BaseModel):
    rows: list[TaxonomyImportRow] = Field(min_length=1, max_length=3000)
    dry_run: bool = True
    """기본이 미리 보기다 — 무엇이 생기고 옮겨지는지 보고 나서 넣는다."""


Action = Literal["create", "update", "move", "restore", "unchanged"]


class ImportFieldOut(BaseModel):
    key: str
    name: str
    action: Action
    before_name: str | None = None
    """이름이 바뀌면 옛 이름."""


class ImportGroupOut(BaseModel):
    key: str
    name: str
    field_key: str
    action: Action
    before_name: str | None = None
    before_field_key: str | None = None
    """다른 분야에서 옮겨 오면 옛 분야."""


class ImportMemberOut(BaseModel):
    property_key: str
    property_name: str
    group_key: str
    action: Literal["assign", "move", "unchanged"]
    before_group_key: str | None = None
    domain: str = ""
    """물성의 키 앞머리."""
    cross_domain: bool = False
    """**키 앞머리와 다른 씨앗 분야로 간다** — 막지 않고 미리 보기에 세운다. 이름이 정확히
    맞아도 뜻이 다른 물성일 수 있다: 「항복응력」 은 유변학 물성이라, 기계 > 강도에 적으면
    금속의 항복강도가 아니라 페이스트가 흐르는 응력이 들어간다(2026-10-03 개발 DB 점검에서
    실제로 걸렸다). 분야 키가 키 앞머리가 아니면(`pf-0001` · SP 의 키) 견줄 수 없어
    거짓이다."""


class ImportErrorOut(BaseModel):
    row: int
    """붙여넣은 표의 줄 번호(1부터)."""
    message: str


class TaxonomyImportOut(BaseModel):
    applied: bool
    fields: list[ImportFieldOut]
    groups: list[ImportGroupOut]
    members: list[ImportMemberOut]
    errors: list[ImportErrorOut]
    """하나라도 있으면 넣지 않는다 — 분류는 반만 들어가면 안 된다."""


# ── 바깥(SP)이 읽어 가는 목록 — SP 연동 지침 §3.1 ─────────────────────────────


class FeedFieldOut(BaseModel):
    key: str
    name: str
    description: str | None
    sort_order: int
    group_count: int
    property_count: int
    status: Literal["active", "deprecated"]
    """폐기했으면 `deprecated` — SP 연동 지침 §12-A ④(그만 쓰는 것은 `deprecated`)."""
    is_active: bool
    deleted: bool
    """`is_active` 의 반대. **SP 의 데이터 소스가 읽는 것은 이 칸뿐이다** — `deleted: true` 인
    행을 「사라진 것」 으로 보고 그 객체를 사용 중지로 바꾼다(SP `datasources/services.py`).
    `status` · `is_active` 는 칸 대응의 대상이 아니라서, 이 칸이 없으면 여기서 폐기한 것이 SP
    에서는 영영 「사용」 으로 남는다(2026-10-03 SP 코드를 읽고 찾았다)."""
    updated_at: datetime


class FeedGroupOut(BaseModel):
    key: str
    name: str
    description: str | None
    field_key: str
    field_name: str
    sort_order: int
    property_count: int
    status: Literal["active", "deprecated"]
    is_active: bool
    deleted: bool
    """`is_active` 의 반대 — `FeedFieldOut.deleted` 의 까닭."""
    updated_at: datetime


class FeedPropertyOut(BaseModel):
    key: str
    """허브 키 — 안 바뀐다. 문헌은 `domain.name`, MatNexus 에서 만든 것은 `local.` 으로
    시작한다."""
    name: str
    symbol: str | None
    unit: str | None
    """원본 표기 그대로(`kg/m^3`). 환산하지 않는다."""
    value_type: str
    description: str | None
    test_standard: str | None
    condition_axes: str | None
    """이 물성이 조건 없이 무의미해지는 축을 `;` 로 이은 것."""
    origin: Literal["literature", "local"]
    domain: str
    """키 앞머리 — 분류가 아니다(분류는 `group_key` · `field_key`)."""
    group_key: str | None
    group_name: str | None
    field_key: str | None
    field_name: str | None
    aliases: str | None
    """다른 이름들을 `;` 로 이은 것 — SP 의 별칭 칸에 그대로 잇는다."""
    status: Literal["active", "deprecated"]
    superseded_by: str | None
    deprecation_note: str | None
    is_active: bool
    deleted: bool
    """폐기된 키면 참 — `FeedFieldOut.deleted` 의 까닭. SP 는 이 행의 다른 칸을 읽지 않고 사용
    중지로만 바꾼다."""
    updated_at: datetime


class FeedFieldPage(BaseModel):
    items: list[FeedFieldOut]
    total: int
    page: int
    page_size: int


class FeedGroupPage(BaseModel):
    items: list[FeedGroupOut]
    total: int
    page: int
    page_size: int


class FeedPropertyPage(BaseModel):
    items: list[FeedPropertyOut]
    total: int
    page: int
    page_size: int
