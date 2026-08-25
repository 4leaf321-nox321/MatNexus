"""시험 API 형태.

시험 종류 정의를 그대로 내려보낸다. 화면이 채널·조건 폼을 **정의에서 그려야**
새 시험 종류를 배포 없이 추가할 수 있다(수준 2). 화면이 항목을 하드코딩하면
정의를 데이터로 둔 이유가 사라진다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- 정의 -------------------------------------------------------------------


class TestChannelOut(BaseModel):
    key: str
    label: str
    dimension: str
    si_unit: str
    is_required: bool
    sort_order: int


class TestConditionFieldOut(BaseModel):
    key: str
    label: str
    value_type: str
    dimension: str | None
    si_unit: str | None
    choices: list[str] | None
    is_required: bool
    sort_order: int


class TestTypeOut(BaseModel):
    id: uuid.UUID
    key: str
    owner_workspace_slug: str | None
    owner_workspace_name: str | None
    is_global: bool
    """누가 만들었나. **안 보이면 왜 못 고치는지 알 수 없다.**

    전역은 여러 부서가 함께 쓰므로 시스템 관리자만 고친다. 화면이 그 사실을
    보여 주지 않으면 편집 버튼을 눌러 보고 403 을 받고서야 알게 된다."""
    label: str
    abbr: str
    description: str | None
    parser_key: str | None
    extensions: list[str]
    """**파서가 선언한** 확장자. 파일 이름만 보고 종류를 찍는 데 쓴다."""
    profile_extensions: list[str] = Field(default_factory=list)
    """이 종류를 읽는 **파일 형식(프로파일)** 이 받는 확장자.

    파서와 따로 두는 이유: 프로파일은 **내용을 보고** 정한다(헤더의 열 이름).
    확장자가 같아도 안 맞으면 안 읽히므로, 이 목록으로 종류를 찍으면 안 된다 —
    화면이 「무엇을 받는가」를 말하는 데만 쓴다.

    전에는 이 목록이 어디에도 없어서, 일괄 등록 화면이 `.tra` 만 적어 두고
    **`.csv`·`.mtet` 는 지원하지 않는 것처럼 보였다.**
    """
    """이 종류가 읽을 수 있는 파일 확장자(소문자, 점 포함).

    파서 플러그인이 선언한 것을 그대로 내보낸다. 화면이 **파일만 보고 시험 종류를
    추정**하는 데 쓴다 — 종류가 열 개, 스무 개로 늘면 사람이 파일마다 고르는 것이
    일이 된다. 목록을 화면에 하드코딩하면 파서를 추가할 때 두 곳을 고쳐야 한다."""
    is_active: bool
    max_upload_bytes: int | None
    """**저장된 값.** `None` 이면 "전역 설정을 따른다" 는 뜻이다.

    실제로 강제되는 값은 `max_upload_bytes_effective` 다. 둘을 갈라 놓지 않으면
    화면이 되돌려 보낼 값을 잃는다 — 정의는 한 벌 통째로 갈아 끼우므로, 화면이
    받은 것을 그대로 돌려보내지 못하면 **그 값은 저장하는 순간 사라진다.**

    실제로 그랬다. 이 필드가 실효값(50MB)만 주던 동안 편집기 두 곳이 되돌려 보낼
    것이 없어 `null` 을 박아 넣었고, 부서가 API 로 올려 둔 한도는 편집기에서
    저장 한 번에 조용히 지워졌다. 감사 로그를 붙이고 나서 드러났다."""
    max_upload_bytes_effective: int
    """**실제로 강제되는 값.** 저장된 값이 없으면 전역 기본값이 채워져 나간다 —
    화면이 한도를 보여 줄 때 두 곳을 보지 않게."""
    revision: int
    """저장할 때마다 오르는 번호. **고칠 때 이 값을 그대로 돌려보내야 한다**
    (ADR 0015) — 그사이 남이 고쳤으면 서버가 409 로 막는다.

    이 정의는 한 벌 통째로 갈아 끼우므로, 못 막으면 뒤에 저장한 쪽이 앞을 덮는
    것이 아니라 **자식까지 통째로 지운다.**"""
    run_count: int
    """이 종류로 등록된 시험 수. 0 이 아니면 채널의 key·단위·차원이 잠긴다.

    화면이 **이유와 함께 잠가야** 사람이 납득한다. 눌러 보고 나서 409 를 받으면
    무엇이 문제인지 알기 어렵다."""
    channels: list[TestChannelOut]
    conditions: list[TestConditionFieldOut]


# --- 시험 -------------------------------------------------------------------


#: 한 번에 다룰 수 있는 시험 수. **서버가 강제한다** — 화면이 200건까지만
#: 고른다고 요청도 그렇다는 보장은 없다.
MAX_RUNS = 500

#: 여럿을 한 번에 고칠 수 있는 칸. **여기 없는 것은 일부러 없다.**
#:
#: 시편·재료·시험 종류는 이름을 만드는 값이라(ADR 0004) 바꾸면 `record_name` 과
#: 그 아래가 흔들린다. 상태·채택 결과는 처리 파이프라인이 쓰는 값이라 손으로
#: 옮기면 「읽힌 적 없는데 처리됨」 같은 상태가 만들어진다. 조건값은 단위가 딸려
#: 있어서 한 값만 갈아 끼우면 단위 기록과 어긋난다.
#:
#: 남는 것은 **올릴 때 사람이 적는 메타데이터**뿐이고, 그것이 이 목록이다.
EDITABLE_FIELDS: dict[str, str] = {
    "division": "사업부",
    "instrument": "장비",
    "operator": "시험자",
    "tested_at": "시험일",
    "note": "메모",
}


class RunDeleteRequest(BaseModel):
    """여러 건을 한 번에 지운다."""

    run_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_RUNS)


class RunBulkUpdateRequest(BaseModel):
    """고른 시험의 **칸 하나**를 같은 값으로 맞춘다.

    한 번에 한 칸이다. 여러 칸을 함께 받으면 「안 보낸 것」과 「비운 것」을
    구별할 수 없고, 화면도 「무엇을 바꾸는 중인가」를 말하기 어려워진다.
    """

    run_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_RUNS)
    field: Literal["division", "instrument", "operator", "tested_at", "note"]
    value: str | None = None
    """비우면 그 칸을 지운다. **빈 문자열과 `null` 을 같게 본다** — 화면의 빈
    칸이 둘 중 어느 것으로 오는지에 뜻이 달라지면 안 된다."""


class RunBulkUpdateOut(BaseModel):
    updated: int
    unchanged: int
    """이미 그 값이던 것. **조용히 성공으로 세지 않는다** — 20건을 골랐는데
    「17건 바꿨습니다」 가 나오면 나머지 셋이 왜 빠졌는지 알 수 있어야 한다."""
    blocked: list[str]


class RunDeleteOut(BaseModel):
    """무엇이 지워졌고 무엇이 안 지워졌나.

    **한 건이 막혔다고 나머지를 되돌리지 않는다.** 20건을 골라 지우는데 하나가
    권한 밖이라 전부 실패하면, 사람은 어느 것이 문제인지 모른 채 다시 골라야
    한다. 대신 **안 지워진 것을 이름과 이유로 돌려준다.**
    """

    deleted: int
    blocked: list[str]


class RunFacetOut(BaseModel):
    """거를 수 있는 값 하나와 **그것이 몇 건인가.**

    화면이 한 쪽에서 세면 안 된다 — 50건만 받아 세면 「인장시험 50」이라고
    적히는데 실제로는 300건일 수 있고, 그러면 필터 옆의 숫자가 거짓말을 한다.
    """

    key: str
    label: str
    count: int


class RunFacetsOut(BaseModel):
    """무엇으로 거를 수 있나. **지금 걸린 필터를 안 본다.**

    「무엇이 있나」를 답하는 자리다 — 필터를 걸 때마다 다른 축의 숫자가 같이
    줄면, 필터를 풀기 전에는 그 축에 무엇이 있는지 알 수 없다.
    """

    test_types: list[RunFacetOut]
    orientations: list[RunFacetOut]
    registrants: list[RunFacetOut]
    divisions: list[RunFacetOut]
    statuses: list[RunFacetOut]


class TestRunOut(BaseModel):
    id: uuid.UUID
    result_count: int = 0
    """저장된 처리 결과 수. **목록에서 진행이 보여야 한다** — 시편 20개짜리
    배치에서 무엇이 아직 안 됐는지를 하나씩 열어 봐야 아는 것은 일이 아니다."""
    adopted_result_id: uuid.UUID | None = None
    """채택된 결과. 있으면 '이 시험의 물성' 이 정해졌다는 뜻이다(ADR 0007)."""
    record_name: str
    seq_no: int
    status: str
    parse_error: str | None

    specimen_id: uuid.UUID
    specimen_name: str | None
    orientation: str | None
    specimen_standard: str | None = None
    """시편 규격. **시편의 값이고 시험의 값이 아니다** — 그래도 여기 실어 준다.

    곡선을 보는 자리에서 "이게 어떤 시편이었나" 를 알아야 한다. 다른 규격끼리
    연신율을 견주면 그 차이는 재료 차이가 아니라 시편 차이다."""
    material_id: uuid.UUID | None
    material_name: str | None

    test_type_key: str
    test_type_label: str

    conditions: dict[str, Any]
    tested_at: datetime | None
    operator: str | None
    instrument: str | None
    division: str | None = None
    """어느 사업부가 낸 시험인가. 부서(권한)와 다른 축이다."""

    registered_by: str | None = None
    """올린 사람. **목록에서 보여야 한다** — 파일이 이상할 때 물어볼 데가
    거기다. 계정이 지워졌으면 빈다(기록은 남고 이름만 사라진다)."""

    source_filename: str | None
    source_bytes: int | None
    source_sha256: str | None
    note: str | None
    """등록 메모. 서버가 "내용이 같은 파일이 이미 N건 있습니다" 를 여기 적는다 —
    실을 곳이 없으면 서버만 알고 사용자는 끝내 모른다."""

    row_count: int | None
    channels: list[str]
    warnings: list[str]
    created_at: datetime


class TestSummaryOut(BaseModel):
    key: str
    label: str | None
    source: str
    """`instrument` = 장비가 계산한 값, `matnexus` = 우리가 계산한 값.

    나란히 두는 것이 목적이다. 우리 계산이 장비 값과 크게 다르면 뭔가 잘못됐다."""
    value: float | None
    text: str | None
    si_unit: str | None
    dimension: str | None = None
    """단위만으로 못 가르는 것을 가른다 — 변형률은 %, 개수는 그대로."""


class CurveOut(BaseModel):
    """저장된 곡선 하나.

    **여럿일 수 있다.** TA DMA850 주파수-온도 스윕은 `[step]` 마다 별개 측정이라
    곡선이 6벌 나온다. 하나만 보여 주면 나머지는 저장돼 있는데 화면에서 영원히
    안 보인다 — 실제로 그랬다.
    """

    key: str
    label: str | None
    """표 이름(`Temperature Sweep (Multifrequency) - 2`). 없을 수 있다."""
    kind: str
    """`measured`(측정) | `derived`(장비가 계산해 준 것).

    **버리지도 섞지도 않는다.** 버리면 장비가 계산한 결과를 잃고, 섞으면 Phase 3
    의 처리가 마스터 곡선을 원본으로 착각한다."""
    row_count: int
    channels: list[str]


class TestRunDetailOut(TestRunOut):
    summary: list[TestSummaryOut]
    source_metadata: dict[str, str]
    curves: list[CurveOut]
    parser_version: str | None
    """무엇으로 읽었는가(`profile:ta_dma850` · `zwick_tra:1`). 곡선이 이상할 때
    가장 먼저 봐야 하는 값이다."""


class CurvePointsOut(BaseModel):
    x: str
    y: str
    row_count: int
    """원본 행 수. 축약 전이다."""
    returned: int
    points: list[tuple[float, float]]


class ReparseOut(BaseModel):
    status: str
    message: str


# --- 저장소 정리 ------------------------------------------------------------


class StorageItemOut(BaseModel):
    path: str
    bytes: int


class IncompleteOut(StorageItemOut):
    age_hours: float


class ExpiredOut(StorageItemOut):
    run_id: uuid.UUID
    record_name: str
    deleted_at: datetime


class StorageReportOut(BaseModel):
    """치울 것이 **세 종류**다. 하나만 다루면 나머지가 영원히 쌓인다."""

    root: str
    total_bytes: int
    retention_days: int
    live_count: int
    live_bytes: int
    orphans: list[StorageItemOut]
    """DB 에 행이 없는 폴더. 트랜잭션이 파일시스템까지 덮지 못해 생긴다."""
    incomplete: list[IncompleteOut]
    """쓰다 만 `.part`. 폴더는 살아 있어서 오펀 탐색에 안 걸린다."""
    expired: list[ExpiredOut]
    """보존기간 지난 소프트 삭제. **행이 있어서 오펀으로 영원히 안 잡힌다** —
    실측으로 확인한, 셋 중 가장 큰 구멍이다."""
    reclaimable_bytes: int


class CleanupRequest(BaseModel):
    dry_run: bool = True
    """기본이 안전한 쪽이다. 되돌릴 수 없는 작업이라 명시적으로 꺼야 지운다."""
    retention_days: int | None = Field(default=None, ge=0)


class CleanupQueuedOut(BaseModel):
    status: str
    message: str
    dry_run: bool


# --- 정의 편집 --------------------------------------------------------------
#
# **여기가 위험한 자리다.** 채널의 `key` 와 `si_unit` 은 이미 저장된 데이터의
# 해석을 바꾼다.
#
#   key       Parquet 컬럼 이름이자 `Curve.channels` 의 값이다. 바꾸면 저장된
#             곡선을 못 읽고, 조용히 "채널 없음" 이 된다.
#   si_unit   저장된 숫자는 그대로인데 뜻이 바뀐다. force 를 N → kN 으로 바꾸면
#             3466.4 N 이 3466.4 kN 으로 읽힌다. **숫자가 그대로라 티가 안 난다.**
#
# 그래서 그 종류로 등록된 시험이 하나라도 있으면 둘을 잠근다. 라벨·정렬·필수
# 여부는 언제든 바꿀 수 있다 — 그것들은 해석을 바꾸지 않는다.


class ParserOut(BaseModel):
    """`matcore.registry` 에 등록된 파서. 종류를 만들 때 여기서 고른다."""

    id: str
    label: str
    version: str
    extensions: list[str]
    applies_to: list[str]


class ChannelInput(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    """소문자·숫자·밑줄만. Parquet 컬럼 이름이 되므로 공백과 기호를 막는다."""
    label: str = Field(min_length=1, max_length=100)
    dimension: str = Field(min_length=1, max_length=20)
    si_unit: str = Field(min_length=1, max_length=20)
    is_required: bool = True
    sort_order: int = 0


class ConditionInput(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    value_type: str = Field(pattern="^(number|text|choice|date|boolean)$")
    dimension: str | None = Field(default=None, max_length=20)
    si_unit: str | None = Field(default=None, max_length=20)
    choices: list[str] | None = None
    is_required: bool = False
    sort_order: int = 0


class TestTypeSaveRequest(BaseModel):
    """정의 한 벌을 통째로 저장한다.

    항목별 엔드포인트를 늘어놓지 않는 이유: 화면은 폼 하나를 채워 저장한다.
    부분 갱신으로 쪼개면 "채널만 바꿨는데 조건이 사라졌다" 같은 어긋남이 생기고,
    무엇이 지워졌는지 판정하는 곳도 화면과 서버 둘로 갈라진다.
    """

    label: str = Field(min_length=1, max_length=100)
    abbr: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$")
    """시험 이름에 들어가는 약어. 이름에 쓰이므로 영숫자만."""
    description: str | None = None
    parser_key: str | None = None
    is_active: bool = True
    sort_order: int = 0
    max_upload_bytes: int | None = Field(default=None, gt=0)
    channels: list[ChannelInput]
    conditions: list[ConditionInput] = []


class TestTypeUpdateRequest(TestTypeSaveRequest):
    """고칠 때만 쓴다. 만들 때는 견줄 상대가 없다."""

    expected_revision: int
    """**열었을 때 받은 `revision` 을 그대로 넣는다.**

    선택이 아니라 필수다. 선택으로 두면 안 보내는 클라이언트가 조용히 검사를
    지나가고, **빠뜨린 것이 사고가 난 뒤에야 드러난다.**"""


class TestTypeCreateRequest(TestTypeSaveRequest):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    """만든 뒤에는 바꿀 수 없다. 시험 종류를 가리키는 안정된 이름이다.

    **전사에서 유일하다.** 두 부서가 같은 시험을 하면 종류를 둘로 만들 것이
    아니라 하나를 같이 써야 한다(ADR 0006)."""
    owner_workspace_slug: str | None = None
    """누구 것으로 만들지. 비우면 전역 — **시스템 관리자만** 할 수 있다."""


class DefinitionLocksOut(BaseModel):
    """무엇을 왜 못 바꾸는지. 화면이 이유와 함께 잠가야 사람이 납득한다."""

    run_count: int
    locked: bool
    reason: str | None


# --- 형식 프로파일 ----------------------------------------------------------
#
# **장비가 늘 때마다 파서를 짜지 않으려고 만든 길이다.** 구조는 코드가 자동으로
# 읽고, "이 열이 무엇인가" 만 사람이 한 번 정해 저장한다. 그 저장물이 프로파일이다.
#
# 결정적인 점: **운영 서버에서 실제 파일을 보며 만든다.** 현장 파일이 개발자에게
# 갈 필요가 없다.


class DetectOut(BaseModel):
    """파일 하나를 보고 시험 종류를 골라 본 결과.

    **고르는 일을 없애는 것이 목적이다.** 종류가 늘수록 사람이 매번 드롭다운에서
    찾는 비용이 커지는데, 그 답은 파일이 이미 갖고 있다.
    """

    filename: str
    test_type_key: str | None
    test_type_label: str | None
    profile_key: str | None
    source: str
    """`profile` · `extension` · `none`. **무엇으로 정했는지 화면이 보여 준다** —
    자동 선택이 틀렸을 때 사람이 의심할 근거가 있어야 한다."""
    reason: str


class TablePreviewOut(BaseModel):
    index: int
    name: str | None
    header: list[str]
    units: list[str]
    unit_symbols: list[str | None]
    """파일에 적힌 단위를 **우리 표의 정본 심볼**로 바꾼 것. 모르면 `None`.

    `°C → degC`, `Mpa → MPa` 처럼 표기가 다른 것을 흡수한 결과다."""
    dimensions: list[str | None]
    """그 단위의 차원. 화면이 이것으로 **새 채널을 제안한다.**

    프론트에 단위 표를 복제해 계산하면 언젠가 두 표가 갈라진다 — 변환 규칙은
    `matcore/units` 한 곳에만 둔다(ADR 0004)."""
    row_count: int
    column_count: int
    first_line: int
    sample_rows: list[list[str]]
    """앞 몇 행. **사람이 눈으로 확인하는 근거다.**

    자동 감지는 인코딩이 이중으로 깨진 파일도 '성공' 시킨다(실측). 숫자는 멀쩡하고
    글자만 깨지므로, 표를 직접 보지 않으면 알 수 없다."""


class StructurePreviewOut(BaseModel):
    """파일을 저장하지 않고 구조만 읽어 본 결과."""

    filename: str
    encoding: str
    delimiter: str
    line_count: int
    meta: list[tuple[str, str]]
    tables: list[TablePreviewOut]
    warnings: list[str]
    """**추측한 것**을 그대로 드러낸다. 인코딩을 UTF-8 이 아닌 것으로 골랐다면
    그 사실이 여기 있다."""
    matched_profile: str | None
    """이미 있는 프로파일이 이 파일을 잡는가. 있으면 새로 만들 필요가 없다."""


class FormatProfileOut(BaseModel):
    id: uuid.UUID
    key: str
    owner_workspace_slug: str | None
    owner_workspace_name: str | None
    is_global: bool
    """`NULL` 소유 = 전역. 여러 부서가 함께 쓰므로 시스템 관리자만 고친다."""
    label: str
    description: str | None
    test_type_key: str
    test_type_label: str
    definition: dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FormatProfileSaveRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    description: str | None = None
    test_type_key: str = Field(min_length=1)
    definition: dict[str, Any]
    priority: int = 0
    is_active: bool = True


class FormatProfileCreateRequest(FormatProfileSaveRequest):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    owner_workspace_slug: str | None = None
    """누구 것으로 만들지. `None` 이면 전역이고 **시스템 관리자만** 할 수 있다.

    장비는 부서마다 다르다 — 남의 부서 파일을 어떻게 읽을지를 시스템 관리자가
    알 리 없어서, 부서 관리자가 자기 부서 것을 만든다."""


class TriedChannelOut(BaseModel):
    key: str
    label: str | None
    source_unit: str | None
    """파일에 적힌 단위. **환산이 맞았는지 사람이 판단할 유일한 근거다** —
    `°C → K` 는 값이 크게 바뀌므로, 원 단위가 안 보이면 틀렸는지 알 수 없다."""
    si_unit: str
    first: float | None
    last: float | None


class TriedCurveOut(BaseModel):
    key: str
    label: str | None
    row_count: int
    channels: list[TriedChannelOut]


class TriedSummaryOut(BaseModel):
    key: str
    label: str | None
    value: float | None
    text: str | None
    si_unit: str | None


class ProfileTryOut(BaseModel):
    """프로파일을 저장하기 전에 그 파일에 적용해 본 결과.

    저장하고 나서 틀린 것을 아는 것과, 저장 전에 아는 것은 다르다.
    """

    curves: list[TriedCurveOut]
    summary: list[TriedSummaryOut]
    metadata: dict[str, str]
    warnings: list[str]


class InstrumentDimensionOut(BaseModel):
    """장비 파일이 준 시편 치수 하나."""

    field: str
    """치수 칸의 키. **규격이 정한다** — `thickness` · `diameter` · `free_length`."""
    label: str
    symbol: str | None = None
    """그 규격의 도면이 쓰는 글자. **파일 항목 이름이 곧 이 글자다** — Zwick 은
    두께를 `a0`, 폭을 `b0`, 직경을 `d0` 로 적는다."""
    value_m: float | None
    """파일이 준 값. **없을 수 있다** — 게이지 길이는 시험기 설정값이라 파일에
    안 적히는 것이 보통이다. 그 경우 사람이 직접 넣는 수밖에 없고, 화면이 그
    사실을 말해야 한다."""
    current_m: float | None
    """시편에 이미 있는 값. 있으면 덮어쓰기가 된다 — 화면이 그 사실을 보여야 한다."""


class InstrumentDimensionsOut(BaseModel):
    items: list[InstrumentDimensionOut]
    specimen_id: uuid.UUID


class AppliedDimensionsOut(BaseModel):
    """무엇을 채웠는지. **시편 전체를 돌려주지 않는다** — 이 응답이 답해야 하는
    질문은 "지금 무슨 일이 일어났나" 이고, 시편은 화면이 다시 읽으면 된다."""

    specimen_id: uuid.UUID
    filled: list[str]


class SummaryImportRequest(BaseModel):
    """표로 시험을 흡수한다. **한 줄이 시험 하나다.**

    첫 줄은 열 이름이다 — `시편`·`방향`·`원본 파일명` 과, 시험 종류가 선언한
    조건, 나머지는 요약값이다. 숫자 열은 헤더에 단위를 적는다(`항복강도 (MPa)`).
    """

    sample_id: uuid.UUID
    """어느 시료의 표인가. **표에는 재료 이름이 없다** — 한 파일이 대개 한 시료
    분이라, 어디 붙는지는 사람이 고른다."""
    test_type: str = Field(min_length=1, max_length=50)
    values: list[str] = Field(min_length=1, max_length=1000)
    create_missing: bool = False
    """없는 시편을 만들까.

    **기본은 끔이다.** 만들면 편하지만 오타 하나가 유령 시편을 만든다 —
    기준정보에서 겪은 것과 같은 병이다."""


class SummaryImportItemOut(BaseModel):
    """한 줄의 결과."""

    input: str
    status: str
    """`new` · `existing` · `rejected` · `skipped`. 미리보기에서도 같은 말이다."""
    specimen: str | None = None
    creates_specimen: bool = False
    """이 줄이 시편까지 만드는가. **켜 두면 표가 시편을 늘린다** — 보여야 한다."""
    run: str | None = None
    """만들어진 시험 이름. 미리보기에서는 비어 있다."""
    conditions: dict[str, float] = {}
    summaries: dict[str, float | str] = {}
    reason: str | None = None
    warnings: list[str] = []


class SummaryImportOut(BaseModel):
    created: int
    existing: int
    skipped: int
    rejected: int
    specimens_created: int = 0
    items: list[SummaryImportItemOut]
