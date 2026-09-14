"""측정 의뢰 API 형태."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class NamedOut(BaseModel):
    """이름 붙은 참조 하나 — 부서·사람·재료."""

    id: uuid.UUID
    name: str


class WorkspaceRefOut(BaseModel):
    slug: str
    name: str


class SampleRefOut(BaseModel):
    id: uuid.UUID
    record_name: str
    material_id: uuid.UUID
    material_name: str


class ProgressOut(BaseModel):
    """항목 전부를 합친 진행률. **저장하지 않고 센다** — 시험이 지워지면 함께 준다."""

    total: int
    """의뢰한 시편 수의 합."""
    linked: int
    """붙은 시험 수."""
    done: int
    """붙은 시험 가운데 결과가 채택된 것."""


class CommissionOut(BaseModel):
    """목록 한 줄. 상세는 `CommissionDetailOut`."""

    id: uuid.UUID
    seq: int
    title: str
    status: str
    status_label: str
    priority: str
    priority_label: str
    requester_workspace: WorkspaceRefOut
    lab_workspace: WorkspaceRefOut
    sample: SampleRefOut | None
    """등록된 시료. 새 재료 의뢰면 비어 있고 `material_hint` 가 대신 말한다."""
    material_hint: str | None
    due_on: date | None
    created_at: datetime
    created_by: str | None
    status_at: datetime
    status_by: str | None
    assignee: NamedOut | None
    item_count: int
    progress: ProgressOut
    is_mine: bool
    """내가 낸 것인가."""
    side: str
    """이 사람이 이 건에서 어느 쪽인가 — `requester` · `lab` · `both` · `viewer`(시스템
    관리자가 어느 쪽도 아닐 때). 화면이 「내가 낸 것 / 우리 부서가 받은 것」 탭과
    단추를 이것으로 가른다 — 부서 멤버십을 화면이 다시 따지지 않는다."""
    event_count: int
    """등록을 뺀 이벤트 수."""
    can_delete: bool
    """지울 수 있는가 — 낸 사람은 받는 쪽이 손대기 전까지, 시스템 관리자는 언제나.
    서버가 정한다 — 목록과 상세가 같은 규칙으로 단추를 보인다."""


class LinkedRunOut(BaseModel):
    id: uuid.UUID
    record_name: str
    status: str
    adopted: bool
    """채택된 처리 결과가 있는가 — 진행률에 드는 것은 이것뿐이다."""
    specimen_name: str | None
    tested_at: datetime | None


class CommissionItemOut(BaseModel):
    id: uuid.UUID
    position: int
    test_type_key: str | None
    """비어 있으면 시험 종류 미정 — `property_hint` 가 무엇을 재는지 말한다."""
    test_type_label: str | None
    property_hint: str | None
    conditions: dict[str, Any]
    """SI 값. 화면이 `input_units` 로 되돌려 보인다."""
    input_units: dict[str, str]
    orientations: list[str]
    count: int
    deliverable: str | None
    note: str | None
    runs: list[LinkedRunOut]
    done: int
    candidates: list[LinkedRunOut] = Field(default_factory=list)
    """이 항목에 붙일 수 있는 시험 — 같은 시료, 같은 시험 종류, 아직 어느 항목에도
    안 붙은 것. **받는 쪽에만** 준다."""


class CommissionEventOut(BaseModel):
    id: uuid.UUID
    at: datetime
    by: str | None
    from_status: str | None
    to_status: str
    to_status_label: str
    note: str | None


class CommissionDetailOut(CommissionOut):
    purpose: str
    sample_plan: str | None
    items: list[CommissionItemOut]
    events: list[CommissionEventOut]
    allowed: list[str]
    """**이 사람이 지금 옮길 수 있는 상태.** 받는 쪽과 낸 사람이 다르다 — 화면이
    규칙을 외우지 않는다."""
    allowed_labels: dict[str, str]
    note_required: list[str]
    can_edit: bool
    """제목·목적·항목을 고칠 수 있는가 — 낸 사람이 작성 중·접수 대기일 때."""
    can_link: bool
    """시험을 붙이고 뗄 수 있는가 — 받는 쪽이 접수 뒤."""
    can_assign: bool
    """담당자를 정할 수 있는가 — 받는 쪽."""
    can_resolve: bool
    """시료를 잇거나 항목의 시험 종류를 정할 수 있는가 — 받는 쪽, 완료·반려 전."""
    assignees: list[NamedOut] = Field(default_factory=list)
    """담당자 후보 — 받는 부서 멤버. `can_assign` 일 때만."""


class CommissionStatusOut(BaseModel):
    key: str
    label: str


class CommissionItemIn(BaseModel):
    """항목 하나. **시험 종류 또는 물성 이름** 중 하나는 있어야 한다 — 종류를 모르면
    「무엇을 재는지」 를 글로 적고 받는 쪽이 종류를 정한다."""

    test_type_key: str | None = Field(default=None, max_length=50)
    property_hint: str | None = Field(default=None, max_length=500)
    conditions: dict[str, Any] = Field(default_factory=dict)
    """화면이 받은 값 그대로 — 단위는 `condition_units` 에. 서버가 SI 로 바꾼다."""
    condition_units: dict[str, str] = Field(default_factory=dict)
    orientations: list[str] = Field(default_factory=list, max_length=10)
    count: int = Field(default=1, ge=1, le=1000)
    deliverable: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _what(self) -> CommissionItemIn:
        if not (self.test_type_key or "").strip() and not (self.property_hint or "").strip():
            raise ValueError("시험 종류를 고르거나, 무엇을 잴지(물성 이름)를 적어야 합니다.")
        return self


class CommissionCreateRequest(BaseModel):
    """**시료 또는 새 재료 설명** 중 하나는 있어야 한다 — 등록된 시료가 없는 새 재료도
    의뢰한다. 그때는 받는 쪽이 재료·시료를 등록한 뒤 잇는다."""

    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1)
    sample_id: uuid.UUID | None = None
    material_hint: str | None = Field(default=None, max_length=2000)
    lab_workspace_slug: str = Field(min_length=1, max_length=100)
    sample_plan: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None
    priority: str = "normal"
    items: list[CommissionItemIn] = Field(min_length=1, max_length=50)
    submit: bool = False
    """참이면 바로 접수 대기로, 아니면 작성 중으로 둔다."""

    @model_validator(mode="after")
    def _target(self) -> CommissionCreateRequest:
        if self.sample_id is None and not (self.material_hint or "").strip():
            raise ValueError("시료를 고르거나, 새 재료가 무엇인지 적어야 합니다.")
        return self


class CommissionUpdateRequest(BaseModel):
    """낸 것을 고친다 — 작성 중·접수 대기에서 낸 사람만. **안 보낸 칸은 안 건드린다.**

    `due_on` 은 비울 수 있는 칸이라 「안 보냄」 과 「비움」 을 `model_fields_set` 으로
    가른다(AGENTS.md). `items` 를 보내면 항목 전부를 갈아 넣는다 — 항목은 표 한 장으로
    편집하는 것이라 낱개로 받으면 순서가 꼬인다.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, min_length=1)
    sample_id: uuid.UUID | None = None
    material_hint: str | None = Field(default=None, max_length=2000)
    lab_workspace_slug: str | None = Field(default=None, min_length=1, max_length=100)
    sample_plan: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None
    priority: str | None = None
    items: list[CommissionItemIn] | None = Field(default=None, min_length=1, max_length=50)


class AssignRequest(BaseModel):
    """담당자 지정 — 받는 쪽. `None` 이면 비운다."""

    assignee_id: uuid.UUID | None = None


class CommissionEventRequest(BaseModel):
    """상태를 옮기거나 말을 보탠다. **둘 중 하나는 있어야 한다.**"""

    status: str | None = None
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _something(self) -> CommissionEventRequest:
        if self.status is None and not (self.note or "").strip():
            raise ValueError("상태를 옮기거나 말을 적어야 합니다.")
        return self


class LinkRunRequest(BaseModel):
    run_id: uuid.UUID


class AttachSampleRequest(BaseModel):
    """새 재료 의뢰에 등록된 시료를 잇는다 — 받는 쪽이 재료·시료를 만든 뒤."""

    sample_id: uuid.UUID


class ResolveItemRequest(BaseModel):
    """종류 미정 항목에 시험 종류를 정한다 — 받는 쪽. 조건은 그 종류의 칸으로 함께."""

    test_type_key: str = Field(min_length=1, max_length=50)
    conditions: dict[str, Any] = Field(default_factory=dict)
    condition_units: dict[str, str] = Field(default_factory=dict)
