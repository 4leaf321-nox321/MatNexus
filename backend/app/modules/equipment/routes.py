"""보유 장비 API — **읽기는 모두가, 쓰기는 관리자가.**

측정법(`metrology`)이 읽기 전용인 것과 반대다. 저기는 이관물이라 사람이 못
고치고, 여기는 사내 자산이라 사람이 관리하는 것이 전부다.

## 무엇을 못 하게 하나

**실삭제는 참조가 없을 때만 된다.** 지난 시험이 가리키는 장비를 지우면 "이
물성값을 무엇으로 쟀나" 에 답할 수 없다. 폐기는 `status='retired'` 이고, 그것이
정상 경로다 — 목록에서 빠질 뿐 행은 산다.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.equipment import models
from app.modules.equipment.models import (
    EquipmentCalibration,
    EquipmentPart,
    EquipmentUnit,
)
from app.modules.equipment.schemas import (
    EquipmentBulkRequest,
    EquipmentBulkResult,
    EquipmentBulkRowResult,
    EquipmentCalibrationCreate,
    EquipmentCalibrationOut,
    EquipmentPartCreate,
    EquipmentPartOut,
    EquipmentPartUpdate,
    EquipmentSummaryOut,
    EquipmentSummaryRow,
    EquipmentTermRef,
    EquipmentUnitCreate,
    EquipmentUnitOut,
    EquipmentUnitUpdate,
    EquipmentWorkspaceRef,
)
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import VocabularyTerm
from app.modules.workspaces.models import Workspace
from app.shared import audit, dependents
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.pagination import Page
from app.shared.permissions import is_any_manager

router = APIRouter(prefix="/equipment", tags=["equipment"])

#: 교정 만료가 임박했다고 볼 날 수. 30일이면 다음 달 계획에 넣을 수 있다.
DUE_SOON_DAYS = 30

#: 기준정보로 해석되는 칸. **목록을 여기 적지 않는다** — 축이 늘면
#: `vocabulary_services.EQUIPMENT_BINDINGS` 한 곳만 고친다.
BOUND_FIELDS = tuple(one.field for one in vocabulary_services.EQUIPMENT_BINDINGS)


def _require_manager(db: Session, user: User) -> None:
    """**부서 하나라도 관리자면 된다.**

    장비는 부서에 매여 있지 않다 — 「생기연 DMA」 를 재료연구팀 사람이 쓴다.
    `workspace_id` 는 관리 책임을 적는 칸이지 접근을 가르는 칸이 아니다(모델 주석).
    그래서 여기서는 「관리자인가」 만 본다.
    """
    if user.is_system_admin or is_any_manager(db, user):
        return
    raise AppError(
        "MNX-EQUIPMENT-0001",
        "장비를 고치려면 부서 관리자여야 합니다.",
        status=403,
    )


def _term_ref(
    term: VocabularyTerm | None, parent: VocabularyTerm | None
) -> EquipmentTermRef | None:
    if term is None:
        return None
    return EquipmentTermRef(
        id=term.id,
        label=term.value,
        parent_id=parent.id if parent else None,
        parent_label=parent.value if parent else None,
    )


def _terms_by_id(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, VocabularyTerm]:
    """**한 번에 읽는다.** 줄마다 기준정보를 부르면 목록 한 장에 N+1 이 난다."""
    if not ids:
        return {}
    rows = db.scalars(select(VocabularyTerm).where(VocabularyTerm.id.in_(ids))).all()
    found = {row.id: row for row in rows}
    # 부모(사업부)도 함께 — 조직만 오면 화면이 사업부를 또 물어야 한다.
    parents = {row.parent_term_id for row in rows if row.parent_term_id} - set(found)
    if parents:
        for row in db.scalars(select(VocabularyTerm).where(VocabularyTerm.id.in_(parents))):
            found[row.id] = row
    return found


def _calibration_map(
    db: Session, unit_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[date, date | None]]:
    """장비별 **가장 최근** 교정. 목록에서 만료를 보려면 필요하다."""
    if not unit_ids:
        return {}
    latest = (
        select(
            EquipmentCalibration.unit_id,
            func.max(EquipmentCalibration.performed_on).label("performed_on"),
        )
        .where(EquipmentCalibration.unit_id.in_(unit_ids))
        .group_by(EquipmentCalibration.unit_id)
        .subquery()
    )
    rows = db.execute(
        select(
            EquipmentCalibration.unit_id,
            EquipmentCalibration.performed_on,
            EquipmentCalibration.valid_until,
        ).join(
            latest,
            (EquipmentCalibration.unit_id == latest.c.unit_id)
            & (EquipmentCalibration.performed_on == latest.c.performed_on),
        )
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _workspace_refs(
    db: Session, ids: set[uuid.UUID]
) -> dict[uuid.UUID, EquipmentWorkspaceRef]:
    """부서와 **그 트리의 꼭대기**를 함께 준다.

    사업부별 현황이 꼭대기로 묶인다. 장비에 상위 조직을 따로 안 적으므로 여기서
    타고 올라간다 — 같은 답을 두 번 저장하지 않는 대신 한 번 더 읽는다.

    **트리 전체를 한 번에 읽는다.** 부서는 많아야 수백이고, 줄마다 부모를 따라
    올라가면 목록 한 장에 N+1 이 난다.
    """
    if not ids:
        return {}
    rows = {row.id: row for row in db.scalars(select(Workspace)).all()}

    def root(one: Workspace) -> Workspace:
        seen: set[uuid.UUID] = set()
        while one.parent_id and one.parent_id in rows and one.parent_id not in seen:
            seen.add(one.id)  # 순환은 없어야 하지만, 있으면 여기서 멈춘다
            one = rows[one.parent_id]
        return one

    found: dict[uuid.UUID, EquipmentWorkspaceRef] = {}
    for one in ids:
        row = rows.get(one)
        if row is None:
            continue
        top = root(row)
        found[one] = EquipmentWorkspaceRef(
            id=row.id,
            slug=row.slug,
            label=row.name,
            root_id=top.id if top.id != row.id else None,
            root_label=top.name if top.id != row.id else None,
        )
    return found


def _part_counts(db: Session, unit_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not unit_ids:
        return {}
    rows = db.execute(
        select(EquipmentPart.unit_id, func.count())
        .where(EquipmentPart.unit_id.in_(unit_ids))
        .group_by(EquipmentPart.unit_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _to_out(
    unit: EquipmentUnit,
    terms: dict[uuid.UUID, VocabularyTerm],
    workspaces: dict[uuid.UUID, EquipmentWorkspaceRef],
    calibrations: dict[uuid.UUID, tuple[date, date | None]],
    parts: dict[uuid.UUID, int],
) -> EquipmentUnitOut:
    def ref(term_id: uuid.UUID | None) -> EquipmentTermRef | None:
        term = terms.get(term_id) if term_id else None
        parent = terms.get(term.parent_term_id) if term and term.parent_term_id else None
        return _term_ref(term, parent)

    done = calibrations.get(unit.id)
    return EquipmentUnitOut(
        id=unit.id,
        asset_no=unit.asset_no,
        name=unit.name,
        ownership=unit.ownership,
        status=unit.status,
        vendor=unit.vendor,
        model=unit.model,
        serial_no=unit.serial_no,
        instrument_id=unit.instrument_id,
        instrument_type=ref(unit.type_term_id),
        instrument_term=ref(unit.instrument_term_id),
        org=workspaces.get(unit.workspace_id) if unit.workspace_id else None,
        lab=ref(unit.lab_term_id),
        location_detail=unit.location_detail,
        workspace_id=unit.workspace_id,
        owner_name=unit.owner_name,
        owner_contact=unit.owner_contact,
        commissioned_on=unit.commissioned_on,
        retired_on=unit.retired_on,
        attributes=dict(unit.attributes or {}),
        notes=unit.notes,
        last_calibrated_on=done[0] if done else None,
        calibration_valid_until=done[1] if done else None,
        part_count=parts.get(unit.id, 0),
        created_at=unit.created_at,
        updated_at=unit.updated_at,
    )


def _load_out(db: Session, units: list[EquipmentUnit]) -> list[EquipmentUnitOut]:
    ids = [unit.id for unit in units]
    term_ids = {
        one
        for unit in units
        for one in (unit.type_term_id, unit.instrument_term_id, unit.lab_term_id)
        if one is not None
    }
    terms = _terms_by_id(db, term_ids)
    workspaces = _workspace_refs(
        db, {unit.workspace_id for unit in units if unit.workspace_id}
    )
    calibrations = _calibration_map(db, ids)
    parts = _part_counts(db, ids)
    return [_to_out(unit, terms, workspaces, calibrations, parts) for unit in units]


def _get(db: Session, unit_id: uuid.UUID) -> EquipmentUnit:
    unit = db.get(EquipmentUnit, unit_id)
    if unit is None:
        raise NotFound("MNX-EQUIPMENT-0002", "그 장비를 찾을 수 없습니다.")
    return unit


def _workspace_id(db: Session, wanted: str | None) -> uuid.UUID | None:
    """slug 나 이름으로 부서를 찾는다. **없으면 만들지 않고 거절한다.**

    기준정보는 없으면 만들지만 부서는 권한이 붙는 자리다 — 폼이나 붙여넣기 한
    번으로 조직이 생기면 안 된다. 사람이 조직 화면에서 만든 뒤 다시 고른다.
    """
    if not wanted:
        return None
    found = db.scalars(
        select(Workspace).where(or_(Workspace.slug == wanted, Workspace.name == wanted))
    ).first()
    if found is None:
        raise AppError(
            "MNX-EQUIPMENT-0007",
            f"'{wanted}' 라는 부서가 없습니다. 조직 화면에서 먼저 만드세요 — "
            "여기서는 부서를 만들지 않습니다.",
            status=422,
        )
    return found.id


def _assert_asset_free(db: Session, key: str | None, *, skip: uuid.UUID | None = None) -> None:
    if key is None:
        return
    query = select(EquipmentUnit).where(EquipmentUnit.asset_key == key)
    if skip is not None:
        query = query.where(EquipmentUnit.id != skip)
    found = db.scalars(query).first()
    if found is not None:
        raise Conflict(
            "MNX-EQUIPMENT-0003",
            f"자산번호 '{found.asset_no}' 는 이미 '{found.name}' 에 붙어 있습니다.",
        )


# --- 목록 ---------------------------------------------------------------------


@router.get("/units", response_model=Page[EquipmentUnitOut])
def list_units(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ownership: str | None = Query(default=None),
    workspace_id: uuid.UUID | None = Query(default=None),
    lab_term_id: uuid.UUID | None = Query(default=None),
    type_term_id: uuid.UUID | None = Query(default=None),
    calibration_due: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[EquipmentUnitOut]:
    """**서버가 상한을 강제한다**(AGENTS.md) — `le=200`.

    폐기 장비는 기본으로 뺀다. 목록의 주 쓰임이 「지금 쓸 수 있는 것」 이라
    폐기까지 섞이면 세는 숫자가 틀린다 — `status=retired` 로 골라 보면 나온다.
    """
    query: Select[tuple[EquipmentUnit]] = select(EquipmentUnit)
    if status:
        query = query.where(EquipmentUnit.status == status)
    else:
        query = query.where(EquipmentUnit.status != "retired")
    if ownership:
        query = query.where(EquipmentUnit.ownership == ownership)
    for column, value in (
        (EquipmentUnit.workspace_id, workspace_id),
        (EquipmentUnit.lab_term_id, lab_term_id),
        (EquipmentUnit.type_term_id, type_term_id),
    ):
        if value is not None:
            query = query.where(column == value)

    if q:
        # **이름은 부분 일치, 자산번호는 정확 일치.** 사람은 「DMA」 를 치고
        # 「생기연 DMA」 를 찾는다. 자산번호는 정규화 열에 등호라 유니크 색인을 탄다.
        key = models.asset_key(q)
        branches: list[Any] = [
            EquipmentUnit.name.ilike(f"%{q}%"),
            EquipmentUnit.model.ilike(f"%{q}%"),
        ]
        if key:
            branches.append(EquipmentUnit.asset_key == key)
        query = query.where(or_(*branches))

    if calibration_due:
        # 유효기간이 지났거나 곧 끝나는 것. **기간이 없는 것은 여기 안 넣는다** —
        # 「모른다」 를 「만료」 로 읽으면 멀쩡한 장비가 목록을 채운다.
        edge = date.today() + timedelta(days=DUE_SOON_DAYS)
        recent = (
            select(
                EquipmentCalibration.unit_id,
                func.max(EquipmentCalibration.valid_until).label("valid_until"),
            )
            .group_by(EquipmentCalibration.unit_id)
            .subquery()
        )
        query = query.join(recent, recent.c.unit_id == EquipmentUnit.id).where(
            recent.c.valid_until <= edge
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    units = list(
        db.scalars(query.order_by(EquipmentUnit.name).limit(limit).offset(offset)).all()
    )
    return Page(items=_load_out(db, units), total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=EquipmentSummaryOut)
def summary(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> EquipmentSummaryOut:
    """상위 조직별·부서별·시험실별 현황.

    **상위 조직은 부서 트리를 타고 나온다** — 장비에 상위 조직을 따로 안 적기
    때문이다(`Workspace.parent_id`). 같은 답을 두 번 저장하면 언젠가 갈린다.
    """
    units = list(db.scalars(select(EquipmentUnit)).all())
    terms = _terms_by_id(db, {unit.lab_term_id for unit in units if unit.lab_term_id})
    workspaces = _workspace_refs(
        db, {unit.workspace_id for unit in units if unit.workspace_id}
    )
    edge = date.today() + timedelta(days=DUE_SOON_DAYS)
    calibrations = _calibration_map(db, [unit.id for unit in units])

    def blank(key: str, label: str) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "total": 0,
            "active": 0,
            "maintenance": 0,
            "idle": 0,
            "retired": 0,
            "external": 0,
            "calibration_due": 0,
        }

    buckets: dict[str, dict[str, dict[str, Any]]] = {"root": {}, "org": {}, "lab": {}}

    def add(axis: str, key: str, label: str, unit: EquipmentUnit) -> None:
        row = buckets[axis].setdefault(key, blank(key, label))
        row["total"] += 1
        row[unit.status] = row.get(unit.status, 0) + 1
        if unit.ownership == "external":
            row["external"] += 1
        done = calibrations.get(unit.id)
        if done and done[1] is not None and done[1] <= edge:
            row["calibration_due"] += 1

    for unit in units:
        org = workspaces.get(unit.workspace_id) if unit.workspace_id else None
        # 꼭대기가 자기 자신이면 `root_*` 가 비어 온다 — 그때는 그 부서가 곧 상위다.
        root_key = str(org.root_id or org.id) if org else ""
        root_label = (org.root_label or org.label) if org else "미지정"
        lab = terms.get(unit.lab_term_id) if unit.lab_term_id else None
        add("root", root_key, root_label, unit)
        add("org", str(org.id) if org else "", org.label if org else "미지정", unit)
        add("lab", str(lab.id) if lab else "", lab.value if lab else "미지정", unit)

    def rows(axis: str) -> list[EquipmentSummaryRow]:
        return [
            EquipmentSummaryRow(**row)
            for row in sorted(buckets[axis].values(), key=lambda one: -int(one["total"]))
        ]

    return EquipmentSummaryOut(
        total=len(units),
        by_root_org=rows("root"),
        by_org=rows("org"),
        by_lab=rows("lab"),
    )


@router.get("/units/{unit_id}", response_model=EquipmentUnitOut)
def get_unit(
    unit_id: uuid.UUID,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentUnitOut:
    return _load_out(db, [_get(db, unit_id)])[0]


# --- 쓰기 ---------------------------------------------------------------------


@router.post("/units", response_model=EquipmentUnitOut, status_code=201)
def create_unit(
    payload: EquipmentUnitCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentUnitOut:
    _require_manager(db, user)
    key = models.asset_key(payload.asset_no)
    _assert_asset_free(db, key)
    data = payload.model_dump()
    names = {field: data.pop(field) for field in BOUND_FIELDS}
    data["workspace_id"] = _workspace_id(db, data.pop("workspace"))
    unit = EquipmentUnit(**data, asset_key=key)
    db.add(unit)
    # **기준정보는 기계가 해석한다** — 없는 이름은 만들고, FK 와 문자열을 함께
    # 채우고, 사용수까지 옮긴다. 라우트가 직접 하면 축마다 같은 코드가 생긴다.
    vocabulary_services.apply_bindings(
        db,
        unit,
        vocabulary_services.EQUIPMENT_BINDINGS,
        names,
        created_by_id=user.id,
    )
    db.commit()
    db.refresh(unit)
    return _load_out(db, [unit])[0]


@router.patch("/units/{unit_id}", response_model=EquipmentUnitOut)
def update_unit(
    unit_id: uuid.UUID,
    payload: EquipmentUnitUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentUnitOut:
    """**보낸 것만 바꾼다.** 안 보낸 것과 비운 것을 구별한다(AGENTS.md)."""
    _require_manager(db, user)
    unit = _get(db, unit_id)
    data = payload.model_dump(exclude_unset=True)
    if "asset_no" in data:
        key = models.asset_key(data["asset_no"])
        _assert_asset_free(db, key, skip=unit.id)
        unit.asset_key = key
    # **보낸 것만 넘긴다.** `apply_bindings` 는 `values` 에 없는 필드를 안 건드린다 —
    # 그것이 「안 보낸 것」 과 「비운 것」 의 구별이다.
    names = {field: data.pop(field) for field in BOUND_FIELDS if field in data}
    if "workspace" in data:
        unit.workspace_id = _workspace_id(db, data.pop("workspace"))
    for field, value in data.items():
        setattr(unit, field, value)
    if names:
        vocabulary_services.apply_bindings(
            db,
            unit,
            vocabulary_services.EQUIPMENT_BINDINGS,
            names,
            created_by_id=user.id,
        )
    db.commit()
    db.refresh(unit)
    return _load_out(db, [unit])[0]


@router.delete("/units/{unit_id}", status_code=204)
def delete_unit(
    unit_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """**가리키는 것이 있으면 못 지운다.**

    부속·교정은 함께 지워진다(장비를 떠나 살지 않는다). 그 밖의 참조가 있으면
    거절하고 무엇이 가리키는지 말해 준다 — 폐기하려는 것이면 `status='retired'` 다.
    """
    _require_manager(db, user)
    unit = _get(db, unit_id)
    found = [
        one
        for one in dependents.references_to(db, table="equipment_units", pk=unit.id)
        if one.table not in {"equipment_parts", "equipment_calibrations"}
    ]
    blocking = dependents.blocking(found)
    if blocking:
        raise Conflict(
            "MNX-EQUIPMENT-0004",
            "이 장비를 가리키는 것이 있어 지울 수 없습니다 — "
            f"{dependents.describe(blocking)}. "
            "쓰지 않는 장비라면 상태를 '폐기' 로 바꾸세요.",
        )
    audit.record(
        db,
        action=audit.EQUIPMENT_DELETED,
        actor=user,
        target_table="equipment_units",
        target_id=unit.id,
        target_label=f"{unit.name} ({unit.asset_no or '자산번호 없음'})",
        workspace_id=unit.workspace_id,
    )
    db.delete(unit)
    db.commit()


# --- 부속 ---------------------------------------------------------------------


@router.get("/units/{unit_id}/parts", response_model=list[EquipmentPartOut])
def list_parts(
    unit_id: uuid.UUID,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EquipmentPartOut]:
    _get(db, unit_id)
    rows = db.scalars(
        select(EquipmentPart)
        .where(EquipmentPart.unit_id == unit_id)
        .order_by(EquipmentPart.kind)
    ).all()
    return [EquipmentPartOut.model_validate(row) for row in rows]


@router.post("/units/{unit_id}/parts", response_model=EquipmentPartOut, status_code=201)
def create_part(
    unit_id: uuid.UUID,
    payload: EquipmentPartCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentPartOut:
    _require_manager(db, user)
    _get(db, unit_id)
    part = EquipmentPart(unit_id=unit_id, **payload.model_dump())
    db.add(part)
    db.commit()
    db.refresh(part)
    return EquipmentPartOut.model_validate(part)


@router.patch("/parts/{part_id}", response_model=EquipmentPartOut)
def update_part(
    part_id: uuid.UUID,
    payload: EquipmentPartUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentPartOut:
    _require_manager(db, user)
    part = db.get(EquipmentPart, part_id)
    if part is None:
        raise NotFound("MNX-EQUIPMENT-0005", "그 부속을 찾을 수 없습니다.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(part, field, value)
    db.commit()
    db.refresh(part)
    return EquipmentPartOut.model_validate(part)


@router.delete("/parts/{part_id}", status_code=204)
def delete_part(
    part_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_manager(db, user)
    part = db.get(EquipmentPart, part_id)
    if part is None:
        raise NotFound("MNX-EQUIPMENT-0005", "그 부속을 찾을 수 없습니다.")
    db.delete(part)
    db.commit()


# --- 교정 ---------------------------------------------------------------------


@router.get("/units/{unit_id}/calibrations", response_model=list[EquipmentCalibrationOut])
def list_calibrations(
    unit_id: uuid.UUID,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EquipmentCalibrationOut]:
    """최근 것이 위로. **이력이라 지우지 않는다** — 고칠 일이 있으면 한 줄 더 넣는다."""
    _get(db, unit_id)
    rows = db.scalars(
        select(EquipmentCalibration)
        .where(EquipmentCalibration.unit_id == unit_id)
        .order_by(EquipmentCalibration.performed_on.desc())
    ).all()
    return [EquipmentCalibrationOut.model_validate(row) for row in rows]


@router.post(
    "/units/{unit_id}/calibrations", response_model=EquipmentCalibrationOut, status_code=201
)
def create_calibration(
    unit_id: uuid.UUID,
    payload: EquipmentCalibrationCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentCalibrationOut:
    _require_manager(db, user)
    _get(db, unit_id)
    if payload.valid_until and payload.valid_until < payload.performed_on:
        raise AppError(
            "MNX-EQUIPMENT-0006",
            "유효기간이 교정일보다 앞설 수 없습니다.",
            status=422,
        )
    row = EquipmentCalibration(unit_id=unit_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return EquipmentCalibrationOut.model_validate(row)


# --- 붙여넣기 일괄 등록 --------------------------------------------------------


@router.post("/units/bulk", response_model=EquipmentBulkResult)
def bulk_create(
    payload: EquipmentBulkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EquipmentBulkResult:
    """엑셀에서 복사해 붙인 표를 받는다 — **드라이런이 기본이다.**

    기준정보는 **이름으로 온다**(사람이 엑셀에 id 를 적지 않는다). 없는 이름은
    새 값이 되는데, 그것이 이 화면에서 가장 흔한 사고다(오타 하나가 새 조직을
    만든다). 그래서 드라이런이 **무엇이 새로 생기는지 먼저 보여 준다.**
    """
    _require_manager(db, user)
    axes = {
        one.field: vocabulary_services.get_vocabulary(db, one.slug)
        for one in vocabulary_services.EQUIPMENT_BINDINGS
    }
    results: list[EquipmentBulkRowResult] = []
    created = skipped = errors = 0
    seen: set[str] = set()

    for index, row in enumerate(payload.rows):
        fresh: list[str] = []
        try:
            key = models.asset_key(row.asset_no)
            if key and (
                key in seen
                or db.scalars(
                    select(EquipmentUnit).where(EquipmentUnit.asset_key == key)
                ).first()
            ):
                results.append(
                    EquipmentBulkRowResult(
                        index=index,
                        name=row.name,
                        outcome="skip",
                        reason=f"자산번호 '{row.asset_no}' 가 이미 있습니다.",
                    )
                )
                skipped += 1
                continue

            values = row.model_dump()
            names = {field: values.pop(field) for field in BOUND_FIELDS}
            values["workspace_id"] = _workspace_id(db, values.pop("workspace"))
            # **새로 생길 값을 먼저 센다.** 드라이런이 보여 줄 것이 이것이고,
            # 오타 하나가 새 조직을 만드는 사고를 여기서 막는다.
            for field, name in names.items():
                if name and vocabulary_services.resolve(db, axes[field], name) is None:
                    fresh.append(f"{axes[field].label}: {name}")

            if payload.dry_run:
                results.append(
                    EquipmentBulkRowResult(
                        index=index, name=row.name, outcome="create", new_terms=fresh
                    )
                )
                created += 1
                continue

            unit = EquipmentUnit(**values, asset_key=key)
            db.add(unit)
            vocabulary_services.apply_bindings(
                db,
                unit,
                vocabulary_services.EQUIPMENT_BINDINGS,
                names,
                created_by_id=user.id,
            )
            db.flush()
            if key:
                seen.add(key)
            results.append(
                EquipmentBulkRowResult(
                    index=index,
                    name=row.name,
                    outcome="create",
                    unit_id=unit.id,
                    new_terms=fresh,
                )
            )
            created += 1
        except AppError as refused:
            db.rollback()
            results.append(
                EquipmentBulkRowResult(
                    index=index, name=row.name, outcome="error", reason=refused.message
                )
            )
            errors += 1

    if payload.dry_run or errors:
        # **하나라도 걸리면 아무것도 안 쓴다.** 절반만 들어간 표는 사람이 무엇을
        # 다시 붙여야 하는지 알 수 없다 — 이관기와 같은 규율이다.
        db.rollback()
    else:
        db.commit()
    return EquipmentBulkResult(
        dry_run=payload.dry_run or errors > 0,
        created=created,
        skipped=skipped,
        errors=errors,
        rows=results,
    )
