"""SP 코어 온톨로지 — 받은 것 보기 · 받기 부르기 · 대조 · 잇기 · 끊기(ADR 0063).

    GET  /sp-core/status                     설정 · 타입마다 받은 수 · 최근 실행 · 연결 수
    POST /sp-core/sync                       받기를 지금 부른다(워커가 돈다) — 자료 관리자
    GET  /sp-core/objects                    받은 객체 찾기(타입 · 이름 · key)
    GET  /sp-core/objects/{type}/{key}       객체 하나 — 선 · 연결과 함께
    GET  /sp-core/match                      한 SP 타입 ↔ 한 대상(기준정보 축 · 물성 · 물성군
    · 분야) 대조
    GET  /sp-core/links                      연결 목록
    GET  /sp-core/linked                     한 대상 종류(기준정보는 한 축)에 이어진 SP — 배지
    POST /sp-core/links                      잇기 — 미리보기가 기본 · 자료 관리자
    POST /sp-core/links/remove               끊기 — 미리보기가 기본 · 자료 관리자

**잇는 화면은 없다** — 잇는 일은 운영에서 AI 가 MCP 로 후보를 보이고 사람이 확인한다. 화면은
이어진 것을 **보이기만** 한다(2026-11-02 — 기준정보 · 물성 분류의 「SP」 배지). 전에는 그것도
없어서 이어도 변경 이력 말고는 어디에도 안 보였다. 읽기는 로그인한 누구나 한다 — 바깥
시스템의 공개 목록이다.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.sp_core import links, sync
from app.modules.sp_core.models import (
    SpCoreLink,
    SpCoreObject,
    SpCoreRelation,
    SpCoreRun,
    SpCoreType,
)
from app.modules.sp_core.schemas import (
    SpCoreLinkedOut,
    SpCoreLinkedPage,
    SpCoreLinkOut,
    SpCoreLinkPage,
    SpCoreLinkPlanOut,
    SpCoreLinkRequest,
    SpCoreMatchOut,
    SpCoreObjectDetailOut,
    SpCoreObjectOut,
    SpCoreObjectPage,
    SpCoreRelationOut,
    SpCoreRunOut,
    SpCoreStatusOut,
    SpCoreSyncOut,
    SpCoreSyncRequest,
    SpCoreTypeOut,
    SpCoreUnlinkOut,
    SpCoreUnlinkRequest,
)
from app.shared import audit, link_targets, permissions, sp_connection
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound

router = APIRouter(prefix="/sp-core", tags=["sp_core"])

_CODE = "MNX-SPCORE-0007"
_WHAT = "SP 코어 온톨로지 받기 · 연결"
#: 목록 엔드포인트의 상한(AGENTS — 서버가 강제한다).
PAGE_MAX = 200
#: 객체 상세에 싣는 선의 상한.
EDGES_MAX = 200
#: 배지용 연결의 상한 — 한 대상 종류(한 축)에 이보다 많이 이어지면 일부만 싣고 그렇다고 말한다.
LINKED_MAX = 5000
RUNS_SHOWN = 5


def _source(db: Session) -> str | None:
    """받는 곳 — **호스트까지만.** 토큰은 물론, 주소의 경로도 바깥에 말할 까닭이 없다."""
    found = sp_connection.connection(db)
    if found is None:
        return None
    parts = urlsplit(found.url)
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else None


def _run_out(run: SpCoreRun) -> SpCoreRunOut:
    return SpCoreRunOut(
        id=run.id,
        trigger=run.trigger,
        full=run.full,
        system=run.system,
        revision=run.revision,
        ok=run.ok,
        error=run.error,
        warnings=list(run.warnings or []),
        counts=dict(run.counts or {}),
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/status", response_model=SpCoreStatusOut)
def status(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> SpCoreStatusOut:
    """**지금 무엇을 받아 두었나** — 설정 · 타입마다 받은 수 · 최근 실행 · 연결 수."""
    alive: Counter[str] = Counter()
    gone: Counter[str] = Counter()
    for slug, deleted, count in db.execute(
        select(SpCoreObject.type_slug, SpCoreObject.deleted, func.count()).group_by(
            SpCoreObject.type_slug, SpCoreObject.deleted
        )
    ):
        (gone if deleted else alive)[slug] += int(count)
    edges = Counter(
        {
            slug: int(count)
            for slug, count in db.execute(
                select(SpCoreRelation.src_type, func.count())
                .where(SpCoreRelation.deleted.is_(False))
                .group_by(SpCoreRelation.src_type)
            )
        }
    )
    tied = Counter(
        {
            slug: int(count)
            for slug, count in db.execute(
                select(SpCoreLink.sp_type, func.count()).group_by(SpCoreLink.sp_type)
            )
        }
    )
    types = [
        SpCoreTypeOut(
            slug=one.slug,
            label=one.label,
            description=one.description,
            published=one.published,
            sp_count=one.sp_count,
            received=alive[one.slug],
            deleted=gone[one.slug],
            relations=edges[one.slug],
            links=tied[one.slug],
            properties=list(one.properties or []),
            relation_kinds=list(one.relation_kinds or []),
            rows_as_of=one.rows_as_of,
            relations_as_of=one.relations_as_of,
            full_at=one.full_at,
        )
        for one in db.scalars(select(SpCoreType).order_by(SpCoreType.slug))
    ]
    runs = [
        _run_out(one)
        for one in db.scalars(
            select(SpCoreRun).order_by(SpCoreRun.started_at.desc()).limit(RUNS_SHOWN)
        )
    ]
    return SpCoreStatusOut(
        configured=sync.configured(db),
        source=_source(db),
        types=types,
        runs=runs,
        links=sum(tied.values()),
    )


@router.post("/sync", response_model=SpCoreSyncOut, status_code=202)
def request_sync(
    payload: SpCoreSyncRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreSyncOut:
    """받기를 **지금** 부른다 — 워커가 돈다(보통은 하루 한 번 저절로)."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    if not sync.configured(db):
        raise Conflict(
            "MNX-SPCORE-0001",
            "SP 코어 주소 · 토큰이 설정돼 있지 않아 받을 수 없습니다 — 시스템 관리자가 "
            "「관리 > 외부 연동」 의 Standard Platform 에 주소와 core:read 토큰을 넣으세요.",
        )
    job = queue.enqueue(
        db,
        kind=kinds.SP_CORE_PULL,
        payload={"trigger": "manual", "full": payload.full, "requested_by_id": str(user.id)},
        max_attempts=1,
    )
    audit.record(
        db,
        action=audit.SP_CORE_SYNC_REQUESTED,
        actor=user,
        target_table="sp_core_runs",
        target_id=None,
        target_label="SP 코어 온톨로지 받기",
        changes={"full": payload.full},
    )
    db.commit()
    return SpCoreSyncOut(
        queued=True,
        job_id=job.id,
        message=(
            "받기를 큐에 넣었습니다 — 워커가 돕니다. 결과는 잠시 뒤 상태(최근 실행)에서 "
            "봅니다."
        ),
    )


