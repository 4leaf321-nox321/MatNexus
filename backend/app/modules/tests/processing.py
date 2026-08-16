"""처리 — 레시피 저장, 미리보기, 결과.

**저장 전에 돌려 볼 수 있어야 한다.** 형식 프로파일의 `/try` 와 같은 판단이다
(ADR 0005). 처리가 잘못되면 곡선이 조용히 이상해지는데, 그것은 저장한 뒤에는
찾기가 매우 어렵다. 그래서 `/preview` 는 아무것도 저장하지 않고 계산만 한다.

**시편 치수는 곡선에 없다.** 게이지 길이와 단면적은 `Specimen` 에 있고,
`matcore` 는 DB 를 모른다. 그 다리를 여기서 놓는다 — 읽어서 `given` 으로
넘기고, 레시피는 `"@specimen_gauge_length"` 로 참조한다.

라우트를 `routes.py` 에 더 밀어 넣지 않고 파일을 나눈 이유는 `formats.py` 와
같다. 이쪽은 "무엇을 어떻게 계산할지 정하는" 작업이고 시험 등록과 성격이 다르다.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.materials.models import Specimen
from app.modules.tests import services
from app.modules.tests.models import (
    Curve,
    ProcessingRecipe,
    ProcessingResult,
    TestRun,
    TestType,
)
from app.modules.tests.schemas import (
    ProcessingPreviewOut,
    ProcessingResultOut,
    ProcessingRunRequest,
    ProcessingScalarOut,
    ProcessingStageOut,
    ProcessingStepOut,
    RecipeCreateRequest,
    RecipeOut,
    RecipeSaveRequest,
    StepParamOut,
)
from app.modules.workspaces.models import Workspace
from app.shared import filestore
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.permissions import (
    require_owner_edit,
    resolve_owner_workspace,
    visible_owner_clause,
)
from matcore import curves, processing, registry
from matcore.parsers import Channel

router = APIRouter(prefix="/processing", tags=["processing"])

#: 미리보기가 돌려주는 점 수 상한. 화면 픽셀에 겹치는 점을 보낼 이유가 없다.
PREVIEW_POINTS = 600


# --- 단계 목록 ---------------------------------------------------------------


@router.get("/steps", response_model=list[ProcessingStepOut])
def list_steps(
    test_type: str | None = Query(default=None),
    user: User = Depends(current_user),
) -> list[ProcessingStepOut]:
    """등록된 처리 단계와 그 입력 칸.

    **화면이 이 응답만으로 폼을 그린다.** `ParamSpec` 이 곧 입력 칸이고, 새 계산을
    등록하면 화면이 따라온다 — 목록을 프론트에 하드코딩하면 계산을 추가할 때
    두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
    """
    processing.load_builtin()
    return [
        ProcessingStepOut(
            id=plugin.id,
            label=plugin.label,
            version=plugin.version,
            applies_to=list(plugin.applies_to),
            params=[
                StepParamOut(
                    name=spec.name,
                    label=spec.label,
                    type=spec.type,
                    default=spec.default,
                    choices=list(spec.choices),
                    unit=spec.unit,
                    help=spec.help,
                )
                for spec in plugin.params
            ],
        )
        for plugin in registry.list_plugins(kind="processing", applies_to=test_type)
    ]


# --- 곡선을 Frame 으로 ---------------------------------------------------------


def _frame_of(
    db: Session, run: TestRun, curve_key: str | None
) -> tuple[processing.Frame, Curve]:
    available = services.curves_of(db, [run.id]).get(run.id, [])
    if not available:
        raise NotFound(
            "MNX-PROCESSING-0001",
            "정규화된 곡선이 아직 없습니다. 파일이 읽히기를 기다리거나 다시 읽으세요.",
        )
    curve = (
        next((item for item in available if item.key == curve_key), None)
        if curve_key
        else available[0]
    )
    if curve is None:
        keys = ", ".join(item.key for item in available)
        raise NotFound(
            "MNX-PROCESSING-0002", f"'{curve_key}' 곡선이 없습니다. 있는 곡선: {keys}"
        )

    raw = curves.read_columns(filestore.read_bytes(curve.storage_path))
    units = services.channel_units(db, run.test_type_id)
    columns = {
        name: np.asarray(
            [np.nan if value is None else float(value) for value in values], dtype=np.float64
        )
        for name, values in raw.items()
    }
    return processing.Frame(columns, {name: units.get(name, "1") for name in columns}), curve


def _given(db: Session, run: TestRun) -> list[processing.Scalar]:
    """시편 치수를 파이프라인이 참조할 수 있게 넘긴다.

    **없는 값은 넘기지 않는다.** 0 이나 기본값으로 채우면 응력이 조용히 틀린다 —
    단면적이 잘못되면 자릿수가 통째로 어긋나는데 숫자는 그럴듯해 보인다. 없으면
    `@specimen_area` 참조가 "그 값이 없습니다" 로 실패하고, 그게 맞다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        return []
    given: list[processing.Scalar] = []
    if specimen.gauge_length_m:
        given.append(
            processing.Scalar(
                "specimen_gauge_length", "시편 게이지 길이", specimen.gauge_length_m, "m"
            )
        )
    if specimen.width_m:
        given.append(processing.Scalar("specimen_width", "시편 폭", specimen.width_m, "m"))
    if specimen.thickness_m:
        given.append(
            processing.Scalar("specimen_thickness", "시편 두께", specimen.thickness_m, "m")
        )
    if specimen.width_m and specimen.thickness_m:
        given.append(
            processing.Scalar(
                "specimen_area",
                "시편 초기 단면적",
                specimen.width_m * specimen.thickness_m,
                "m2",
            )
        )
    return given


