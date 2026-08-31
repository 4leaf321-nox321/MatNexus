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
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.jobs import kinds, queue
from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests import formats, importing, services
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
    AppliedDimensionsOut,
    CleanupQueuedOut,
    CleanupRequest,
    CurveOut,
    CurvePointsOut,
    DetectOut,
    InstrumentDimensionOut,
    InstrumentDimensionsOut,
    ParserOut,
    ReparseOut,
    ReparseRequest,
    RetypeOut,
    RetypeRequest,
    RunBulkUpdateOut,
    RunBulkUpdateRequest,
    RunDeleteOut,
    RunDeleteRequest,
    RunFacetOut,
    RunFacetsOut,
    StorageReportOut,
    SummaryImportItemOut,
    SummaryImportOut,
    SummaryImportRequest,
    TestChannelOut,
    TestConditionFieldOut,
    TestRunDetailOut,
    TestRunOut,
    TestSummaryOut,
    TestTypeCapabilityOut,
    TestTypeCreateRequest,
    TestTypeOut,
    TestTypeUpdateRequest,
)
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.modules.vocabulary import services as vocabulary_services
from app.modules.workspaces.models import Workspace
from app.shared import (
    audit,
    contention,
    curvedata,
    filestore,
    permissions,
    revision,
    sorting,
    specimen_size,
)
from app.shared import divisions as divisions_order
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.pagination import Page, clamp_limit
from app.shared.permissions import (
    require_owner_edit,
    resolve_owner_workspace,
    visible_owner_clause,
)
from matcore import naming, parsers, processing, readers, registry
from matcore.groups import prony as _prony_group  # noqa: F401  (등록시킨다)
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