def _object_out(obj: SpCoreObject) -> SpCoreObjectOut:
    return SpCoreObjectOut(
        type_slug=obj.type_slug,
        key=obj.key,
        label=obj.label,
        status=obj.status,
        deleted=obj.deleted,
        hidden=obj.hidden,
        merged_into=obj.merged_into,
        previous_keys=list(obj.previous_keys or []),
        properties=dict(obj.properties or {}),
        sp_updated_at=obj.sp_updated_at,
        received_at=obj.received_at,
    )


@router.get("/objects", response_model=SpCoreObjectPage)
def list_objects(
    type: str | None = Query(default=None, description="SP 타입 slug"),
    q: str | None = Query(default=None, description="이름 · key 에 들어간 글자"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=PAGE_MAX),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreObjectPage:
    query = select(SpCoreObject)
    if type:
        query = query.where(SpCoreObject.type_slug == type)
    if not include_deleted:
        query = query.where(SpCoreObject.deleted.is_(False))
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(SpCoreObject.label.ilike(needle), SpCoreObject.key.ilike(needle))
        )
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(SpCoreObject.type_slug, SpCoreObject.key).limit(limit).offset(offset)
    )
    return SpCoreObjectPage(
        items=[_object_out(one) for one in rows], total=total, limit=limit, offset=offset
    )


