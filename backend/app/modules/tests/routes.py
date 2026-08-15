"""시험 라우터 — 정의 조회, 업로드, 곡선.

업로드는 **파일만 받고 202 로 끝낸다.** 파싱은 워커가 한다. 요청 안에서 파싱하면
큰 파일에서 브라우저가 먼저 끊고, 그때 사용자는 실패한 줄 아는데 서버는 계속
처리하고 있다. 대신 상태(`uploaded → parsing → parsed | failed`)를 DB 에 두고
목록에서 보이게 한다.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests import services
from app.modules.tests.models import (
    Curve,
    TestChannel,
    TestConditionField,
    TestRun,
    TestSummary,
    TestType,
)
from app.modules.tests.schemas import (
    CurvePointsOut,
    ReparseOut,
    TestChannelOut,
    TestConditionFieldOut,
    TestRunDetailOut,
    TestRunOut,
    TestSummaryOut,
    TestTypeOut,
)
from app.shared import filestore, permissions
from app.shared.auth import current_user
from app.shared.errors import AppError, NotFound
from app.shared.pagination import Page, clamp_limit
from matcore import naming

router = APIRouter(prefix="/test-types", tags=["tests"])
runs_router = APIRouter(prefix="/test-runs", tags=["tests"])

#: 차트가 한 번에 받는 점의 상한. 이보다 많이 보내 봐야 화면 픽셀에 겹친다.
MAX_CURVE_POINTS = 5000
DEFAULT_CURVE_POINTS = 1200


def _now() -> datetime:
    return datetime.now(UTC)


# --- 정의 -------------------------------------------------------------------


@router.get("", response_model=list[TestTypeOut])
def list_test_types(
    include_inactive: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TestTypeOut]:
    """시험 종류와 그 채널·조건 정의.

    화면이 이 응답만으로 업로드 폼을 그릴 수 있어야 한다 — 그것이 정의를 DB 에
    둔 이유다.
    """
    query = select(TestType).order_by(TestType.sort_order, TestType.label)
    if not include_inactive:
        query = query.where(TestType.is_active.is_(True))
    types = list(db.scalars(query))
    if not types:
        return []

    ids = [t.id for t in types]
    channels: dict[uuid.UUID, list[TestChannel]] = {i: [] for i in ids}
    for channel in db.scalars(
        select(TestChannel)
        .where(TestChannel.test_type_id.in_(ids))
        .order_by(TestChannel.sort_order)
    ):
        channels[channel.test_type_id].append(channel)

    conditions: dict[uuid.UUID, list[TestConditionField]] = {i: [] for i in ids}
    for field in db.scalars(
        select(TestConditionField)
        .where(TestConditionField.test_type_id.in_(ids))
        .order_by(TestConditionField.sort_order)
    ):
        conditions[field.test_type_id].append(field)

    fallback = get_settings().max_upload_bytes
    return [
        TestTypeOut(
            id=t.id,
            key=t.key,
            label=t.label,
            abbr=t.abbr,
            description=t.description,
            parser_key=t.parser_key,
            is_active=t.is_active,
            max_upload_bytes=t.max_upload_bytes or fallback,
            channels=[
                TestChannelOut(
                    key=c.key,
                    label=c.label,
                    dimension=c.dimension,
                    si_unit=c.si_unit,
                    is_required=c.is_required,
                    sort_order=c.sort_order,
                )
                for c in channels[t.id]
            ],
            conditions=[
                TestConditionFieldOut(
                    key=f.key,
                    label=f.label,
                    value_type=f.value_type,
                    dimension=f.dimension,
                    si_unit=f.si_unit,
                    choices=f.choices,
                    is_required=f.is_required,
                    sort_order=f.sort_order,
                )
                for f in conditions[t.id]
            ],
        )
        for t in types
    ]


# --- 매퍼 -------------------------------------------------------------------


def _context(db: Session, runs: list[TestRun]) -> dict[str, dict[uuid.UUID, Any]]:
    """목록에 필요한 주변 정보를 한 번에 모은다 (N+1 방지)."""
    if not runs:
        return {"specimens": {}, "samples": {}, "materials": {}, "types": {}, "curves": {}}

    specimen_ids = [r.specimen_id for r in runs]
    specimens = {
        s.id: s for s in db.scalars(select(Specimen).where(Specimen.id.in_(specimen_ids)))
    }
    sample_ids = [s.sample_id for s in specimens.values()]
    samples = {s.id: s for s in db.scalars(select(Sample).where(Sample.id.in_(sample_ids)))}
    material_ids = [s.material_id for s in samples.values()]
    materials = {
        m.id: m for m in db.scalars(select(Material).where(Material.id.in_(material_ids)))
    }
    types = {
        t.id: t
        for t in db.scalars(
            select(TestType).where(TestType.id.in_([r.test_type_id for r in runs]))
        )
    }
    curve_rows = db.scalars(
        select(Curve).where(
            Curve.test_run_id.in_([r.id for r in runs]), Curve.key == services.RAW_CURVE
        )
    )
    return {
        "specimens": specimens,
        "samples": samples,
        "materials": materials,
        "types": types,
        "curves": {c.test_run_id: c for c in curve_rows},
    }


def _run_out(run: TestRun, ctx: dict[str, dict[uuid.UUID, Any]]) -> TestRunOut:
    specimen = ctx["specimens"].get(run.specimen_id)
    sample = ctx["samples"].get(specimen.sample_id) if specimen else None
    material = ctx["materials"].get(sample.material_id) if sample else None
    test_type = ctx["types"].get(run.test_type_id)
    curve = ctx["curves"].get(run.id)
    warnings = run.source_metadata.get("_warnings", "")

    return TestRunOut(
        id=run.id,
        record_name=run.record_name,
        seq_no=run.seq_no,
        status=run.status,
        parse_error=run.parse_error,
        specimen_id=run.specimen_id,
        specimen_name=specimen.record_name if specimen else None,
        orientation=specimen.orientation if specimen else None,
        material_id=material.id if material else None,
        material_name=material.record_name if material else None,
        test_type_key=test_type.key if test_type else "?",
        test_type_label=test_type.label if test_type else "?",
        conditions=run.conditions,
        tested_at=run.tested_at,
        operator=run.operator,
        instrument=run.instrument,
        source_filename=run.source_filename,
        source_bytes=run.source_bytes,
        source_sha256=run.source_sha256,
        row_count=curve.row_count if curve else None,
        channels=list(curve.channels) if curve else [],
        warnings=[w for w in warnings.split(" / ") if w],
        created_at=run.created_at,
    )


# --- 업로드 -----------------------------------------------------------------


@runs_router.post("", response_model=TestRunOut, status_code=202)
def upload_test_run(
    specimen_id: uuid.UUID = Form(...),
    test_type: str = Form(..., description="시험 종류 key (예: tensile)"),
    conditions: str = Form(default="{}", description="조건 JSON"),
    tested_at: datetime | None = Form(default=None),
    operator: str | None = Form(default=None),
    instrument: str | None = Form(default=None),
    note: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TestRunOut:
    """원본을 받아 저장하고 파싱을 큐에 넣는다. 202 를 준다 — 아직 안 끝났다."""
    specimen = permissions.visible_specimen(db, user, specimen_id)
    definition = services.get_test_type(db, test_type)
    try:
        raw_conditions = json.loads(conditions or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            "MNX-TESTS-0013", "조건 JSON 형식이 잘못되었습니다.", status=422
        ) from exc
    if not isinstance(raw_conditions, dict):
        raise AppError("MNX-TESTS-0013", "조건은 객체여야 합니다.", status=422)

    values, input_units = services.normalize_conditions(db, definition, raw_conditions)

    seq_no = services.next_run_seq(db, specimen.id, definition.id)
    run = TestRun(
        workspace_id=specimen.workspace_id,
        specimen_id=specimen.id,
        test_type_id=definition.id,
        seq_no=seq_no,
        record_name=naming.test_run_name(
            specimen=specimen.record_name, type_abbr=definition.abbr, seq_no=seq_no
        ),
        conditions=values,
        input_units=input_units,
        tested_at=tested_at,
        operator=operator,
        instrument=instrument,
        note=note,
        status="uploaded",
        registered_by_id=user.id,
    )
    db.add(run)
    db.flush()  # id 와 created_at 이 있어야 저장 경로가 정해진다
    db.refresh(run)

    stored = filestore.save_stream(
        file.file,
        relative_dir=f"{filestore.run_dir(run.id, run.created_at)}/source",
        filename=file.filename or "upload.dat",
        max_bytes=services.upload_limit(definition),
    )
    run.source_filename = file.filename
    run.source_path = stored.relative_path
    run.source_sha256 = stored.sha256
    run.source_bytes = stored.size

    # 같은 파일을 두 번 올렸는지 알려 준다(막지는 않는다 — 재시험일 수 있다).
    duplicate = db.scalar(
        select(func.count())
        .select_from(TestRun)
        .where(
            TestRun.source_sha256 == stored.sha256,
            TestRun.id != run.id,
            TestRun.deleted_at.is_(None),
        )
    )
    if duplicate:
        run.note = (
            f"{run.note}\n" if run.note else ""
        ) + f"※ 내용이 같은 파일이 이미 {duplicate}건 등록돼 있습니다."

    # 도메인 변경과 같은 트랜잭션에 넣는다 — 따로 커밋하면 "시험은 생겼는데
    # 파싱 작업은 없는" 상태가 생긴다.
    queue.enqueue(db, kind=kinds.TESTS_PARSE_UPLOAD, payload={"test_run_id": str(run.id)})
    db.commit()
    return _run_out(run, _context(db, [run]))


# --- 조회 -------------------------------------------------------------------


@runs_router.get("", response_model=Page[TestRunOut])
def list_runs(
    workspace: str | None = Query(
        default=None, description="부서 slug — 그 부서가 등록한 것만"
    ),
    specimen_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(uploaded|parsing|parsed|failed)$"),
    limit: int | None = Query(default=None, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Page[TestRunOut]:
    """**가시 범위와 기본 필터는 다른 것이다.**

    가시 범위(`visible_runs`)는 "볼 권한이 있는가"이고 재료를 따라간다. 그런데
    화면이 `/w/:slug/tests` 라고 말해 놓고 전사를 보여 주면, 사이드바의 '부서'
    라는 말이 거짓이 된다. 부서가 하나뿐인 동안은 드러나지 않지만 두 번째 부서가
    쓰기 시작하면 바로 이상해진다.

    `workspace` 는 **좁히기만 한다.** 권한을 넓히지 않는다 — 남의 부서 slug 를
    넣어도 원래 볼 수 있던 것 안에서만 걸러진다.
    """
    query = services.visible_runs(db, user)
    if workspace:
        scope = permissions.workspace_by_slug(db, workspace)
        query = query.where(TestRun.workspace_id == scope.id)
    if specimen_id:
        query = query.where(TestRun.specimen_id == specimen_id)
    if material_id:
        query = query.where(
            TestRun.specimen_id.in_(
                select(Specimen.id)
                .join(Sample, Sample.id == Specimen.sample_id)
                .where(Sample.material_id == material_id)
            )
        )
    if status:
        query = query.where(TestRun.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    runs = list(
        db.scalars(query.order_by(TestRun.created_at.desc()).limit(size).offset(offset))
    )
    ctx = _context(db, runs)
    return Page(
        items=[_run_out(run, ctx) for run in runs], total=total, limit=size, offset=offset
    )


@runs_router.get("/{run_id}", response_model=TestRunDetailOut)
def get_run(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TestRunDetailOut:
    run = services.get_run(db, user, run_id)
    ctx = _context(db, [run])
    summary = db.scalars(
        select(TestSummary)
        .where(TestSummary.test_run_id == run.id)
        .order_by(TestSummary.source, TestSummary.key)
    )
    base = _run_out(run, ctx)
    return TestRunDetailOut(
        **base.model_dump(),
        summary=[
            TestSummaryOut(
                key=s.key,
                label=s.label,
                source=s.source,
                value=s.value_num,
                text=s.value_text,
                si_unit=s.si_unit,
            )
            for s in summary
        ],
        source_metadata={k: v for k, v in run.source_metadata.items() if k != "_warnings"},
    )


@runs_router.get("/{run_id}/curve", response_model=CurvePointsOut)
def get_curve(
    run_id: uuid.UUID,
    x: str | None = None,
    y: str | None = None,
    max_points: int = Query(default=DEFAULT_CURVE_POINTS, ge=10, le=MAX_CURVE_POINTS),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CurvePointsOut:
    """차트가 쓸 점들. 축을 고르지 않으면 정의 순서상 첫 두 채널."""
    run = services.get_run(db, user, run_id)
    if x is None or y is None:
        default_x, default_y = services.default_axes(db, run.test_type_id)
        x, y = x or default_x, y or default_y
    return CurvePointsOut(**services.curve_points(db, run, x=x, y=y, max_points=max_points))


@runs_router.get("/{run_id}/source")
def download_source(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """원본 그대로 내려받는다.

    파서가 못 읽었을 때 사람이 열어 봐야 한다 — 그 경로가 없으면 실패한 업로드는
    서버 파일시스템을 직접 뒤지는 수밖에 없다.
    """
    run = services.get_run(db, user, run_id)
    if not run.source_path:
        raise NotFound("MNX-TESTS-0014", "원본 파일이 없습니다.")
    return FileResponse(
        filestore.resolve(run.source_path),
        filename=run.source_filename or "source.dat",
        media_type="application/octet-stream",
    )


@runs_router.post("/{run_id}/reparse", response_model=ReparseOut, status_code=202)
def reparse(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReparseOut:
    """파서를 고친 뒤 다시 읽는다. 원본을 보관하는 이유가 이것이다."""
    run = services.get_run(db, user, run_id)
    if not run.source_path:
        raise AppError("MNX-TESTS-0014", "원본 파일이 없어 다시 읽을 수 없습니다.", status=422)
    run.status = "uploaded"
    run.parse_error = None
    queue.enqueue(db, kind=kinds.TESTS_PARSE_UPLOAD, payload={"test_run_id": str(run.id)})
    db.commit()
    return ReparseOut(status="queued", message="다시 읽기를 큐에 넣었습니다.")


@runs_router.delete("/{run_id}", status_code=204)
def delete_run(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """소프트 삭제. 파일은 남긴다 — 실수로 지운 것을 되돌릴 수 있어야 한다.

    파일은 오펀 정리 잡이 나중에 치운다. 여기서 바로 지우면 되돌릴 방법이 없고,
    커밋이 실패했을 때 파일만 사라진 상태가 된다.
    """
    run = services.get_run(db, user, run_id)
    run.deleted_at = _now()
    db.commit()
    return Response(status_code=204)
