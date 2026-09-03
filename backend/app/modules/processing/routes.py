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
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select, delete, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.processing.models import ProcessingRecipe, ProcessingResult
from app.modules.processing.schemas import (
    BatchItemOut,
    BatchOut,
    BatchRequest,
    ProcessingPreviewOut,
    ProcessingResultOut,
    ProcessingRunRequest,
    ProcessingScalarOut,
    ProcessingStageOut,
    ProcessingStepOut,
    ProducedOut,
    RecipeCreateRequest,
    RecipeOut,
    RecipeUpdateRequest,
    ResultCurveOut,
    StepParamOut,
)
from app.modules.tests.models import Curve, TestRun, TestSummary, TestType
from app.modules.workspaces.models import Workspace
from app.shared import curvedata, filestore, revision, test_type_channels
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.permissions import (
    get_run,
    require_owner_edit,
    resolve_owner_workspace,
    visible_owner_clause,
)
from matcore import curves, processing, registry, runtime
from matcore.parsers import Channel

router = APIRouter(prefix="/processing", tags=["processing"])

#: 미리보기가 돌려주는 점 수 상한. 화면 픽셀에 겹치는 점을 보낼 이유가 없다.
PREVIEW_POINTS = 600


# --- 단계 목록 ---------------------------------------------------------------


def _produced(item: registry.Produced) -> ProducedOut:
    return ProducedOut(key=item.key, label=item.label, si_unit=item.si_unit, help=item.help)


@router.get("/steps", response_model=list[ProcessingStepOut])
def list_steps(
    test_type: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
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
            requires_channels=[list(one) for one in plugin.requires_channels],
            params=[
                StepParamOut(
                    name=spec.name,
                    label=spec.label,
                    type=spec.type,
                    default=spec.default,
                    choices=list(spec.choices),
                    choice_labels=dict(spec.choice_labels),
                    unit=spec.unit,
                    dimension=spec.dimension,
                    unit_from=spec.unit_from,
                    help=spec.help,
                    required=spec.required,
                    role=spec.role,
                    links_to=spec.links_to,
                    when={key: list(values) for key, values in spec.when.items()},
                )
                for spec in plugin.params
            ],
            makes_columns=[_produced(item) for item in plugin.makes_columns],
            makes_values=[_produced(item) for item in plugin.makes_values],
            order=plugin.order,
        )
        for plugin in registry.list_plugins(
            kind="processing",
            applies_to=test_type,
            # **키가 아니라 채널로도 잡는다.** 부서가 만든 DMA 종류는 키가 다른데,
            # 저장·손실 탄성률을 그대로 재므로 DMA 단계가 성립한다.
            channels=test_type_channels.channels_of(db, test_type),
        )
    ]


# --- 곡선을 Frame 으로 ---------------------------------------------------------


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
    frame, curve = curvedata.load_frame(db, run, curve_key)
    try:
        result = processing.apply(
            _steps(steps),
            frame,
            # 시편 치수 + **시험 조건**. 둘 다 바깥에서 들어오는 값이다.
            given=[
                *curvedata.specimen_scalars(db, run),
                *curvedata.condition_scalars(db, run),
                # **재료에 적어 둔 값**도 넘긴다(ADR 0016). 탄성 구간이 성긴 곡선은
                # 탄성계수를 못 재는데, 그 값은 대개 재료에 적혀 있다.
                *curvedata.declared_scalars(db, run),
            ],
        )
    except processing.ProcessingError as exc:
        # **처리 실패는 사용자 오류다.** 500 으로 내면 로그를 뒤져야 알 수 있고,
        # 메시지에는 이미 어느 단계에서 무엇이 어긋났는지 적혀 있다.
        failure = AppError("MNX-PROCESSING-0004", str(exc), status=422)
        # 여기까지 된 것을 함께 든다 — 미리보기가 그것을 그린다(저장은 안 쓴다).
        failure.done = exc.done  # type: ignore[attr-defined]
        failure.curve = curve  # type: ignore[attr-defined]
        raise failure from exc
    return result, curve


def _recipe_or_none(db: Session, user: User, key: str | None) -> ProcessingRecipe | None:
    if not key:
        return None
    recipe = db.scalar(_visible_recipes(db, user).where(ProcessingRecipe.key == key))
    if recipe is None:
        raise NotFound("MNX-PROCESSING-0005", f"레시피를 찾을 수 없습니다: {key}")
    return recipe


