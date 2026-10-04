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

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.formulas.models import Formula
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import (
    ProcessingRecipe,
    ProcessingResult,
    ProcessingResultFormula,
)
from app.modules.processing.schemas import (
    AdoptManyItemOut,
    AdoptManyOut,
    AdoptManyRequest,
    BatchItemOut,
    BatchOut,
    BatchRequest,
    BatchUndoItemOut,
    BatchUndoOut,
    BatchUndoRequest,
    CurvesRequest,
    OverviewRequest,
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
    ResultBriefOut,
    ResultContextOut,
    ResultCurveOut,
    ResultGuideOut,
    ResultLineOut,
    RunOverviewOut,
    StagePointsOut,
    StepParamOut,
)
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.models import Curve, TestRun, TestSummary, TestType
from app.modules.workspaces.models import Workspace
from app.shared import (
    audit,
    curvedata,
    definition_keys,
    filestore,
    permissions,
    revision,
    test_type_channels,
)
from app.shared.access import AccessBook, EditAccessOut, access_of
from app.shared.auth import current_user
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.permissions import get_run, visible_runs
from matcore import curves, processing, registry, runtime
from matcore.parsers import Channel
from matcore.processing import SCALAR_KEY_MAX

router = APIRouter(prefix="/processing", tags=["processing"])

#: 미리보기가 돌려주는 점 수 상한. 화면 픽셀에 겹치는 점을 보낼 이유가 없다.
PREVIEW_POINTS = 600

#: 단계별 곡선은 **뒤에 깔린다** — 그림용이라 600점까지 필요 없다. 단계가 예닐곱
#: 이면 응답이 그만큼 커지는데, 켜 보지도 않는 사람에게까지 그 값을 물린다.
STAGE_POINTS = 300


# --- 단계 목록 ---------------------------------------------------------------


def _produced(item: registry.Produced) -> ProducedOut:
    return ProducedOut(
        key=item.key,
        label=item.label,
        si_unit=item.si_unit,
        help=item.help,
        property_key=item.property_key,
    )


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


def _recipe_or_none(db: Session, key: str | None) -> ProcessingRecipe | None:
    if not key:
        return None
    recipe = db.scalar(_visible_recipes(db).where(ProcessingRecipe.key == key))
    if recipe is None:
        raise NotFound("MNX-PROCESSING-0005", f"레시피를 찾을 수 없습니다: {key}")
    return recipe


def _comparable(steps: list[dict[str, Any]] | None) -> list[tuple[str, dict[str, Any]]]:
    """단계를 견줄 모양으로 — **빈 옵션은 없는 것과 같다**(화면이 비운 칸을 null 로 보낸다)."""
    return [
        (
            str(step.get("plugin", "")),
            {
                key: value
                for key, value in dict(step.get("options") or {}).items()
                if value is not None
            },
        )
        for step in steps or []
    ]


