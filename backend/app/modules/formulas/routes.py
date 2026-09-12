"""계산식 라우터 — 목록·만들기·고치기·지우기·미리보기 (ADR 0030).

시스템 관리자만 만들고 고친다 — 식은 모든 부서의 레시피·카드에 걸린다. 보는 것은
누구나(레시피 편집기가 단계 목록으로 본다).
"""

from __future__ import annotations

import uuid

import numpy as np
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.formulas import services
from app.modules.formulas.models import KIND_LABELS, Formula
from app.modules.formulas.schemas import (
    FormulaCreate,
    FormulaOut,
    FormulaPreviewIn,
    FormulaPreviewOut,
    FormulaUpdate,
    FormulaVocabularyOut,
)
from app.modules.processing.models import ProcessingResult
from app.shared import filestore, permissions
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, NotFound
from matcore import cards, curves, fitting, formula, processing, registry
from matcore import formulas as kit

router = APIRouter(prefix="/formulas", tags=["formulas"])


def _out(db: Session, row: Formula, *, with_references: bool = True) -> FormulaOut:
    name = None
    if row.created_by_id is not None:
        name = db.scalar(select(User.display_name).where(User.id == row.created_by_id))
    return FormulaOut(
        id=row.id,
        key=row.key,
        registry_key=row.registry_key,
        kind=row.kind,
        kind_label=KIND_LABELS.get(row.kind, row.kind),
        label=row.label,
        expression=row.expression,
        describe=row.describe,
        variables=list(row.variables or []),
        parameters=list(row.parameters or []),
        result=row.result,
        x_column=row.x_column,
        y_column=row.y_column,
        block=row.block,
        applies_to=list(row.applies_to or []),
        version=int(row.version),
        enabled=bool(row.enabled),
        created_by=name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        references=services.references(db, row) if with_references else {},
    )