def _labels(db: Session, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """(타입, key) → 이름. 선의 끝점을 사람이 읽게."""
    if not pairs:
        return {}
    found: dict[tuple[str, str], str] = {}
    by_type: dict[str, set[str]] = {}
    for slug, key in pairs:
        by_type.setdefault(slug, set()).add(key)
    for slug, keys in by_type.items():
        for key, label in db.execute(
            select(SpCoreObject.key, SpCoreObject.label).where(
                SpCoreObject.type_slug == slug, SpCoreObject.key.in_(keys)
            )
        ):
            found[(slug, key)] = label
    return found


def _link_outs(db: Session, rows: list[SpCoreLink]) -> list[SpCoreLinkOut]:
    names = {
        one.id: one.display_name
        for one in db.scalars(
            select(User).where(
                User.id.in_({row.created_by_id for row in rows if row.created_by_id})
            )
        )
    }
    sp_labels = _labels(db, {(row.sp_type, row.sp_key) for row in rows})
    out: list[SpCoreLinkOut] = []
    for row in rows:
        try:
            target_label = links.target_label(db, row.target_kind, row.target_ref)
        except AppError:
            # 모르는 대상 종류가 남아 있어도 목록은 선다.
            target_label = None
        out.append(
            SpCoreLinkOut(
                id=row.id,
                sp_type=row.sp_type,
                sp_key=row.sp_key,
                sp_label=sp_labels.get((row.sp_type, row.sp_key)),
                target=row.target_kind,
                target_ref=row.target_ref,
                target_label=target_label,
                note=row.note,
                created_by=names.get(row.created_by_id) if row.created_by_id else None,
                created_at=row.created_at,
            )
        )
    return out


@router.get("/objects/{type_slug}/{key:path}", response_model=SpCoreObjectDetailOut)
def get_object(
    type_slug: str,
    key: str,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreObjectDetailOut:
    obj = db.scalar(
        select(SpCoreObject).where(
            SpCoreObject.type_slug == type_slug, SpCoreObject.key == key
        )
    )
    if obj is None:
        raise NotFound("MNX-SPCORE-0003", f"받은 SP 객체에 없습니다: {type_slug}/{key}")
    outgoing = list(
        db.scalars(
            select(SpCoreRelation)
            .where(SpCoreRelation.src_type == type_slug, SpCoreRelation.src == key)
            .order_by(SpCoreRelation.relation, SpCoreRelation.dst)
            .limit(EDGES_MAX)
        )
    )
    incoming = list(
        db.scalars(
            select(SpCoreRelation)
            .where(SpCoreRelation.dst_type == type_slug, SpCoreRelation.dst == key)
            .order_by(SpCoreRelation.relation, SpCoreRelation.src)
            .limit(EDGES_MAX)
        )
    )
    names = _labels(
        db,
        {(one.dst_type, one.dst) for one in outgoing}
        | {(one.src_type, one.src) for one in incoming},
    )

    def edge(one: SpCoreRelation) -> SpCoreRelationOut:
        return SpCoreRelationOut(
            src_type=one.src_type,
            src=one.src,
            src_label=names.get((one.src_type, one.src))
            or (obj.label if one.src == key else None),
            relation=one.relation,
            dst_type=one.dst_type,
            dst=one.dst,
            dst_label=names.get((one.dst_type, one.dst))
            or (obj.label if one.dst == key else None),
            deleted=one.deleted,
            properties=dict(one.properties or {}),
        )

    tied = list(
        db.scalars(
            select(SpCoreLink)
            .where(SpCoreLink.sp_type == type_slug, SpCoreLink.sp_key == key)
            .order_by(SpCoreLink.created_at)
        )
    )
    return SpCoreObjectDetailOut(
        **_object_out(obj).model_dump(),
        outgoing=[edge(one) for one in outgoing],
        incoming=[edge(one) for one in incoming],
        links=_link_outs(db, tied),
    )


@router.get("/match", response_model=SpCoreMatchOut)
def match(
    sp_type: str = Query(..., description="SP 타입 slug"),
    target: str = Query(..., description="term · property · property_group · property_field"),
    vocabulary: str | None = Query(
        default=None, description="target=term 이면 기준정보 축 slug"
    ),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreMatchOut:
    """한 SP 타입을 한 대상과 견준다 — **쓰지 않는다.** 후보는 사람이 보고 잇는다."""
    if db.scalar(select(SpCoreType.id).where(SpCoreType.slug == sp_type)) is None:
        raise NotFound("MNX-SPCORE-0002", f"받은 SP 타입에 없습니다: {sp_type}")
    return SpCoreMatchOut(**links.match(db, sp_type, target, vocabulary))


@router.get("/links", response_model=SpCoreLinkPage)
def list_links(
    sp_type: str | None = Query(default=None),
    target: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=PAGE_MAX),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreLinkPage:
    query = select(SpCoreLink)
    if sp_type:
        query = query.where(SpCoreLink.sp_type == sp_type)
    if target:
        query = query.where(SpCoreLink.target_kind == target)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        db.scalars(
            query.order_by(SpCoreLink.sp_type, SpCoreLink.sp_key).limit(limit).offset(offset)
        )
    )
    return SpCoreLinkPage(items=_link_outs(db, rows), total=total, limit=limit, offset=offset)


@router.get("/linked", response_model=SpCoreLinkedPage)
def list_linked(
    target: str = Query(..., description="term · property · property_group · property_field"),
    vocabulary: str | None = Query(
        default=None, description="target=term 이면 기준정보 축 slug"
    ),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreLinkedPage:
    """**화면의 「SP」 배지** — 한 대상 종류(기준정보는 한 축)에 이어진 SP 객체를 한 번에.

    화면은 줄마다 묻지 않는다 — 한 번 받아 대상 키로 찾는다. 연결 목록(`/links`)과 달리 대상
    이름을 다시 찾지 않는다(화면이 이미 갖고 있다). SP 쪽 이름 · 사라짐은 한 질의로 붙인다.
    """
    if target not in links.TARGETS:
        raise link_targets.bad_kind(target)
    query = (
        select(SpCoreLink, SpCoreObject.label, SpCoreObject.deleted, SpCoreType.label)
        .outerjoin(
            SpCoreObject,
            and_(
                SpCoreObject.type_slug == SpCoreLink.sp_type,
                SpCoreObject.key == SpCoreLink.sp_key,
            ),
        )
        .outerjoin(SpCoreType, SpCoreType.slug == SpCoreLink.sp_type)
        .where(SpCoreLink.target_kind == target)
    )
    if target == "term":
        query = query.where(SpCoreLink.target_ref.in_(link_targets.axis_refs(db, vocabulary)))
    rows = db.execute(
        query.order_by(SpCoreLink.target_ref, SpCoreLink.sp_type, SpCoreLink.sp_key).limit(
            LINKED_MAX + 1
        )
    ).all()
    return SpCoreLinkedPage(
        target=target,
        vocabulary=vocabulary if target == "term" else None,
        items=[
            SpCoreLinkedOut(
                link_id=link.id,
                target_ref=link.target_ref,
                sp_type=link.sp_type,
                sp_type_label=type_label,
                sp_key=link.sp_key,
                sp_label=sp_label,
                sp_deleted=bool(sp_deleted),
            )
            for link, sp_label, sp_deleted, type_label in rows[:LINKED_MAX]
        ],
        truncated=len(rows) > LINKED_MAX,
    )


@router.post("/links", response_model=SpCoreLinkPlanOut)
def create_links(
    payload: SpCoreLinkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreLinkPlanOut:
    """잇는다 — **기본이 미리보기다.** `dry_run: false` 일 때만 잇고, 오류가 한 줄이라도 있으면
    하나도 안 잇는다(422)."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    items: list[dict[str, Any]] = [one.model_dump() for one in payload.items]
    planned = links.plan(db, items)
    if payload.dry_run:
        return SpCoreLinkPlanOut(**planned.out(applied=False))
    links.apply(db, user, planned, note=payload.note)
    db.commit()
    return SpCoreLinkPlanOut(**planned.out(applied=True))


@router.post("/links/remove", response_model=SpCoreUnlinkOut)
def remove_links(
    payload: SpCoreUnlinkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SpCoreUnlinkOut:
    """끊는다 — 기본이 미리보기다. 없는 id 는 이유와 함께 말한다."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    out = links.remove(db, user, list(payload.ids), dry_run=payload.dry_run)
    if not payload.dry_run:
        db.commit()
    return SpCoreUnlinkOut(**out)