def _recipe_link(
    recipe: ProcessingRecipe | None, steps: list[dict[str, Any]]
) -> tuple[ProcessingRecipe | None, str | None]:
    """`(이을 레시피, 결과에 남길 이름)`. **단계가 그 레시피와 같을 때만 잇는다.**

    화면은 레시피를 불러온 뒤 단계를 고칠 수 있다. 고친 것을 그 레시피의 결과라고 적으면
    「이 레시피로 낸 결과」(그래프의 `ran_with`)에 다른 단계의 결과가 섞인다 — 그래서 고쳤으면
    잇지 않고 이름에만 어디서 시작했는지 남긴다. 단계 자체는 늘 스냅숏으로 남는다.
    """
    if recipe is None:
        return None, None
    if _comparable(steps) == _comparable(recipe.steps):
        return recipe, recipe.label
    return None, f"{recipe.label} (단계 고침)"[:120]


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
        extra={CONTEXT_KEY: _context_bytes(result.stages)},
        channels=[
            Channel(
                key=name,
                label=name,
                si_unit=frame.units.get(name, "1"),
                values=tuple(
                    None if np.isnan(value) else float(value) for value in frame.columns[name]
                ),
            )
            for name in sorted(frame.columns)
        ],
    )
    # **결과마다 새 파일이다.** 불변이므로 덮어쓸 일이 없고, 덮어쓰기가 없으면
    # "예전 결과를 열었더니 값이 달라졌다" 가 구조적으로 불가능하다.
    stored = filestore.write_bytes(
        data, relative_dir=f"processing/{run.id}", filename=f"{uuid.uuid4().hex}.parquet"
    )
    linked, label = _recipe_link(recipe, steps)
    item = ProcessingResult(
        test_run_id=run.id,
        source_curve_key=curve.key,
        recipe_id=linked.id if linked else None,
        recipe_key=linked.key if linked else None,
        recipe_label=label,
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
    # **식 단계마다 연결 한 줄** — 「이 값 어느 식으로 계산됐나」 를 그래프가 걷는다(4단계).
    # 식이 지워졌거나 키가 바뀐 경우는 그냥 넘어간다 — 결과 저장이 식 목록에 막히면 안 된다.
    _link_formulas(db, item)
    return item


def _link_formulas(db: Session, item: ProcessingResult) -> None:
    """`stages[].plugin == "formula.<key>"` 인 단계를 식 행에 잇는다(4단계, 2026-09-16).

    식이 지워졌거나 키가 바뀐 경우는 그냥 넘어간다 — 결과 저장이 식 목록에 막히면 안 된다.
    """
    keys = {
        str(stage.get("plugin", "")).removeprefix("formula.")
        for stage in item.stages or []
        if str(stage.get("plugin", "")).startswith("formula.")
    }
    if not keys:
        return
    for row in db.scalars(select(Formula).where(Formula.key.in_(keys))):
        db.add(
            ProcessingResultFormula(
                result_id=item.id, formula_id=row.id, formula_version=int(row.version)
            )
        )


def _batch_scalars(rows: Any) -> list[ProcessingScalarOut]:
    """저장된 결과의 스칼라 → 응답 모양. **미리보기와 저장이 같은 함수를 쓴다.**"""
    return [
        ProcessingScalarOut(
            key=str(one.get("key", "")),
            label=str(one.get("label", "")),
            value=float(one.get("value", 0.0)),
            si_unit=str(one.get("si_unit") or "1"),
            dimension=(str(one["dimension"]) if one.get("dimension") else None),
        )
        for one in (rows or [])
    ]


def _adopted_scalars(db: Session, run: TestRun) -> list[ProcessingScalarOut]:
    """지금 이 시험의 값. 채택된 결과가 없으면 빈 목록."""
    if run.adopted_result_id is None:
        return []
    found = db.get(ProcessingResult, run.adopted_result_id)
    return _batch_scalars(found.scalars) if found else []


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


def _points(
    frame: processing.Frame, x: str, y: str, *, max_points: int = PREVIEW_POINTS
) -> list[tuple[float, float]]:
    """이 프레임의 두 열을 점으로. **없는 축이면 빈 목록이다.**

    빈 것과 「값이 0 인 것」 은 다르다 — 진소성변형률은 변환 단계에서 생기므로
    그 앞 단계에는 아예 없다. 여기서 0 으로 채우면 화면이 없는 곡선을 그린다.
    """
    if x not in frame.columns or y not in frame.columns:
        return []
    return curves.downsample(
        [None if np.isnan(v) else float(v) for v in frame.columns[x]],
        [None if np.isnan(v) else float(v) for v in frame.columns[y]],
        max_points=max_points,
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
    # **단계마다의 곡선을 함께 준다.** 화면이 골라 겹쳐 보는 데 쓴다 — 켤 때마다
    # 서버를 부르면 그때마다 파이프라인 전체가 다시 돈다.
    stage_points = [
        StagePointsOut(
            index=one.index,
            label=one.label,
            points=_points(one.frame, x or "", y or "", max_points=STAGE_POINTS),
        )
        for one in result.stages
    ]
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
        stage_points=stage_points,
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
        _recipe_or_none(db, payload.recipe_key),
        user,
    )
    # **「이 결과 누가 돌렸지」.** 사람이 화면에서 돌린 것은 안 남는다 — 결과 자체가
    # 단계·버전·실행 환경을 통째로 들고 있어 그걸로 충분하다. 빠진 것은 **길**
    # 하나였다: 같은 토큰으로 AI 가 돌린 것과 사람이 돌린 것이 구별되지 않았다.
    audit.record_by_client(
        db,
        action=audit.PROCESSING_RUN_BY_CLIENT,
        actor=user,
        target_table="processing_results",
        target_id=item.id,
        target_label=run.record_name,
        workspace_id=run.workspace_id,
        changes={"steps": len(payload.steps), "recipe": payload.recipe_key},
    )
    db.commit()
    db.refresh(item)
    return _result_out(item)


def _require_result_removal(
    db: Session, user: User, run: TestRun, item: ProcessingResult
) -> None:
    """처리 결과를 지울 수 있나 — **만든 사람**이거나 그 시험을 고칠 수 있는 사람.

    결과는 불변이라 고치는 길이 없고 지우는 길만 있다. 전에는 부서 관리자만 지울 수
    있어서 자기가 돌려 본 결과를 자기가 못 치웠다(ADR 0035 배경).
    """
    if item.created_by_id is not None and item.created_by_id == user.id:
        return
    permissions.require_edit(db, user, run, code="MNX-PROCESSING-0015")


def _jsonable(options: dict[str, Any]) -> dict[str, Any]:
    """numpy 스칼라를 파이썬 값으로. JSONB 가 numpy 를 모른다."""
    return {
        key: (float(value) if isinstance(value, np.floating | np.integer) else value)
        for key, value in options.items()
    }


def _stale(item: ProcessingResult, run: TestRun) -> bool:
    """원본을 바꾼 뒤에 만든 결과가 아니면 옛 곡선의 것이다."""
    return run.source_replaced_at is not None and item.created_at < run.source_replaced_at


def _result_out(
    item: ProcessingResult, *, adopted: bool = False, stale: bool = False
) -> ProcessingResultOut:
    return ProcessingResultOut(
        id=item.id,
        is_adopted=adopted,
        stale=stale,
        test_run_id=item.test_run_id,
        source_curve_key=item.source_curve_key,
        recipe_key=item.recipe_key,
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
    return [
        _result_out(item, adopted=item.id == run.adopted_result_id, stale=_stale(item, run))
        for item in items
    ]


# --- 레시피 ------------------------------------------------------------------


def _visible_recipes(db: Session) -> Select[tuple[ProcessingRecipe]]:
    """살아 있는 레시피 전부. **전원이 전부 본다**(ADR 0035).

    남의 부서가 어떤 규격으로 탄성 구간을 잡는지 보이는 것이 공유의 절반이다 — 같은
    재료를 두 부서가 다르게 처리했으면 그 차이가 어디서 왔는지 레시피가 말해 준다.
    고치는 것은 등록자 · 편집을 받은 부서 · 자료 관리자다(`permissions.require_edit`).

    **지운 것은 여기서 빠진다.** 소프트 삭제라 행은 남는다 — 이 한 곳을 안 거르면
    지운 레시피가 처리 탭의 레시피 고르기에 그대로 뜬다.
    """
    return select(ProcessingRecipe).where(ProcessingRecipe.deleted_at.is_(None))


def _audit_recipe(db: Session, user: User, item: ProcessingRecipe, *, made: bool) -> None:
    """레시피를 **사람이 아닌 것이** 저장했으면 남긴다.

    레시피는 「이 부서가 어느 규격을 따르는가」 다(ADR 0005·0006). 과거의 결과는
    스냅샷이 지켜 주지만, **앞으로 돌아갈 모든 처리**가 이 단계 구성을 쓴다 —
    그것을 AI 가 소리 없이 바꿔 두면 다음 사람은 자기가 무엇을 따르는지 모른다.
    """
    audit.record_by_client(
        db,
        action=audit.RECIPE_SAVED_BY_CLIENT,
        actor=user,
        target_table="processing_recipes",
        target_id=item.id,
        target_label=f"{item.label} ({item.key})",
        workspace_id=item.owner_workspace_id,
        changes={"created": made, "steps": len(item.steps or [])},
    )


def _recipe_out(
    db: Session, item: ProcessingRecipe, access: EditAccessOut | None = None
) -> RecipeOut:
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
        access=access,
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
    query = _visible_recipes(db).order_by(ProcessingRecipe.label)
    if test_type:
        query = query.where(ProcessingRecipe.test_type_id == _resolve_type(db, test_type).id)
    items = list(db.scalars(query))
    book = AccessBook(db, user).prime(items)
    return [_recipe_out(db, item, book.of(item)) for item in items]


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def create_recipe(
    payload: RecipeCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    """누구나 만든다 — 등록자가 고치고, 필요하면 부서에 편집을 준다(ADR 0035).

    **부서마다 규격이 다르다.** 탄성 구간을 어디로 잡을지는 따르는 규격이 정하고,
    그 판단은 그 부서가 한다 — 형식 프로파일과 같은 이유다(ADR 0005·0006). 그래서
    등록 부서를 적어 둔다(안 보내면 내 소속).
    """
    owner_id = permissions.registering_workspace(
        db,
        user,
        payload.owner_workspace_slug,
        given="owner_workspace_slug" in payload.model_fields_set,
        what="레시피",
        code="MNX-PROCESSING-0007",
    )
    # **지운 것은 안 센다.** 위 프로파일·시험 정의와 같은 이유다.
    key = definition_keys.resolve(
        db,
        ProcessingRecipe,
        payload.key,
        prefix="rcp",
        what="레시피",
        code="MNX-PROCESSING-0008",
    )
    _validate(payload.steps)
    item = ProcessingRecipe(
        key=key,
        label=payload.label,
        description=payload.description,
        owner_workspace_id=owner_id,
        test_type_id=_resolve_type(db, payload.test_type_key).id,
        steps=payload.steps,
        is_active=payload.is_active,
        created_by_id=user.id,
    )
    db.add(item)
    db.flush()
    _audit_recipe(db, user, item, made=True)
    db.commit()
    db.refresh(item)
    return _recipe_out(db, item, access_of(db, user, item))


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
    item = db.scalar(_visible_recipes(db).where(ProcessingRecipe.key == key))
    if item is None:
        raise NotFound("MNX-PROCESSING-0009", f"레시피를 찾을 수 없습니다: {key}")
    permissions.require_edit(db, user, item, code="MNX-PROCESSING-0007")
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
    _audit_recipe(db, user, item, made=False)
    db.commit()
    db.refresh(item)
    return _recipe_out(db, item, access_of(db, user, item))


@router.delete("/recipes/{key}", status_code=204)
def delete_recipe(
    key: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    item = db.scalar(_visible_recipes(db).where(ProcessingRecipe.key == key))
    if item is None:
        raise NotFound("MNX-PROCESSING-0009", f"레시피를 찾을 수 없습니다: {key}")
    permissions.require_edit(db, user, item, code="MNX-PROCESSING-0007")
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


def _require_adoptable(item: ProcessingResult) -> None:
    """채택할 수 있는 결과인가 — 한 건 · 여러 건이 같은 규칙으로 막는다.

    이 검사가 생기기 전(2026-10-04)에 저장된 결과는 긴 이름을 들고 있을 수 있다 —
    요약값 칸에 안 들어가 500 이었다. 결과는 불변이라 고칠 수 없고, 다시 돌리는 것이 답이다.
    """
    too_long = [
        str(s.get("key", ""))
        for s in item.scalars
        if len(str(s.get("key", ""))) > SCALAR_KEY_MAX
    ]
    if too_long:
        raise Conflict(
            "MNX-PROCESSING-0018",
            f"이 결과는 이름이 {SCALAR_KEY_MAX}자를 넘는 값을 들고 있어 채택할 수 없습니다: "
            f"{', '.join(too_long)}. 그 계산이 이름을 줄인 뒤 같은 레시피로 다시 돌려 "
            f"저장한 결과를 채택하세요.",
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
    # **채택은 시험을 고치는 일이다**(ADR 0035) — 「이 시험의 물성은 이것」 이라는
    # 선언이라 통계·카드가 그것을 읽는다. 해석하는 사람이 다르면 그 부서에 편집을 준다.
    permissions.require_edit(db, user, run, code="MNX-PROCESSING-0017")
    _require_adoptable(item)
    run.adopted_result_id = item.id
    _project_summaries(db, run, item)
    db.commit()
    db.refresh(item)
    return _result_out(item, adopted=True, stale=_stale(item, run))


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


#: 채택 화면이 앞쪽 곡선 · 보조선을 그리는 축 — 공칭 응력-변형률.
CONTEXT_AXES = ("strain_engineering", "stress_engineering")

#: 결과 파일에 싣는 「자르기 전 곡선」 의 이름(`curves.read_extra`).
CONTEXT_KEY = "context"

#: 다시 계산한 앞쪽 곡선이 저장된 결과의 첫 점과 이만큼 넘게 어긋나면 그렇다고 말한다.
CONTEXT_MISMATCH = 0.01


def _context_points(stage: processing.Stage) -> list[tuple[float, float]]:
    """그 단계의 공칭 곡선을 그림용으로 줄인다. **NaN 은 결측으로** — JSON 에 못 싣는다."""
    x_key, y_key = CONTEXT_AXES

    def finite(values: np.ndarray) -> list[float | None]:
        return [float(value) if np.isfinite(value) else None for value in values]

    return curves.downsample(
        finite(stage.frame.columns[x_key]),
        finite(stage.frame.columns[y_key]),
        max_points=PREVIEW_POINTS,
    )


def _context_bytes(stages: tuple[processing.Stage, ...]) -> bytes:
    """결과 파일에 싣는 앞쪽 곡선. **앞을 안 잃었으면 `null`** — 「없다」 가 아니라
    「필요 없다」 를 적어 둬야, 이 칸이 생기기 전의 파일(키가 아예 없다)과 갈린다."""
    stage = processing.front_intact_stage(stages, *CONTEXT_AXES)
    if stage is None or stage is stages[-1]:
        return b"null"
    return json.dumps(
        {"stage": f"{stage.index + 1}. {stage.label}", "points": _context_points(stage)}
    ).encode()


def _first_point(data: bytes) -> tuple[float, float] | None:
    """저장된 결과의 공칭 곡선에서 변형률이 가장 작은 점 — 앞이 어디서 잘렸나."""
    x_key, y_key = CONTEXT_AXES
    raw = curves.read_columns(data, list(CONTEXT_AXES))
    pairs = [
        (float(x), float(y))
        for x, y in zip(raw[x_key], raw[y_key], strict=True)
        if x is not None and y is not None and np.isfinite(x) and np.isfinite(y)
    ]
    return min(pairs) if pairs else None


def _recomputed_context(
    db: Session, run: TestRun, item: ProcessingResult, data: bytes
) -> tuple[ResultContextOut | None, str | None]:
    """**이 칸이 생기기 전에 저장한 결과** — 그 결과의 단계를 지금 원본에 다시 돌린다
    (ADR 0053).

    저장된 값이 아니라 참고 그림이다. 그 사이 원본 · 시편 값 · 플러그인이 바뀌었으면 그림이
    결과와 어긋날 수 있으므로, 저장된 결과의 첫 점이 다시 계산한 곡선 위에 있는지 견주고
    어긋나면 그렇다고 적는다.
    """
    try:
        stages = _run_pipeline(db, run, item.source_curve_key, list(item.steps_snapshot))[
            0
        ].stages
    except AppError as exc:
        # **여기까지 된 것을 쓴다.** 뒤 단계가 멈춰도 앞쪽 곡선은 대개 이미 나와 있다.
        done = getattr(exc, "done", None)
        if done is None or not done.stages:
            return None, f"앞쪽 곡선을 다시 그리지 못했습니다 — {exc.message}"
        stages = done.stages
    stage = processing.front_intact_stage(stages, *CONTEXT_AXES)
    first = _first_point(data)
    if stage is None or first is None:
        return None, None
    x_key, y_key = CONTEXT_AXES
    xs, ys = stage.frame.columns[x_key], stage.frame.columns[y_key]
    if float(np.nanmin(xs)) >= first[0]:
        return None, None  # 저장된 결과가 앞을 안 잃었다 — 결과 곡선이 곧 전체다
    order = np.argsort(xs)
    expected = float(np.interp(first[0], xs[order], ys[order]))
    note = None
    if first[1] and abs(expected - first[1]) > CONTEXT_MISMATCH * abs(first[1]):
        gap = abs(expected - first[1]) / abs(first[1]) * 100
        note = (
            f"다시 계산한 곡선이 저장된 결과의 첫 점과 {gap:.1f}% 어긋납니다 — 그 사이 "
            f"원본 · 시편 값 · 처리 방식이 바뀌었을 수 있습니다."
        )
    context = ResultContextOut(
        points=_context_points(stage),
        stage_label=f"{stage.index + 1}. {stage.label}",
        recomputed=True,
        note=note,
    )
    return context, None


def _context(
    db: Session, run: TestRun, item: ProcessingResult, data: bytes
) -> tuple[ResultContextOut | None, str | None]:
    stored = curves.read_extra(data, CONTEXT_KEY)
    if stored is None:
        return _recomputed_context(db, run, item, data)
    body = json.loads(stored)
    if body is None:
        return None, None
    return (
        ResultContextOut(
            points=[(float(x), float(y)) for x, y in body["points"]],
            stage_label=str(body["stage"]),
            recomputed=False,
        ),
        None,
    )


def _stage_axes(stage: Mapping[str, Any]) -> tuple[str, str]:
    options = stage.get("options") or {}
    return (
        str(options.get("strain") or CONTEXT_AXES[0]),
        str(options.get("stress") or CONTEXT_AXES[1]),
    )


def _last_stage(item: ProcessingResult, plugin: str) -> Mapping[str, Any] | None:
    found = [stage for stage in item.stages or [] if stage.get("plugin") == plugin]
    return found[-1] if found else None


def _guides(
    item: ProcessingResult,
) -> tuple[list[ResultGuideOut], tuple[float, float] | None]:
    """결과에 든 값으로 긋는 보조선 — **그 값을 잰 단계가 공칭 축에서 쟀을 때만.**

    탄성 직선은 탄성계수 단계가 맞춘 σ = Eε + 절편, 오프셋 선은 항복강도 단계가 교점을
    찾은 σ = E(ε - 오프셋) 그대로다(그 단계에 들어간 E — 직접 넣었으면 그 값). 선은 항복강도의
    1.2 배까지 — 없으면 인장강도의 0.9 배까지 — 긋는다. 곡선 전체 높이로 그으면 탄성 구간이
    눌려 안 보인다.
    """
    values = {
        str(one.get("key")): float(one["value"])
        for one in item.scalars or []
        if isinstance(one.get("value"), int | float)
    }
    proof = values.get("proof_stress")
    strength = values.get("tensile_strength")
    top = 1.2 * proof if proof else (0.9 * strength if strength else None)
    if not top or top <= 0:
        return [], None
    guides: list[ResultGuideOut] = []
    elastic = _last_stage(item, "tensile.elastic_modulus")
    modulus = values.get("youngs_modulus")
    if (
        elastic is not None
        and modulus
        and modulus > 0
        and _stage_axes(elastic) == CONTEXT_AXES
    ):
        intercept = values.get("elastic_intercept", 0.0)
        guides.append(
            ResultGuideOut(
                kind="elastic",
                modulus=modulus,
                points=[(-intercept / modulus, 0.0), ((top - intercept) / modulus, top)],
            )
        )
    yielded: tuple[float, float] | None = None
    proof_stage = _last_stage(item, "tensile.proof_stress")
    proof_strain = values.get("proof_strain")
    if (
        proof_stage is not None
        and proof
        and proof_strain is not None
        and _stage_axes(proof_stage) == CONTEXT_AXES
    ):
        used = (proof_stage.get("options") or {}).get("youngs_modulus")
        slope = float(used) if isinstance(used, int | float) and used > 0 else modulus
        offset = values.get("proof_offset", 0.002)
        if slope and slope > 0:
            guides.append(
                ResultGuideOut(
                    kind="offset",
                    modulus=slope,
                    offset=offset,
                    points=[(offset, 0.0), (offset + top / slope, top)],
                )
            )
        yielded = (proof_strain, proof)
    return guides, yielded


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
    run = get_run(db, user, item.test_run_id)  # 가시성 판정

    data = filestore.read_bytes(item.storage_path)
    columns = sorted(curves.column_names(data))
    axis_x, axis_y = _result_axes(columns, x, y)
    units = curves.read_units(data)
    points: list[tuple[float, float]] = []
    if axis_x in columns and axis_y in columns:
        raw = curves.read_columns(data, [axis_x, axis_y])
        points = curves.downsample(raw[axis_x], raw[axis_y], max_points=PREVIEW_POINTS)
    # **앞쪽 곡선 · 보조선은 공칭 축에서만** — 진응력 축에는 탄성 구간이라는 것이 없다.
    context: ResultContextOut | None = None
    context_note: str | None = None
    guides: list[ResultGuideOut] = []
    yielded: tuple[float, float] | None = None
    if (axis_x, axis_y) == CONTEXT_AXES and points:
        context, context_note = _context(db, run, item, data)
        guides, yielded = _guides(item)
    return ResultCurveOut(
        result_id=item.id,
        x=axis_x,
        y=axis_y,
        columns=columns,
        units={name: units.get(name, "1") for name in columns},
        row_count=item.row_count,
        points=points,
        context=context,
        context_note=context_note,
        guides=guides,
        yield_point=yielded,
    )


@router.delete("/results/{result_id}", status_code=204)
def delete_result(
    result_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """시도 하나를 **지운다. 되돌릴 수 없다.**

    ## 왜 필요한가 (2026-09-11 지적)

    *"각 시험 데이터에서 처리한 결과 삭제가 안 되는 문제가 있어. 삭제 버튼이
    없어."* 결과는 여러 벌 쌓이는 것이 정상이다(회귀로도 재고 현으로도 재고
    네킹 후보로 잘라도 본다). 그런데 지울 길이 없으니 **잘못 돌린 것과 견주려고
    돌린 것이 영원히 목록에 남고**, 그중 어느 것이 쓸 것인지가 갈수록 안 보인다.

    ## 두 가지는 막는다

        채택된 결과        이 시험의 물성이다 — 먼저 채택을 거두게 한다
        묶음이 근거로 쓴 것  평균이 무엇으로 나왔는지가 사라진다

    막는 쪽을 고른 이유: 둘 다 **다른 자리에 이미 실린 값**이라, 지우면 그 값이
    어디서 왔는지 답할 수 없게 된다. 채택은 한 번 거두면 되고, 묶음은 다시 낼 수
    있다 — 되돌릴 수 있는 쪽을 사람이 먼저 하게 한다.

    휴지통에 안 넣는다. 결과에는 `deleted_at` 이 없고(불변으로 설계했다), 그
    자리를 지금 만들면 「지운 결과가 통계에 잡히나」 를 모든 질의가 다시 물어야
    한다. 대신 **감사에 남긴다** — 그 값이 보고서에 실렸을 수 있다.
    """
    item = db.get(ProcessingResult, result_id)
    if item is None:
        raise NotFound("MNX-PROCESSING-0010", "처리 결과를 찾을 수 없습니다.")
    run = get_run(db, user, item.test_run_id)
    _require_result_removal(db, user, run, item)

    if run.adopted_result_id == item.id:
        raise Conflict(
            "MNX-PROCESSING-0013",
            "채택된 결과입니다 — 이 시험의 물성이라 지울 수 없습니다. 채택을 먼저 거두세요.",
        )

    # **FK 가 아니라 JSONB 배열이라 의존성 레지스트리가 못 잡는다.** 반복 시편
    # 통계는 「어느 결과로 냈는지」 를 id 목록으로 들고 있다
    # (`ensemble_results.result_ids`) — 그것이 평균의 근거다.
    used = db.scalar(
        select(func.count())
        .select_from(EnsembleResult)
        .where(EnsembleResult.result_ids.contains([str(item.id)]))
    )
    if used:
        raise Conflict(
            "MNX-PROCESSING-0014",
            f"반복 시편 통계 {used}건이 이 결과를 근거로 싣고 있어 지울 수 없습니다 — "
            f"지우면 그 평균이 무엇으로 나왔는지 알 수 없게 됩니다. "
            f"묶음을 먼저 지우거나 다시 내세요.",
        )

    audit.record(
        db,
        action=audit.PROCESSING_RESULT_DELETED,
        actor=user,
        target_table="processing_results",
        target_id=item.id,
        target_label=f"{run.record_name} · {len(item.steps_snapshot)}단계",
        workspace_id=run.workspace_id,
        changes={"created_at": str(item.created_at), "row_count": item.row_count},
    )
    # **행보다 파일을 먼저 지우지 않는다.** 파일만 지우고 커밋이 실패하면 행은
    # 남는데 곡선을 못 읽는다 — 그 결과는 열 때마다 500 이 난다.
    stored = item.storage_path
    db.delete(item)
    db.commit()
    filestore.delete_file(stored)
    return Response(status_code=204)


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
    permissions.require_edit(db, user, run, code="MNX-PROCESSING-0017")
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


@router.post("/batch/undo", response_model=BatchUndoOut)
def undo_batch(
    payload: BatchUndoRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BatchUndoOut:
    """방금 건 배치를 **되돌린다** — 만든 결과를 지우고 채택을 원래대로.

    ## 왜 「삭제」 가 아니라 「되돌리기」 인가

    배치는 대개 채택까지 함께 옮긴다. 만든 결과만 지우고 말면 **원래 있던 값까지
    사라진다** — 시험은 채택이 빈 상태로 남고, 사람은 배치를 걸기 전보다 나쁜
    자리에 선다. 그래서 부르는 쪽이 `restore_adopted_id`(배치 응답의
    `previous_adopted_id`)를 함께 보내고, 여기서 그것으로 돌려놓는다.

    ## 한 건씩과 같은 규칙으로 막는다

    통계가 근거로 실은 결과는 못 지운다(`delete_result` 와 같은 판단) — 되돌리는
    길이라고 그 규칙이 느슨해지지 않는다. 이미 없는 것은 **성공으로 친다**:
    되돌리기를 두 번 눌렀거나 누가 먼저 지운 것이고, 어느 쪽이든 원하는 상태다.

    **건별로 커밋한다.** 하나가 막혔다고 앞의 되돌리기를 취소하면, 사람은 무엇이
    남았는지 모른 채 다시 눌러야 한다.
    """
    rows: list[BatchUndoItemOut] = []
    for asked in payload.items:
        item = db.get(ProcessingResult, asked.result_id)
        if item is None:
            rows.append(BatchUndoItemOut(result_id=asked.result_id, status="missing"))
            continue
        try:
            run = get_run(db, user, item.test_run_id)
            _require_result_removal(db, user, run, item)
            used = db.scalar(
                select(func.count())
                .select_from(EnsembleResult)
                .where(EnsembleResult.result_ids.contains([str(item.id)]))
            )
            if used:
                raise Conflict(
                    "MNX-PROCESSING-0014",
                    f"반복 시편 통계 {used}건이 이 결과를 근거로 싣고 있어 지울 수 없습니다.",
                )

            restored = False
            if run.adopted_result_id == item.id:
                # **원래 채택으로 돌려놓는다.** 그 결과가 이 시험의 것이 아니면
                # 안 받는다 — 남의 시험 결과를 채택하는 길이 되면 안 된다.
                back = (
                    db.get(ProcessingResult, asked.restore_adopted_id)
                    if asked.restore_adopted_id
                    else None
                )
                if asked.restore_adopted_id and (back is None or back.test_run_id != run.id):
                    raise Conflict(
                        "MNX-PROCESSING-0016",
                        "되돌릴 채택 결과가 이 시험의 것이 아닙니다.",
                    )
                run.adopted_result_id = back.id if back else None
                _project_summaries(db, run, back)
                restored = back is not None

            audit.record(
                db,
                action=audit.PROCESSING_RESULT_DELETED,
                actor=user,
                target_table="processing_results",
                target_id=item.id,
                target_label=f"{run.record_name} · 배치 되돌리기",
                workspace_id=run.workspace_id,
                changes={"undo": True, "restored_adopted": restored},
            )
            stored = item.storage_path
            db.delete(item)
            db.commit()
            filestore.delete_file(stored)
            rows.append(
                BatchUndoItemOut(result_id=asked.result_id, status="ok", restored=restored)
            )
        except AppError as exc:
            db.rollback()
            rows.append(
                BatchUndoItemOut(result_id=asked.result_id, status="failed", error=exc.message)
            )

    undone = sum(1 for one in rows if one.status in ("ok", "missing"))
    return BatchUndoOut(
        requested=len(rows), undone=undone, failed=len(rows) - undone, items=rows
    )


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
    recipe = _recipe_or_none(db, payload.recipe_key)
    editor = permissions.editor(db, user)

    items: list[BatchItemOut] = []
    #: 감사 한 줄에 적을 부서. 여러 부서면 비운다(아래).
    workspaces: list[uuid.UUID | None] = []
    #: 채택까지 된 시험 — 남의 것이면 끝에서 한 번에 적는다(`note_edit`).
    took: list[TestRun] = []
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

        # **전과 후를 함께 낸다.** 「무엇이 어떻게 달라지나」 를 보고 정하려면
        # 지금 값이 있어야 한다. 실패한 건에도 붙인다 — 「원래 값은 있었는데
        # 이번에 못 냈다」 와 「원래도 없었다」 는 다른 말이다.
        before = _adopted_scalars(db, run)
        was_adopted = run.adopted_result_id

        # **채택까지 걸면 그 시험을 고칠 수 있어야 한다**(ADR 0035). 결과만 쌓는 것은
        # 누구나 하지만, 「이 시험의 물성」 을 바꾸는 것은 고치는 일이다. 미리보기에서도
        # 같은 자리에서 막아야 걸어 보고 나서 놀라지 않는다.
        if payload.adopt and not editor.allows(run):
            locked = permissions.locked(db, run, code="MNX-PROCESSING-0017")
            items.append(
                BatchItemOut(
                    test_run_id=run.id,
                    record_name=run.record_name,
                    status="failed",
                    error=f"{locked.message} 채택 없이 결과만 쌓으려면 채택을 끄세요.",
                    previous=before,
                    previous_adopted_id=was_adopted,
                )
            )
            continue

        try:
            if payload.dry_run:
                # **저장하지 않는다.** 파일도 행도 안 만들고 계산만 한다 —
                # `_store` 와 같은 `_run_pipeline` 을 지나므로 값이 어긋날 수 없다.
                computed, _ = _run_pipeline(db, run, payload.source_curve_key, payload.steps)
                items.append(
                    BatchItemOut(
                        test_run_id=run.id,
                        record_name=run.record_name,
                        status="ok",
                        adopted=False,
                        scalars=[_scalar_out(one) for one in computed.scalars],
                        previous=before,
                        previous_adopted_id=was_adopted,
                    )
                )
                continue
            stored = _store(db, run, payload.source_curve_key, payload.steps, recipe, user)
            workspaces.append(run.workspace_id)
        except AppError as exc:
            db.rollback()
            items.append(
                BatchItemOut(
                    test_run_id=run_id,
                    record_name=run.record_name,
                    status="failed",
                    error=exc.message,
                    previous=before,
                    previous_adopted_id=was_adopted,
                )
            )
            continue

        adopted = False
        if payload.adopt:
            run.adopted_result_id = stored.id
            _project_summaries(db, run, stored)
            adopted = True
            took.append(run)
        db.commit()
        db.refresh(stored)
        items.append(
            BatchItemOut(
                test_run_id=run.id,
                record_name=run.record_name,
                status="ok",
                result_id=stored.id,
                adopted=adopted,
                scalars=_batch_scalars(stored.scalars),
                previous=before,
                previous_adopted_id=was_adopted,
            )
        )

    succeeded = sum(1 for item in items if item.status == "ok")
    # **배치는 한 줄로 남긴다.** 건별로 남기면 한 번 돌린 것이 감사 표 50줄이 되고,
    # 그 표에서 정작 찾을 것(계정·삭제)을 못 찾는다 — 그것이 이 표의 원래 규칙이다.
    if succeeded and not payload.dry_run:
        # **채택은 그 시험을 고치는 일이다** — 남의 시험을 채택했으면 여기서 한 번에 적는다.
        # 시험마다 커밋해서(하나가 실패해도 나머지는 남게) 돌면서 적으면 시험 수만큼 줄이
        # 생긴다. 끝의 한 트랜잭션에 모아 등록자마다 한 줄로 남긴다 — 실제로 채택된 것만.
        for one in took:
            permissions.note_edit(db, user, one)
        spaces = {one for one in workspaces if one is not None}
        audit.record_by_client(
            db,
            action=audit.PROCESSING_RUN_BY_CLIENT,
            actor=user,
            target_table="processing_results",
            target_id=None,
            target_label=f"일괄 처리 {succeeded}건",
            # 여러 부서에 걸쳐 돌렸으면 **비운다** — 한쪽 부서 것으로 적으면 그
            # 부서 관리자가 남의 부서 일을 자기 것으로 읽는다.
            workspace_id=next(iter(spaces)) if len(spaces) == 1 else None,
            changes={
                "requested": len(items),
                "succeeded": succeeded,
                "steps": len(payload.steps),
                "recipe": payload.recipe_key,
                "adopt": payload.adopt,
            },
        )
        db.commit()
    return BatchOut(
        requested=len(items),
        succeeded=succeeded,
        failed=len(items) - succeeded,
        dry_run=payload.dry_run,
        items=items,
    )


# --- 채택 검토대 (ADR 0058) --------------------------------------------------
#
# **여러 시험의 결과를 한 화면에서 견주어 한 번에 채택한다.** 시험마다 결과 탭을 열고
# 닫던 것을 셋으로 바꾼다 — 결과를 한 번에(`overview`), 겹쳐 그릴 곡선을 한 번에
# (`results/curves`), 채택을 건별로(`adopt-many`). 셋 다 한 요청이다: 시험 스무 건을
# 스무 번 부르는 것이 화면 쪽의 N+1 이다.


def _brief(item: ProcessingResult, run: TestRun) -> ResultBriefOut:
    return ResultBriefOut(
        id=item.id,
        created_at=item.created_at,
        recipe_key=item.recipe_key,
        recipe_label=item.recipe_label,
        step_count=len(item.steps_snapshot or []),
        row_count=item.row_count,
        has_true_stress="stress_true" in (item.columns or []),
        stale=_stale(item, run),
        is_adopted=item.id == run.adopted_result_id,
        scalars=_batch_scalars(item.scalars),
    )


@router.post("/overview", response_model=list[RunOverviewOut])
def overview(
    payload: OverviewRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[RunOverviewOut]:
    """시험마다 결과 목록 · 지금 채택 · 고칠 수 있나 — **요청 차례 그대로, 한 번에.**

    못 보는 시험도 줄을 지킨다(`found=False`). 바구니에 담아 둔 시험이 그사이 지워졌거나
    권한이 바뀌었을 수 있고, 줄이 조용히 빠지면 사람은 그 한 건을 찾으러 다닌다.
    """
    asked = list(dict.fromkeys(payload.test_run_ids))
    runs = {
        run.id: run for run in db.scalars(visible_runs(db, user).where(TestRun.id.in_(asked)))
    }
    # **이름은 한 번에 잇는다** — 시편 → 시료 → 재료, 시험 종류.
    names = (
        {
            run_id: (specimen, material, test_type)
            for run_id, specimen, material, test_type in db.execute(
                select(TestRun.id, Specimen, Material, TestType)
                .join(Specimen, Specimen.id == TestRun.specimen_id)
                .join(Sample, Sample.id == Specimen.sample_id)
                .join(Material, Material.id == Sample.material_id)
                .join(TestType, TestType.id == TestRun.test_type_id)
                .where(TestRun.id.in_(list(runs)))
            )
        }
        if runs
        else {}
    )
    results: dict[uuid.UUID, list[ProcessingResult]] = {}
    if runs:
        for item in db.scalars(
            select(ProcessingResult)
            .where(ProcessingResult.test_run_id.in_(list(runs)))
            .order_by(ProcessingResult.created_at.desc())
        ):
            results.setdefault(item.test_run_id, []).append(item)
    book = AccessBook(db, user).prime(runs.values())

    out: list[RunOverviewOut] = []
    for run_id in asked:
        run = runs.get(run_id)
        if run is None:
            out.append(RunOverviewOut(test_run_id=run_id, found=False, results=[]))
            continue
        specimen, material, test_type = names.get(run.id, (None, None, None))
        out.append(
            RunOverviewOut(
                test_run_id=run.id,
                found=True,
                code=run.code,
                record_name=run.record_name,
                status=run.status,
                test_type_key=test_type.key if test_type else None,
                test_type_label=test_type.label if test_type else None,
                material_id=material.id if material else None,
                material_name=material.record_name if material else None,
                specimen_name=specimen.record_name if specimen else None,
                orientation=specimen.orientation if specimen else None,
                adopted_result_id=run.adopted_result_id,
                access=book.of(run),
                results=[_brief(item, run) for item in results.get(run.id, [])],
            )
        )
    return out


#: 겹쳐 그릴 때 선 하나의 점 수. 결과 탭(600)보다 적다 — 한 판에 수십 개가 겹치면 점이
#: 더 많아도 눈에 안 보이고 응답만 커진다.
LINE_POINTS = 200


@router.post("/results/curves", response_model=list[ResultLineOut])
def result_curves(
    payload: CurvesRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ResultLineOut]:
    """고른 결과들의 곡선 — **겹쳐 그리기용, 한 번에.**

    축은 결과 탭이 처음 여는 축과 같다(공칭이 먼저). 앞쪽 곡선 · 보조선은 싣지 않는다 —
    그것은 한 건을 자세히 볼 때(`/results/{id}/curve`)의 일이고, 옛 결과는 그때마다 다시
    돌려 그리므로(ADR 0053) 수십 건에 붙이면 겹쳐 보기가 느려진다.

    못 보는 결과 · 지워진 결과는 **빼고** 준다 — 화면은 받은 것만 그리고, 무엇이 빠졌는지는
    목록(`overview`)이 이미 말한다.
    """
    asked = list(dict.fromkeys(payload.result_ids))
    items = list(db.scalars(select(ProcessingResult).where(ProcessingResult.id.in_(asked))))
    visible = set(
        db.scalars(
            visible_runs(db, user)
            .with_only_columns(TestRun.id)
            .where(TestRun.id.in_({item.test_run_id for item in items}))
        )
    )
    by_id = {item.id: item for item in items if item.test_run_id in visible}
    out: list[ResultLineOut] = []
    for result_id in asked:
        item = by_id.get(result_id)
        if item is None:
            continue
        data = filestore.read_bytes(item.storage_path)
        columns = sorted(curves.column_names(data))
        axis_x, axis_y = _result_axes(columns, None, None)
        units = curves.read_units(data)
        points: list[tuple[float, float]] = []
        if axis_x in columns and axis_y in columns:
            raw = curves.read_columns(data, [axis_x, axis_y])
            points = curves.downsample(raw[axis_x], raw[axis_y], max_points=LINE_POINTS)
        out.append(
            ResultLineOut(
                result_id=item.id,
                test_run_id=item.test_run_id,
                x=axis_x,
                y=axis_y,
                units={axis_x: units.get(axis_x, "1"), axis_y: units.get(axis_y, "1")},
                points=points,
            )
        )
    return out


@router.post("/adopt-many", response_model=AdoptManyOut)
def adopt_many(
    payload: AdoptManyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AdoptManyOut:
    """시험마다 고른 결과를 채택한다 — **건별로 커밋하고 건별로 말한다.**

    한 건과 같은 규칙이다: 고칠 수 있는 사람만(ADR 0035), 이름이 긴 값을 든 옛 결과는
    못 하고, 요약값 표를 통째로 다시 만든다(`_project_summaries`). `result_id` 가 `null`
    이면 채택을 거둔다 — **되돌리기가 그 길이다**: 응답의 `previous_adopted_id` 를 그대로
    돌려보내면 채택 전으로 돌아간다(채택은 결과를 지우지 않으므로 되돌릴 수 있다).

    **고른 결과가 그 시험의 것인지 본다.** 안 보면 남의 시험 결과를 채택하는 길이 된다 —
    배치 되돌리기가 같은 자리를 막는다(`MNX-PROCESSING-0016`).

    하나가 막혔다고 앞의 채택을 취소하지 않는다. 무엇이 됐고 무엇이 왜 막혔는지가 줄마다
    온다 — 그래야 막힌 것만 다시 한다.
    """
    editor = permissions.editor(db, user)
    rows: list[AdoptManyItemOut] = []
    #: 실제로 채택을 바꾼 시험 — 남의 것이면 끝에서 한 번에 적는다(배치와 같다).
    took: list[TestRun] = []
    for asked in payload.items:
        try:
            run = get_run(db, user, asked.test_run_id)
        except AppError as exc:
            rows.append(
                AdoptManyItemOut(
                    test_run_id=asked.test_run_id,
                    record_name="?",
                    status="failed",
                    error=exc.message,
                )
            )
            continue
        was = run.adopted_result_id
        if asked.result_id == was:
            # 이미 그렇다 — 고친 것이 없으니 「남의 자료를 고쳤다」 도 남기지 않는다.
            rows.append(
                AdoptManyItemOut(
                    test_run_id=run.id,
                    record_name=run.record_name,
                    status="unchanged",
                    previous_adopted_id=was,
                    adopted_result_id=was,
                )
            )
            continue
        try:
            if not editor.allows(run):
                raise permissions.locked(db, run, code="MNX-PROCESSING-0017")
            target: ProcessingResult | None = None
            if asked.result_id is not None:
                target = db.get(ProcessingResult, asked.result_id)
                if target is None or target.test_run_id != run.id:
                    raise Conflict(
                        "MNX-PROCESSING-0019",
                        "고른 결과가 이 시험의 것이 아닙니다 — 목록을 다시 읽어 고르세요.",
                    )
                _require_adoptable(target)
            run.adopted_result_id = target.id if target else None
            _project_summaries(db, run, target)
            db.commit()
            took.append(run)
            rows.append(
                AdoptManyItemOut(
                    test_run_id=run.id,
                    record_name=run.record_name,
                    status="ok",
                    previous_adopted_id=was,
                    adopted_result_id=run.adopted_result_id,
                )
            )
        except AppError as exc:
            db.rollback()
            rows.append(
                AdoptManyItemOut(
                    test_run_id=asked.test_run_id,
                    record_name=run.record_name,
                    status="failed",
                    previous_adopted_id=was,
                    adopted_result_id=was,
                    error=exc.message,
                )
            )

    # **남의 시험을 채택했으면 등록자마다 한 줄로 적는다**(`note_edit`). 시험마다 커밋해서
    # (하나가 막혀도 나머지는 남게) 돌면서 적으면 시험 수만큼 줄이 생긴다 — 실제로 바꾼 것만
    # 끝의 한 트랜잭션에 모은다. 배치(`run_batch`)와 같은 판단이다.
    if took:
        for one in took:
            permissions.note_edit(db, user, one)
        db.commit()
    changed = sum(1 for one in rows if one.status == "ok")
    unchanged = sum(1 for one in rows if one.status == "unchanged")
    return AdoptManyOut(
        requested=len(rows),
        changed=changed,
        unchanged=unchanged,
        failed=len(rows) - changed - unchanged,
        items=rows,
    )