def _steps(raw: list[dict[str, Any]]) -> list[processing.Step]:
    if not raw:
        raise AppError("MNX-PROCESSING-0003", "단계가 하나도 없습니다.", status=422)
    return [
        processing.Step(str(item.get("plugin") or ""), dict(item.get("options") or {}))
        for item in raw
    ]


def _run_pipeline(
    db: Session, run: TestRun, curve_key: str | None, steps: list[dict[str, Any]]
) -> tuple[processing.PipelineResult, Curve]:
    processing.load_builtin()
    frame, curve = _frame_of(db, run, curve_key)
    try:
        result = processing.apply(_steps(steps), frame, given=_given(db, run))
    except processing.ProcessingError as exc:
        # **처리 실패는 사용자 오류다.** 500 으로 내면 로그를 뒤져야 알 수 있고,
        # 메시지에는 이미 어느 단계에서 무엇이 어긋났는지 적혀 있다.
        raise AppError("MNX-PROCESSING-0004", str(exc), status=422) from exc
    return result, curve


def _stage_out(stage: processing.Stage) -> ProcessingStageOut:
    return ProcessingStageOut(
        index=stage.index,
        plugin=stage.plugin,
        label=stage.label,
        version=stage.version,
        options=stage.options,
        notes=list(stage.notes),
        row_count=stage.frame.length(),
        columns=sorted(stage.frame.columns),
        scalars=[_scalar_out(item) for item in stage.scalars],
    )


def _scalar_out(scalar: processing.Scalar) -> ProcessingScalarOut:
    return ProcessingScalarOut(
        key=scalar.key, label=scalar.label, value=scalar.value, si_unit=scalar.si_unit
    )


def _points(frame: processing.Frame, x: str, y: str) -> list[tuple[float, float]]:
    if x not in frame.columns or y not in frame.columns:
        return []
    return curves.downsample(
        [None if np.isnan(v) else float(v) for v in frame.columns[x]],
        [None if np.isnan(v) else float(v) for v in frame.columns[y]],
        max_points=PREVIEW_POINTS,
    )


