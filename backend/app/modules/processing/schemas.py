"""처리 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# --- 처리 (Phase 3) ---------------------------------------------------------


class StepParamOut(BaseModel):
    """단계 하나의 입력 칸. **화면의 폼 필드가 여기서 생성된다.**

    프론트에 목록을 하드코딩하지 않는 이유: 계산을 추가할 때 두 곳을 고쳐야 하고,
    그러면 한 곳을 빠뜨린다. `matcore.ParamSpec` 을 그대로 내보낸다.
    """

    name: str
    label: str
    type: str
    default: Any = None
    choices: list[str] = []
    choice_labels: dict[str, str] = {}
    """값 → 사람이 읽는 이름. 값 자체는 레시피에 저장되는 계약이라 안 바꾼다."""
    unit: str | None = None
    dimension: str | None = None
    """단위만으로 못 가르는 것을 가른다 — 변형률은 %, tan δ 는 그대로."""
    unit_from: str | None = None
    """이 칸의 단위를 **어느 칸이 가리키는 열이 정하는가.**

    `curve.crop` 의 시작·끝이 그렇다 — 기준 열이 변형률이면 무차원이고 온도면
    K 다. 화면이 그 열의 선언을 보고 단위를 붙인다. 없으면 아무것도 안 붙고,
    그때 「시작 / 끝」 두 칸만으로는 무엇을 넣는지 알 수 없다(실사용 2026-09-01)."""
    help: str | None = None
    required: bool = False
    """비면 계산이 실패하는 칸. 화면이 **켠 단계 중 덜 채운 것**을 붉게 짚는다.

    `when` 이 걸린 칸은 그 조건일 때만 필수다."""
    role: str | None = None
    """`column` 이면 프레임의 **열 이름**을 받는 칸이다. 화면이 목록을 낸다.

    전에는 프론트에 열 받는 칸 이름을 적어 뒀다 — 새 계산을 만들 때 그 목록에도
    이름을 더해야 했고, 안 더하면 자유 입력이 됐다."""
    links_to: str | None = None
    """이 칸에 이어 붙일 수 있는 **앞 단계의 값 이름.**

    비면 화면이 **칸 이름과 같은 이름**을 찾는다. 이름이 다를 때만 채워진다 —
    네킹을 자르는 `manual_index` 칸이 `necking_candidate_index` 를 받는 것이
    그 경우다."""
    when: dict[str, list[str]] = {}
    """이 칸이 쓰이는 조건. 비어 있으면 늘 쓰인다."""


class ProducedOut(BaseModel):
    """이 계산이 만들어 내는 것 하나 — 열이거나 값이다.

    **이름만 주면 화면이 `strain_true_plastic` 을 그대로 보여 준다.** 그것이
    무엇인지는 코드를 읽어야 알게 되고, 그러면 아무도 안 읽는다.
    """

    key: str
    """`{param}` 이 있으면 그 단계 옵션 값으로 치환한다."""
    label: str
    si_unit: str = "1"
    help: str | None = None


class ProcessingStepOut(BaseModel):
    """등록된 계산 하나. **화면이 이 응답만으로 순서도와 폼을 그린다.**"""

    id: str
    label: str
    version: str
    """계산이 바뀌면 올라간다. 결과에 기록해 "이 값은 v1 계산이다" 를 남긴다."""
    applies_to: list[str]
    requires_channels: list[list[str]] = []
    """필요한 채널. **안쪽 묶음은 「그중 하나」.**

    시험 종류를 만드는 화면이 이것을 읽어 「이 채널을 넣으면 무엇이 열리나」 를
    보여 준다. 키(`applies_to`)만으로 거르면 부서가 만든 종류에서 그 단계가
    조용히 사라진다."""
    params: list[StepParamOut]
    makes_columns: list[ProducedOut] = []
    """이 단계가 새로 더하는 열. `{param}` 은 그 단계 옵션 값으로 치환한다.

    **없으면 화면이 "지금 고를 수 있는 열" 을 모른다.** 장비가 준 것은 변위·
    하중뿐이라, 한 번 돌려 보기 전에는 `strain_engineering` 이 목록에 없었다 —
    돌려 보려면 골라야 하고 고르려면 돌려 봐야 하는 자리였다."""
    makes_values: list[ProducedOut] = []
    """이 단계가 내는 스칼라. 뒤 단계가 `@` 로 가리킨다."""
    order: int = 100
    """권장 순서. 작을수록 앞. 목록이 이미 이 순서로 온다."""


class ProcessingScalarOut(BaseModel):
    key: str
    label: str
    value: float
    si_unit: str
    dimension: str | None = None
    """단위만으로 못 가르는 것을 가른다 — 변형률은 %, 개수는 그대로."""
    source: str | None = None
    """`run` 이 시험이 잰 값 · `measured` 시편에 적힌 값 · `nominal` 규격 공칭 ·
    `condition` 시험 종류가 선언한 조건.

    **값이 세 곳에 살 수 있다.** 어느 것을 썼는지 안 보이면 사람이 "어느 게
    맞느냐" 에 답할 수 없다. 단면적처럼 계산된 값은 비어 있다."""


