"""형식 프로파일 — 미리보기와 저장.

**장비가 늘 때마다 파서를 짜지 않으려고 만든 길이다.** 라우트를 `routes.py` 에
더 밀어 넣지 않고 파일을 나눈 이유는, 이 기능이 시험 등록과 성격이 다르기
때문이다 — 이쪽은 "무엇을 어떻게 읽을지 정하는" 관리 작업이다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.tests.models import FormatProfile, TestType
from app.modules.tests.schemas import (
    FormatProfileCreateRequest,
    FormatProfileOut,
    FormatProfileSaveRequest,
    ProfileTryOut,
    StructurePreviewOut,
    TablePreviewOut,
    TriedChannelOut,
    TriedCurveOut,
    TriedSummaryOut,
)
from app.shared.auth import require_system_admin
from app.shared.errors import AppError, Conflict, NotFound
from matcore import readers, units
from matcore.parsers import ParseError
from matcore.readers import profile as profiles

router = APIRouter(prefix="/formats", tags=["tests"])

#: 미리보기에 보여 줄 행 수. 사람이 "맞게 읽혔나" 를 판단하는 데 이 정도면 된다.
PREVIEW_ROWS = 8


def _out(db: Session, item: FormatProfile) -> FormatProfileOut:
    test_type = db.get(TestType, item.test_type_id)
    return FormatProfileOut(
        id=item.id,
        key=item.key,
        label=item.label,
        description=item.description,
        test_type_key=test_type.key if test_type else "?",
        test_type_label=test_type.label if test_type else "?",
        definition=item.definition,
        priority=item.priority,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _symbol(raw: str) -> str | None:
    """장비 표기 → 정본 심볼. 화면이 새 채널을 제안하는 근거다."""
    return profiles.unit_symbol(raw)


def _dimension(raw: str) -> str | None:
    symbol = profiles.unit_symbol(raw)
    if symbol is None:
        return None
    try:
        return units.unit_of(symbol).dimension
    except units.UnknownUnit:
        return None


def _resolve_type(db: Session, key: str) -> TestType:
    test_type = db.scalar(select(TestType).where(TestType.key == key))
    if test_type is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    return test_type


@router.post("/preview", response_model=StructurePreviewOut)
def preview(
    file: UploadFile = File(...),
    header_rows: int = Form(default=1, ge=1, le=5),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> StructurePreviewOut:
    """파일을 **저장하지 않고** 구조만 읽어 본다.

    새 장비 파일이 왔을 때 가장 먼저 하는 일이다. 저장하지 않는 이유: 아직 이
    파일이 어느 시편의 것인지도 모르고, 프로파일을 만드는 중에 실패한 시험 기록이
    쌓일 이유가 없다.

    `header_rows` 만 사람이 준다. 헤더가 몇 줄인지는 **기계가 알 수 없기 때문이다**
    — 그룹 머리(버려도 되는 줄)와 나뉜 이름(버리면 안 되는 줄)은 생김새가 같다.
    """
    data = file.file.read()
    filename = file.filename or "upload.dat"
    try:
        structure = readers.read(data, readers.ReadOptions(header_rows=header_rows))
    except readers.ReadError as exc:
        raise AppError("MNX-TESTS-0022", str(exc), status=422) from exc

    matched = None
    for candidate in db.scalars(
        select(FormatProfile)
        .where(FormatProfile.is_active.is_(True))
        .order_by(FormatProfile.priority.desc(), FormatProfile.key)
    ):
        if profiles.matches(candidate.definition, filename=filename, structure=structure):
            matched = candidate.key
            break

    return StructurePreviewOut(
        filename=filename,
        encoding=structure.encoding,
        delimiter=structure.delimiter,
        line_count=structure.line_count,
        meta=[(key, value) for key, value in structure.meta],
        tables=[
            TablePreviewOut(
                index=table.index,
                name=table.name,
                header=list(table.header),
                units=list(table.units),
                unit_symbols=[_symbol(cell) for cell in table.units],
                dimensions=[_dimension(cell) for cell in table.units],
                row_count=table.row_count,
                column_count=table.column_count,
                first_line=table.first_line,
                sample_rows=[list(row) for row in table.rows[:PREVIEW_ROWS]],
            )
            for table in structure.tables
        ],
        warnings=list(structure.warnings),
        matched_profile=matched,
    )


@router.post("/try", response_model=ProfileTryOut)
def try_profile(
    definition: str = Form(..., description="프로파일 JSON"),
    file: UploadFile = File(...),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> ProfileTryOut:
    """저장하기 **전에** 이 프로파일로 그 파일을 읽어 본다.

    저장하고 나서 틀린 것을 아는 것과 저장 전에 아는 것은 다르다. 프로파일이
    잘못되면 곡선이 조용히 이상해지는데, 그것은 나중에 찾기가 매우 어렵다.
    """
    import json

    try:
        rule = json.loads(definition or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            "MNX-TESTS-0013", "프로파일 JSON 이 잘못되었습니다.", status=422
        ) from exc
    if not isinstance(rule, dict):
        raise AppError("MNX-TESTS-0013", "프로파일은 객체여야 합니다.", status=422)

    try:
        parsed = profiles.apply(rule, file.file.read())
    except (ParseError, readers.ReadError) as exc:
        raise AppError("MNX-TESTS-0023", str(exc), status=422) from exc

    return ProfileTryOut(
        curves=[
            TriedCurveOut(
                key=curve.key,
                label=curve.label,
                row_count=len(curve.channels[0].values) if curve.channels else 0,
                channels=[
                    TriedChannelOut(
                        key=channel.key,
                        label=channel.label,
                        source_unit=channel.source_unit,
                        si_unit=channel.si_unit,
                        first=channel.values[0] if channel.values else None,
                        last=channel.values[-1] if channel.values else None,
                    )
                    for channel in curve.channels
                ],
            )
            for curve in parsed.all_curves
        ],
        summary=[
            TriedSummaryOut(
                key=value.key,
                label=value.label,
                value=value.value,
                text=value.text,
                si_unit=value.si_unit,
            )
            for value in parsed.summary
        ],
        metadata=parsed.metadata,
        warnings=list(parsed.warnings),
    )


@router.get("", response_model=list[FormatProfileOut])
def list_profiles(
    test_type: str | None = Query(default=None),
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[FormatProfileOut]:
    query = select(FormatProfile).order_by(FormatProfile.priority.desc(), FormatProfile.key)
    if test_type:
        query = query.where(FormatProfile.test_type_id == _resolve_type(db, test_type).id)
    return [_out(db, item) for item in db.scalars(query)]


@router.post("", response_model=FormatProfileOut, status_code=201)
def create_profile(
    payload: FormatProfileCreateRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> FormatProfileOut:
    if db.scalar(select(FormatProfile).where(FormatProfile.key == payload.key)):
        raise Conflict("MNX-TESTS-0024", f"이미 있는 프로파일입니다: {payload.key}")
    _validate(payload.definition)
    item = FormatProfile(
        key=payload.key,
        label=payload.label,
        description=payload.description,
        test_type_id=_resolve_type(db, payload.test_type_key).id,
        definition=payload.definition,
        priority=payload.priority,
        is_active=payload.is_active,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _out(db, item)


@router.put("/{key}", response_model=FormatProfileOut)
def update_profile(
    key: str,
    payload: FormatProfileSaveRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> FormatProfileOut:
    """프로파일을 고친다. **이미 읽은 데이터는 안 바뀐다.**

    시험 종류 정의와 달리 여기는 잠그지 않는다 — 프로파일이 틀렸다는 것을 나중에
    알게 되는 것이 정상이고, 그때 고쳐서 **원본으로 다시 읽으면** 되기 때문이다.
    원본을 그대로 보관하는 두 번째 이유가 이것이다.
    """
    item = db.scalar(select(FormatProfile).where(FormatProfile.key == key))
    if item is None:
        raise NotFound("MNX-TESTS-0025", f"프로파일을 찾을 수 없습니다: {key}")
    _validate(payload.definition)
    item.label = payload.label
    item.description = payload.description
    item.test_type_id = _resolve_type(db, payload.test_type_key).id
    item.definition = payload.definition
    item.priority = payload.priority
    item.is_active = payload.is_active
    db.commit()
    db.refresh(item)
    return _out(db, item)


@router.delete("/{key}", status_code=204)
def delete_profile(
    key: str,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    item = db.scalar(select(FormatProfile).where(FormatProfile.key == key))
    if item is None:
        raise NotFound("MNX-TESTS-0025", f"프로파일을 찾을 수 없습니다: {key}")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def _validate(definition: dict[str, Any]) -> None:
    """지문이 없으면 거절한다.

    지문 없는 프로파일은 **모든 파일에 맞는다.** 그러면 다른 장비 파일까지
    이 규칙으로 읽혀 조용히 엉뚱한 곡선이 만들어진다.
    """
    match = definition.get("match") or {}
    if not any(match.get(key) for key in ("extensions", "header_any", "meta_any")):
        raise AppError(
            "MNX-TESTS-0026",
            "지문이 없습니다. 확장자·헤더·메타 중 하나는 있어야 합니다 — "
            "지문 없는 프로파일은 모든 파일에 맞아 다른 장비 파일까지 읽어 버립니다.",
            status=422,
        )
    if not definition.get("columns"):
        raise AppError("MNX-TESTS-0026", "열 매핑이 비어 있습니다.", status=422)
