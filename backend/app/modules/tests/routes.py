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
    FormatProfile,
    TestChannel,
    TestConditionField,
    TestRun,
    TestSummary,
    TestType,
)
from app.modules.tests.schemas import (
    CleanupQueuedOut,
    CleanupRequest,
    CurvePointsOut,
    DetectOut,
    ParserOut,
    ReparseOut,
    StorageReportOut,
    TestChannelOut,
    TestConditionFieldOut,
    TestRunDetailOut,
    TestRunOut,
    TestSummaryOut,
    TestTypeCreateRequest,
    TestTypeOut,
    TestTypeSaveRequest,
)
from app.shared import filestore, permissions
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.pagination import Page, clamp_limit
from matcore import naming, parsers, readers, registry
from matcore.readers import profile as profiles

router = APIRouter(prefix="/test-types", tags=["tests"])
runs_router = APIRouter(prefix="/test-runs", tags=["tests"])
maintenance_router = APIRouter(prefix="/maintenance", tags=["tests"])

#: 차트가 한 번에 받는 점의 상한. 이보다 많이 보내 봐야 화면 픽셀에 겹친다.
MAX_CURVE_POINTS = 5000
DEFAULT_CURVE_POINTS = 1200


def _now() -> datetime:
    return datetime.now(UTC)


# --- 정의 -------------------------------------------------------------------


def _extensions(parser_key: str | None) -> list[str]:
    """파서가 선언한 확장자. 화면이 파일만 보고 종류를 추정하는 데 쓴다.

    **소문자로 내보낸다.** 디스크에 `.tra` 34개와 `.TRA` 10개가 함께 있는 것을
    실측했다(`002_Material`). 대소문자를 그대로 비교하면 절반이 안 잡힌다.
    """
    if not parser_key:
        return []
    parsers.load_builtin()
    try:
        plugin = registry.get(parser_key)
    except KeyError:
        # 정의는 있는데 파서가 등록돼 있지 않다. 목록 전체를 죽일 일은 아니다 —
        # 업로드할 때 어차피 실패하고 그때 이유가 남는다.
        return []
    declared: tuple[str, ...] = plugin.meta.get("extensions", ())
    return sorted({str(item).lower() for item in declared})


