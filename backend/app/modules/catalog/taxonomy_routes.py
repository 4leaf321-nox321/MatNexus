"""물성 분류 API — **분야 ⊃ 물성군 ⊃ 물성** (ADR 0054).

    GET    /api/catalog/taxonomy                  트리 — 분야 · 물성군 · 물성 전부(문헌 + 사내)
    POST   /api/catalog/taxonomy/fields           분야 만들기
    PATCH  /api/catalog/taxonomy/fields/{key}     분야 고치기 · 폐기 · 되살리기
    POST   /api/catalog/taxonomy/groups           물성군 만들기
    PATCH  /api/catalog/taxonomy/groups/{key}     물성군 고치기 · 다른 분야로 옮기기 · 폐기
    PUT    /api/catalog/taxonomy/members          물성 여럿을 한 군에 넣기 · 빼기
    POST   /api/catalog/taxonomy/import           밀어 넣기 — 기본이 미리 보기(`dry_run`)

    GET    /api/catalog/feed/fields               바깥(SP)이 읽어 가는 목록 — 연동 지침 §3.1
    GET    /api/catalog/feed/groups
    GET    /api/catalog/feed/properties

**고치는 일은 자료 관리자 · 시스템 관리자다** — 정의문 고치기와 같은 판정이다(ADR 0035 D4).
분류는 전사 자산이고 바깥이 그대로 읽어 간다. 읽기는 누구나다.

**물성 목록의 정본은 여기다**(ADR 0054). SP 는 데이터 소스로 이 셋을 밤마다 읽고, 받은 쪽은
읽기 전용이다 — 고칠 것은 여기서 고친다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.catalog import taxonomy
from app.modules.catalog.taxonomy_schemas import (
    FeedFieldPage,
    FeedGroupPage,
    FeedPropertyPage,
    PropertyFieldCreate,
    PropertyFieldOut,
    PropertyFieldUpdate,
    PropertyGroupCreate,
    PropertyGroupOut,
    PropertyGroupUpdate,
    TaxonomyAssignIn,
    TaxonomyAssignOut,
    TaxonomyImportIn,
    TaxonomyImportOut,
    TaxonomyOut,
)
from app.shared import permissions
from app.shared.auth import current_user
from app.shared.errors import Conflict

router = APIRouter(prefix="/catalog/taxonomy", tags=["catalog"])
feed_router = APIRouter(prefix="/catalog/feed", tags=["catalog"])

_CODE = "MNX-CATALOG-0055"
_WHAT = "물성 분류 고치기"


def _commit(db: Session) -> None:
    """키는 고유다 — 같은 키가 방금 다른 데서 생겼으면 500 이 아니라 다시 하라고 말한다."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict(
            "MNX-CATALOG-0057", "같은 키가 방금 생겼습니다 — 화면을 새로 읽고 다시 해 주세요."
        ) from None


@router.get("", response_model=TaxonomyOut)
def get_taxonomy(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TaxonomyOut:
    """분야 · 물성군 · 물성 전부. 화면이 트리로 엮는다 — 미분류 물성은 `group_key` 가
    비었다."""
    return taxonomy.tree(db)


@router.post("/fields", response_model=PropertyFieldOut, status_code=201)
def create_field(
    payload: PropertyFieldCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyFieldOut:
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    row = taxonomy.create_field(db, user, payload)
    _commit(db)
    return taxonomy.field_out(db, row)


@router.patch("/fields/{key}", response_model=PropertyFieldOut)
def update_field(
    key: str,
    payload: PropertyFieldUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyFieldOut:
    """부분 수정. 키는 못 바꾼다 — 바깥이 키로 잇는다. `retired: true` 는 폐기(지우지
    않는다)."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    row = taxonomy.update_field(db, user, key, payload)
    _commit(db)
    return taxonomy.field_out(db, row)


@router.post("/groups", response_model=PropertyGroupOut, status_code=201)
def create_group(
    payload: PropertyGroupCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyGroupOut:
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    row = taxonomy.create_group(db, user, payload)
    _commit(db)
    return taxonomy.group_out(db, row)


@router.patch("/groups/{key}", response_model=PropertyGroupOut)
def update_group(
    key: str,
    payload: PropertyGroupUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyGroupOut:
    """부분 수정. `field_key` 를 보내면 다른 분야로 옮긴다 — 든 물성이 함께 가고 키는
    그대로다."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    row = taxonomy.update_group(db, user, key, payload)
    _commit(db)
    return taxonomy.group_out(db, row)


@router.put("/members", response_model=TaxonomyAssignOut)
def assign_members(
    payload: TaxonomyAssignIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaxonomyAssignOut:
    """물성 여럿을 한 물성군에. 다른 군에 있던 것은 옮겨진다(물성은 한 군에만 든다)."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    out = taxonomy.assign(db, user, payload.group_key, payload.property_keys)
    _commit(db)
    return out


@router.post("/import", response_model=TaxonomyImportOut)
def import_taxonomy(
    payload: TaxonomyImportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaxonomyImportOut:
    """표로 붙여넣은 분류를 밀어 넣는다. **기본이 미리 보기다** — `dry_run: false` 일 때만
    넣고, 오류가 한 줄이라도 있으면 아무것도 안 넣는다(422)."""
    permissions.require_steward(user, code=_CODE, what=_WHAT)
    plan = taxonomy.plan_import(db, payload.rows)
    if payload.dry_run:
        return plan.out(applied=False)
    taxonomy.apply_import(db, user, plan)
    _commit(db)
    return plan.out(applied=True)


# ── 바깥(SP)이 읽는 목록 — 연동 지침 §3.1 ─────────────────────────────────────
#
# 모양: `{items, total, page, page_size}`. 행은 평평하고, 키 차례로 늘 같은 순서다. 폐기한 것도
# 행으로 남는다(`is_active: false`). `page_size` 는 1000 까지 — 넘게 달라면 깎지 않고 거절한다
# (`taxonomy.FEED_PAGE_MAX` 의 까닭).


@feed_router.get("/fields", response_model=FeedFieldPage)
def feed_fields(
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FeedFieldPage:
    """물성 분야 전부."""
    return taxonomy.feed_fields(db, page, page_size)


@feed_router.get("/groups", response_model=FeedGroupPage)
def feed_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FeedGroupPage:
    """물성군 전부 — 행마다 든 분야(`field_key`)."""
    return taxonomy.feed_groups(db, page, page_size)


@feed_router.get("/properties", response_model=FeedPropertyPage)
def feed_properties(
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FeedPropertyPage:
    """물성(허브 키) 전부 — 문헌 + 사내, 폐기한 것까지. 행마다 물성군 · 분야 · 별칭."""
    return taxonomy.feed_properties(db, page, page_size)
