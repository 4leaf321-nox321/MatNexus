"""보유 장비 API 의 입출력.

**「안 보낸 것」과 「비운 것」을 구별한다**(AGENTS.md). 수정은 `exclude_unset` 으로
받으므로, 담당자를 안 보내면 그대로 두고 `null` 을 보내면 지운다. 안 구별하면
장비명만 고쳐 저장할 때마다 나머지 칸이 지워진다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.modules.equipment.models import (
    CALIBRATION_RESULTS,
    OWNERSHIPS,
    PART_KINDS,
    STATUSES,
)


def _one_of(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ValueError(
            f"{what} 는 {', '.join(allowed)} 중 하나여야 합니다 (받은 값: {value})"
        )
    return value


class EquipmentWorkspaceRef(BaseModel):
    """장비를 들고 있는 부서 — **상위 조직까지 함께.**

    부서는 본부→팀 트리라(`Workspace.parent_id`) 「어느 본부의 팀인가」 가 목록
    한 줄에서 보여야 한다. 화면이 부서 목록을 따로 받아 잇게 두면 줄마다 그 일을
    한다.
    """

    id: uuid.UUID
    slug: str
    label: str
    #: 트리의 꼭대기. 사업부별 현황이 이것으로 묶인다.
    root_id: uuid.UUID | None = None
    root_label: str | None = None


class EquipmentTermRef(BaseModel):
    """기준정보 값 하나 — id 와 함께 **보여 줄 이름**을 싣는다.

    화면이 이름을 얻으려고 축 목록을 따로 부르지 않게 한다. 부모(사업부)를 함께
    싣는 이유도 같다 — 조직만 오면 「어느 사업부인가」 를 화면이 또 물어야 한다.
    """

    id: uuid.UUID
    label: str
    parent_id: uuid.UUID | None = None
    parent_label: str | None = None


class EquipmentCalibrationOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    part_id: uuid.UUID | None
    performed_on: date
    valid_until: date | None
    agency: str | None
    certificate_no: str | None
    result: str
    storage_path: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EquipmentCalibrationCreate(BaseModel):
    part_id: uuid.UUID | None = None
    performed_on: date
    valid_until: date | None = None
    agency: str | None = None
    certificate_no: str | None = None
    result: str = "pass"
    notes: str | None = None

    @field_validator("result")
    @classmethod
    def _result(cls, value: str) -> str:
        return _one_of(value, CALIBRATION_RESULTS, "교정 결과")


class EquipmentPartOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    kind: str
    label: str
    asset_no: str | None
    manufacturer: str | None
    model: str | None
    serial_no: str | None
    capacity: str | None
    installed_on: date | None
    removed_on: date | None
    notes: str | None

    model_config = {"from_attributes": True}


class EquipmentPartCreate(BaseModel):
    kind: str = "other"
    label: str = Field(min_length=1, max_length=120)
    asset_no: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    capacity: str | None = None
    installed_on: date | None = None
    removed_on: date | None = None
    notes: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        return _one_of(value, PART_KINDS, "부속 종류")


class EquipmentPartUpdate(BaseModel):
    kind: str | None = None
    label: str | None = None
    asset_no: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    capacity: str | None = None
    installed_on: date | None = None
    removed_on: date | None = None
    notes: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str | None) -> str | None:
        return None if value is None else _one_of(value, PART_KINDS, "부속 종류")


class EquipmentUnitOut(BaseModel):
    """목록과 상세가 같은 모양을 쓴다 — 목록에서 본 것이 상세에 없으면 놀란다."""

    id: uuid.UUID
    asset_no: str | None
    name: str
    ownership: str
    status: str

    manufacturer: str | None
    model: str | None
    serial_no: str | None
    instrument_id: uuid.UUID | None

    #: 기준정보들. 이름까지 실어 화면이 축을 따로 안 부르게 한다.
    instrument_type: EquipmentTermRef | None = None
    instrument_term: EquipmentTermRef | None = None
    lab: EquipmentTermRef | None = None

    #: 장비를 들고 있는 조직 = 부서. **상위 조직을 함께 싣는다** — 부서 트리를
    #: 타고 올라간 것이라 화면이 또 물을 필요가 없다.
    org: EquipmentWorkspaceRef | None = None

    location_detail: str | None
    workspace_id: uuid.UUID | None
    owner_name: str | None
    owner_contact: str | None
    commissioned_on: date | None
    retired_on: date | None
    attributes: dict[str, Any]
    notes: str | None

    #: 최근 교정과 그 유효기간. **목록에서 만료를 보려면 여기 있어야 한다** —
    #: 장비마다 교정 목록을 따로 부르면 목록 한 장에 N+1 이 난다.
    last_calibrated_on: date | None = None
    calibration_valid_until: date | None = None
    part_count: int = 0

    created_at: datetime
    updated_at: datetime


class EquipmentUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    asset_no: str | None = None
    ownership: str = "internal"
    status: str = "active"

    instrument_id: uuid.UUID | None = None

    #: 장비를 들고 있는 부서 — **slug 나 이름으로 받는다.** 화면의 부서 피커가
    #: slug 로 움직인다(`WorkspacePicker`). **없으면 만들지 않고 거절한다** —
    #: 기준정보와 다른 점이고, 부서는 권한이 붙는 자리이기 때문이다.
    workspace: str | None = None

    #: **기준정보는 이름으로 받는다.** 화면의 피커가 이름으로 움직이고
    #: (`VocabularyField`), 서버가 `apply_bindings` 로 해석해 FK 까지 채운다 —
    #: 없는 이름이면 만든다(`open` 축). 사람이 폼에 id 를 적지 않는다.
    instrument_type: str | None = None
    instrument: str | None = None
    lab: str | None = None

    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    location_detail: str | None = None
    owner_name: str | None = None
    owner_contact: str | None = None
    commissioned_on: date | None = None
    retired_on: date | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("ownership")
    @classmethod
    def _ownership(cls, value: str) -> str:
        return _one_of(value, OWNERSHIPS, "소속 구분")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        return _one_of(value, STATUSES, "상태")


class EquipmentUnitUpdate(BaseModel):
    """**전부 선택이다.** 보낸 것만 바꾼다(`exclude_unset`)."""

    name: str | None = None
    asset_no: str | None = None
    ownership: str | None = None
    status: str | None = None

    instrument_id: uuid.UUID | None = None
    workspace: str | None = None

    instrument_type: str | None = None
    instrument: str | None = None
    lab: str | None = None

    manufacturer: str | None = None
    model: str | None = None
    serial_no: str | None = None
    location_detail: str | None = None
    owner_name: str | None = None
    owner_contact: str | None = None
    commissioned_on: date | None = None
    retired_on: date | None = None
    attributes: dict[str, Any] | None = None
    notes: str | None = None

    @field_validator("ownership")
    @classmethod
    def _ownership(cls, value: str | None) -> str | None:
        return None if value is None else _one_of(value, OWNERSHIPS, "소속 구분")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str | None) -> str | None:
        return None if value is None else _one_of(value, STATUSES, "상태")


class EquipmentBulkRow(EquipmentUnitCreate):
    """붙여넣기 표 한 줄.

    등록 요청과 같은 모양이다 — 부서를 slug·이름으로 받는 것이 이제 양쪽 공통이다.
    """


class EquipmentBulkRequest(BaseModel):
    rows: list[EquipmentBulkRow]
    dry_run: bool = True
    """**드라이런이 기본이다.** 붙여넣기는 한 번에 수십 줄이 들어오는 자리라,
    무엇이 만들어지고 무엇이 걸리는지 보고 나서 누르게 한다(이관기와 같은 규율)."""


class EquipmentBulkRowResult(BaseModel):
    index: int
    name: str
    outcome: str
    """`create` · `skip` · `error`."""
    reason: str | None = None
    unit_id: uuid.UUID | None = None
    #: 이 줄이 새로 만들 기준정보 값. **미리 보여 준다** — 오타가 새 값을 만드는
    #: 것이 이 화면에서 가장 흔한 사고다.
    new_terms: list[str] = Field(default_factory=list)


class EquipmentBulkResult(BaseModel):
    dry_run: bool
    created: int
    skipped: int
    errors: int
    rows: list[EquipmentBulkRowResult]


class EquipmentSummaryRow(BaseModel):
    """현황 한 줄. 사업부·조직 어느 층으로도 묶인다."""

    key: str
    label: str
    total: int
    active: int
    maintenance: int
    idle: int
    retired: int
    external: int
    calibration_due: int
    """교정 유효기간이 지났거나 30일 안에 끝나는 대수."""


class EquipmentSummaryOut(BaseModel):
    total: int
    #: 부서 트리의 꼭대기로 묶은 것. 사업부·본부 층이다.
    by_root_org: list[EquipmentSummaryRow]
    #: 장비를 들고 있는 부서 그대로.
    by_org: list[EquipmentSummaryRow]
    by_lab: list[EquipmentSummaryRow]