def _run_counts(db: Session, type_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """종류별 시험 수. 소프트 삭제도 센다 — 되살릴 수 있는 데이터의 해석을
    바꾸면 안 된다."""
    if not type_ids:
        return {}
    rows = db.execute(
        select(TestRun.test_type_id, func.count())
        .where(TestRun.test_type_id.in_(type_ids))
        .group_by(TestRun.test_type_id)
    )
    return {type_id: count for type_id, count in rows}


def _type_out(db: Session, test_type: TestType) -> TestTypeOut:
    """정의 하나를 응답 형태로. 목록과 편집 응답이 같은 모양이어야 화면이
    저장 뒤 다시 불러오지 않아도 된다."""
    channels = list(
        db.scalars(
            select(TestChannel)
            .where(TestChannel.test_type_id == test_type.id)
            .order_by(TestChannel.sort_order)
        )
    )
    conditions = list(
        db.scalars(
            select(TestConditionField)
            .where(TestConditionField.test_type_id == test_type.id)
            .order_by(TestConditionField.sort_order)
        )
    )
    return TestTypeOut(
        id=test_type.id,
        run_count=_run_counts(db, [test_type.id]).get(test_type.id, 0),
        key=test_type.key,
        label=test_type.label,
        abbr=test_type.abbr,
        description=test_type.description,
        parser_key=test_type.parser_key,
        extensions=_extensions(test_type.parser_key),
        is_active=test_type.is_active,
        max_upload_bytes=test_type.max_upload_bytes or get_settings().max_upload_bytes,
        channels=[
            TestChannelOut(
                key=c.key,
                label=c.label,
                dimension=c.dimension,
                si_unit=c.si_unit,
                is_required=c.is_required,
                sort_order=c.sort_order,
            )
            for c in channels
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
            for f in conditions
        ],
    )


@router.post("/detect", response_model=DetectOut)
def detect_test_type(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DetectOut:
    """이 파일이 어느 시험 종류인가. **고르는 일을 없애려고 있다.**

    확장자만으로는 부족하다. 확장자는 *파서가* 선언한 것에서 나오는데, 프로파일로
    읽는 종류는 파서가 없어서 확장자가 비어 있다 — 그래서 프로파일을 만들어 두고도
    일괄 등록에서 매번 손으로 골라야 했다.

    **지문이 확장자보다 정확하다.** `.csv` 는 어느 장비나 쓰지만 헤더의 열 이름은
    그 장비의 것이다. 프로파일을 먼저 보고, 없으면 확장자로 내려간다.

    관리자 전용이 아니다 — 파일을 올리는 사람이 쓰는 기능이다.

    화면은 **첫 조각만 보낸다.** 지문은 머리에 있고, 20개짜리 배치를 통째로 두 번
    보낼 이유가 없다.
    """
    data = file.file.read()
    filename = file.filename or "upload.dat"
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""

    # 같은 종류에 프로파일이 여럿일 수 있다(장비 소프트웨어 버전이 달라진 경우).
    # 종류별로 하나만 남기면, 우선순위는 높지만 **안 맞는** 프로파일이 맞는 것을
    # 가려 버린다. 전부 보고 우선순위 순으로 맞는 첫 번째를 쓴다.
    candidates = list(
        db.scalars(
            select(FormatProfile)
            .where(FormatProfile.is_active.is_(True))
            .order_by(FormatProfile.priority.desc(), FormatProfile.key)
        )
    )

    try:
        structure = readers.sniff(data)
    except readers.ReadError:
        structure = None

    if structure is not None:
        for candidate in candidates:
            if not profiles.matches(
                candidate.definition, filename=filename, structure=structure
            ):
                continue
            test_type = db.get(TestType, candidate.test_type_id)
            if test_type is None or not test_type.is_active:
                continue
            return DetectOut(
                filename=filename,
                test_type_key=test_type.key,
                test_type_label=test_type.label,
                profile_key=candidate.key,
                source="profile",
                reason=f"'{candidate.label}' 프로파일의 지문이 맞습니다.",
            )

    # 프로파일이 없을 때만 확장자로 내려간다. 파서가 있는 종류는 이 길로 잡힌다.
    if suffix:
        matched = [
            test_type
            for test_type in db.scalars(
                select(TestType)
                .where(TestType.is_active.is_(True))
                .order_by(TestType.sort_order, TestType.label)
            )
            if suffix in _extensions(test_type.parser_key)
        ]
        if len(matched) == 1:
            return DetectOut(
                filename=filename,
                test_type_key=matched[0].key,
                test_type_label=matched[0].label,
                profile_key=None,
                source="extension",
                reason=f"{suffix} 를 읽는 종류가 하나입니다.",
            )
        if len(matched) > 1:
            # **여럿이면 고르지 않는다.** 하나를 찍으면 그럴듯해 보이는데 틀린다.
            return DetectOut(
                filename=filename,
                test_type_key=None,
                test_type_label=None,
                profile_key=None,
                source="none",
                reason=(
                    f"{suffix} 를 읽는 종류가 {len(matched)}개입니다: "
                    f"{', '.join(t.label for t in matched)}. 골라 주세요."
                ),
            )

    return DetectOut(
        filename=filename,
        test_type_key=None,
        test_type_label=None,
        profile_key=None,
        source="none",
        reason=(
            "맞는 프로파일도 확장자도 없습니다. 종류를 고르거나 형식 프로파일을 만드세요."
        ),
    )


@router.get("/parsers", response_model=list[ParserOut])
def list_parsers(user: User = Depends(require_system_admin)) -> list[ParserOut]:
    """등록된 파서. 종류를 만들 때 여기서 고른다.

    **파서는 정의로 만들 수 없다.** 코드다(`matcore/parsers`). 정의를 데이터로
    둔 것은 "어떤 시험이 있고 무엇을 입력받는가" 까지이고, 파일을 실제로 읽는
    일은 플러그인이 한다 — 그 경계를 화면이 분명히 보여 줘야 한다.
    """
    parsers.load_builtin()
    return [
        ParserOut(
            id=plugin.id,
            label=plugin.label,
            version=plugin.version,
            extensions=sorted(
                {str(item).lower() for item in plugin.meta.get("extensions", ())}
            ),
            applies_to=list(plugin.applies_to),
        )
        for plugin in registry.list_plugins(kind="parser")
    ]


@router.post("", response_model=TestTypeOut, status_code=201)
def create_test_type(
    payload: TestTypeCreateRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TestTypeOut:
    """새 시험 종류. **배포 없이 추가된다** — 그것이 정의를 데이터로 둔 이유다."""
    if db.scalar(select(TestType).where(TestType.key == payload.key)):
        raise Conflict("MNX-TESTS-0021", f"이미 있는 시험 종류입니다: {payload.key}")
    data = payload.model_dump()
    key = data.pop("key")
    test_type = services.save_definition(db, key=key, **data)
    return _type_out(db, test_type)


@router.put("/{key}", response_model=TestTypeOut)
def update_test_type(
    key: str,
    payload: TestTypeSaveRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TestTypeOut:
    """정의 한 벌을 갈아 끼운다.

    등록된 시험이 있으면 채널의 **key·단위·차원은 거절한다** — 저장된 곡선의
    해석이 바뀌기 때문이다. 라벨·정렬·필수여부는 언제든 바꿀 수 있다.
    """
    if db.scalar(select(TestType).where(TestType.key == key)) is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    test_type = services.save_definition(db, key=key, **payload.model_dump())
    return _type_out(db, test_type)


@router.delete("/{key}", status_code=204)
def delete_test_type(
    key: str,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    services.delete_definition(db, key)
    return Response(status_code=204)


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
    counts = _run_counts(db, ids)
    return [
        TestTypeOut(
            id=t.id,
            run_count=counts.get(t.id, 0),
            key=t.key,
            label=t.label,
            abbr=t.abbr,
            description=t.description,
            parser_key=t.parser_key,
            extensions=_extensions(t.parser_key),
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
        note=run.note,
        row_count=curve.row_count if curve else None,
        channels=list(curve.channels) if curve else [],
        warnings=[w for w in warnings.split(" / ") if w],
        created_at=run.created_at,
    )


# --- 업로드 -----------------------------------------------------------------


def _json_object(text: str, label: str) -> dict[str, Any]:
    """multipart 폼으로 온 JSON 한 덩이. 객체가 아니면 거절한다."""
    try:
        parsed = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            "MNX-TESTS-0013", f"{label} JSON 형식이 잘못되었습니다.", status=422
        ) from exc
    if not isinstance(parsed, dict):
        raise AppError("MNX-TESTS-0013", f"{label} 은 객체여야 합니다.", status=422)
    return parsed


@runs_router.post("", response_model=TestRunOut, status_code=202)
def upload_test_run(
    specimen_id: uuid.UUID = Form(...),
    test_type: str = Form(..., description="시험 종류 key (예: tensile)"),
    conditions: str = Form(default="{}", description="조건 JSON"),
    condition_units: str = Form(
        default="{}",
        description="조건 키 → 화면이 받은 단위. 없으면 정의의 si_unit 으로 본다",
    ),
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
    raw_conditions = _json_object(conditions, "조건")
    # 화면은 사람이 쓰는 단위로 입력을 받는다(예: mm/min). 그 단위를 함께 보내지
    # 않으면 서버가 정의의 si_unit(m/s)으로 해석해 **6만 배** 어긋난 값을 저장한다.
    given_units = {
        str(key): str(value)
        for key, value in _json_object(condition_units, "조건 단위").items()
    }

    values, input_units = services.normalize_conditions(
        db, definition, raw_conditions, given_units
    )

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


# --- 저장소 정리 ------------------------------------------------------------
#
# **실행 경로가 없으면 만들어 둔 정리 잡은 없는 것과 같다.** 핸들러만 등록해 두고
# 큐에 넣는 곳을 안 만들어서, 한 번도 돌지 않은 채 파일이 쌓이고 있었다.


@maintenance_router.get("/storage", response_model=StorageReportOut)
def storage(
    retention_days: int | None = Query(default=None, ge=0),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> StorageReportOut:
    """무엇이 얼마나 있고 무엇을 치울 수 있는지. 읽기만 한다.

    폴더를 훑는 정도라 요청 안에서 끝난다 — 지우는 것만 워커로 넘긴다.
    """
    return StorageReportOut(**services.storage_report(db, retention_days=retention_days))


@maintenance_router.post("/cleanup", response_model=CleanupQueuedOut, status_code=202)
def cleanup(
    payload: CleanupRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> CleanupQueuedOut:
    """정리를 큐에 넣는다. 파일이 많으면 오래 걸리므로 요청을 붙잡지 않는다."""
    queue.enqueue(
        db,
        kind=kinds.TESTS_CLEANUP_STORAGE,
        payload={"dry_run": payload.dry_run, "retention_days": payload.retention_days},
    )
    db.commit()
    return CleanupQueuedOut(
        status="queued",
        message=(
            "미리보기를 큐에 넣었습니다. 로그에 결과가 남습니다."
            if payload.dry_run
            else "정리를 큐에 넣었습니다. 파일을 실제로 지웁니다."
        ),
        dry_run=payload.dry_run,
    )