def _profile_extensions(
    db: Session, user: User, type_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """종류별로, 그 종류를 읽는 **파일 형식**이 받는 확장자.

    **가시 범위를 따른다** — 안 보이는 프로파일의 확장자를 「받는다」 고 적으면,
    그 파일을 올린 사람은 왜 안 읽히는지 알 방법이 없다(자동 추정과 같은 판단).
    """
    if not type_ids:
        return {}
    found: dict[uuid.UUID, set[str]] = {}
    rows = db.scalars(
        formats.visible_profiles(db, user).where(
            FormatProfile.is_active.is_(True),
            FormatProfile.test_type_id.in_(type_ids),
        )
    )
    for profile in rows:
        match = profile.definition.get("match") or {}
        for item in match.get("extensions", ()):
            found.setdefault(profile.test_type_id, set()).add(str(item).lower())
    return {type_id: sorted(values) for type_id, values in found.items()}


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


def _visible_types(db: Session, user: User) -> Select[tuple[TestType]]:
    """내 부서 것 + 전역. 재료·형식 프로파일과 **같은 규칙, 같은 코드**다.

    **지운 것은 여기서 빠진다.** 소프트 삭제라 행은 남는데, 이 한 곳을 안 거르면
    지운 정의가 업로드 폼의 드롭다운에 그대로 뜬다 — 목록·상세·삭제가 모두 이
    함수를 지나므로 여기가 유일한 관문이다.
    """
    return select(TestType).where(
        visible_owner_clause(db, user, TestType.owner_workspace_id),
        TestType.deleted_at.is_(None),
    )


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
    owner = (
        db.get(Workspace, test_type.owner_workspace_id)
        if test_type.owner_workspace_id
        else None
    )
    return TestTypeOut(
        id=test_type.id,
        run_count=_run_counts(db, [test_type.id]).get(test_type.id, 0),
        key=test_type.key,
        owner_workspace_slug=owner.slug if owner else None,
        owner_workspace_name=owner.name if owner else None,
        is_global=test_type.owner_workspace_id is None,
        label=test_type.label,
        abbr=test_type.abbr,
        description=test_type.description,
        parser_key=test_type.parser_key,
        extensions=_extensions(test_type.parser_key),
        is_active=test_type.is_active,
        max_upload_bytes=test_type.max_upload_bytes,
        max_upload_bytes_effective=(
            test_type.max_upload_bytes or get_settings().max_upload_bytes
        ),
        revision=test_type.revision,
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
    # 자동 추정도 **가시 범위**를 따른다. 화면에 안 보이는 프로파일이 종류를
    # 정해 버리면, 사람은 왜 그 종류가 골라졌는지 알 방법이 없다.
    candidates = list(
        db.scalars(
            formats.visible_profiles(db, user)
            .where(FormatProfile.is_active.is_(True))
            .order_by(
                FormatProfile.owner_workspace_id.is_(None),
                FormatProfile.priority.desc(),
                FormatProfile.key,
            )
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


@router.get("/capabilities", response_model=list[TestTypeCapabilityOut])
def list_capabilities(user: User = Depends(current_user)) -> list[TestTypeCapabilityOut]:
    """**어떤 채널이 무엇을 여는가.** 시험 종류를 만드는 화면이 참조한다.

    계산은 채널을 **이름으로** 찾는다(`registry.requires_channels`). 그래서 저장
    탄성률을 `E_prime` 이라고 적으면 DMA 단계가 목록에서 조용히 사라진다 — 막히는
    것이 아니라 안 보이는 것이라, 사람은 「이 기능이 없구나」 로 읽는다.

    요건을 적어 둔 자리는 레지스트리 하나뿐이고, 이 응답이 그것을 그대로 옮긴다.
    """
    processing.load_builtin()
    return [
        TestTypeCapabilityOut(
            id=plugin.id,
            label=plugin.label,
            kind=plugin.kind,
            requires_channels=[list(one) for one in plugin.requires_channels],
        )
        for plugin in registry.list_plugins()
        if plugin.requires_channels
    ]


@router.get("/parsers", response_model=list[ParserOut])
def list_parsers(user: User = Depends(current_user)) -> list[ParserOut]:
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
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TestTypeOut:
    """새 시험 종류. **배포 없이 추가된다** — 그것이 정의를 데이터로 둔 이유다.

    **부서 관리자도 만든다**(ADR 0006). 새 장비를 붙이는 일은 사업부에서 시작되고,
    새 장비란 대개 없는 종류를 재는 장비다. 시스템 관리자만 만들 수 있게 두었을
    때는 형식 프로파일 화면에서 매핑을 다 끝낸 뒤 저장 순간 403 이 났다.

    키는 **전사에서 유일하다.** 두 부서가 같은 시험을 하면 종류를 둘로 만들 것이
    아니라 하나를 같이 써야 하고, 여기서 부딪히면 그 사실을 알게 된다.
    """
    # **지운 것은 안 센다.** 소프트 삭제라 행은 남는데, 여기서 세면 지운 종류의
    # key 로 다시 만들 수 없으면서 화면 어디에도 그것이 없다 — 재료가 그 상태로
    # 이관을 막았다(2026-08-28). 되살리는 길은 휴지통이다.
    existing = db.scalar(
        select(TestType).where(TestType.key == payload.key, TestType.deleted_at.is_(None))
    )
    if existing:
        owner = (
            db.get(Workspace, existing.owner_workspace_id)
            if existing.owner_workspace_id
            else None
        )
        whose = f"{owner.name} 부서가" if owner else "전사에"
        raise Conflict(
            "MNX-TESTS-0021",
            f"이미 있는 시험 종류입니다: {payload.key} ({whose} 만들어 둔 "
            f"'{existing.label}'). 같은 시험이면 그것을 쓰고, 다른 시험이면 "
            f"키를 다르게 지으세요.",
        )
    data = payload.model_dump()
    key = data.pop("key")
    owner_slug = data.pop("owner_workspace_slug", None)
    owner_id = resolve_owner_workspace(
        db, user, owner_slug, what="시험 종류", code="MNX-TESTS-0029"
    )
    test_type = services.save_definition(db, key=key, owner_workspace_id=owner_id, **data)
    return _type_out(db, test_type)


@router.put("/{key}", response_model=TestTypeOut)
def update_test_type(
    key: str,
    payload: TestTypeUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TestTypeOut:
    """정의 한 벌을 갈아 끼운다.

    등록된 시험이 있으면 채널의 **key·단위·차원은 거절한다** — 저장된 곡선의
    해석이 바뀌기 때문이다. 라벨·정렬·필수여부는 언제든 바꿀 수 있다.
    """
    existing = db.scalar(_visible_types(db, user).where(TestType.key == key))
    if existing is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    require_owner_edit(
        db, user, existing.owner_workspace_id, what="시험 종류", code="MNX-TESTS-0029"
    )
    # **덮어쓰기를 막는다**(ADR 0015). 정의를 한 벌 통째로 갈아 끼우므로, 뒤에
    # 저장한 쪽이 앞의 채널·조건을 통째로 지운다 — 덮는 것이 아니라 지우는 것이다.
    revision.guard(
        db, existing, payload.expected_revision, what="시험 종류", code="MNX-TESTS-0030"
    )
    # **자식만 바뀌어도 올린다.** 여기서 올려 두면 `save_definition` 의 커밋에
    # 함께 실린다 — `updated_at` 이 못 하던 바로 그 일이다.
    revision.bump(existing)
    body = payload.model_dump()
    body.pop("expected_revision", None)
    test_type = services.save_definition(db, key=key, actor=user, **body)
    return _type_out(db, test_type)


@router.delete("/{key}", status_code=204)
def delete_test_type(
    key: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    existing = db.scalar(_visible_types(db, user).where(TestType.key == key))
    if existing is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    require_owner_edit(
        db, user, existing.owner_workspace_id, what="시험 종류", code="MNX-TESTS-0029"
    )
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
    query = _visible_types(db, user).order_by(TestType.sort_order, TestType.label)
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
    # **한 번에 긁는다.** 종류마다 물으면 목록 하나에 쿼리가 종류 수만큼 붙는다.
    profile_suffixes = _profile_extensions(db, user, ids)
    # 소유 부서를 한 번에 긁는다. 종류마다 `db.get` 하면 목록 하나에 쿼리가
    # 종류 수만큼 붙는다(CLAUDE.md: N+1 은 명시적 join 으로 막는다).
    owner_ids = {t.owner_workspace_id for t in types if t.owner_workspace_id}
    owners = {
        w.id: w
        for w in db.scalars(select(Workspace).where(Workspace.id.in_(owner_ids)))
        if owner_ids
    }
    return [
        TestTypeOut(
            id=t.id,
            run_count=counts.get(t.id, 0),
            key=t.key,
            owner_workspace_slug=(
                owners[t.owner_workspace_id].slug if t.owner_workspace_id in owners else None
            ),
            owner_workspace_name=(
                owners[t.owner_workspace_id].name if t.owner_workspace_id in owners else None
            ),
            is_global=t.owner_workspace_id is None,
            label=t.label,
            abbr=t.abbr,
            description=t.description,
            parser_key=t.parser_key,
            extensions=_extensions(t.parser_key),
            profile_extensions=profile_suffixes.get(t.id, []),
            is_active=t.is_active,
            max_upload_bytes=t.max_upload_bytes,
            max_upload_bytes_effective=t.max_upload_bytes or fallback,
            revision=t.revision,
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
        return {
            "specimens": {},
            "samples": {},
            "materials": {},
            "types": {},
            "curves": {},
            "results": {},
            "users": {},
        }

    # **올린 사람.** 파일이 이상할 때 물어볼 데가 거기다.
    people = {
        u.id: u
        for u in db.scalars(
            select(User).where(
                User.id.in_([r.registered_by_id for r in runs if r.registered_by_id])
            )
        )
    }
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
    # **`raw` 만 보면 안 된다.** 표가 여럿인 파일은 표 이름이 키가 되고 `raw` 가
    # 아예 없다 — 그때 목록의 행수·채널이 비어 보였다.
    by_run = services.curves_of(db, [r.id for r in runs])
    curve_rows = [items[0] for items in by_run.values() if items]
    # **처리 진행이 목록에서 보여야 한다.** 시편 20개짜리 배치에서 무엇이 아직
    # 처리 안 됐는지를 하나씩 열어 봐야 아는 것은 일이 아니다. 시험마다 세는
    # 대신 한 번에 집계한다(CLAUDE.md: N+1 은 명시적 join 으로 막는다).
    counts = {
        run_id: count
        for run_id, count in db.execute(
            select(ProcessingResult.test_run_id, func.count())
            .where(ProcessingResult.test_run_id.in_([r.id for r in runs]))
            .group_by(ProcessingResult.test_run_id)
        )
    }
    # **마스터커브가 있나.** 글로벌 피팅은 그것이 있는 시험만 쓸 수 있는데, 없는
    # 것을 목록에 두면 골라 보고서야 안다 — 그리고 변형률 스윕처럼 **애초에 만들
    # 수 없는** 시험도 같은 목록에 섞여 있다(둘 다 시험종류가 `dma_sweep` 이다).
    #
    # 시험마다 세지 않고 한 번에 집계한다(CLAUDE.md: N+1 은 명시적 join 으로 막는다).
    curves_made = {
        run_id: count
        for run_id, count in db.execute(
            select(MasterCurve.test_run_id, func.count())
            .where(MasterCurve.test_run_id.in_([r.id for r in runs]))
            .group_by(MasterCurve.test_run_id)
        )
    }
    return {
        "specimens": specimens,
        "samples": samples,
        "materials": materials,
        "types": types,
        "curves": {c.test_run_id: c for c in curve_rows},
        "results": counts,
        "master_curves": curves_made,
        "users": people,
    }


def _run_out(run: TestRun, ctx: dict[str, dict[uuid.UUID, Any]]) -> TestRunOut:
    specimen = ctx["specimens"].get(run.specimen_id)
    sample = ctx["samples"].get(specimen.sample_id) if specimen else None
    material = ctx["materials"].get(sample.material_id) if sample else None
    test_type = ctx["types"].get(run.test_type_id)
    person = ctx["users"].get(run.registered_by_id) if run.registered_by_id else None
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
        specimen_standard=specimen.standard if specimen else None,
        registered_by=person.display_name if person else None,
        material_id=material.id if material else None,
        material_name=material.record_name if material else None,
        test_type_key=test_type.key if test_type else "?",
        test_type_label=test_type.label if test_type else "?",
        conditions=run.conditions,
        tested_at=run.tested_at,
        operator=run.operator,
        instrument=run.instrument,
        division=run.division,
        source_filename=run.source_filename,
        source_bytes=run.source_bytes,
        source_sha256=run.source_sha256,
        note=run.note,
        row_count=curve.row_count if curve else None,
        channels=list(curve.channels) if curve else [],
        warnings=[w for w in warnings.split(" / ") if w],
        result_count=int(ctx["results"].get(run.id, 0)),
        master_curve_count=int(ctx["master_curves"].get(run.id, 0)),
        temperature_step_count=run.temperature_step_count,
        adopted_result_id=run.adopted_result_id,
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


def _import_out(rows: list[importing.Row]) -> SummaryImportOut:
    return SummaryImportOut(
        created=sum(1 for row in rows if row.status == "new"),
        existing=sum(1 for row in rows if row.status == "existing"),
        skipped=sum(1 for row in rows if row.status == "skipped"),
        rejected=sum(1 for row in rows if row.status == "rejected"),
        specimens_created=sum(
            1 for row in rows if row.status == "new" and row.creates_specimen
        ),
        items=[
            SummaryImportItemOut(
                input=row.raw,
                status=row.status,
                specimen=row.specimen.record_name
                if row.specimen
                else row.specimen_label or None,
                creates_specimen=row.creates_specimen,
                run=row.run_name,
                conditions=row.conditions,
                summaries={
                    key: (value if value is not None else (text or ""))
                    for key, _label, value, text, _unit in row.summaries
                },
                reason=row.reason,
                warnings=row.warnings,
            )
            for row in rows
        ],
    )


def _import_target(
    db: Session, user: User, payload: SummaryImportRequest
) -> tuple[Sample, TestType]:
    # 시편과 같은 가시 범위를 쓴다 — 재료를 볼 수 있으면 그 시료도 본다.
    sample = db.scalar(
        select(Sample).where(
            Sample.id == payload.sample_id,
            Sample.deleted_at.is_(None),
            Sample.material_id.in_(permissions.visible_material_ids(db, user)),
        )
    )
    if sample is None:
        raise NotFound("MNX-TESTS-0033", "시료를 찾을 수 없습니다.")
    return sample, services.get_test_type(db, payload.test_type)


@runs_router.post("/import/preview", response_model=SummaryImportOut)
def preview_summary_import(
    payload: SummaryImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SummaryImportOut:
    """표가 **어떤 시험이 될지** 미리 말한다. 아무것도 쓰지 않는다.

    미리보기와 실제 흡수가 **같은 코드로** 답한다 — 두 곳에 두면 갈라지고,
    그러면 미리보기가 거짓말을 한다.
    """
    sample, definition = _import_target(db, user, payload)
    rows = importing.plan(
        db,
        sample=sample,
        definition=definition,
        lines=payload.values,
        create_missing=payload.create_missing,
    )
    return _import_out(rows)


@runs_router.post("/import", response_model=SummaryImportOut)
def import_summaries(
    payload: SummaryImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SummaryImportOut:
    """표를 시험으로 만든다. **곡선은 없다.**

    곡선이 없다고 못 쓰는 데이터가 아니다 — 통계도 되고 카드의 근거도 된다.
    안 되는 것은 곡선을 다시 처리하는 일뿐이다.
    """
    sample, definition = _import_target(db, user, payload)
    rows = importing.plan(
        db,
        sample=sample,
        definition=definition,
        lines=payload.values,
        create_missing=payload.create_missing,
    )
    importing.require_columns(rows)
    importing.apply(db, sample=sample, definition=definition, rows=rows, user_id=user.id)
    db.commit()

    return _import_out(rows)


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
    division: str | None = Form(default=None),
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

    def _make() -> TestRun:
        """회차를 받아 시험을 만든다. **번호 읽기부터 flush 까지가 한 덩이다.**

        둘이 같은 순간에 올리면 같은 회차를 읽고, 뒤엣것이 유니크에 부딪힌다
        (실측 2026-08-28). 다시 할 때 **번호도 다시 읽어야** 하므로 여기 안에
        둔다 — 바깥에서 정해 넘기면 재시도가 같은 번호로 또 부딪힌다.

        일괄 등록이 이 자리를 특히 많이 지난다.
        """
        seq_no = services.next_run_seq(db, specimen.id, definition.id)
        made = TestRun(
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
            note=note,
            status="uploaded",
            registered_by_id=user.id,
        )
        # 장비 기준정보(ADR 0010). 'Zwick Z100' 과 'zwick z100' 이 갈리면 장비별
        # 비교가 무의미해진다.
        vocabulary_services.apply_bindings(
            db,
            made,
            vocabulary_services.TEST_RUN_BINDINGS,
            {"instrument": instrument, "division": division},
            created_by_id=user.id,
        )
        db.add(made)
        db.flush()  # id 와 created_at 이 있어야 저장 경로가 정해진다
        return made

    # **파일을 저장하기 전에 부딪힌다.** 회차 충돌은 이 flush 에서 나므로,
    # 다시 해도 저장한 파일이 남지 않는다.
    run = contention.with_retry(
        db,
        _make,
        code="MNX-TESTS-0032",
        message=(
            "같은 순간에 여러 사람이 이 시편에 시험을 올리고 있습니다. 다시 시도해 주세요."
        ),
    )
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


#: 시험 목록에서 정렬할 수 있는 열. **화면이 목록을 정하지 않는다.**
#:
#: 시험일(`tested_at`)이 등록 일시와 따로 있는 것이 요점이다 — 옛 시험을 오늘
#: 올리는 일이 흔하고(이관), 그때 둘은 몇 달 벌어진다. 어느 것으로 볼지는 보는
#: 사람이 정한다.
RUN_SORTS = {
    "created_at": TestRun.created_at,
    "record_name": TestRun.record_name,
    "tested_at": TestRun.tested_at,
    "operator": TestRun.operator,
    "instrument": TestRun.instrument,
    "division": TestRun.division,
    "status": TestRun.status,
}


@runs_router.get("", response_model=Page[TestRunOut])
def list_runs(
    workspace: str | None = Query(
        default=None, description="부서 slug — 그 부서가 등록한 것만"
    ),
    specimen_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(uploaded|parsing|parsed|failed)$"),
    test_type_key: str | None = Query(default=None),
    orientation: str | None = Query(default=None),
    registered_by: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    testing_group: str | None = Query(default=None),
    division: str | None = Query(default=None),
    q: str | None = Query(default=None),
    adopted: bool | None = Query(
        default=None, description="채택된 처리 결과가 있는가 — 없는 것만 보려면 false"
    ),
    sort: str | None = Query(default=None, description="정렬할 열. 기본은 등록 일시"),
    desc: bool = Query(default=True, description="내림차순. 기본은 최근 등록순"),
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

    `adopted=false` 는 **"올렸는데 아직 아무것도 안 한 것"** 을 세는 자리다.
    부서 홈이 "처리 대기 N건" 을 말하려면 서버가 세야 한다 — 목록을 받아 화면이
    세면 상한(`limit`)에 걸린 순간 숫자가 조용히 틀린다.
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
    # **거르는 일은 서버가 한다.** 한 쪽만 받아 화면에서 거르면 뒤엣것이 없는
    # 시험이 된다 — 목록이 조용히 잘리는 것이 가장 나쁘다(이 화면의 머리말이
    # 그 이야기다).
    if test_type_key:
        found = db.scalar(select(TestType).where(TestType.key == test_type_key))
        query = query.where(
            TestRun.test_type_id == (found.id if found else None),
            TestRun.test_type_id.is_not(None),
        )
    if orientation == EMPTY_FILTER_KEY:
        query = query.where(
            TestRun.specimen_id.in_(select(Specimen.id).where(Specimen.orientation.is_(None)))
        )
    elif orientation:
        query = query.where(
            TestRun.specimen_id.in_(
                select(Specimen.id).where(Specimen.orientation == orientation)
            )
        )
    if registered_by == EMPTY_FILTER_KEY:
        # **계정이 지워진 것도 여기 걸린다.** 기록은 남고 이름만 사라지는데,
        # 그것도 「등록한 사람을 모르는」 상태다.
        query = query.where(TestRun.registered_by_id.is_(None))
    elif registered_by:
        query = query.where(
            TestRun.registered_by_id.in_(
                select(User.id).where(User.display_name == registered_by)
            )
        )
    if operator == EMPTY_FILTER_KEY:
        query = query.where(TestRun.operator.is_(None))
    elif operator:
        query = query.where(TestRun.operator == operator)
    if testing_group == EMPTY_FILTER_KEY:
        # **키가 아예 없는 것과 값이 비어 있는 것을 같게 본다.** `->>` 는 둘 다
        # NULL 로 낸다 — 사람에게는 어느 쪽이든 「안 적은 것」 이다.
        query = query.where(TestRun.conditions["testing_group"].astext.is_(None))
    elif testing_group:
        # **JSONB 안의 글자 하나로 거른다.** `->>` 는 텍스트로 꺼내므로 값이
        # 없는 행은 NULL 이 되어 자연히 빠진다.
        query = query.where(TestRun.conditions["testing_group"].astext == testing_group)
    if division == EMPTY_FILTER_KEY:
        query = query.where(TestRun.division.is_(None))
    elif division:
        query = query.where(TestRun.division == division)
    if q and (text := q.strip()):
        like = f"%{text}%"
        query = query.where(
            or_(TestRun.record_name.ilike(like), TestRun.source_filename.ilike(like))
        )
    if adopted is not None:
        query = query.where(
            TestRun.adopted_result_id.is_not(None)
            if adopted
            else TestRun.adopted_result_id.is_(None)
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    size = clamp_limit(limit)
    runs = list(
        db.scalars(
            query.order_by(
                *sorting.order_by(
                    RUN_SORTS,
                    sort=sort,
                    desc=desc,
                    default="created_at",
                    tiebreaker=TestRun.id,
                )
            )
            .limit(size)
            .offset(offset)
        )
    )
    ctx = _context(db, runs)
    return Page(
        items=[_run_out(run, ctx) for run in runs], total=total, limit=size, offset=offset
    )


@runs_router.get("/facets", response_model=RunFacetsOut)
def run_facets(
    workspace: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunFacetsOut:
    """무엇으로 거를 수 있나. **화면이 목록에서 세지 않는다.**

    한 쪽만 받아 세면 「인장시험 50」이라고 적히는데 실제로는 300건일 수 있고,
    그러면 필터 옆의 숫자가 거짓말을 한다(카드 목록과 같은 판단).

    **지금 걸린 필터를 안 본다** — 「무엇이 있나」를 답하는 자리다.
    """
    query = services.visible_runs(db, user)
    if workspace:
        scope = permissions.workspace_by_slug(db, workspace)
        query = query.where(TestRun.workspace_id == scope.id)
    base = query.subquery()

    def tally(column: Any) -> list[tuple[Any, int]]:
        return [
            (row[0], int(row[1]))
            for row in db.execute(
                select(column, func.count()).select_from(base).group_by(column)
            ).all()
        ]

    labels = {row.id: (row.key, row.label) for row in db.scalars(select(TestType))}
    names = {row.id: row.display_name for row in db.scalars(select(User))}
    kinds = [
        RunFacetOut(
            key=labels.get(key, (str(key), str(key)))[0],
            label=labels.get(key, (str(key), str(key)))[1],
            count=count,
        )
        for key, count in tally(base.c.test_type_id)
        if key is not None
    ]
    people = [
        RunFacetOut(key=names[key], label=names[key], count=count)
        for key, count in tally(base.c.registered_by_id)
        if key is not None and key in names
    ]

    def empty_row(pairs: list[tuple[Any, int]]) -> RunFacetOut | None:
        """빈 값의 수. **없으면 줄을 안 낸다** — 0 짜리 줄은 고를 수 없는 선택지다.

        빈 것을 못 고르면 「사업부를 안 적은 시험」 을 찾을 길이 목록을 눈으로
        훑는 것뿐이다. 스무 건이면 되지만 이백 건이면 안 된다.
        """
        total = sum(count for value, count in pairs if value is None or value == "")
        if total == 0:
            return None
        return RunFacetOut(key=EMPTY_FILTER_KEY, label=EMPTY_FILTER_LABEL, count=total)

    def with_empty(rows: list[RunFacetOut], pairs: list[tuple[Any, int]]) -> list[RunFacetOut]:
        """**「없음」 은 늘 끝에 둔다.** 값들 사이에 가나다순으로 끼면 눈이 못 찾는다."""
        blank = empty_row(pairs)
        return [*rows, blank] if blank is not None else rows

    # **차례는 한 군데서 정한다.** 그룹핑이 준 순서를 그대로 쓰면 거르기 목록이
    # 홈의 표와 다른 차례로 서고, 사람은 그것을 다른 목록으로 읽는다.
    divisions = sorted(
        (
            RunFacetOut(key=str(value), label=str(value), count=count)
            for value, count in tally(base.c.division)
            if value
        ),
        key=lambda one: divisions_order.rank(one.key),
    )
    orientation_pairs = [
        (value, int(count))
        for value, count in db.execute(
            select(Specimen.orientation, func.count())
            .select_from(base)
            .join(Specimen, Specimen.id == base.c.specimen_id)
            .group_by(Specimen.orientation)
        ).all()
    ]
    group_pairs = [
        (value, int(count))
        for value, count in db.execute(
            select(base.c.conditions["testing_group"].astext.label("g"), func.count())
            .select_from(base)
            .group_by("g")
        ).all()
    ]
    # 방향은 시편에 있다 — 시험에서 바로 못 센다.
    directions = [
        RunFacetOut(key=str(value), label=str(value), count=count)
        for value, count in orientation_pairs
        if value
    ]
    statuses = [
        RunFacetOut(key=str(value), label=str(value), count=count)
        for value, count in tally(base.c.status)
    ]
    operators = [
        RunFacetOut(key=str(value), label=str(value), count=count)
        for value, count in tally(base.c.operator)
        if value
    ]
    # **조건 dict 안이라 컬럼처럼 못 센다.** `->>` 로 꺼내 묶는다.
    groups = [
        RunFacetOut(key=str(value), label=str(value), count=count)
        for value, count in group_pairs
        if value
    ]
    return RunFacetsOut(
        test_types=sorted(kinds, key=lambda one: one.label),
        orientations=with_empty(
            sorted(directions, key=lambda one: one.label), orientation_pairs
        ),
        registrants=with_empty(
            sorted(people, key=lambda one: one.label), tally(base.c.registered_by_id)
        ),
        operators=with_empty(
            sorted(operators, key=lambda one: one.label), tally(base.c.operator)
        ),
        testing_groups=with_empty(sorted(groups, key=lambda one: one.label), group_pairs),
        divisions=with_empty(
            sorted(divisions, key=lambda one: one.label), tally(base.c.division)
        ),
        statuses=sorted(statuses, key=lambda one: one.key),
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
    fits = db.scalar(
        select(func.count())
        .select_from(PronyFit)
        .join(MasterCurve, MasterCurve.id == PronyFit.master_curve_id)
        .where(MasterCurve.test_run_id == run.id)
    )
    return TestRunDetailOut(
        **base.model_dump(),
        prony_fit_count=int(fits or 0),
        summary=[
            TestSummaryOut(
                key=s.key,
                label=s.label,
                source=s.source,
                value=s.value_num,
                text=s.value_text,
                si_unit=s.si_unit,
                dimension=s.dimension,
            )
            for s in summary
        ],
        source_metadata={k: v for k, v in run.source_metadata.items() if k != "_warnings"},
        parser_version=run.parser_version,
        parse_profile_key=(
            pinned.key if (pinned := db.get(FormatProfile, run.parse_profile_id)) else None
        )
        if run.parse_profile_id
        else None,
        curves=[
            CurveOut(
                key=curve.key,
                label=curve.label,
                kind=curve.kind,
                row_count=curve.row_count,
                channels=list(curve.channels),
            )
            for curve in services.curves_of(db, [run.id]).get(run.id, [])
        ],
    )


@runs_router.get("/{run_id}/curve", response_model=CurvePointsOut)
def get_curve(
    run_id: uuid.UUID,
    x: str | None = None,
    y: str | None = None,
    curve: str | None = Query(default=None, description="곡선 키. 없으면 첫 곡선"),
    max_points: int = Query(default=DEFAULT_CURVE_POINTS, ge=10, le=MAX_CURVE_POINTS),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CurvePointsOut:
    """차트가 쓸 점들. 축을 고르지 않으면 정의 순서상 첫 두 채널.

    `curve` 를 받는 이유: 한 시험이 곡선을 여럿 가질 수 있다(DMA 의 `[step]`).
    안 주면 첫 곡선 — 표가 하나뿐인 파일에서는 예전과 같다.
    """
    run = services.get_run(db, user, run_id)
    if x is None or y is None:
        default_x, default_y = services.default_axes(db, run.test_type_id)
        x, y = x or default_x, y or default_y
    return CurvePointsOut(
        **services.curve_points(db, run, x=x, y=y, max_points=max_points, curve_key=curve)
    )


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


@runs_router.post("/{run_id}/test-type", response_model=RetypeOut, status_code=202)
def retype(
    run_id: uuid.UUID,
    payload: RetypeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RetypeOut:
    """올릴 때 종류를 잘못 고른 시험을 바로잡는다.

    ## 왜 아무 때나 못 바꾸는가

    시험 종류는 **이름의 한 칸**이고(ADR 0004), 회차도 종류별로 매긴다. 그것만
    이면 다시 지으면 되는데, 종류가 바뀌면 **이미 나온 것들이 전부 뜻을 잃는다**.

      * 곡선은 옛 종류의 채널로 읽힌 것이다.
      * 처리 결과는 그 채널을 입력으로 삼았고 **불변**이다 — 고쳐 끼울 수 없다.
      * 조건값은 옛 종류의 칸에 맞춰 단위까지 정규화돼 있다.

    그래서 **아직 아무것도 안 나온 시험만** 바꾼다. 곡선도 처리 결과도 없고
    채택도 안 된 것 — 올리자마자 읽기에 실패한 시험이 정확히 그 상태다.

    이미 읽힌 시험을 바꾸려면 지우고 다시 올리는 편이 낫다. 여기서 곡선과
    결과를 말없이 지워 주면, 그 사람은 **무엇이 사라졌는지 모른 채** 새 이름을
    얻는다.
    """
    run = services.get_run(db, user, run_id)

    made = db.scalar(
        select(func.count()).select_from(Curve).where(Curve.test_run_id == run.id)
    )
    results = db.scalar(
        select(func.count())
        .select_from(ProcessingResult)
        .where(ProcessingResult.test_run_id == run.id)
    )
    if made or results or run.adopted_result_id is not None:
        raise AppError(
            "MNX-TESTS-0023",
            f"이미 읽힌 시험입니다(곡선 {made or 0}개 · 처리 결과 {results or 0}건). "
            "종류를 바꾸면 그것들이 무엇의 결과인지 알 수 없게 됩니다 — "
            "지우고 올바른 종류로 다시 올리세요.",
            status=409,
        )

    fresh = services.get_test_type(db, payload.test_type_key)
    if fresh.id == run.test_type_id:
        raise AppError("MNX-TESTS-0024", "이미 그 종류입니다.", status=422)

    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        raise NotFound("MNX-TESTS-0025", "시편을 찾을 수 없습니다.")

    before = run.record_name
    # **새 종류 안에서 다시 채번한다.** 회차는 종류별이라, 옛 번호를 들고 가면
    # 새 종류에서 이미 쓰인 번호와 부딪힌다.
    run.seq_no = services.next_run_seq(db, specimen.id, fresh.id)
    run.test_type_id = fresh.id
    run.record_name = naming.test_run_name(
        specimen=specimen.record_name, type_abbr=fresh.abbr, seq_no=run.seq_no
    )

    # 조건은 **새 종류에도 있는 칸만** 남긴다. 옛 칸의 값을 들고 있으면 화면이
    # 그리지도 못하면서 저장돼 있게 된다.
    keep = {
        key
        for key in db.scalars(
            select(TestConditionField.key).where(TestConditionField.test_type_id == fresh.id)
        )
    }
    dropped = sorted(key for key in run.conditions if key not in keep)
    run.conditions = {key: value for key, value in run.conditions.items() if key in keep}
    run.input_units = {key: value for key, value in run.input_units.items() if key in keep}

    # 읽을 형식 고정은 **옛 종류의 것이다.** 그대로 두면 새 종류로 못 읽는다.
    run.parse_profile_id = None
    run.status = "uploaded"
    run.parse_error = None

    audit.record(
        db,
        action=audit.TEST_RUN_UPDATED,
        actor=user,
        target_table="test_runs",
        target_id=run.id,
        target_label=run.record_name,
        workspace_id=run.workspace_id,
        changes={
            "test_type": {"before": before, "after": run.record_name},
            "dropped_conditions": {"before": dropped, "after": []},
        },
    )
    queue.enqueue(db, kind=kinds.TESTS_PARSE_UPLOAD, payload={"test_run_id": str(run.id)})
    db.commit()

    return RetypeOut(
        record_name=run.record_name,
        test_type_key=fresh.key,
        dropped_conditions=dropped,
        message=(
            f"'{fresh.label}' 로 바꾸고 다시 읽기를 큐에 넣었습니다. "
            f"이름이 '{before}' 에서 '{run.record_name}' 으로 바뀌었습니다."
            + (f" 조건 {len(dropped)}칸은 새 종류에 없어 버렸습니다." if dropped else "")
        ),
    )


@runs_router.post("/{run_id}/reparse", response_model=ReparseOut, status_code=202)
def reparse(
    run_id: uuid.UUID,
    payload: ReparseRequest | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ReparseOut:
    """다시 읽는다. 원본을 보관하는 이유가 이것이다.

    ## 왜 형식을 고를 수 있어야 하는가

    자동 선택이 틀리는 자리가 있다. 같은 장비의 형식이 조금 달라져 프로파일을
    하나 더 만들면 지문이 겹치고, 우선순위가 높은 쪽이 이겨서 **엉뚱한 것으로
    읽거나 아예 실패한다.** 그때 「다시 읽기」 만 있으면 **같은 선택을 그대로
    반복한다** — 고칠 자리가 없었다.

    고른 것은 시험에 남는다(`parse_profile_id`). 큐 페이로드에만 실으면
    재시도에서 사라지고, 나중에 누가 다시 읽으면 또 자동으로 돌아간다.

    비워 보내면 **고정을 푼다** — 프로파일을 고친 뒤 자동으로 되돌리는 길이다.
    """
    run = services.get_run(db, user, run_id)
    if not run.source_path:
        raise AppError("MNX-TESTS-0014", "원본 파일이 없어 다시 읽을 수 없습니다.", status=422)

    # **안 보낸 것과 비운 것을 구별한다.** 안 구별하면 그냥 「다시 읽기」 를
    # 누를 때마다 고정이 풀리고, 그 사실은 또 실패해야 드러난다.
    given = payload is not None and "profile_key" in payload.model_fields_set
    key = payload.profile_key if payload else None
    if given and key:
        # **이 시험 종류의 것만.** 다른 종류의 프로파일로 읽으면 채널 이름이
        # 안 맞아 어차피 실패하는데, 그 실패는 「형식이 틀렸다」 로 안 읽힌다.
        profile = db.scalar(
            formats.visible_profiles(db, user).where(
                FormatProfile.key == key,
                FormatProfile.test_type_id == run.test_type_id,
            )
        )
        if profile is None:
            raise AppError(
                "MNX-TESTS-0022",
                f"그 시험 종류로 쓸 수 있는 형식이 아닙니다: {key}",
                status=422,
            )
        run.parse_profile_id = profile.id
    elif given:
        # 명시적으로 비웠다 — 자동으로 되돌린다.
        run.parse_profile_id = None

    run.status = "uploaded"
    run.parse_error = None
    queue.enqueue(db, kind=kinds.TESTS_PARSE_UPLOAD, payload={"test_run_id": str(run.id)})
    db.commit()
    pinned = db.get(FormatProfile, run.parse_profile_id) if run.parse_profile_id else None
    return ReparseOut(
        status="queued",
        message=(
            f"'{pinned.key}' 로 다시 읽기를 큐에 넣었습니다."
            if pinned
            else "다시 읽기를 큐에 넣었습니다(형식은 자동으로 고릅니다)."
        ),
        profile_key=pinned.key if pinned else None,
    )


#: 「값이 없는 것」 을 가리키는 거르기 표식.
#:
#: **왜 별도 매개변수가 아니라 표식인가.** 거르기 목록은 서버가 준 `{key, label,
#: count}` 를 그대로 그린다 — 화면은 그 key 를 되돌려 보낼 뿐 뜻을 모른다. 여기에
#: `division_empty=true` 같은 칸을 더하면 거를 수 있는 열마다 매개변수가 하나씩
#: 늘고, 화면이 열마다 다른 길을 알아야 한다.
#:
#: 진짜 값과 겹칠 위험이 있지만, 사업부·시험자·시험 그룹에 이 글자를 그대로 적는
#: 일은 없다고 본다. 겹치면 그 값으로 거르는 대신 빈 것이 걸린다 — **틀린 값이
#: 저장되는 종류의 사고는 아니다.**
EMPTY_FILTER_KEY = "__none__"

#: 빈 것을 가리키는 이름. 화면이 그대로 그린다.
EMPTY_FILTER_LABEL = "(없음)"


def _plain(value: object) -> object:
    """감사 로그에 실을 수 있는 값으로. 날짜는 문자열이어야 JSON 이 된다."""
    return value.isoformat() if isinstance(value, datetime) else value


def _before_of(run: Any, field: str) -> Any:
    """일괄 수정이 보는 지금 값. **시험 그룹만 조건 dict 안에 있다.**"""
    if field == "testing_group":
        return (run.conditions or {}).get(field)
    return getattr(run, field)


@runs_router.post("/bulk-update", response_model=RunBulkUpdateOut)
def bulk_update_runs(
    payload: RunBulkUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunBulkUpdateOut:
    """고른 시험의 **칸 하나**를 같은 값으로 맞춘다.

    ## 왜 아무 칸이나 못 고치는가

    고칠 수 있는 칸은 `EDITABLE_FIELDS` 가 정한다. 시편·재료·시험 종류는 이름을
    만드는 값이라(ADR 0004) 바꾸면 `record_name` 과 그 아래가 흔들리고, 상태·채택
    결과는 처리 파이프라인이 쓰는 값이라 손으로 옮기면 **「읽힌 적 없는데
    처리됨」 같은 상태**가 만들어진다. 조건값은 단위가 딸려 있어서 한 값만 갈아
    끼우면 단위 기록과 어긋난다.

    남는 것은 올릴 때 사람이 적는 메타데이터뿐이다. 그걸 나중에 고치는 길이
    지금까지 아예 없어서, 사업부를 빠뜨리면 다시 올리는 수밖에 없었다.

    **예외는 시험 그룹 하나다.** 조건값이지만 단위가 없는 글자라(`text`) 위의
    이유가 안 걸린다. 그리고 이 값은 **나중에 묶으려고 적는 것**이라 — 스무 건을
    올린 뒤에 "이건 2026 고온 묶음이었다" 를 깨닫는 일이 실제로 잦다.

    ## 왜 건마다 기록을 남기는가

    한 번에 스무 건을 바꾸는 일이라 **누가 무엇을 어떻게 바꿨는지**가 남지
    않으면 나중에 「이 값이 왜 이래」 에 답할 수 없다. 지우기와 같은 이유다.
    """
    field = payload.field
    raw = (payload.value or "").strip() or None

    # **날짜는 미리 판정한다.** 열 건을 고치다 열한 번째에서 형식이 틀렸다고
    # 멈추면 앞의 열 건만 바뀐 상태가 남는다. 값이 하나뿐인 요청이니 손대기
    # 전에 걸러야 맞다.
    when: datetime | None = None
    if field == "tested_at" and raw is not None:
        try:
            when = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise AppError(
                "MNX-TESTS-0021",
                f"시험일 형식이 아닙니다: {raw}",
                status=422,
            ) from exc

    updated = 0
    unchanged = 0
    blocked: list[str] = []

    for run_id in payload.run_ids:
        try:
            run = services.get_run(db, user, run_id)
        except AppError:
            # **이름을 모르면 id 라도 준다.** 조용히 세지 않는 것이 요점이다.
            blocked.append(str(run_id))
            continue

        before = _before_of(run, field)
        if field == "testing_group":
            # **조건 dict 는 통째로 갈아 끼운다.** JSONB 를 제자리에서 고치면
            # SQLAlchemy 가 바뀐 줄 모르고 UPDATE 를 안 낸다 — 화면에는 「바꿨다」
            # 가 뜨고 DB 는 그대로인 상태가 된다.
            conditions = dict(run.conditions or {})
            if raw is None:
                conditions.pop(field, None)
            else:
                conditions[field] = raw
            run.conditions = conditions
        elif field in ("division", "instrument"):
            # 기준정보를 거친다(ADR 0010). `usage_count` 도 여기서 옮겨진다 —
            # 옛 값은 하나 줄고 새 값은 하나 는다.
            vocabulary_services.apply_bindings(
                db,
                run,
                vocabulary_services.TEST_RUN_BINDINGS,
                {field: raw},
                created_by_id=user.id,
            )
        elif field == "tested_at":
            run.tested_at = when
        else:
            setattr(run, field, raw)

        after = _before_of(run, field)
        if before == after:
            unchanged += 1
            continue

        audit.record(
            db,
            action=audit.TEST_RUN_UPDATED,
            actor=user,
            target_table="test_runs",
            target_id=run.id,
            target_label=run.record_name,
            workspace_id=run.workspace_id,
            changes={field: {"before": _plain(before), "after": _plain(after)}},
        )
        updated += 1

    db.commit()
    return RunBulkUpdateOut(updated=updated, unchanged=unchanged, blocked=blocked)


@runs_router.post("/delete", response_model=RunDeleteOut)
def delete_runs(
    payload: RunDeleteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunDeleteOut:
    """여러 건을 한 번에 지운다. **소프트 삭제이고, 건마다 기록을 남긴다.**

    ## 왜 하나가 막혀도 멈추지 않는가

    20건을 골라 지우는데 하나가 권한 밖이라 전부 실패하면, 사람은 어느 것이
    문제인지 모른 채 다시 골라야 한다. **지울 수 있는 것은 지우고, 못 지운
    것은 이름으로 돌려준다.**

    ## 왜 `DELETE` 가 아니라 `POST /delete` 인가

    본문에 목록을 싣는다. `DELETE` 에 본문을 싣는 것은 규격이 권하지 않고,
    id 를 쿼리로 늘어놓으면 URL 길이 제한에 걸린다 — 200건을 고르는 화면이다.
    """
    deleted = 0
    blocked: list[str] = []
    for run_id in payload.run_ids:
        try:
            run = services.get_run(db, user, run_id)
        except AppError:
            # **이름을 모르면 id 라도 준다.** 조용히 세지 않는 것이 요점이다.
            blocked.append(str(run_id))
            continue
        run.deleted_at = _now()
        vocabulary_services.release_bindings(db, run, vocabulary_services.TEST_RUN_BINDINGS)
        audit.record(
            db,
            action=audit.TEST_RUN_DELETED,
            actor=user,
            target_table="test_runs",
            target_id=run.id,
            target_label=run.source_filename or str(run.id),
            workspace_id=run.workspace_id,
            changes={"deleted_at": {"after": run.deleted_at.isoformat()}},
        )
        deleted += 1
    db.commit()
    return RunDeleteOut(deleted=deleted, blocked=blocked)


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
    vocabulary_services.release_bindings(db, run, vocabulary_services.TEST_RUN_BINDINGS)
    # **되돌릴 수 있어도 남긴다.** 되돌리려면 먼저 지워졌다는 것을 알아야 하고,
    # 파일 정리 잡이 나중에 파일을 치우면 그때는 정말로 되돌릴 수 없다.
    audit.record(
        db,
        action=audit.TEST_RUN_DELETED,
        actor=user,
        target_table="test_runs",
        target_id=run.id,
        target_label=run.source_filename or str(run.id),
        workspace_id=run.workspace_id,
        changes={"deleted_at": {"after": run.deleted_at.isoformat()}},
    )
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


# --- 장비가 준 시편 치수 ------------------------------------------------------


@runs_router.get("/{run_id}/instrument-dimensions", response_model=InstrumentDimensionsOut)
def instrument_dimensions(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InstrumentDimensionsOut:
    """장비 파일이 준 시편 치수와, 시편에 지금 들어 있는 값.

    **둘을 나란히 준다.** 파일 값만 주면 화면이 "덮어쓰는 것인지" 를 판단할 수
    없다. 채우기와 덮어쓰기는 사람에게 다른 결정이다.
    """
    run = permissions.get_run(db, user, run_id)
    specimen = db.get(Specimen, run.specimen_id)
    fields = specimen_size.dimension_fields(db, specimen)
    found = curvedata.instrument_dimensions(run.source_metadata, fields)
    measured = dict((specimen.dimensions if specimen else None) or {})
    for key, column in specimen_size.LEGACY_COLUMNS.items():
        if key not in measured and specimen is not None:
            value = getattr(specimen, column, None)
            if value:
                measured[key] = float(value)

    # **찾은 것만 주지 않는다.** 화면이 "이건 파일에 없어서 직접 넣어야 한다" 를
    # 말하려면 없는 것도 알아야 한다. 찾은 것만 주면 화면은 빈 목록을 보고
    # "파일에 치수가 아예 없다" 로 잘못 읽는다.
    # **그래서 이 시험은 얼마로 도는가.** 파일 값과 시편 값만 주면 셋 중 어느
    # 것이 이겼는지 화면이 알 수 없다 — 치수는 세 곳에 살 수 있다(v1.118.0).
    effective = (
        specimen_size.sizes_of(db, specimen, run.dimensions or {}) if specimen else None
    )
    sizes = {item.key: item for item in (effective.items if effective else ())}

    return InstrumentDimensionsOut(
        specimen_id=run.specimen_id,
        items=[
            InstrumentDimensionOut(
                field=item.key,
                label=item.label,
                symbol=item.symbol,
                value_m=found.get(item.key),
                current_m=measured.get(item.key),
                run_m=sizes[item.key].value if item.key in sizes else None,
                source=sizes[item.key].source if item.key in sizes else None,
            )
            for item in fields
        ],
    )


@runs_router.post("/{run_id}/apply-instrument-dimensions", response_model=AppliedDimensionsOut)
def apply_instrument_dimensions(
    run_id: uuid.UUID,
    overwrite: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AppliedDimensionsOut:
    """장비가 준 치수를 시편에 채운다.

    **기본은 빈 칸만 채운다.** 사람이 이미 재어 넣은 값을 파일이 조용히 바꾸면
    어느 것이 맞는지 알 수 없다 — 그래서 자동으로는 아무것도 안 했다. 그런데
    그 판단이 "채우는 길이 아예 없다" 로 굳어 있었다. 시편 41개 중 치수가 있는
    것이 3개뿐이었고, 그래서 처리가 첫 단계에서 막혔다.

    덮어쓰기는 **명시적으로 요청해야** 한다(`overwrite=true`).
    """
    run = permissions.get_run(db, user, run_id)
    specimen = permissions.visible_specimen(db, user, run.specimen_id)
    fields = specimen_size.dimension_fields(db, specimen)
    found = curvedata.instrument_dimensions(run.source_metadata, fields)
    if not found:
        raise AppError(
            "MNX-TESTS-0030",
            "이 파일에는 시편 치수가 없습니다. 시편 기록에 직접 넣으세요.",
            status=422,
        )
    labels = {item.key: item.label for item in fields}
    measured = dict(specimen.dimensions or {})
    filled: list[str] = []
    for key, value in found.items():
        if measured.get(key) is not None and not overwrite:
            continue
        measured[key] = value
        filled.append(labels.get(key, key))
    specimen.dimensions = measured
    # **옛 컬럼도 함께 적는다**(ADR 0010 Expand). 아직 그쪽을 읽는 코드가 있다.
    for key, column in specimen_size.LEGACY_COLUMNS.items():
        if key in measured:
            setattr(specimen, column, measured[key])
    if not filled:
        raise AppError(
            "MNX-TESTS-0031",
            "시편에 이미 치수가 들어 있습니다. 덮어쓰려면 다시 확인해 주세요.",
            status=409,
        )
    db.commit()
    return AppliedDimensionsOut(specimen_id=specimen.id, filled=filled)
