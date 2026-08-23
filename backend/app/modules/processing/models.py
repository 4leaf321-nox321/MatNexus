"""처리 — 레시피(가변)와 결과(불변).

**한 테이블에 두지 않는 이유.** 레시피는 사람이 계속 고친다 — 탄성 구간을 조금
옮기고, 평활 창을 바꾸고, 네킹 후보로 잘라 본다. 결과는 반대로 절대 안 바뀌어야
한다. 섞어 두면 라벨 하나 바꿨다고 저장된 결과가 재계산되거나, 레시피를 고쳤을
때 예전 결과가 무엇으로 나왔는지 잊힌다(CLAUDE.md 의 불변/가변 분리).

시험 계층 전체의 저장 구조는 ADR 0007 에 있다:

    ① 원본 파일      TestRun.storage_path       불변
    ② 측정 곡선      Curve                      불변
    ③ 처리 결과      ProcessingResult           불변, 여러 벌
    ④ 채택          TestRun.adopted_result_id  ★ 유일한 가변
    ⑤ 요약값        TestSummary                ①과 ④의 투영
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcessingRecipe(Base):
    """처리 레시피 — 어떤 단계를 어떤 순서로 어떤 옵션으로 돌릴지.

    **가변이다.** 사람이 계속 고친다 — 탄성 구간을 조금 옮기고, 평활 창을 바꾸고,
    네킹 후보로 잘라 본다. 그래서 결과와 한 테이블에 두지 않는다. 라벨 하나
    바꿨다고 저장된 결과가 다시 계산되면 안 되고, 반대로 레시피를 고쳤다고
    예전 결과가 무엇으로 나왔는지 잊혀도 안 된다(CLAUDE.md 의 불변/가변 분리).

    소유는 재료·형식 프로파일·시험 종류와 **같은 모델**이다(ADR 0004·0006) —
    `owner_workspace_id IS NULL` 이면 전역. 부서마다 규격이 달라 탄성 구간을
    다르게 잡는 일이 실제로 있고, 그 판단은 그 부서가 한다.
    """

    __tablename__ = "processing_recipes"
    __table_args__ = (
        UniqueConstraint(
            "owner_workspace_id",
            "key",
            name="uq_processing_recipes_scope_key",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(80), index=True)
    """**시험 종류와 달리 부서마다 같은 키를 쓸 수 있다.**

    시험 종류 키를 전사 유일로 둔 것은 두 부서가 같은 시험을 하면 하나를 같이
    써야 하기 때문이었다. 레시피는 반대다 — 같은 인장이라도 부서마다 따르는
    규격이 다르고, `tensile_standard` 라는 이름을 각자 쓰는 것이 자연스럽다."""
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    test_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_types.id"), index=True
    )
    """어느 시험 종류에 쓰는 레시피인가. 인장 레시피가 DMA 곡선에 걸리면
    '변형률 열이 없습니다' 로 실패하는데, 그 전에 목록에서 안 보이는 편이 낫다."""

    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """`[{"plugin": "tensile.elastic_modulus", "options": {...}}, ...]`.

    **데이터다.** 단계를 늘리는 것은 코드지만(플러그인), 어떤 단계를 어떤 순서로
    쓸지는 사람이 화면에서 정한다 — 형식 프로파일과 같은 구도다(ADR 0005)."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProcessingResult(Base):
    """처리 결과 한 벌. **불변이다** — 다시 돌리면 새 행을 만든다.

    ## 왜 스냅샷을 함께 저장하는가

    `recipe_id` 만 두면 레시피가 나중에 바뀌었을 때 **이 결과가 무엇으로 나왔는지
    영원히 알 수 없다.** 탄성 구간을 옮기고 다시 저장한 순간, 어제 뽑은 항복강도가
    어느 구간에서 나온 값인지 추적이 끊긴다. 그 값은 이미 보고서에 들어가 있다.

    그래서 `steps_snapshot` 에 그때의 단계를 통째로 박아 둔다. 레시피를 지워도
    결과는 자기가 무엇이었는지 안다(그래서 `recipe_id` 는 nullable 이다).

    `stages` 에는 단계별 **근거와 플러그인 버전**이 들어간다. 계산 코드가 바뀌면
    version 이 올라가므로, "이 값은 v1 계산이다" 를 나중에 판정할 수 있다.

    곡선 자체는 Parquet 로 나간다 — `Curve` 와 같은 이유다(수천~수만 행).
    """

    __tablename__ = "processing_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("test_runs.id"), index=True
    )
    source_curve_key: Mapped[str] = mapped_column(String(50))
    """어느 곡선을 처리했는가. 한 시험이 곡선을 여럿 갖는다(DMA 구간별)."""

    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("processing_recipes.id"), index=True, nullable=True
    )
    """저장된 레시피로 돌렸으면 그 id. 화면에서 즉석으로 짠 단계면 NULL 이다 —
    **즉석 처리를 막지 않는다.** 레시피로 만들기 전에 한 번 돌려 보는 것이 정상
    작업 흐름이고, 그것을 막으면 사람이 레시피를 함부로 만들어 목록이 쓰레기가 된다."""
    recipe_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    steps_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    stages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """단계별 `{plugin, label, version, options, notes}`. 근거가 여기 산다."""
    scalars: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """`[{key, label, value, si_unit}]`. 탄성계수·항복강도·인장강도."""

    storage_path: Mapped[str] = mapped_column(String(500))
    row_count: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    columns: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")

    runtime: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    """이 결과를 낸 **환경** — python·numpy·scipy·pyarrow 버전(`matcore.runtime`).

    `stages` 의 플러그인 버전이 "어느 계산이었나" 에 답한다면, 이것은 "그 계산이
    무엇 위에서 돌았나" 에 답한다. **둘 다 있어야 재현이 닫힌다** — 우리 적합은
    `scipy.optimize.least_squares` 를 쓰고, scipy 가 바뀌면 같은 데이터에서 다른
    파라미터가 나올 수 있다.

    **비어 있으면 v1.48.0 이전에 만들어진 것**이다. 그때 무엇이었는지는 알 길이
    없고, 그래서 `runtime.same` 은 기록이 없는 쪽을 "같다" 고 하지 않는다."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