@router.post("/preview", response_model=ProcessingPreviewOut)
def preview(
    payload: ProcessingRunRequest,
    x: str | None = Query(default=None),
    y: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingPreviewOut:
    """**저장하지 않고** 돌려 본다.

    저장하고 나서 틀린 것을 아는 것과 저장 전에 아는 것은 다르다. 처리가 잘못되면
    곡선이 조용히 이상해지고, 그 곡선으로 적합한 물성이 그대로 해석에 들어간다.
    """
    run = services.get_run(db, user, payload.test_run_id)
    result, curve = _run_pipeline(db, run, payload.source_curve_key, payload.steps)
    frame = result.frame
    columns = sorted(frame.columns)
    return ProcessingPreviewOut(
        source_curve_key=curve.key,
        source_row_count=curve.row_count,
        row_count=frame.length(),
        columns=columns,
        units={name: frame.units.get(name, "1") for name in columns},
        stages=[_stage_out(stage) for stage in result.stages],
        scalars=[_scalar_out(item) for item in result.scalars],
        notes=list(result.notes),
        points=_points(frame, x or "", y or ""),
    )


@router.post("/results", response_model=ProcessingResultOut, status_code=201)
def create_result(
    payload: ProcessingRunRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingResultOut:
    """결과를 저장한다. **불변이다** — 다시 돌리면 새 행이 생긴다.

    레시피 id 만 남기지 않고 **단계를 통째로 스냅샷**한다. 레시피가 나중에
    바뀌면 이 결과가 무엇으로 나왔는지 알 수 없게 되는데, 그 값은 이미 보고서에
    들어가 있다.
    """
    run = services.get_run(db, user, payload.test_run_id)
    result, curve = _run_pipeline(db, run, payload.source_curve_key, payload.steps)

    recipe = None
    if payload.recipe_key:
        recipe = db.scalar(
            _visible_recipes(db, user).where(ProcessingRecipe.key == payload.recipe_key)
        )
        if recipe is None:
            raise NotFound(
                "MNX-PROCESSING-0005", f"레시피를 찾을 수 없습니다: {payload.recipe_key}"
            )

    frame = result.frame
    data = curves.to_parquet(
        [
            Channel(
                key=name,
                label=name,
                si_unit=frame.units.get(name, "1"),
                values=tuple(
                    None if np.isnan(value) else float(value) for value in frame.columns[name]
                ),
            )
            for name in sorted(frame.columns)
        ]
    )
    # **결과마다 새 파일이다.** 불변이므로 덮어쓸 일이 없고, 덮어쓰기가 없으면
    # "예전 결과를 열었더니 값이 달라졌다" 가 구조적으로 불가능하다.
    stored = filestore.write_bytes(
        data, relative_dir=f"processing/{run.id}", filename=f"{uuid.uuid4().hex}.parquet"
    )

    item = ProcessingResult(
        test_run_id=run.id,
        source_curve_key=curve.key,
        recipe_id=recipe.id if recipe else None,
        recipe_label=recipe.label if recipe else None,
        steps_snapshot=payload.steps,
        stages=[
            {
                "plugin": stage.plugin,
                "label": stage.label,
                "version": stage.version,
                "options": _jsonable(stage.options),
                "notes": list(stage.notes),
            }
            for stage in result.stages
        ],
        scalars=[
            {"key": s.key, "label": s.label, "value": s.value, "si_unit": s.si_unit}
            for s in result.scalars
        ],
        storage_path=stored.relative_path,
        row_count=frame.length(),
        sha256=stored.sha256,
        byte_size=stored.size,
        columns=sorted(frame.columns),
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _result_out(item)


def _jsonable(options: dict[str, Any]) -> dict[str, Any]:
    """numpy 스칼라를 파이썬 값으로. JSONB 가 numpy 를 모른다."""
    return {
        key: (float(value) if isinstance(value, np.floating | np.integer) else value)
        for key, value in options.items()
    }


def _result_out(item: ProcessingResult) -> ProcessingResultOut:
    return ProcessingResultOut(
        id=item.id,
        test_run_id=item.test_run_id,
        source_curve_key=item.source_curve_key,
        recipe_key=None,
        recipe_label=item.recipe_label,
        steps=item.steps_snapshot,
        stages=[
            ProcessingStageOut(
                index=index,
                plugin=str(stage.get("plugin", "")),
                label=str(stage.get("label", "")),
                version=str(stage.get("version", "")),
                options=dict(stage.get("options") or {}),
                notes=list(stage.get("notes") or []),
                row_count=item.row_count,
                columns=item.columns,
                scalars=[],
            )
            for index, stage in enumerate(item.stages)
        ],
        scalars=[
            ProcessingScalarOut(
                key=str(s.get("key", "")),
                label=str(s.get("label", "")),
                value=float(s.get("value", 0.0)),
                si_unit=str(s.get("si_unit", "1")),
            )
            for s in item.scalars
        ],
        row_count=item.row_count,
        columns=item.columns,
        created_at=item.created_at,
    )


@router.get("/results", response_model=list[ProcessingResultOut])
def list_results(
    test_run_id: uuid.UUID = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProcessingResultOut]:
    run = services.get_run(db, user, test_run_id)
    items = db.scalars(
        select(ProcessingResult)
        .where(ProcessingResult.test_run_id == run.id)
        .order_by(ProcessingResult.created_at.desc())
    )
    return [_result_out(item) for item in items]


# --- 레시피 ------------------------------------------------------------------


def _visible_recipes(db: Session, user: User) -> Select[tuple[ProcessingRecipe]]:
    """내 부서 것 + 전역. 재료·프로파일·시험 종류와 **같은 규칙, 같은 코드**다."""
    return select(ProcessingRecipe).where(
        visible_owner_clause(db, user, ProcessingRecipe.owner_workspace_id)
    )


def _recipe_out(db: Session, item: ProcessingRecipe) -> RecipeOut:
    owner = db.get(Workspace, item.owner_workspace_id) if item.owner_workspace_id else None
    test_type = db.get(TestType, item.test_type_id)
    return RecipeOut(
        id=item.id,
        key=item.key,
        label=item.label,
        description=item.description,
        owner_workspace_slug=owner.slug if owner else None,
        owner_workspace_name=owner.name if owner else None,
        is_global=item.owner_workspace_id is None,
        test_type_key=test_type.key if test_type else "?",
        test_type_label=test_type.label if test_type else "?",
        steps=item.steps,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _resolve_type(db: Session, key: str) -> TestType:
    test_type = db.scalar(select(TestType).where(TestType.key == key))
    if test_type is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    return test_type


def _validate(steps: list[dict[str, Any]]) -> None:
    """단계 이름이 실재하는지만 본다. 옵션의 타당성은 돌려 봐야 안다.

    등록되지 않은 단계를 저장하게 두면, 그 레시피는 **쓸 때마다 실패한다.**
    저장 시점에 아는 것을 저장 시점에 말한다.
    """
    processing.load_builtin()
    for index, step in enumerate(_steps(steps)):
        try:
            plugin = registry.get(step.plugin)
        except KeyError:
            raise AppError(
                "MNX-PROCESSING-0006",
                f"{index + 1}단계: 등록되지 않은 처리입니다: {step.plugin}",
                status=422,
            ) from None
        if plugin.kind != "processing":
            raise AppError(
                "MNX-PROCESSING-0006",
                f"{index + 1}단계: 처리 단계가 아닙니다: {step.plugin}",
                status=422,
            )


@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes(
    test_type: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[RecipeOut]:
    query = _visible_recipes(db, user).order_by(ProcessingRecipe.label)
    if test_type:
        query = query.where(ProcessingRecipe.test_type_id == _resolve_type(db, test_type).id)
    return [_recipe_out(db, item) for item in db.scalars(query)]


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def create_recipe(
    payload: RecipeCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    """부서 관리자가 자기 부서 레시피를 만든다.

    **부서마다 규격이 다르다.** 탄성 구간을 어디로 잡을지는 따르는 규격이 정하고,
    그 판단은 그 부서가 한다 — 형식 프로파일과 같은 이유다(ADR 0005·0006).
    """
    owner_id = resolve_owner_workspace(
        db, user, payload.owner_workspace_slug, what="레시피", code="MNX-PROCESSING-0007"
    )
    duplicate = db.scalar(
        select(ProcessingRecipe).where(
            ProcessingRecipe.key == payload.key,
            ProcessingRecipe.owner_workspace_id.is_(None)
            if owner_id is None
            else ProcessingRecipe.owner_workspace_id == owner_id,
        )
    )
    if duplicate:
        raise Conflict("MNX-PROCESSING-0008", f"이미 있는 레시피입니다: {payload.key}")
    _validate(payload.steps)
    item = ProcessingRecipe(
        key=payload.key,
        label=payload.label,
        description=payload.description,
        owner_workspace_id=owner_id,
        test_type_id=_resolve_type(db, payload.test_type_key).id,
        steps=payload.steps,
        is_active=payload.is_active,
        created_by_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _recipe_out(db, item)


@router.put("/recipes/{key}", response_model=RecipeOut)
def update_recipe(
    key: str,
    payload: RecipeSaveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    """레시피를 고친다. **저장된 결과는 안 바뀐다.**

    결과가 단계를 통째로 스냅샷해 두기 때문이다. 레시피를 고치는 것이 과거의
    숫자를 소급해 바꾸면, 어제 보고서에 적은 항복강도가 오늘 다른 값이 된다.
    """
    item = db.scalar(_visible_recipes(db, user).where(ProcessingRecipe.key == key))
    if item is None:
        raise NotFound("MNX-PROCESSING-0009", f"레시피를 찾을 수 없습니다: {key}")
    require_owner_edit(
        db, user, item.owner_workspace_id, what="레시피", code="MNX-PROCESSING-0007"
    )
    _validate(payload.steps)
    item.label = payload.label
    item.description = payload.description
    item.test_type_id = _resolve_type(db, payload.test_type_key).id
    item.steps = payload.steps
    item.is_active = payload.is_active
    db.commit()
    db.refresh(item)
    return _recipe_out(db, item)


@router.delete("/recipes/{key}", status_code=204)
def delete_recipe(
    key: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    item = db.scalar(_visible_recipes(db, user).where(ProcessingRecipe.key == key))
    if item is None:
        raise NotFound("MNX-PROCESSING-0009", f"레시피를 찾을 수 없습니다: {key}")
    require_owner_edit(
        db, user, item.owner_workspace_id, what="레시피", code="MNX-PROCESSING-0007"
    )
    # **결과는 남는다.** `recipe_id` 를 끊을 뿐이다 — 스냅샷이 있으므로 결과는
    # 자기가 무엇으로 계산됐는지 여전히 안다. 레시피를 지웠다고 이미 보고서에
    # 들어간 숫자의 출처가 사라지면 안 된다.
    db.execute(
        update(ProcessingResult)
        .where(ProcessingResult.recipe_id == item.id)
        .values(recipe_id=None)
    )
    db.delete(item)
    db.commit()
    return Response(status_code=204)