def _store(
    db: Session,
    run: TestRun,
    curve_key: str | None,
    steps: list[dict[str, Any]],
    recipe: ProcessingRecipe | None,
    user: User,
) -> ProcessingResult:
    """돌리고 저장한다. **한 건 저장과 배치가 같은 경로를 쓴다.**

    나누면 "화면에서는 되는데 배치에서는 다른 값이 나온다" 가 가능해지고, 그
    어긋남은 숫자로만 드러나서 아무도 못 본다.

    `db.commit()` 은 호출부가 한다 — 배치는 **건별로** 커밋해야 부분 성공이
    지켜진다.
    """
    result, curve = _run_pipeline(db, run, curve_key, steps)
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
        steps_snapshot=steps,
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
            {
                "key": s.key,
                "label": s.label,
                "value": s.value,
                "si_unit": s.si_unit,
                "dimension": s.dimension,
            }
            for s in result.scalars
        ],
        # **계산이 무엇 위에서 돌았는지.** 플러그인 버전이 "어느 계산" 이라면
        # 이것은 "그 계산이 무엇 위에서" 다 — 둘 다 있어야 재현이 닫힌다.
        runtime=runtime.manifest(),
        storage_path=stored.relative_path,
        row_count=frame.length(),
        sha256=stored.sha256,
        byte_size=stored.size,
        columns=sorted(frame.columns),
        created_by_id=user.id,
    )
    db.add(item)
    db.flush()
    return item


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


def _scalar_out(
    scalar: processing.Scalar, sources: Mapping[str, str] | None = None
) -> ProcessingScalarOut:
    return ProcessingScalarOut(
        key=scalar.key,
        label=scalar.label,
        value=scalar.value,
        si_unit=scalar.si_unit,
        dimension=scalar.dimension,
        source=(sources or {}).get(scalar.key),
    )


def _points(frame: processing.Frame, x: str, y: str) -> list[tuple[float, float]]:
    if x not in frame.columns or y not in frame.columns:
        return []
    return curves.downsample(
        [None if np.isnan(v) else float(v) for v in frame.columns[x]],
        [None if np.isnan(v) else float(v) for v in frame.columns[y]],
        max_points=PREVIEW_POINTS,
    )


