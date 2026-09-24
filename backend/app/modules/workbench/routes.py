"""워크벤치 — 작업과 바구니(ADR 0024·0025).

**여기에 도메인이 없다.** 담고 · 빼고 · 진행을 적어 두는 것이 전부다. 무엇을 어떻게
처리하는지는 각 도메인의 화면과 API 가 한다 — 워크벤치는 그것들을 잇는 자리이고, 그
선이 흐려지면 같은 일을 하는 자리가 둘이 된다(ADR 0024 의 경계).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.workbench import services
from app.modules.workbench.models import BomAlias, WorkbenchItem, WorkbenchRun
from app.modules.workbench.schemas import (
    BomAliasIn,
    BomAliasLookupOut,
    BomAliasLookupRequest,
    BomAliasOut,
    ItemAddRequest,
    ItemOut,
    RunCreateRequest,
    RunDetailOut,
    RunOut,
    RunPatchRequest,
)
from app.shared import permissions
from app.shared.access import AccessBook, EditAccessOut, access_of
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from app.shared.text import clean, compare_key

router = APIRouter(prefix="/workbench", tags=["workbench"])


def _run_or_404(db: Session, run_id: uuid.UUID) -> WorkbenchRun:
    """작업 하나. **누구나 연다**(ADR 0035 3단계).

    전에는 그 부서 멤버가 아니면 「없다」 였다 — 보기와 고치기가 한 판정이라, 남의
    부서 사람에게 작업 주소를 보내면 있는 작업이 없다고 떴다. 고치는 것은 따로 본다
    (`_editable_run`)."""
    found = db.get(WorkbenchRun, run_id)
    if found is None:
        raise NotFound("MNX-WORKBENCH-0001", "작업을 찾을 수 없습니다.")
    return found


def _editable_run(db: Session, user: User, run_id: uuid.UUID) -> WorkbenchRun:
    """고칠 작업 — **그 부서 사람 · 시작한 사람 · 자료 관리자**(`permissions.require_edit`).

    부서 안에서 함께 미는 것이 작업의 뜻이다(ADR 0025). 그 밖의 사람은 보기만 한다 —
    담긴 것을 빼거나 진행을 옮기면, 그 부서 사람이 이어 할 때 무엇이 바뀌었는지 모른다.
    """
    run = _run_or_404(db, run_id)
    permissions.require_edit(db, user, run, code="MNX-WORKBENCH-0004")
    return run


def _count(db: Session, run_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(WorkbenchItem)
            .where(WorkbenchItem.run_id == run_id)
        )
        or 0
    )


def _out(db: Session, run: WorkbenchRun, access: EditAccessOut | None = None) -> RunOut:
    return RunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        owner_id=run.owner_id,
        owner_name=services.owner_name(db, run.owner_id),
        workflow_key=run.workflow_key,
        title=run.title,
        status=run.status,
        steps=dict(run.steps or {}),
        note=run.note,
        item_count=_count(db, run.id),
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished_at=run.finished_at,
        access=access,
    )


def _detail(db: Session, run: WorkbenchRun, user: User) -> RunDetailOut:
    items = list(
        db.scalars(
            select(WorkbenchItem)
            .where(WorkbenchItem.run_id == run.id)
            .order_by(WorkbenchItem.added_at, WorkbenchItem.id)
        )
    )
    return RunDetailOut(
        **_out(db, run, access_of(db, user, run)).model_dump(),
        items=services.resolve(db, items),
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    status: str | None = Query(default=None, pattern="^(running|finished|dropped)$"),
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    limit: int = Query(default=20, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[RunOut]:
    """작업들. **진행 중인 것이 먼저다** — 「계속」 이 이 목록이다.

    `scope=mine`(기본)은 **내가 이어 할 수 있는 것** — 내 부서의 작업과 내가 시작한 것.
    `all` 은 전사다(ADR 0035 3단계 — 보기는 전원). 기본을 좁히는 이유는 이 목록이
    「계속」 이라서다: 남의 부서 작업이 섞이면 이어 할 것이 안 보인다.
    """
    query = select(WorkbenchRun).order_by(WorkbenchRun.updated_at.desc()).limit(limit)
    if scope == "mine":
        query = query.where(
            or_(
                WorkbenchRun.workspace_id.in_(permissions.my_workspace_ids(db, user)),
                WorkbenchRun.owner_id == user.id,
            )
        )
    if status:
        query = query.where(WorkbenchRun.status == status)
    runs = list(db.scalars(query))
    book = AccessBook(db, user).prime(runs)
    return [_out(db, run, book.of(run)) for run in runs]


@router.post("/runs", response_model=RunDetailOut, status_code=201)
def create_run(
    payload: RunCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunDetailOut:
    """작업을 시작한다. **부서가 있어야 한다** — 공유의 단위가 부서다."""
    if user.home_workspace_id is None:
        raise AppError(
            "MNX-WORKBENCH-0002",
            "소속 부서가 없어 작업을 시작할 수 없습니다. 관리자에게 문의하세요.",
            status=422,
        )
    run = WorkbenchRun(
        workspace_id=user.home_workspace_id,
        owner_id=user.id,
        workflow_key=payload.workflow_key,
        title=payload.title,
        note=payload.note,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _detail(db, run, user)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunDetailOut:
    return _detail(db, _run_or_404(db, run_id), user)


@router.patch("/runs/{run_id}", response_model=RunDetailOut)
def patch_run(
    run_id: uuid.UUID,
    payload: RunPatchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunDetailOut:
    """이름·상태·진행을 고친다.

    **안 보낸 것은 안 고친다.** 진행만 밀었는데 제목이 지워지면 사람은 무엇이
    지웠는지 모른다.
    """
    run = _editable_run(db, user, run_id)
    if payload.title is not None:
        run.title = payload.title
    if payload.note is not None:
        run.note = payload.note
    if payload.steps is not None:
        run.steps = payload.steps
    if payload.status is not None and payload.status != run.status:
        run.status = payload.status
        # **끝낸 시각을 남긴다.** 「그때 무엇을 묶었나」 가 기록이고, 언제 끝냈는지가
        # 그 기록의 절반이다(ADR 0025 — 끝낸 작업을 안 지운다).
        run.finished_at = datetime.now(UTC) if payload.status != "running" else None
    db.commit()
    db.refresh(run)
    return _detail(db, run, user)


@router.post("/runs/{run_id}/items", response_model=list[ItemOut], status_code=201)
def add_items(
    run_id: uuid.UUID,
    payload: ItemAddRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ItemOut]:
    """담는다. **이미 담긴 것은 조용히 넘어간다** — 두 번 담기는 실수이지 오류가
    아니고, 여럿을 한 번에 담을 때 하나가 겹쳤다고 전부를 실패시키면 사람은 무엇이
    들어갔는지 모른다."""
    run = _editable_run(db, user, run_id)
    already = set(
        db.scalars(
            select(WorkbenchItem.target_id).where(
                WorkbenchItem.run_id == run.id, WorkbenchItem.kind == payload.kind
            )
        )
    )
    made: list[WorkbenchItem] = []
    for target_id in payload.target_ids:
        if target_id in already:
            continue
        item = WorkbenchItem(
            run_id=run.id, kind=payload.kind, target_id=target_id, note=payload.note
        )
        db.add(item)
        made.append(item)
        already.add(target_id)
    # 담으면 목록에서 위로 올라와야 한다 — 「계속」 이 최근 순이다.
    run.updated_at = datetime.now(UTC)
    db.commit()
    for item in made:
        db.refresh(item)
    return services.resolve(db, made)


@router.delete("/runs/{run_id}/items/{item_id}", status_code=204)
def remove_item(
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    run = _editable_run(db, user, run_id)
    item = db.get(WorkbenchItem, item_id)
    if item is None or item.run_id != run.id:
        raise NotFound("MNX-WORKBENCH-0003", "담긴 것을 찾을 수 없습니다.")
    db.delete(item)
    run.updated_at = datetime.now(UTC)
    db.commit()


# ── BOM 매칭 기억 ──────────────────────────────────────────────────────────────
#
# 혼합 덱(BOM 붙여넣기)의 「한 번 고른 매칭」 저장소다. 도메인이 아니라 기억이라
# 워크벤치에 산다 — 매칭 후보를 내는 것은 재료·카탈로그의 기존 API 이고, 화면이
# 그것들을 조립한다(ADR 0024).


def _alias_out(row: BomAlias) -> BomAliasOut:
    return BomAliasOut(
        query=row.query,
        material_id=row.material_id,
        catalog_material_id=row.catalog_material_id,
    )


@router.post("/bom-aliases/lookup", response_model=BomAliasLookupOut)
def bom_alias_lookup(
    payload: BomAliasLookupRequest,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BomAliasLookupOut:
    keys = [compare_key(clean(one) or "") for one in payload.queries]
    rows = {
        row.normalized: row
        for row in db.scalars(select(BomAlias).where(BomAlias.normalized.in_(keys)))
    }
    return BomAliasLookupOut(
        found=[(_alias_out(rows[key]) if key in rows else None) for key in keys]
    )


@router.put("/bom-aliases", response_model=BomAliasOut)
def bom_alias_put(
    payload: BomAliasIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BomAliasOut:
    """기억 하나를 넣거나 갱신한다 — 마지막 판단이 이긴다.

    사내·문헌 어느 쪽도 없으면 **기억을 지운다**(그 이름은 다시 물어보라는 뜻).
    """
    cleaned = clean(payload.query)
    if cleaned is None:
        raise AppError("MNX-WORKBENCH-0010", "빈 이름은 기억할 수 없습니다.", status=422)
    key = compare_key(cleaned)
    row = db.scalar(select(BomAlias).where(BomAlias.normalized == key))
    if payload.material_id is None and payload.catalog_material_id is None:
        if row is not None:
            db.delete(row)
            db.commit()
        return BomAliasOut(query=cleaned, material_id=None, catalog_material_id=None)
    if row is None:
        row = BomAlias(normalized=key, query=cleaned, created_by_id=user.id)
        db.add(row)
    row.query = cleaned
    row.material_id = payload.material_id
    row.catalog_material_id = payload.catalog_material_id
    db.commit()
    return _alias_out(row)
