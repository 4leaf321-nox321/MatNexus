"""받기 — SP 연동 지침서 §4.2 「받는 쪽의 반복문」 그대로(ADR 0063).

    카탈로그(`GET /api/core`)  → 공개 타입 목록 · 칸 · 관계 종류 · 판(revision)
    타입마다 행                 → since = 지난 as_of, next 가 빌 때까지, 끝까지 받은 뒤에만
    as_of 저장
    타입마다 선(관계가 있으면)   → 같은 규칙 + reset 이면 처음부터

## 지킬 것(지침서의 번호)

1 · 2  `as_of` 는 SP 가 준 것을 **끝까지 받은 뒤에만** 저장한다. 중간에 멈추면 그대로 둔다 —
다음
       주기에 같은 자리부터 다시 받는다(같은 행이 두 번 와도 덮어쓰면 해가 없다 — 6).
3      `key` 로 가린다. 4 `deleted` 는 지우지 않고 표시, `renamed_from` · `previous_keys` 로
옛 행을
       찾아 키를 옮긴다(연결도 함께). `hidden` 이면 값은 두고 사라진 것처럼.
5      모르는 칸은 `properties` 에 그대로 담고 해석하지 않는다.
7      처음부터 받은 판(since 없음)은 **끝까지 받은 뒤** 이번에 안 온 것을 사라진 것으로
둔다(부재
       대조). 일주일에 한 번은 처음부터 받는다 — 토큰 주인의 소속이 줄면 표식 없이 빠지기 때문.
8      지워졌던 key 가 다시 오면 되살린다. 9 지워진 객체를 끝점으로 하는 선은 이쪽이 끊는다.
11     404 둘을 가른다 — 공개가 풀린 타입은 멈추고 알리고, 커서를 못 읽으면 커서 없이 다시.

**쪽마다 커밋한다.** 큰 타입을 한 트랜잭션으로 받으면 끝에서 실패할 때 다 잃는다. `as_of` 는
타입을 끝까지 받은 뒤에만 옮기므로 쪽마다 커밋해도 빠지는 행이 없다.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.sp_core.client import BadCursor, NotPublished, SpCoreClient, SpCoreError
from app.modules.sp_core.models import (
    KEY_MAX,
    SLUG_MAX,
    SpCoreLink,
    SpCoreObject,
    SpCoreRelation,
    SpCoreRun,
    SpCoreType,
)

logger = logging.getLogger(__name__)

#: 처음부터 받아 부재 대조를 하는 주기(규칙 7의 「주 1회쯤」).
FULL_EVERY = timedelta(days=7)
#: 경고 목록이 끝없이 길어지지 않게.
WARNINGS_MAX = 50


def configured() -> bool:
    settings = get_settings()
    return bool(settings.sp_core_url and settings.sp_core_token)


def open_client(transport: httpx.BaseTransport | None = None) -> SpCoreClient:
    """설정의 주소 · 토큰으로 연다. 시험은 `transport` 를 넣는다."""
    settings = get_settings()
    return SpCoreClient(settings.sp_core_url, settings.sp_core_token, transport=transport)


def _now() -> datetime:
    return datetime.now(UTC)


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def pull(
    db: Session,
    client: SpCoreClient,
    *,
    trigger: str = "schedule",
    full: bool = False,
    requested_by_id: uuid.UUID | None = None,
) -> SpCoreRun:
    """한 번 받는다. **실패해도 예외를 올리지 않고** 기록(`SpCoreRun`)에 남긴다 — 밤에 도는
    일이라 남는 것이 기록뿐이다."""
    run = SpCoreRun(trigger=trigger, full=full, requested_by_id=requested_by_id)
    db.add(run)
    db.commit()
    warnings: list[str] = []
    failures: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    try:
        catalog = client.catalog()
    except SpCoreError as failed:
        return _finish(db, run, counts, warnings, [str(failed)])

    run.system = _text(catalog.get("system"), 100) or None
    run.revision = _text(catalog.get("revision"), 100) or None
    entries = [
        one for one in catalog.get("types") or [] if isinstance(one, dict) and one.get("slug")
    ]
    _sync_types(db, run, entries, warnings)
    db.commit()

    for entry in entries:
        slug = _text(entry["slug"], SLUG_MAX)
        sp_type = db.scalar(select(SpCoreType).where(SpCoreType.slug == slug))
        if sp_type is None:
            continue
        whole = full or sp_type.full_at is None or _now() - sp_type.full_at > FULL_EVERY
        tally: Counter[str] = Counter()
        try:
            _pull_rows(db, run, client, sp_type, whole=whole, tally=tally)
            if entry.get("relations"):
                _pull_relations(db, run, client, sp_type, whole=whole, tally=tally)
            if whole:
                sp_type.full_at = _now()
            db.commit()
        except NotPublished as failed:
            db.rollback()
            sp_type = db.scalar(select(SpCoreType).where(SpCoreType.slug == slug))
            if sp_type is not None:
                sp_type.published = False
            warnings.append(f"{slug}: {failed} 받은 것은 남겨 둡니다.")
            db.commit()
        except SpCoreError as failed:
            # 이 타입만 멈춘다 — as_of 를 안 옮겼으니 다음 주기에 같은 자리부터 다시 받는다.
            db.rollback()
            failures.append(f"{slug}: {failed}")
        counts[slug] = dict(tally)
    return _finish(db, run, counts, warnings, failures)


def _finish(
    db: Session,
    run: SpCoreRun,
    counts: dict[str, dict[str, int]],
    warnings: list[str],
    failures: list[str],
) -> SpCoreRun:
    run = db.get(SpCoreRun, run.id) or run
    run.counts = counts
    run.warnings = warnings[:WARNINGS_MAX]
    run.ok = not failures
    run.error = "; ".join(failures) or None
    run.finished_at = _now()
    db.commit()
    if failures:
        logger.warning("SP 코어 받기 실패: %s", run.error)
    return run


def _sync_types(
    db: Session, run: SpCoreRun, entries: list[dict[str, Any]], warnings: list[str]
) -> None:
    """카탈로그를 타입 표에 옮긴다. **공개가 풀린 타입은 지우지 않는다** — 받은 것과 연결이
    거기 매달려 있다."""
    previous = db.scalar(
        select(SpCoreRun.revision)
        .where(SpCoreRun.ok.is_(True), SpCoreRun.id != run.id)
        .order_by(SpCoreRun.started_at.desc())
        .limit(1)
    )
    if previous and run.revision and previous != run.revision:
        warnings.append(
            f"SP 의 공개 구조가 바뀌었습니다(판 {previous} → {run.revision}) — 칸 · 관계 "
            "종류를 "
            "다시 보세요."
        )
    known = {one.slug: one for one in db.scalars(select(SpCoreType))}
    seen: set[str] = set()
    for entry in entries:
        slug = _text(entry["slug"], SLUG_MAX)
        seen.add(slug)
        sp_type = known.get(slug)
        if sp_type is None:
            sp_type = SpCoreType(slug=slug)
            db.add(sp_type)
        sp_type.label = _text(entry.get("label"), 200) or slug
        sp_type.description = str(entry.get("description") or "") or None
        sp_type.properties = [
            one for one in entry.get("properties") or [] if isinstance(one, dict)
        ]
        sp_type.relation_kinds = [
            one for one in entry.get("relation_kinds") or [] if isinstance(one, dict)
        ]
        sp_type.sp_count = int(entry.get("count") or 0)
        sp_type.published = True
    for slug, sp_type in known.items():
        if slug not in seen and sp_type.published:
            sp_type.published = False
            warnings.append(
                f"{slug}: SP 가 더 이상 공개하지 않습니다 — 받은 것은 남겨 둡니다."
            )


# ── 행 ──────────────────────────────────────────────────────────────────────


def _pull_rows(
    db: Session,
    run: SpCoreRun,
    client: SpCoreClient,
    sp_type: SpCoreType,
    *,
    whole: bool,
    tally: Counter[str],
) -> None:
    slug = sp_type.slug
    since = None if whole else sp_type.rows_as_of
    cursor: str | None = None
    restarted = False
    as_of: Any = None
    while True:
        try:
            page = client.rows(slug, since=since, cursor=cursor)
        except BadCursor:
            # 규칙 11 — 커서 없이 지난 as_of 부터 다시. 두 번째도 못 읽으면 멈춘다.
            if cursor is None or restarted:
                raise
            restarted = True
            cursor = None
            tally["cursor_restart"] += 1
            continue
        for row in page.get("items") or []:
            if isinstance(row, dict):
                _apply_row(db, run, slug, row, tally)
        db.commit()
        cursor = page.get("next") or None
        if not cursor:
            as_of = page.get("as_of")
            break
    if since is None:
        tally["absent"] += _absent_objects(db, run, slug)
    if isinstance(as_of, str) and as_of:
        sp_type.rows_as_of = as_of[:40]


def _find(db: Session, slug: str, key: str) -> SpCoreObject | None:
    return db.scalar(
        select(SpCoreObject).where(SpCoreObject.type_slug == slug, SpCoreObject.key == key)
    )


def _apply_row(
    db: Session, run: SpCoreRun, slug: str, row: dict[str, Any], tally: Counter[str]
) -> None:
    key = _text(row.get("key"), KEY_MAX)
    if not key:
        tally["skipped"] += 1
        return
    obj = _find(db, slug, key)
    if obj is None:
        # 규칙 4 — 옛 식별자로 가진 행을 찾아 키를 옮긴다. 가장 최근 것부터 본다.
        olds = [row.get("renamed_from"), *reversed(row.get("previous_keys") or [])]
        for old in olds:
            old_key = _text(old, KEY_MAX)
            if old_key and old_key != key:
                found = _find(db, slug, old_key)
                if found is not None:
                    obj = _rename(db, found, key)
                    tally["renamed"] += 1
                    break
    if obj is None:
        obj = SpCoreObject(type_slug=slug, key=key)
        db.add(obj)
        tally["new"] += 1

    if row.get("deleted"):
        if not obj.deleted:
            tally["deleted"] += 1
            _cut_relations(db, slug, key)
        obj.deleted = True
        obj.hidden = bool(row.get("hidden"))
        obj.merged_into = _text(row.get("merged_into"), KEY_MAX) or None
        # `hidden` 은 이름 · 칸이 안 온다 — 가진 값은 둔다(규칙 4).
        if not obj.hidden and row.get("label"):
            obj.label = _text(row.get("label"), 300)
    else:
        if obj.deleted:
            tally["revived"] += 1
        obj.deleted = False
        obj.hidden = False
        obj.merged_into = None
        obj.label = _text(row.get("label"), 300)
        obj.status = _text(row.get("status"), 20) or "active"
        properties = row.get("properties")
        obj.properties = dict(properties) if isinstance(properties, dict) else {}
    obj.previous_keys = [str(one) for one in row.get("previous_keys") or []]
    obj.sp_updated_at = _text(row.get("updated_at"), 40) or None
    obj.seen_run_id = run.id
    tally["rows"] += 1


def _rename(db: Session, obj: SpCoreObject, new_key: str) -> SpCoreObject:
    """키를 옮긴다 — **받은 선과 연결도 함께.** 하나라도 옛 키에 남으면 같은 것이 둘이 된다."""
    slug, old = obj.type_slug, obj.key
    obj.key = new_key
    db.execute(
        update(SpCoreRelation)
        .where(SpCoreRelation.src_type == slug, SpCoreRelation.src == old)
        .values(src=new_key)
    )
    db.execute(
        update(SpCoreRelation)
        .where(SpCoreRelation.dst_type == slug, SpCoreRelation.dst == old)
        .values(dst=new_key)
    )
    db.execute(
        update(SpCoreLink)
        .where(SpCoreLink.sp_type == slug, SpCoreLink.sp_key == old)
        .values(sp_key=new_key)
    )
    return obj


def _cut_relations(db: Session, slug: str, key: str) -> None:
    """규칙 9 — 사라진 객체를 끝점으로 하는 선은 SP 가 「끊겼다」 고 안 보낸다. 이쪽이
    끊는다."""
    db.execute(
        update(SpCoreRelation)
        .where(
            or_(
                and_(SpCoreRelation.src_type == slug, SpCoreRelation.src == key),
                and_(SpCoreRelation.dst_type == slug, SpCoreRelation.dst == key),
            ),
            SpCoreRelation.deleted.is_(False),
        )
        .values(deleted=True)
    )


def _absent_objects(db: Session, run: SpCoreRun, slug: str) -> int:
    """처음부터 받았는데 이번에 안 온 것 — SP 에서 사라졌다(규칙 7). **끝까지 받은 뒤에만**
    부른다."""
    gone = list(
        db.scalars(
            select(SpCoreObject).where(
                SpCoreObject.type_slug == slug,
                SpCoreObject.deleted.is_(False),
                or_(SpCoreObject.seen_run_id.is_(None), SpCoreObject.seen_run_id != run.id),
            )
        )
    )
    for obj in gone:
        obj.deleted = True
        _cut_relations(db, slug, obj.key)
    return len(gone)


# ── 선 ──────────────────────────────────────────────────────────────────────


def _pull_relations(
    db: Session,
    run: SpCoreRun,
    client: SpCoreClient,
    sp_type: SpCoreType,
    *,
    whole: bool,
    tally: Counter[str],
) -> None:
    slug = sp_type.slug
    since = None if whole else sp_type.relations_as_of
    cursor: str | None = None
    restarted = False
    as_of: Any = None
    while True:
        try:
            page = client.relations(slug, since=since, cursor=cursor)
        except BadCursor:
            if cursor is None or restarted:
                raise
            restarted = True
            cursor = None
            tally["cursor_restart"] += 1
            continue
        if page.get("reset") and since is not None:
            # SP 가 「그 사이 무엇이 끊겼는지 말해 줄 수 없다」 고 했다 — 처음부터 받고 부재
            # 대조.
            since, cursor = None, None
            tally["relations_reset"] += 1
            continue
        for row in page.get("items") or []:
            if isinstance(row, dict):
                _apply_relation(db, run, slug, row, tally)
        db.commit()
        cursor = page.get("next") or None
        if not cursor:
            as_of = page.get("as_of")
            break
    if since is None:
        tally["relations_absent"] += _absent_relations(db, run, slug)
    if isinstance(as_of, str) and as_of:
        sp_type.relations_as_of = as_of[:40]


def _apply_relation(
    db: Session, run: SpCoreRun, slug: str, row: dict[str, Any], tally: Counter[str]
) -> None:
    src = _text(row.get("src"), KEY_MAX)
    relation = _text(row.get("relation"), SLUG_MAX)
    dst = _text(row.get("dst"), KEY_MAX)
    dst_type = _text(row.get("dst_type"), SLUG_MAX)
    if not (src and relation and dst and dst_type):
        tally["skipped"] += 1
        return
    edge = db.scalar(
        select(SpCoreRelation).where(
            SpCoreRelation.src_type == slug,
            SpCoreRelation.src == src,
            SpCoreRelation.relation == relation,
            SpCoreRelation.dst == dst,
            SpCoreRelation.dst_type == dst_type,
        )
    )
    if edge is None:
        edge = SpCoreRelation(
            src_type=slug, src=src, relation=relation, dst=dst, dst_type=dst_type
        )
        db.add(edge)
    edge.deleted = bool(row.get("deleted"))
    edge.evidence_note = str(row.get("evidence_note") or "") or None
    properties = row.get("properties")
    edge.properties = dict(properties) if isinstance(properties, dict) else {}
    edge.sp_updated_at = _text(row.get("updated_at"), 40) or None
    edge.seen_run_id = run.id
    tally["relations"] += 1


def _absent_relations(db: Session, run: SpCoreRun, slug: str) -> int:
    gone = db.execute(
        update(SpCoreRelation)
        .where(
            SpCoreRelation.src_type == slug,
            SpCoreRelation.deleted.is_(False),
            or_(SpCoreRelation.seen_run_id.is_(None), SpCoreRelation.seen_run_id != run.id),
        )
        .values(deleted=True)
    )
    return int(getattr(gone, "rowcount", 0) or 0)