class ProcessingStageOut(BaseModel):
    """단계 하나가 끝난 시점. **근거가 여기 산다.**

    화면이 단계별로 접어 보여 준다 — "정렬에서 몇 점이 합쳐졌나", "탄성계수를
    어느 구간의 몇 점으로 쟀나" 가 값 옆에 없으면, 반년 뒤 그 값을 설명할 수 없다.
    """

    index: int
    plugin: str
    label: str
    version: str
    options: dict[str, Any]
    notes: list[str]
    row_count: int
    columns: list[str]
    scalars: list[ProcessingScalarOut]


class ProcessingRunRequest(BaseModel):
    test_run_id: uuid.UUID
    source_curve_key: str | None = None
    """어느 곡선인가. 비우면 첫 번째 — 표가 하나뿐인 파일이 대부분이다."""
    steps: list[dict[str, Any]]
    """`[{"plugin": ..., "options": {...}}]`. 저장된 레시피 없이도 돌린다."""
    recipe_key: str | None = None
    """저장된 레시피로 돌렸으면 그 키. 결과에 이름을 남기려고 받는다."""


class ProcessingPreviewOut(BaseModel):
    source_curve_key: str
    source_row_count: int
    row_count: int
    columns: list[str]
    units: dict[str, str]
    stages: list[ProcessingStageOut]
    scalars: list[ProcessingScalarOut]
    notes: list[str]
    points: list[tuple[float, float]]
    problem: str | None = None
    """**멈춘 자리.** 값이 있으면 이 미리보기는 거기까지만 돈 것이다.

    다섯 중 넷이 돌고 다섯째가 멈추면 그 넷의 곡선은 멀쩡히 나와 있다. 그것을
    버리고 오류만 돌려주면 사람은 어디가 어긋났는지 **눈으로 못 보고** 단계를
    하나씩 지워 가며 다시 돌린다(실사용, 2026-09-02).

    **저장은 여전히 막는다** — 반쯤 돈 결과가 채택되면 카드까지 간다."""

    stage_index: int | None = None
    """`points`·`columns`·`units` 가 **어느 단계의 것인가.** `None` 이면 마지막.

    **되돌려 주는 이유가 있다.** 화면이 요청한 값을 그대로 믿으면, 서버가 범위를
    벗어난 요청을 마지막으로 되돌렸을 때 「3단계를 보는 중」 이라고 적힌 채
    마지막 그림이 뜬다 — 그림이 거짓말을 한다."""