@router.get("", response_model=list[FormulaOut])
def list_formulas(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[FormulaOut]:
    rows = db.scalars(select(Formula).order_by(Formula.kind, Formula.label)).all()
    return [_out(db, row) for row in rows]


@router.get("/vocabulary", response_model=FormulaVocabularyOut)
def vocabulary(_user: User = Depends(current_user)) -> FormulaVocabularyOut:
    """식을 적을 때 고를 수 있는 이름 — 계약서(`docs/확장-계약.md`)와 같은 어휘.

    열·스칼라는 내장·확장 단계의 `makes_columns`·`makes_values` 에서, 블록은 카드
    레지스트리에서. 화면이 이것으로 드롭다운을 그린다 — 이름을 손으로 치면 오타가
    난 채로 저장되고, 그 식은 돌 때마다 「열이 없습니다」 만 남긴다.
    """
    processing.load_builtin()
    cards.load_builtin()
    columns: dict[str, str] = {}
    scalars: dict[str, str] = {}
    for plugin in registry.list_plugins(kind="processing"):
        for made in plugin.makes_columns:
            if (
                "{" not in made.key
            ):  # `{column}_smoothed` 처럼 옵션에 따라 이름이 정해지는 것은 뺀다
                columns.setdefault(made.key, f"{made.label} ({made.si_unit or '?'})")
        for made in plugin.makes_values:
            scalars.setdefault(made.key, f"{made.label} ({made.si_unit or '?'})")
    return FormulaVocabularyOut(
        columns=[{"key": key, "label": label} for key, label in sorted(columns.items())],
        scalars=[{"key": key, "label": label} for key, label in sorted(scalars.items())],
        blocks=[{"key": block.key, "label": block.label} for block in cards.list_blocks()],
        functions=sorted(formula.FUNCTIONS),
        constants=sorted(formula.CONSTANTS),
    )


@router.post("", response_model=FormulaOut, status_code=201)
def create_formula(
    payload: FormulaCreate,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> FormulaOut:
    row = services.create(db, payload.model_dump(), user)
    db.commit()
    services.sync(db)
    return _out(db, row)


@router.patch("/{formula_id}", response_model=FormulaOut)
def update_formula(
    formula_id: uuid.UUID,
    payload: FormulaUpdate,
    _user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> FormulaOut:
    """식이 바뀌면 판이 오른다. 저장된 레시피·결과·카드는 옛 판을 든 채 그대로다."""
    row = services.get(db, formula_id)
    services.update(db, row, payload.model_dump(exclude_unset=True))
    db.commit()
    services.sync(db)
    return _out(db, row)


@router.delete("/{formula_id}", status_code=204)
def delete_formula(
    formula_id: uuid.UUID,
    _user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    """참조가 없을 때만. 있으면 409 — 대신 끈다."""
    row = services.get(db, formula_id)
    services.delete(db, row)
    db.commit()
    services.sync(db)
    return Response(status_code=204)


@router.post("/preview", response_model=FormulaPreviewOut)
def preview(
    payload: FormulaPreviewIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FormulaPreviewOut:
    """저장 전에 실제 채택 결과 하나로 돌려 본다 (D6). **아무것도 저장하지 않는다.**

    문법은 맞는데 뜻이 틀린 식(축을 바꿔 적음, 단위가 천 배)은 여기서 드러난다."""
    result = db.get(ProcessingResult, payload.result_id)
    if result is None:
        raise NotFound("MNX-FORMULAS-0008", "처리 결과를 찾을 수 없습니다.")
    permissions.get_run(db, user, result.test_run_id)  # 가시 범위

    draft = Formula(
        key=payload.spec.key or "preview",
        kind=payload.spec.kind,
        label=payload.spec.label,
        expression=payload.spec.expression,
        variables=[one.model_dump() for one in payload.spec.variables],
        parameters=[one.model_dump() for one in payload.spec.parameters],
        result=payload.spec.result.model_dump() if payload.spec.result else None,
        x_column=payload.spec.x_column,
        y_column=payload.spec.y_column,
        block=payload.spec.block,
        applies_to=list(payload.spec.applies_to),
        version=0,
    )
    services.validate(draft)
    spec = services.spec_of(draft)
    raw = curves.read_columns(filestore.read_bytes(result.storage_path))
    columns = {
        name: np.asarray([np.nan if v is None else float(v) for v in values], dtype=np.float64)
        for name, values in raw.items()
    }

    if spec.kind == "family":
        for axis in (spec.x_column, spec.y_column):
            if axis not in columns:
                raise AppError(
                    "MNX-FORMULAS-0009",
                    f"이 결과에 '{axis}' 열이 없습니다 — "
                    "그 열을 만드는 단계를 거친 결과를 고르세요.",
                    status=422,
                )
        family = kit.build_family(spec)
        x, y = columns[spec.x_column], columns[spec.y_column]
        if family.prepare is not None:
            x, y, _notes = family.prepare(x, y)
        # 레지스트리를 안 건드리고 맞춘다 — 미리보기는 저장이 아니다.
        saved = fitting.FAMILIES.get(family.key)
        fitting.FAMILIES[family.key] = family
        try:
            got = fitting.fit(family.key, x, y)
        except fitting.FittingError as exc:
            return FormulaPreviewOut(kind=spec.kind, ok=False, message=str(exc))
        finally:
            if saved is None:
                fitting.FAMILIES.pop(family.key, None)
            else:
                fitting.FAMILIES[family.key] = saved
        return FormulaPreviewOut(
            kind=spec.kind,
            ok=True,
            message=f"{got.point_count}점에 맞췄습니다. R² = {got.r_squared:.4f}",
            parameters=[
                {"name": p.name, "value": p.value, "unit": p.si_unit} for p in got.parameters
            ],
            r_squared=got.r_squared,
        )

    fn, _kwargs = kit.build_step(spec)
    frame = processing.Frame(columns, dict.fromkeys(columns, "?"))
    if spec.kind == "scalar_step":
        scalars = {str(one.get("key")): one.get("value") for one in result.scalars or []}
        options = {v.name: scalars.get(v.name) for v in spec.variables}
        out = fn(frame, options)
        value = out.scalars[0].value if out.scalars else None
        return FormulaPreviewOut(
            kind=spec.kind,
            ok=value is not None,
            message=(
                f"{spec.result.label if spec.result else ''} = {value:.6g}"
                if value is not None
                else " ".join(out.notes)
            ),
            value=value,
            notes=list(out.notes),
        )

    out = fn(frame, {})
    assert spec.result is not None
    made = out.frame.columns.get(spec.result.key)
    if made is None:
        return FormulaPreviewOut(kind=spec.kind, ok=False, message=" ".join(out.notes))
    head = min(8, len(made))
    sample = [
        {
            **{v.name: float(columns[v.name][i]) for v in spec.variables},
            spec.result.key: float(made[i]),
        }
        for i in range(head)
    ]
    finite = int(np.isfinite(made).sum())
    return FormulaPreviewOut(
        kind=spec.kind,
        ok=True,
        message=f"{len(made)}점 가운데 {finite}점이 수로 나왔습니다.",
        sample=sample,
        notes=list(out.notes),
    )
