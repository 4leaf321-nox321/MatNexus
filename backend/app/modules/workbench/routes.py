"""워크벤치 — 작업과 바구니(ADR 0024·0025).

**여기에 도메인이 없다.** 담고 · 빼고 · 진행을 적어 두는 것이 전부다. 무엇을 어떻게
처리하는지는 각 도메인의 화면과 API 가 한다 — 워크벤치는 그것들을 잇는 자리이고, 그
선이 흐려지면 같은 일을 하는 자리가 둘이 된다(ADR 0024 의 경계).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.workbench import services
from app.modules.workbench.models import WorkbenchItem, WorkbenchRun
from app.modules.workbench.schemas import (
    ItemAddRequest,
    ItemOut,
    RunCreateRequest,
    RunDetailOut,
    RunOut,
    RunPatchRequest,
)
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound

router = APIRouter(prefix="/workbench", tags=["workbench"])


def _run_or_404(db: Session, user: User, run_id: uuid.UUID) -> WorkbenchRun:
    """**부서 안에서 공유한다.** 만든 사람만 열 수 있으면 「어제 하던 것을 오늘
    다른 사람이」 가 안 된다(ADR 0025)."""
    found = db.get(WorkbenchRun, run_id)
    if found is None:
        raise NotFound("MNX-WORKBENCH-0001", "작업을 찾을 수 없습니다.")
    if not user.is_system_admin and found.workspace_id not in permissions.my_workspace_ids(
        db, user
    ):
        raise NotFound("MNX-WORKBENCH-0001", "작업을 찾을 수 없습니다.")
    return found


def _count(db: Session, run_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(WorkbenchItem)
            .where(WorkbenchItem.run_id == run_id)
        )
        or 0
    )


def _out(db: Session, run: WorkbenchRun) -> RunOut:
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
    )


def _detail(db: Session, run: WorkbenchRun) -> RunDetailOut:
    items = list(
        db.scalars(
            select(WorkbenchItem)
            .where(WorkbenchItem.run_id == run.id)
            .order_by(WorkbenchItem.added_at, WorkbenchItem.id)
        )
    )
    return RunDetailOut(**_out(db, run).model_dump(), items=services.resolve(db, items))


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    status: str | None = Query(default=None, pattern="^(running|finished|dropped)$"),
    limit: int = Query(default=20, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[RunOut]:
    """내 부서의 작업들. **진행 중인 것이 먼저다** — 「이어서 하기」 가 이 목록이다."""
    query = select(WorkbenchRun).order_by(WorkbenchRun.updated_at.desc()).limit(limit)
    if not user.is_system_admin:
        query = query.where(
            WorkbenchRun.workspace_id.in_(permissions.my_workspace_ids(db, user))
        )
    if status:
        query = query.where(WorkbenchRun.status == status)
    return [_out(db, run) for run in db.scalars(query)]


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
    return _detail(db, run)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunDetailOut:
    return _detail(db, _run_or_404(db, user, run_id))


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
    run = _run_or_404(db, user, run_id)
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
    return _detail(db, run)


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
    run = _run_or_404(db, user, run_id)
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
    # 담으면 목록에서 위로 올라와야 한다 — 「이어서 하기」 가 최근 순이다.
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
    run = _run_or_404(db, user, run_id)
    item = db.get(WorkbenchItem, item_id)
    if item is None or item.run_id != run.id:
        raise NotFound("MNX-WORKBENCH-0003", "담긴 것을 찾을 수 없습니다.")
    db.delete(item)
    run.updated_at = datetime.now(UTC)
    db.commit()