@router.get("/inputs", response_model=list[ProcessingScalarOut])
def list_inputs(
    test_run_id: uuid.UUID = Query(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProcessingScalarOut]:
    """이 시험을 돌리면 **바깥에서 들어오는 값**. 시편 치수와 단면적이다.

    **화면이 값을 알아야 한다.** 전에는 화면이 `@specimen_gauge_length` 로 이어
    붙일 이름 셋을 코드에 박아 두고 있었고(게이지 길이·단면적·탄성계수), 그것도
    이름만 알지 값은 몰랐다. 그래서 두 가지가 안 됐다.

      - 규격에 칸을 더해도(자유 길이·직경) 처리 화면이 모른다. 값은 이미 서버가
        보내고 있는데 집을 자리가 없어서, 사람은 자를 대고 다시 잰다.
      - 이어 붙인 값이 **몇인지** 안 보인다. 규격의 공칭과 그 시편의 실측은 뜻이
        조금 다른데, 얼마인지 모른 채로는 고칠지 말지를 판단할 수 없다.

    돌려 보기 전에 답해야 하므로 파이프라인을 돌리지 않는다.
    """
    run = get_run(db, user, test_run_id)
    conditions = curvedata.condition_scalars(db, run)
    # **재료에 적어 둔 값도 여기 선다.** 파이프라인은 이미 받는데(`declared_…`)
    # 이 목록에 없으면 화면의 자동 연결 후보에 안 떠서, 사람은 그 길이 있는 줄도
    # 모른 채 성긴 곡선 앞에 선다.
    declared = curvedata.declared_scalars(db, run)
    # **조건도 어디서 왔는지 말한다.** 같은 줄에 서는데 하나만 출처가 없으면
    # 사람은 그것이 빠뜨려진 것인지 다른 것인지 알 수 없다.
    sources = {
        **curvedata.specimen_sources(db, run),
        **{item.key: "condition" for item in conditions},
        **{item.key: "declared" for item in declared},
    }
    return [
        _scalar_out(item, sources)
        for item in (*curvedata.specimen_scalars(db, run), *conditions, *declared)
    ]


@router.post("/preview", response_model=ProcessingPreviewOut)
def preview(
    payload: ProcessingRunRequest,
    x: str | None = Query(default=None),
    y: str | None = Query(default=None),
    stage: int | None = Query(
        default=None,
        ge=0,
        description="몇 번째 단계의 곡선을 그릴까(0부터). 생략하면 마지막",
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingPreviewOut:
    """**저장하지 않고** 돌려 본다.

    저장하고 나서 틀린 것을 아는 것과 저장 전에 아는 것은 다르다. 처리가 잘못되면
    곡선이 조용히 이상해지고, 그 곡선으로 적합한 물성이 그대로 해석에 들어간다.

    ## 중간 단계도 그린다 (`stage`)

    프레임은 표 하나이고 **모든 열이 x 축을 공유한다.** 그래서 마지막 단계가
    축을 진소성변형률로 바꾸면, 변위·하중도 그 격자로 다시 찍힌다 — 탄성 구간이
    x=0 한 점으로 접히면서 **원본 곡선의 앞부분이 사라진 것처럼 보인다.**
    실사용에서 그 물음이 나왔다(2026-09-01): "S-S 곡선은 알겠는데 변위·하중은
    왜 끊기나".

    전에는 답할 방법이 뒤 단계를 지우고 다시 돌리는 것뿐이었다. 단계마다 프레임이
    이미 남아 있으므로(`processing.Stage.frame`) **어느 것을 그릴지 고르게만
    하면 된다** — 파이프라인은 그대로 돈다.

    `stages`·`scalars`·`notes` 는 **늘 전체**다. 그것들은 한 번 돈 일 전체를
    말하는 것이라 고른 단계에 따라 달라지면 안 된다.
    """
    run = get_run(db, user, payload.test_run_id)
    # **미리보기는 멈춰도 여기까지를 보여 준다.** 저장(`/results`)은 그대로 거절한다 —
    # 반쯤 돈 결과가 채택되면 카드와 덱까지 간다.
    problem: str | None = None
    try:
        result, curve = _run_pipeline(db, run, payload.source_curve_key, payload.steps)
    except AppError as exc:
        done = getattr(exc, "done", None)
        if done is None or not done.stages:
            raise
        result, curve = done, exc.curve  # type: ignore[attr-defined]
        problem = exc.message

    shown: int | None = None
    frame = result.frame
    if stage is not None:
        if stage >= len(result.stages):
            raise AppError(
                "MNX-PROCESSING-0009",
                f"{stage}번째 단계가 없습니다 — 이 구성은 {len(result.stages)}단계입니다.",
                status=422,
            )
        shown = stage
        frame = result.stages[stage].frame

    columns = sorted(frame.columns)
    return ProcessingPreviewOut(
        source_curve_key=curve.key,
        source_row_count=curve.row_count,
        row_count=frame.length(),
        columns=columns,
        units={name: frame.units.get(name, "1") for name in columns},
        stages=[_stage_out(stage_one) for stage_one in result.stages],
        scalars=[_scalar_out(item) for item in result.scalars],
        notes=list(result.notes),
        points=_points(frame, x or "", y or ""),
        stage_index=shown,
        problem=problem,
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
    run = get_run(db, user, payload.test_run_id)
    item = _store(
        db,
        run,
        payload.source_curve_key,
        payload.steps,
        _recipe_or_none(db, user, payload.recipe_key),
        user,
    )
    db.commit()
    db.refresh(item)
    return _result_out(item)


def _jsonable(options: dict[str, Any]) -> dict[str, Any]:
    """numpy 스칼라를 파이썬 값으로. JSONB 가 numpy 를 모른다."""
    return {
        key: (float(value) if isinstance(value, np.floating | np.integer) else value)
        for key, value in options.items()
    }


def _result_out(item: ProcessingResult, *, adopted: bool = False) -> ProcessingResultOut:
    return ProcessingResultOut(
        id=item.id,
        is_adopted=adopted,
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
                dimension=(str(s["dimension"]) if s.get("dimension") else None),
            )
            for s in item.scalars
        ],
        row_count=item.row_count,
        columns=item.columns,
        runtime={str(k): str(v) for k, v in (item.runtime or {}).items()},
        created_at=item.created_at,
    )


@router.get("/results", response_model=list[ProcessingResultOut])
def list_results(
    test_run_id: uuid.UUID = Query(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProcessingResultOut]:
    run = get_run(db, user, test_run_id)
    items = db.scalars(
        select(ProcessingResult)
        .where(ProcessingResult.test_run_id == run.id)
        .order_by(ProcessingResult.created_at.desc())
    )
    return [_result_out(item, adopted=item.id == run.adopted_result_id) for item in items]


# --- 레시피 ------------------------------------------------------------------


def _visible_recipes(db: Session, user: User) -> Select[tuple[ProcessingRecipe]]:
    """내 부서 것 + 전역. 재료·프로파일·시험 종류와 **같은 규칙, 같은 코드**다.

    **지운 것은 여기서 빠진다.** 소프트 삭제라 행은 남는다 — 이 한 곳을 안 거르면
    지운 레시피가 처리 탭의 레시피 고르기에 그대로 뜬다.
    """
    return select(ProcessingRecipe).where(
        visible_owner_clause(db, user, ProcessingRecipe.owner_workspace_id),
        ProcessingRecipe.deleted_at.is_(None),
    )


def _recipe_out(db: Session, item: ProcessingRecipe) -> RecipeOut:
    owner = db.get(Workspace, item.owner_workspace_id) if item.owner_workspace_id else None
    test_type = db.get(TestType, item.test_type_id)
    return RecipeOut(
        id=item.id,
        key=item.key,
        label=item.label,
        description=item.description,
        revision=item.revision,
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
            # **지운 것은 안 센다.** 위 프로파일·시험 정의와 같은 이유다.
            ProcessingRecipe.deleted_at.is_(None),
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
    payload: RecipeUpdateRequest,
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
    # **덮어쓰기를 막는다**(ADR 0015). 레시피는 단계를 통째로 갈아 끼우므로,
    # 뒤에 저장한 쪽이 앞의 단계 구성을 지운다.
    revision.guard(
        db, item, payload.expected_revision, what="레시피", code="MNX-PROCESSING-0010"
    )
    _validate(payload.steps)
    item.label = payload.label
    item.description = payload.description
    item.test_type_id = _resolve_type(db, payload.test_type_key).id
    item.steps = payload.steps
    item.is_active = payload.is_active
    revision.bump(item)
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
    # **지우는 것이 아니라 감추는 것이다.** 되살리는 길은 휴지통에 있다.
    # 위에서 끊은 연결은 되돌리지 않는다 — 결과는 스냅샷으로 이미 자기가 무엇으로
    # 계산됐는지 알고, 그것이 이 화면이 처음부터 지킨 규칙이다.
    item.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


# --- 채택 --------------------------------------------------------------------
#
# **저장된 결과가 전부 동등하면 "이 시험의 항복강도" 에 답할 수 없다.**
# 시도는 자유롭게 쌓이고, 대표는 사람이 한 번 정한다(ADR 0007).


def _project_summaries(db: Session, run: TestRun, result: ProcessingResult | None) -> None:
    """채택된 결과의 값을 요약값 표에 **투영**한다.

    왜 복사하는가: 목록·통계·비교·내보내기가 값을 찾을 곳이 하나여야 한다.
    `TestSummary` 는 이미 그 자리이고, `source` 로 장비 값과 우리 값을 나란히
    두게 설계돼 있었다 — 그런데 지금까지 `matnexus` 쪽이 비어 있었다. 처리가
    자기 JSONB 에만 값을 두고 있었기 때문이다. 같은 성격의 값이 두 곳에 있고
    둘이 서로를 모르는 상태였다.

    **정본은 여전히 결과다.** 여기 있는 것은 파생이고, 채택을 바꾸면 통째로
    다시 만들어진다. 그래서 갱신이 아니라 삭제 후 삽입이다 — 갱신으로 하면
    예전 채택에만 있던 키가 남아 두 계산이 섞인 표가 된다.
    """
    db.execute(
        delete(TestSummary).where(
            TestSummary.test_run_id == run.id, TestSummary.source == "matnexus"
        )
    )
    if result is None:
        return
    for item in result.scalars:
        db.add(
            TestSummary(
                test_run_id=run.id,
                key=str(item.get("key", "")),
                label=str(item.get("label") or item.get("key", "")),
                source="matnexus",
                value_num=float(item.get("value", 0.0)),
                si_unit=str(item.get("si_unit") or "1"),
                dimension=(str(item["dimension"]) if item.get("dimension") else None),
            )
        )


@router.post("/results/{result_id}/adopt", response_model=ProcessingResultOut)
def adopt(
    result_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingResultOut:
    """이 결과를 **이 시험의 물성**으로 삼는다.

    시험당 하나뿐이다 — 포인터가 하나이므로 구조적으로 그렇다. 다른 것을 채택하면
    앞의 것은 시도 목록에 그대로 남는다(지워지지 않는다).
    """
    item = db.get(ProcessingResult, result_id)
    if item is None:
        raise NotFound("MNX-PROCESSING-0010", "처리 결과를 찾을 수 없습니다.")
    run = get_run(db, user, item.test_run_id)
    run.adopted_result_id = item.id
    _project_summaries(db, run, item)
    db.commit()
    db.refresh(item)
    return _result_out(item, adopted=True)


#: 저장된 결과를 열었을 때 먼저 보여 줄 축. 앞이 우선이다.
#:
#: 공칭이 먼저인 것은 그것이 사람이 시험기에서 보던 곡선이기 때문이다. 진응력은
#: **레시피에 '진응력·진소성변형률' 단계를 넣었을 때만** 존재한다 — 없으면 여기
#: 목록에서 그냥 안 걸리고, 화면의 축 목록에도 안 뜬다. 그 없음이 곧 답이다.
RESULT_AXIS_PAIRS = (
    ("strain_engineering", "stress_engineering"),
    ("strain_true_plastic", "stress_true"),
    ("strain_true", "stress_true"),
)


def _result_axes(columns: list[str], x: str | None, y: str | None) -> tuple[str, str]:
    if x and y:
        return x, y
    present = set(columns)
    for left, right in RESULT_AXIS_PAIRS:
        if left in present and right in present:
            return left, right
    return (columns[0], columns[1]) if len(columns) >= 2 else ("", "")


@router.get("/results/{result_id}/curve", response_model=ResultCurveOut)
def result_curve(
    result_id: uuid.UUID,
    x: str | None = Query(default=None),
    y: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResultCurveOut:
    """저장된 결과의 곡선. **다시 계산하지 않는다.**

    저장할 때 쓴 파일을 그대로 읽는다. 재계산하면 그 사이 플러그인이 바뀌었을 때
    화면의 그림과 표의 값이 서로 다른 것에서 나올 수 있고, 그 어긋남은 아무도
    못 본다 — 결과가 불변인 이유와 같다(ADR 0007).
    """
    item = db.get(ProcessingResult, result_id)
    if item is None:
        raise NotFound("MNX-PROCESSING-0010", "처리 결과를 찾을 수 없습니다.")
    get_run(db, user, item.test_run_id)  # 가시성 판정

    data = filestore.read_bytes(item.storage_path)
    columns = sorted(curves.column_names(data))
    axis_x, axis_y = _result_axes(columns, x, y)
    units = curves.read_units(data)
    points: list[tuple[float, float]] = []
    if axis_x in columns and axis_y in columns:
        raw = curves.read_columns(data, [axis_x, axis_y])
        points = curves.downsample(raw[axis_x], raw[axis_y], max_points=PREVIEW_POINTS)
    return ResultCurveOut(
        result_id=item.id,
        x=axis_x,
        y=axis_y,
        columns=columns,
        units={name: units.get(name, "1") for name in columns},
        row_count=item.row_count,
        points=points,
    )


@router.delete("/results/{result_id}/adopt", status_code=204)
def unadopt(
    result_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """채택을 거둔다. **결과는 지워지지 않는다** — 대표만 없어진다."""
    item = db.get(ProcessingResult, result_id)
    if item is None:
        raise NotFound("MNX-PROCESSING-0010", "처리 결과를 찾을 수 없습니다.")
    run = get_run(db, user, item.test_run_id)
    if run.adopted_result_id != item.id:
        raise AppError("MNX-PROCESSING-0011", "채택된 결과가 아닙니다.", status=409)
    run.adopted_result_id = None
    _project_summaries(db, run, None)
    db.commit()
    return Response(status_code=204)


# --- 배치 --------------------------------------------------------------------
#
# **시편 20개를 하나씩 처리하는 것은 일이 아니다.** 한 건으로 단계를 맞춘 뒤
# 나머지에 같은 것을 거는 것이 실제 작업 흐름이고, 그것이 안 되면 실데이터를
# 넣어 볼 수가 없다.

#: 한 번에 처리할 수 있는 시험 수. 서버가 상한을 강제한다(CLAUDE.md).
#:
#: **동기로 둔다. 실측이 그렇게 하라고 했다.**
#:
#:     34건 배치 (실서버, HTTP)        1,026ms  → 건당 30ms
#:     matcore 계산만  30,000행            4ms
#:                    100,000행           10ms
#:
#: 건당 30ms 는 **거의 전부 Parquet 읽기·쓰기와 DB** 다. 행 수는 사실상 공짜다.
#: 그래서 30건에 각 30,000행이라도 1초 안쪽이고, 워커로 옮길 이유가 지금은 없다.
#:
#: 처음에는 행 수로 외삽해 "25분" 이라는 숫자를 냈는데 **틀렸다.** 고정비가
#: 지배하는 것을 재 보지 않고 비례한다고 가정했기 때문이다. 재고 나서 판단이
#: 뒤집혔다.
#:
#: 계획서의 'DB 큐 워커로 장시간 처리 이관' 은 남아 있다 — 이 상한을 넘겨야 할
#: 만큼 커지거나, 처리 단계 자체가 무거워지면(적합·최적화) 그때 옮긴다.
#:
#: **100 → 1000 (2026-08-27).** 옛 DB 이관에서 걸렸다 — 한 재료의 시편이 수백
#: 장이고, 그것을 열 번에 나눠 거는 것은 「나머지에 같은 것을 건다」 는 이 기능의
#: 뜻을 반쯤 없앤다.
#:
#: 위 실측(건당 30ms)이 그대로 근거다 — 1000건이면 **30초쯤**이다. 고정비가
#: 지배하므로 행 수가 커져도 크게 안 늘어난다. 다만 30초는 **사람이 기다리기에는
#: 긴 시간**이라, 화면이 「몇 건 도는 중」 을 말해야 한다.
#:
#: 여기서 더 키우려면 워커로 옮겨야 한다. HTTP 요청 하나가 분 단위로 열려 있는
#: 것은 프록시·브라우저가 끊는 자리이고, 그때는 **어디까지 됐는지 알 방법이
#: 없다** — 건별로 커밋하므로 데이터는 남지만 응답을 못 받는다.
MAX_BATCH = 1000


@router.post("/batch", response_model=BatchOut)
def run_batch(
    payload: BatchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BatchOut:
    """여러 시험에 같은 단계를 건다.

    **부분 실패는 실패가 아니다.** 20건 중 하나가 시편 치수 때문에 막혔다고
    전체를 되돌리면 19건을 다시 해야 하고, 조용히 건너뛰면 사람은 다 된 줄 안다.
    그래서 건별 결과를 그대로 돌려주고, 성공한 것은 그 자리에서 커밋한다.

    실패 이유는 건마다 다르다 — 시편 치수가 없는 것, 탄성 구간에 점이 없는 것,
    채널 이름이 다른 것이 한 배치에 섞여 온다. 하나로 뭉뚱그리면 무엇을 고쳐야
    하는지 알 수 없다.
    """
    if len(payload.test_run_ids) > MAX_BATCH:
        raise AppError(
            "MNX-PROCESSING-0012",
            f"한 번에 {MAX_BATCH}건까지입니다 ({len(payload.test_run_ids)}건 요청). "
            f"나눠서 돌리세요.",
            status=422,
        )
    recipe = _recipe_or_none(db, user, payload.recipe_key)

    items: list[BatchItemOut] = []
    for run_id in payload.test_run_ids:
        # 못 보는 시험도 **건별 실패**로 남긴다. 여기서 404 를 던지면 앞의 성공까지
        # 없던 일이 되고, 사람은 무엇이 문제인지 모른 채 처음부터 다시 한다.
        try:
            run = get_run(db, user, run_id)
        except AppError as exc:
            items.append(
                BatchItemOut(
                    test_run_id=run_id, record_name="?", status="failed", error=exc.message
                )
            )
            continue

        try:
            stored = _store(db, run, payload.source_curve_key, payload.steps, recipe, user)
        except AppError as exc:
            db.rollback()
            items.append(
                BatchItemOut(
                    test_run_id=run_id,
                    record_name=run.record_name,
                    status="failed",
                    error=exc.message,
                )
            )
            continue

        adopted = False
        if payload.adopt:
            run.adopted_result_id = stored.id
            _project_summaries(db, run, stored)
            adopted = True
        db.commit()
        db.refresh(stored)
        items.append(
            BatchItemOut(
                test_run_id=run.id,
                record_name=run.record_name,
                status="ok",
                result_id=stored.id,
                adopted=adopted,
                scalars=[
                    ProcessingScalarOut(
                        key=str(s.get("key", "")),
                        label=str(s.get("label", "")),
                        value=float(s.get("value", 0.0)),
                        si_unit=str(s.get("si_unit") or "1"),
                        dimension=(str(s["dimension"]) if s.get("dimension") else None),
                    )
                    for s in stored.scalars
                ],
            )
        )

    succeeded = sum(1 for item in items if item.status == "ok")
    return BatchOut(
        requested=len(items), succeeded=succeeded, failed=len(items) - succeeded, items=items
    )