class ProcessingResultOut(BaseModel):
    id: uuid.UUID
    is_adopted: bool = False
    """**이 시험의 물성으로 삼은 것인가.** 시험당 하나뿐이다(ADR 0007)."""
    test_run_id: uuid.UUID
    source_curve_key: str
    recipe_key: str | None
    recipe_label: str | None
    steps: list[dict[str, Any]]
    """**그때의 단계 그대로다.** 레시피가 나중에 바뀌어도 이 값은 안 바뀐다."""
    stages: list[ProcessingStageOut]
    scalars: list[ProcessingScalarOut]
    row_count: int
    columns: list[str]
    runtime: dict[str, str] = {}
    """이 결과를 낸 환경(python·numpy·scipy·pyarrow). **비어 있으면 v1.48.0 이전에
    만들어진 것**이고, 그때 무엇이었는지는 알 길이 없다."""
    created_at: datetime


class RecipeSaveRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = None
    test_type_key: str
    steps: list[dict[str, Any]]
    is_active: bool = True


class RecipeUpdateRequest(RecipeSaveRequest):
    """고칠 때만 쓴다. 만들 때는 견줄 상대가 없다."""

    expected_revision: int
    """**열었을 때 받은 `revision` 을 그대로 넣는다.**

    선택이 아니라 필수다. 선택으로 두면 안 보내는 클라이언트가 조용히 검사를
    지나가고, **빠뜨린 것이 사고가 난 뒤에야 드러난다.**"""


class RecipeCreateRequest(RecipeSaveRequest):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    owner_workspace_slug: str | None = None
    """비우면 전역 — **시스템 관리자만** 할 수 있다."""


class RecipeOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    owner_workspace_slug: str | None
    owner_workspace_name: str | None
    is_global: bool
    test_type_key: str
    test_type_label: str
    steps: list[dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    revision: int
    """저장할 때마다 오르는 번호. **고칠 때 이 값을 그대로 돌려보내야 한다**
    (ADR 0015) — 그사이 남이 고쳤으면 서버가 409 로 막는다.

    이 정의는 한 벌 통째로 갈아 끼우므로, 못 막으면 뒤에 저장한 쪽이 앞을 덮는
    것이 아니라 **자식까지 통째로 지운다.**"""


# --- 배치 --------------------------------------------------------------------


class BatchRequest(BaseModel):
    test_run_ids: list[uuid.UUID] = Field(min_length=1)
    source_curve_key: str | None = None
    steps: list[dict[str, Any]]
    recipe_key: str | None = None
    adopt: bool = True
    """성공한 것을 바로 채택할지. **기본이 참인 이유:** 배치를 돌리는 사람은
    이미 한 건으로 단계를 맞춰 본 뒤다. 여기서 또 하나씩 채택하게 하면 배치를
    쓴 의미가 절반이 된다."""


class BatchItemOut(BaseModel):
    test_run_id: uuid.UUID
    record_name: str
    status: str
    """`ok` | `failed`."""
    result_id: uuid.UUID | None = None
    adopted: bool = False
    error: str | None = None
    """어디서 왜 막혔는지. **건별로 다르다** — 시편 치수가 없는 것, 탄성 구간에
    점이 없는 것, 채널 이름이 다른 것이 한 배치에 섞여 온다."""
    scalars: list[ProcessingScalarOut] = []


class BatchOut(BaseModel):
    requested: int
    succeeded: int
    failed: int
    items: list[BatchItemOut]


class ResultCurveOut(BaseModel):
    """저장된 결과의 곡선. **결과 화면이 그림을 그리려면 이것이 필요하다.**

    미리보기(`/preview`)는 돌리면서 점을 함께 주지만, 저장된 결과는 값과 근거만
    있고 곡선은 파일에 있었다 — 그래서 '결과' 탭이 숫자만 보여 줬다. 처리한
    사람이 정작 저장한 곡선을 볼 수 없었다.
    """

    result_id: uuid.UUID
    x: str
    y: str
    columns: list[str]
    """고를 수 있는 축들. 무엇이 있고 무엇이 없는지가 곧 레시피가 한 일이다."""
    units: dict[str, str]
    row_count: int
    points: list[tuple[float, float]]
