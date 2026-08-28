"""장비 커넥터 API. 계약의 정본은 MatPylon 의 `matpylon-openapi.yaml` 이다.

## 인증은 PAT 로

에이전트는 사람이 아니다. 개인 액세스 토큰(ADR 0002)이 그대로 통한다 — `current_user`
가 PAT 를 풀어 주인 계정을 돌려주므로, 권한은 **그 사람의** 부서 소속으로 본다.
남의 부서에 파일을 밀어 넣을 수 없어야 한다.

## 파일은 마지막 파트

`UploadFile` 이 스트리밍으로 받는다. 앞선 폼 필드로 커넥터·해시를 먼저 확인하고
파일은 한 번만 읽는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.pipelines import services
from app.modules.pipelines.models import (
    INBOX_STATUSES,
    PipelineConnector,
    PipelineInboxItem,
)
from app.modules.pipelines.schemas import (
    SHA256_PATTERN,
    SOURCE_KEY_PATTERN,
    AssignIn,
    CandidateOut,
    ConnectorCreate,
    ConnectorOut,
    ConnectorUpdate,
    DiscardIn,
    HeartbeatIn,
    HeartbeatOut,
    Hints,
    InboxItemDetail,
    InboxItemOut,
    ReferenceTree,
    ResolveIn,
    ResolveOut,
)
from app.modules.tests.models import TestType
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, Forbidden, NotFound
from app.shared.pagination import Page, clamp_limit

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# --- 커넥터 ---------------------------------------------------------------------


def _connector_out(
    row: PipelineConnector, *, workspace_name: str | None, waiting: int
) -> ConnectorOut:
    pending, failed = services.heartbeat_totals(row)
    return ConnectorOut(
        id=row.id,
        name=row.name,
        hostname=row.hostname,
        workspace_id=row.workspace_id,
        workspace_name=workspace_name,
        is_active=row.is_active,
        app_version=row.app_version,
        last_seen_at=row.last_seen_at,
        next_run_at=row.next_run_at,
        pending=pending,
        failed=failed,
        waiting=waiting,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
    )


def _workspace_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {w.id: w.name for w in db.scalars(select(Workspace).where(Workspace.id.in_(ids)))}


def _connector_for_edit(db: Session, user: User, connector_id: uuid.UUID) -> PipelineConnector:
    row = services.get_connector(db, connector_id, active_only=False)
    workspace = db.get(Workspace, row.workspace_id)
    if workspace is None:
        raise NotFound("MNX-PIPE-0001", "커넥터의 부서가 없습니다.")
    permissions.require_manager(db, workspace=workspace, user=user)
    return row


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
def create_connector(
    body: ConnectorCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ConnectorOut:
    """장비 PC 하나를 등록한다. 같은 호스트면 기존 것을 돌려준다(201 그대로)."""
    workspace = db.get(Workspace, body.workspace_id)
    if workspace is None:
        raise NotFound("MNX-WORKSPACES-0001", "부서를 찾을 수 없습니다.")
    if not user.is_system_admin and (
        permissions.membership_of(db, workspace_id=workspace.id, user_id=user.id) is None
    ):
        raise Forbidden("MNX-PIPE-0005", "이 부서의 구성원이 아닙니다.")
    row, _created = services.register_connector(
        db, user=user, workspace=workspace, name=body.name, hostname=body.hostname
    )
    db.commit()
    return _connector_out(row, workspace_name=workspace.name, waiting=0)


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[ConnectorOut]:
    rows = list(db.scalars(services.visible_connectors(db, user)))
    names = _workspace_names(db, {r.workspace_id for r in rows})
    waiting = services.waiting_counts(db, [r.id for r in rows])
    return [
        _connector_out(
            r, workspace_name=names.get(r.workspace_id), waiting=waiting.get(r.id, 0)
        )
        for r in rows
    ]


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
def update_connector(
    connector_id: uuid.UUID,
    body: ConnectorUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ConnectorOut:
    row = _connector_for_edit(db, user, connector_id)
    given = body.model_dump(exclude_unset=True)
    if "name" in given and given["name"] is not None:
        row.name = given["name"]
    if "is_active" in given and given["is_active"] is not None:
        row.is_active = given["is_active"]
    db.commit()
    names = _workspace_names(db, {row.workspace_id})
    return _connector_out(
        row,
        workspace_name=names.get(row.workspace_id),
        waiting=services.waiting_counts(db, [row.id]).get(row.id, 0),
    )


@router.post("/connectors/{connector_id}/heartbeat", response_model=HeartbeatOut)
def post_heartbeat(
    connector_id: uuid.UUID,
    body: HeartbeatIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> HeartbeatOut:
    connector = services.get_connector(db, connector_id)
    _require_member(db, user, connector.workspace_id)
    services.heartbeat(
        db,
        connector,
        app_version=body.app_version,
        sources=[s.model_dump(mode="json") for s in body.sources],
        next_run_at=body.next_run_at,
    )
    db.commit()
    return HeartbeatOut(
        server_time=datetime.now(UTC), upload_limit_bytes=get_settings().max_upload_bytes
    )


def _require_member(db: Session, user: User, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound("MNX-PIPE-0001", "커넥터의 부서가 없습니다.")
    if not user.is_system_admin and (
        permissions.membership_of(db, workspace_id=workspace.id, user_id=user.id) is None
    ):
        raise Forbidden("MNX-PIPE-0005", "이 부서의 구성원이 아닙니다.")
    return workspace


# --- 규칙 편집기가 묻는다 ----------------------------------------------------------


@router.post("/resolve", response_model=ResolveOut)
def resolve_hints(
    body: ResolveIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResolveOut:
    """힌트 → 「붙나 / 왜 안 붙나」. 워커와 같은 함수. 아무것도 만들지 않는다."""
    _require_member(db, user, body.workspace_id)
    results = services.resolve(
        db, workspace_id=body.workspace_id, hints=[h.compact() for h in body.hints]
    )
    return ResolveOut.model_validate({"results": results})


@router.get("/reference", response_model=ReferenceTree)
def reference(
    workspace_id: uuid.UUID = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReferenceTree:
    """재료 → 시료 → 시편 이름 트리. 규칙 편집기의 참조 패널. 이름만, 편집 안 함."""
    _require_member(db, user, workspace_id)
    return ReferenceTree.model_validate(services.reference_tree(db, workspace_id=workspace_id))


# --- 수집함 ---------------------------------------------------------------------


def _parse_hints(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        raise AppError("MNX-PIPE-0006", "hints 가 JSON 이 아닙니다.") from None
    if not isinstance(data, dict):
        raise AppError("MNX-PIPE-0006", "hints 는 JSON 객체여야 합니다.")
    try:
        return Hints.model_validate(data).compact()
    except ValidationError:
        raise AppError("MNX-PIPE-0006", "hints 의 값은 문자열이어야 합니다.") from None


@router.post("/inbox", response_model=InboxItemOut, status_code=202)
def upload_inbox(
    connector_id: uuid.UUID = Form(...),
    source_key: str = Form(..., pattern=SOURCE_KEY_PATTERN),
    client_sha256: str = Form(..., pattern=SHA256_PATTERN),
    client_path: str = Form(...),
    mtime: datetime = Form(...),
    hints: str = Form(default="{}"),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InboxItemOut:
    """원본을 받아 수집함에 넣고 202 를 준다 — 파싱은 워커가 한다."""
    connector = services.get_connector(db, connector_id)
    _require_member(db, user, connector.workspace_id)
    given = _parse_hints(hints)
    try:
        item = services.receive(
            db,
            connector=connector,
            source_key=source_key,
            filename=file.filename or "upload.dat",
            stream=file.file,
            client_sha256=client_sha256.lower(),
            client_path=client_path,
            mtime=mtime,
            hints=given,
            max_bytes=get_settings().max_upload_bytes,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return _item_out(item, services.context(db, [item]))


def _item_out(item: PipelineInboxItem, ctx: dict[str, dict[uuid.UUID, Any]]) -> InboxItemOut:
    return InboxItemOut(**_item_fields(item, ctx))


def _item_fields(
    item: PipelineInboxItem, ctx: dict[str, dict[uuid.UUID, Any]]
) -> dict[str, Any]:
    connector = ctx["connectors"].get(item.connector_id)
    test_type = ctx["types"].get(item.test_type_id) if item.test_type_id else None
    profile = ctx["profiles"].get(item.profile_id) if item.profile_id else None
    run = ctx["runs"].get(item.test_run_id) if item.test_run_id else None
    return {
        "id": item.id,
        "status": item.status,
        "connector_id": item.connector_id,
        "connector_name": connector.name if connector else None,
        "source_key": item.source_key,
        "filename": item.filename,
        "size": item.size,
        "sha256": item.sha256,
        "hints": item.hints,
        "test_type_key": test_type.key if test_type else None,
        "test_type_label": test_type.label if test_type else None,
        "profile_key": profile.key if profile else None,
        "test_run_id": item.test_run_id,
        "test_run_name": run.record_name if run else None,
        "error": item.error,
        "candidate_count": len(item.candidates),
        "received_at": item.received_at,
        "resolved_at": item.resolved_at,
    }


def _visible_items(db: Session, user: User) -> Any:
    query = select(PipelineInboxItem).join(
        PipelineConnector, PipelineConnector.id == PipelineInboxItem.connector_id
    )
    if not user.is_system_admin:
        mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        query = query.where(PipelineConnector.workspace_id.in_(mine))
    return query


@router.get("/inbox", response_model=Page[InboxItemOut])
def list_inbox(
    status: str | None = Query(default=None),
    connector_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[InboxItemOut]:
    if status is not None and status not in INBOX_STATUSES:
        raise AppError(
            "MNX-PIPE-0010",
            f"모르는 상태입니다: {status}. 고를 수 있는 것: {', '.join(INBOX_STATUSES)}",
            status=422,
        )
    query = _visible_items(db, user)
    if status is not None:
        query = query.where(PipelineInboxItem.status == status)
    if connector_id is not None:
        query = query.where(PipelineInboxItem.connector_id == connector_id)
    size = clamp_limit(limit)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    items = list(
        db.scalars(
            query.order_by(PipelineInboxItem.received_at.desc(), PipelineInboxItem.id)
            .limit(size)
            .offset(offset)
        )
    )
    ctx = services.context(db, items)
    return Page(
        items=[_item_out(i, ctx) for i in items], total=total, limit=size, offset=offset
    )


def _get_item(db: Session, user: User, item_id: uuid.UUID) -> PipelineInboxItem:
    item: PipelineInboxItem | None = db.scalar(
        _visible_items(db, user).where(PipelineInboxItem.id == item_id)
    )
    if item is None:
        raise NotFound("MNX-PIPE-0011", "수집함 항목이 없습니다.")
    return item


def _detail(db: Session, item: PipelineInboxItem) -> InboxItemDetail:
    fields = _item_fields(item, services.context(db, [item]))
    return InboxItemDetail(
        **fields,
        client_path=item.client_path,
        mtime=item.mtime,
        candidates=[CandidateOut(**c) for c in item.candidates],
        summary=item.summary,
        discard_reason=item.discard_reason,
    )


@router.get("/inbox/{item_id}", response_model=InboxItemDetail)
def get_item(
    item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> InboxItemDetail:
    return _detail(db, _get_item(db, user, item_id))


def _manager_of_item(db: Session, user: User, item: PipelineInboxItem) -> None:
    connector = db.get(PipelineConnector, item.connector_id)
    workspace = db.get(Workspace, connector.workspace_id) if connector else None
    if workspace is None:
        raise NotFound("MNX-PIPE-0001", "커넥터의 부서가 없습니다.")
    permissions.require_manager(db, workspace=workspace, user=user)


@router.post("/inbox/{item_id}/assign", response_model=InboxItemDetail)
def assign_item(
    item_id: uuid.UUID,
    body: AssignIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InboxItemDetail:
    """사람이 시편을 붙인다 → 시험이 된다."""
    item = _get_item(db, user, item_id)
    _manager_of_item(db, user, item)
    specimen = permissions.visible_specimen(db, user, body.specimen_id)
    if body.test_type:
        test_type = db.scalar(select(TestType).where(TestType.key == body.test_type))
        if test_type is None or not test_type.is_active:
            raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {body.test_type}")
    else:
        test_type = db.get(TestType, item.test_type_id) if item.test_type_id else None
        if test_type is None:
            raise AppError(
                "MNX-PIPE-0012",
                "감지된 시험 종류가 없습니다. 종류를 골라 주세요.",
                status=422,
            )
    services.register(db, item, specimen=specimen, test_type=test_type, actor=user)
    db.commit()
    return _detail(db, item)


@router.post("/inbox/{item_id}/discard", status_code=204)
def discard_item(
    item_id: uuid.UUID,
    body: DiscardIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    item = _get_item(db, user, item_id)
    _manager_of_item(db, user, item)
    services.discard(db, item, actor=user, reason=body.reason)
    db.commit()
    return Response(status_code=204)


@router.post("/inbox/{item_id}/retry", response_model=InboxItemOut, status_code=202)
def retry_item(
    item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> InboxItemOut:
    """프로파일을 고친 뒤 다시 파싱."""
    item = _get_item(db, user, item_id)
    _manager_of_item(db, user, item)
    services.retry(db, item)
    db.commit()
    return _item_out(item, services.context(db, [item]))
