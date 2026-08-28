"""장비 커넥터 — 받기·감지·후보·등록.

## 후보 조회는 처음엔 좁게

`material_code` 가 없으면 후보를 만들지 않는다. 시편 이름만으로 전 부서를 뒤지면
엉뚱한 재료에 붙는다 — 이름은 흔하고(`MD_01`), 재료가 다르면 그건 다른 시편이다.

파일 안의 값(프로파일 `identity`)과 파일 이름의 값(에이전트 힌트)이 둘 다 있으면
**파일이 이긴다.** 파일은 장비가 적은 증거고, 이름은 사람이 붙인 이름표다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.pipelines.models import (
    FINAL_STATUSES,
    PipelineConnector,
    PipelineInboxItem,
)
from app.modules.tests.models import FormatProfile, TestRun, TestType
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit, filestore, ingest
from app.shared.errors import AppError, Conflict, NotFound
from matcore.parsers import ParseError

logger = logging.getLogger(__name__)

#: 감지·후보에서 사람이 보는 값들이 넘치지 않게.
MAX_CANDIDATES = 20


def _now() -> datetime:
    return datetime.now(UTC)


# --- 커넥터 -------------------------------------------------------------------


def get_connector(
    db: Session, connector_id: uuid.UUID, *, active_only: bool = True
) -> PipelineConnector:
    row = db.get(PipelineConnector, connector_id)
    if row is None or row.deleted_at is not None or (active_only and not row.is_active):
        raise NotFound("MNX-PIPE-0001", "커넥터가 없거나 비활성입니다.")
    return row


def register_connector(
    db: Session, *, user: User, workspace: Workspace, name: str, hostname: str
) -> tuple[PipelineConnector, bool]:
    """같은 호스트가 있으면 **그것을 돌려준다.** 재설치 뒤 커넥터가 둘이 되면
    관리 화면에서 어느 것이 살아 있는지 알 수 없다. 이름은 새것으로 갱신한다."""
    existing = db.scalar(
        select(PipelineConnector).where(
            PipelineConnector.workspace_id == workspace.id,
            PipelineConnector.hostname == hostname,
            PipelineConnector.deleted_at.is_(None),
        )
    )
    if existing is not None:
        if existing.name != name:
            existing.name = name
        return existing, False
    made = PipelineConnector(
        workspace_id=workspace.id, name=name, hostname=hostname, created_by_id=user.id
    )
    db.add(made)
    db.flush()
    audit.record(
        db,
        action="pipelines.connector.create",
        actor=user,
        target_table="pipeline_connectors",
        target_id=made.id,
        target_label=f"{name} ({hostname})",
        workspace_id=workspace.id,
    )
    return made, True


def heartbeat(
    db: Session,
    connector: PipelineConnector,
    *,
    app_version: str,
    sources: list[dict[str, Any]],
    next_run_at: datetime | None,
) -> None:
    connector.app_version = app_version
    connector.last_seen_at = _now()
    connector.next_run_at = next_run_at
    connector.last_heartbeat = {"sources": sources}


def heartbeat_totals(connector: PipelineConnector) -> tuple[int, int]:
    pending = failed = 0
    for one in connector.last_heartbeat.get("sources", []) or []:
        pending += int(one.get("pending", 0) or 0)
        failed += int(one.get("failed", 0) or 0)
    return pending, failed


def waiting_counts(db: Session, connector_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """서버 쪽에서 사람을 기다리는 것. 커넥터별로 한 번에 센다."""
    if not connector_ids:
        return {}
    rows = db.execute(
        select(PipelineInboxItem.connector_id, func.count())
        .where(
            PipelineInboxItem.connector_id.in_(connector_ids),
            PipelineInboxItem.status.in_(("needs_specimen", "failed")),
        )
        .group_by(PipelineInboxItem.connector_id)
    )
    return {connector_id: int(count) for connector_id, count in rows}


def visible_connectors(db: Session, user: User) -> Any:
    query = select(PipelineConnector).where(PipelineConnector.deleted_at.is_(None))
    if not user.is_system_admin:
        mine = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        query = query.where(PipelineConnector.workspace_id.in_(mine))
    return query.order_by(PipelineConnector.name)


# --- 반입 ---------------------------------------------------------------------


def inbox_dir(item_id: uuid.UUID, when: datetime) -> str:
    return f"inbox/{when:%Y}/{when:%m}/{item_id}/source"


def find_duplicate(
    db: Session, sha256: str, *, except_id: uuid.UUID | None = None
) -> tuple[str, uuid.UUID] | None:
    """같은 내용이 이미 있나. (종류, id). **서버 원장이 정본이다.**

    `except_id` 는 방금 만든 자기 행이다 — 해시를 먼저 적고 flush 하므로 빼지
    않으면 **자기 자신을 중복으로 본다**(실제로 그랬다)."""
    run_id = db.scalar(
        select(TestRun.id).where(TestRun.source_sha256 == sha256, TestRun.deleted_at.is_(None))
    )
    if run_id is not None:
        return "test_run", run_id
    item_id = db.scalar(
        select(PipelineInboxItem.id).where(
            PipelineInboxItem.sha256 == sha256,
            PipelineInboxItem.status != "discarded",
            PipelineInboxItem.id != except_id,
        )
    )
    if item_id is not None:
        return "inbox_item", item_id
    return None


def receive(
    db: Session,
    *,
    connector: PipelineConnector,
    source_key: str,
    filename: str,
    stream: Any,
    client_sha256: str,
    client_path: str,
    mtime: datetime,
    hints: dict[str, str],
    max_bytes: int,
) -> PipelineInboxItem:
    """파일을 받아 수집함에 넣는다. **저장 → 해시 대조 → 중복 검사** 순이다.

    저장을 먼저 하는 이유: 해시는 다 받아야 안다. 대조가 틀리면 방금 저장한 것을
    지운다 — 전송 중 깨진 파일을 남겨 둘 이유가 없다.
    """
    item = PipelineInboxItem(
        connector_id=connector.id,
        source_key=source_key,
        filename=filename[:255],
        size=0,
        sha256=client_sha256,
        client_path=client_path[:1000],
        mtime=mtime,
        hints=hints,
        status="received",
    )
    db.add(item)
    db.flush()
    db.refresh(item)

    directory = inbox_dir(item.id, item.received_at)
    stored = filestore.save_stream(
        stream, relative_dir=directory, filename=filename, max_bytes=max_bytes
    )
    if stored.sha256 != client_sha256:
        filestore.delete_dir(directory.rsplit("/", 1)[0])
        db.rollback()
        raise AppError(
            "MNX-PIPE-0003",
            "받은 파일의 해시가 보낸 쪽과 다릅니다 — 전송 중 깨진 것입니다. 다시 보내세요.",
            details={"expected": client_sha256, "received": stored.sha256},
        )

    duplicate = find_duplicate(db, stored.sha256, except_id=item.id)
    if duplicate is not None:
        kind, existing_id = duplicate
        filestore.delete_dir(directory.rsplit("/", 1)[0])
        db.rollback()
        raise Conflict(
            "MNX-PIPE-0004",
            "같은 내용의 파일이 이미 있습니다.",
            details={"existing_id": str(existing_id), "existing_kind": kind},
        )

    item.size = stored.size
    item.source_path = stored.relative_path
    queue.enqueue(db, kind=kinds.PIPELINES_PARSE_INBOX, payload={"item_id": str(item.id)})
    return item


# --- 워커: 감지·파싱·후보 ------------------------------------------------------


def process(db: Session, item_id: uuid.UUID) -> str:
    """수집함 항목 하나를 읽고 후보를 찾는다. 최종 상태를 돌려준다. 워커가 부른다."""
    item = db.get(PipelineInboxItem, item_id)
    if item is None or item.status in FINAL_STATUSES:
        return "gone"
    connector = db.get(PipelineConnector, item.connector_id)
    if connector is None or not item.source_path:
        return _fail(db, item, "커넥터나 원본이 없습니다.")

    data = filestore.read_bytes(item.source_path)  # 인프라 오류는 그대로 올린다
    detected = ingest.detect(
        db, workspace_id=connector.workspace_id, filename=item.filename, data=data
    )
    if not detected.found or detected.test_type is None:
        return _fail(db, item, detected.reason)
    item.test_type_id = detected.test_type.id
    item.profile_id = detected.profile.id if detected.profile else None

    try:
        parsed = ingest.parse_with(detected, data)
    except ParseError as exc:
        return _fail(db, item, str(exc))
    except Exception as exc:  # 프로파일 버그도 그 파일에서는 계속 난다
        logger.exception("수집함 읽기 실패 (item=%s)", item.id)
        return _fail(db, item, f"파일을 읽는 중 오류가 났습니다: {exc}")

    item.summary = ingest.summarize(parsed)
    item.status = "parsed"
    item.error = None

    candidates = find_candidates(
        db, workspace_id=connector.workspace_id, identity=parsed.identity, hints=item.hints
    )
    item.candidates = [c for c in candidates if "specimen_id" in c]
    if len(item.candidates) == 1:
        specimen = db.get(Specimen, uuid.UUID(item.candidates[0]["specimen_id"]))
        if specimen is not None and specimen.deleted_at is None:
            # **기본은 승인 대기다.** 규칙이 「틀리게 맞으면」 엉뚱한 시편에 시험이
            # 붙고, 사람은 나중에 목록을 훑을 때에야 안다. 검증된 커넥터만
            # `auto_register` 로 바로 등록한다.
            if connector.auto_register:
                register(db, item, specimen=specimen, test_type=detected.test_type, actor=None)
                db.commit()
                return "registered"
            item.status = "suggested"
            item.error = None
            db.commit()
            _notify_managers(db, connector, item)
            db.commit()
            return "suggested"

    why = next((c["reason"] for c in candidates if "specimen_id" not in c), None)
    item.status = "needs_specimen"
    item.error = why
    db.commit()
    _notify_managers(db, connector, item)
    db.commit()
    return "needs_specimen"


def _fail(db: Session, item: PipelineInboxItem, reason: str) -> str:
    item.status = "failed"
    item.error = reason[:2000]
    db.commit()
    return "failed"


def find_candidates(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    identity: dict[str, str],
    hints: dict[str, str],
) -> list[dict[str, Any]]:
    """재료 → 시료 → 시편 순으로 좁힌다. 후보가 없으면 **왜 없는지**를 한 항목으로
    돌려준다(`specimen_id` 없이 `reason` 만) — 사람이 다음에 무엇을 할지 알아야 한다."""

    def pick(file_key: str, hint_key: str) -> str:
        # 파일이 이긴다 — 장비가 적은 증거다. 이름은 사람이 붙인 이름표다.
        return (identity.get(file_key) or hints.get(hint_key) or "").strip()

    material_code = pick("material_grade", "material_code")
    lot = pick("sample_lot_no", "lot")
    specimen_name = pick("specimen_name", "specimen")
    orientation = pick("specimen_orientation", "orientation").upper()
    raw_seq = pick("specimen_seq_no", "specimen")
    seq = int(raw_seq) if raw_seq.isdigit() else None

    if not material_code:
        return [
            {
                "reason": (
                    "재료 코드가 없습니다 — 파일 이름 규칙이나 프로파일의 identity 를 "
                    "확인하세요."
                )
            }
        ]

    materials = list(
        db.scalars(
            select(Material).where(
                Material.deleted_at.is_(None),
                or_(
                    Material.owner_workspace_id.is_(None),
                    Material.owner_workspace_id == workspace_id,
                ),
                or_(
                    Material.record_name == material_code,
                    Material.grade == material_code,
                    Material.alias == material_code,
                ),
            )
        )
    )
    if not materials:
        return [{"reason": f"'{material_code}' 라는 재료가 없습니다. 재료를 먼저 만드세요."}]

    samples = list(
        db.scalars(
            select(Sample).where(
                Sample.material_id.in_([m.id for m in materials]),
                Sample.workspace_id == workspace_id,
                Sample.deleted_at.is_(None),
            )
        )
    )
    if lot:
        narrowed = [s for s in samples if (s.lot_no or "") == lot]
        if narrowed:
            samples = narrowed
        else:
            return [{"reason": f"'{material_code}' 에 로트 '{lot}' 인 시료가 없습니다."}]
    if not samples:
        return [
            {"reason": f"'{material_code}' 에 시료가 없습니다. 시료와 시편을 먼저 만드세요."}
        ]

    specimens = list(
        db.scalars(
            select(Specimen).where(
                Specimen.sample_id.in_([s.id for s in samples]),
                Specimen.deleted_at.is_(None),
            )
        )
    )
    reasons = [f"재료 '{material_code}'"]
    if lot:
        reasons.append(f"로트 '{lot}'")
    if specimen_name:
        # 전체 이름(`SECC_MDOI_1.0__01__MD_01`)이든 끝자리(`MD_01`)든 — 장비는 대개
        # 끝자리만 적는다.
        exact = [
            s
            for s in specimens
            if s.record_name == specimen_name or s.record_name.endswith(f"__{specimen_name}")
        ]
        if exact:
            specimens = exact
            reasons.append(f"시편 이름 '{specimen_name}'")
    if orientation:
        by_orientation = [s for s in specimens if s.orientation == orientation]
        if by_orientation:
            specimens = by_orientation
            reasons.append(f"방향 {orientation}")
    if seq is not None:
        by_seq = [s for s in specimens if s.seq_no == seq]
        if by_seq:
            specimens = by_seq
            reasons.append(f"번호 {seq}")
    if not specimens:
        return [
            {"reason": f"'{material_code}' 아래 맞는 시편이 없습니다. 시편을 먼저 만드세요."}
        ]

    by_sample = {s.id: s for s in samples}
    by_material = {m.id: m for m in materials}
    reason = " · ".join(reasons)
    out: list[dict[str, Any]] = []
    for specimen in specimens[:MAX_CANDIDATES]:
        sample = by_sample.get(specimen.sample_id)
        material = by_material.get(sample.material_id) if sample else None
        out.append(
            {
                "specimen_id": str(specimen.id),
                "specimen_name": specimen.record_name,
                "material_name": material.record_name if material else "?",
                "sample_name": sample.record_name if sample else "?",
                "reason": reason,
            }
        )
    return out


def _notify_managers(
    db: Session, connector: PipelineConnector, item: PipelineInboxItem
) -> None:
    """부서 관리자에게. 알림 모듈의 함수는 못 부르므로 큐에 직접 넣는다(`kinds`)."""
    managers = db.scalars(
        select(WorkspaceMember.user_id).where(
            WorkspaceMember.workspace_id == connector.workspace_id,
            WorkspaceMember.role == "manager",
        )
    )
    for user_id in managers:
        queue.enqueue(
            db,
            kind=kinds.NOTIFY_DELIVER,
            payload={
                "event_kind": "pipelines.needs_specimen",
                "key": f"{item.id}",
                "title": (
                    "장비에서 온 파일이 승인을 기다립니다"
                    if item.status == "suggested"
                    else "장비에서 온 파일에 시편을 붙여 주세요"
                ),
                "body": (
                    f"{connector.name}: {item.filename} — "
                    + (
                        f"{item.candidates[0]['specimen_name']} 에 붙일 준비가 됐습니다."
                        if item.status == "suggested" and item.candidates
                        else f"{item.error or '후보가 여럿입니다.'}"
                    )
                ),
                "link": "/settings/connectors?tab=inbox",
                "to_user_id": str(user_id),
            },
        )


# --- 규칙 편집기가 묻는다 ----------------------------------------------------------


def resolve(
    db: Session, *, workspace_id: uuid.UUID, hints: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """힌트 묶음 → 「붙나 / 왜 안 붙나」. **워커와 같은 함수**(`find_candidates`)를 부른다.

    MatPylon 의 규칙 편집기가 파일 20개의 힌트를 보내 미리 본다. 여기서 「붙는다」 고
    한 것이 반입 뒤에 실제로 붙어야 하므로 규칙을 따로 두지 않는다. 파일이 없으니
    프로파일 `identity` 는 못 본다 — 그것은 반입 뒤 워커가 하고, 파일이 힌트를 이긴다.
    """
    out: list[dict[str, Any]] = []
    for hint in hints:
        found = find_candidates(db, workspace_id=workspace_id, identity={}, hints=hint)
        real = [c for c in found if "specimen_id" in c]
        if len(real) == 1:
            out.append({"outcome": "unique", "candidate": real[0], "candidates": real})
        elif real:
            out.append({"outcome": "multiple", "candidates": real})
        else:
            out.append(
                {
                    "outcome": "none",
                    "candidates": [],
                    "reason": next(
                        (c["reason"] for c in found if "reason" in c), "후보가 없습니다."
                    ),
                }
            )
    return out


def material_aliases(material: Material) -> list[str]:
    """워커가 `material_code` 를 맞출 때 보는 것과 **같은 집합**(`find_candidates`)."""
    seen: list[str] = []
    for one in (material.record_name, material.grade, material.alias):
        if one and one not in seen:
            seen.append(one)
    return seen


def reference_tree(db: Session, *, workspace_id: uuid.UUID) -> dict[str, Any]:
    """재료 → 시료 → 시편 이름. 규칙 편집기의 참조 패널이 본다 — 이름만, 편집 안 함."""
    materials = list(
        db.scalars(
            select(Material)
            .where(
                Material.deleted_at.is_(None),
                or_(
                    Material.owner_workspace_id.is_(None),
                    Material.owner_workspace_id == workspace_id,
                ),
            )
            .order_by(Material.record_name)
        )
    )
    samples = list(
        db.scalars(
            select(Sample)
            .where(
                Sample.material_id.in_([m.id for m in materials]),
                Sample.workspace_id == workspace_id,
                Sample.deleted_at.is_(None),
            )
            .order_by(Sample.seq_no)
        )
    )
    specimens = list(
        db.scalars(
            select(Specimen)
            .where(
                Specimen.sample_id.in_([s.id for s in samples]), Specimen.deleted_at.is_(None)
            )
            .order_by(Specimen.orientation, Specimen.seq_no)
        )
    )
    by_sample: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for specimen in specimens:
        by_sample.setdefault(specimen.sample_id, []).append(
            {
                "id": str(specimen.id),
                "name": specimen.record_name,
                "short": specimen.record_name.rsplit("__", 1)[-1],
                "orientation": specimen.orientation,
                "seq_no": specimen.seq_no,
            }
        )
    by_material: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for sample in samples:
        by_material.setdefault(sample.material_id, []).append(
            {
                "id": str(sample.id),
                "name": sample.record_name,
                "lot": sample.lot_no or "",
                "seq_no": sample.seq_no,
                "specimens": by_sample.get(sample.id, []),
            }
        )
    return {
        "generated_at": _now(),
        "materials": [
            {
                "id": str(m.id),
                "name": m.record_name,
                "grade": m.grade,
                "aliases": material_aliases(m),
                "samples": by_material.get(m.id, []),
            }
            for m in materials
            # 시료가 없는 재료는 뺀다 — 붙을 데가 없으니 참조에도 없는 편이 맞다.
            if m.id in by_material
        ],
    }


# --- 사람이 정한다 --------------------------------------------------------------


def _tested_at(item: PipelineInboxItem) -> datetime | None:
    raw = (item.summary.get("record") or {}).get("tested_at") or item.hints.get("tested_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def register(
    db: Session,
    item: PipelineInboxItem,
    *,
    specimen: Specimen,
    test_type: TestType,
    actor: User | None,
) -> TestRun:
    """시험을 만들고 원본을 옮긴다. 자동 등록과 사람의 붙이기가 **같은 함수**다."""
    if item.status in FINAL_STATUSES:
        raise Conflict("MNX-PIPE-0007", f"이미 {item.status} 된 항목입니다.")
    if not item.source_path:
        raise AppError("MNX-PIPE-0008", "원본 파일이 없습니다.", status=422)
    record = item.summary.get("record") or {}
    run = ingest.create_run(
        db,
        specimen=specimen,
        test_type=test_type,
        source=ingest.Source(
            relative_path=item.source_path,
            filename=item.filename,
            sha256=item.sha256,
            size=item.size,
        ),
        registered_by_id=actor.id if actor else None,
        tested_at=_tested_at(item),
        operator=record.get("operator") or item.hints.get("operator"),
        instrument=record.get("instrument") or item.hints.get("instrument"),
        note=f"장비 커넥터로 들어옴: {item.client_path}",
        profile_id=item.profile_id,
        conflict_code="MNX-PIPE-0009",
    )
    item.test_run_id = run.id
    item.source_path = None
    item.status = "registered"
    item.error = None
    item.resolved_at = _now()
    item.resolved_by_id = actor.id if actor else None
    audit.record(
        db,
        action="pipelines.inbox.register",
        actor=actor,
        target_table="test_runs",
        target_id=run.id,
        target_label=run.record_name,
        workspace_id=run.workspace_id,
        changes={"inbox_item_id": str(item.id), "auto": actor is None},
    )
    return run


def discard(db: Session, item: PipelineInboxItem, *, actor: User, reason: str) -> None:
    """버린다. 원본은 보존 기간까지 남는다 — 되돌릴 수 있어야 한다."""
    if item.status in FINAL_STATUSES:
        raise Conflict("MNX-PIPE-0007", f"이미 {item.status} 된 항목입니다.")
    item.status = "discarded"
    item.discard_reason = reason
    item.resolved_at = _now()
    item.resolved_by_id = actor.id
    audit.record(
        db,
        action="pipelines.inbox.discard",
        actor=actor,
        target_table="pipeline_inbox_items",
        target_id=item.id,
        target_label=item.filename,
        reason=reason,
    )


def retry(db: Session, item: PipelineInboxItem) -> None:
    if item.status in FINAL_STATUSES:
        raise Conflict("MNX-PIPE-0007", f"이미 {item.status} 된 항목입니다.")
    item.status = "received"
    item.error = None
    item.candidates = []
    queue.enqueue(db, kind=kinds.PIPELINES_PARSE_INBOX, payload={"item_id": str(item.id)})


def approve_suggested(db: Session, item: PipelineInboxItem, *, actor: User) -> TestRun:
    """승인 — 대기 중인 항목을 **제 후보**로 등록한다. 다른 시편에 붙이려면 assign."""
    if item.status != "suggested" or len(item.candidates) != 1:
        raise Conflict(
            "MNX-PIPE-0013",
            f"승인 대기 상태가 아닙니다({item.status}). 시편을 골라 붙여 주세요.",
        )
    specimen = db.get(Specimen, uuid.UUID(item.candidates[0]["specimen_id"]))
    if specimen is None or specimen.deleted_at is not None:
        raise Conflict("MNX-PIPE-0013", "후보 시편이 그사이 지워졌습니다. 다시 붙여 주세요.")
    test_type = db.get(TestType, item.test_type_id) if item.test_type_id else None
    if test_type is None:
        raise AppError("MNX-PIPE-0012", "감지된 시험 종류가 없습니다.", status=422)
    return register(db, item, specimen=specimen, test_type=test_type, actor=actor)


# --- 조회 보조 ------------------------------------------------------------------


def context(db: Session, items: list[PipelineInboxItem]) -> dict[str, dict[uuid.UUID, Any]]:
    """목록에 필요한 주변 정보를 한 번에(N+1 방지)."""
    if not items:
        return {"connectors": {}, "types": {}, "profiles": {}, "runs": {}}
    connectors = {
        c.id: c
        for c in db.scalars(
            select(PipelineConnector).where(
                PipelineConnector.id.in_({i.connector_id for i in items})
            )
        )
    }
    type_ids = {i.test_type_id for i in items if i.test_type_id}
    types = {t.id: t for t in db.scalars(select(TestType).where(TestType.id.in_(type_ids)))}
    profile_ids = {i.profile_id for i in items if i.profile_id}
    profiles = {
        p.id: p
        for p in db.scalars(select(FormatProfile).where(FormatProfile.id.in_(profile_ids)))
    }
    run_ids = {i.test_run_id for i in items if i.test_run_id}
    runs = {r.id: r for r in db.scalars(select(TestRun).where(TestRun.id.in_(run_ids)))}
    return {"connectors": connectors, "types": types, "profiles": profiles, "runs": runs}
