"""통계 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OutlierOut(BaseModel):
    """이상치 **후보**. 버려지지 않았다."""

    test_run_id: uuid.UUID
    record_name: str
    value: float
    score: float | None
    """modified z-score. 흩어짐이 0 이면 낼 수 없어 비어 있다."""
    reason: str


class ScalarStatsOut(BaseModel):
    key: str
    label: str
    si_unit: str
    dimension: str | None
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    sample_sd: float | None
    """흩어짐. **1건이면 없다** — 0 이 아니라 없는 것이다.

    0 을 넣으면 "완벽히 일정하다" 로 읽힌다. 한 번밖에 안 재서 모르는 것과
    여러 번 재서 같았던 것은 전혀 다른 말이다.
    """
    mad: float | None
    iqr: float | None
    coefficient_of_variation: float | None
    ci95_low: float | None
    ci95_high: float | None
    outliers: list[OutlierOut]


class MemberCurveOut(BaseModel):
    """시편 하나의 원곡선. **대표 곡선 뒤에 흐리게 깔린다.**

    평균만 보여 주면 그것이 적절한지 알 방법이 없다 — 열 개가 겹쳐 있어서
    평균이 그 자리인 것과, 하나가 딴 데로 가서 끌려간 것이 **평균선 하나로는
    똑같이 생겼다.**
    """

    test_run_id: uuid.UUID
    record_name: str
    points: list[tuple[float, float]]
    """그리기 좋게 솎은 점. **줄였다는 것은 화면이 말한다.**"""


class CurveStatsOut(BaseModel):
    x: str
    y: str
    units: dict[str, str] = {}
    """축의 **저장 단위**. 화면이 표시 단위로 되돌릴 때 쓴다.

    안 보내던 동안 화면이 채널 이름 앞글자로 짐작했다 — `stress*` 면 Pa,
    나머지는 전부 무차원. 그래서 변위가 m 그대로 나오고, 축에는 단위가 아예
    안 붙었다. 처리 결과(`ProcessingResultOut.units`)와 같은 모양이다."""
    mean: list[tuple[float, float]]
    median: list[tuple[float, float]]
    sd: list[tuple[float, float]]
    count: list[tuple[float, float]]
    """점마다 몇 개로 냈는지. 공통 구간 밖은 애초에 계산하지 않는다."""
    members: list[MemberCurveOut] = []
    """대표를 만든 시편들의 원곡선. **같은 축이다** — 축이 섞이면 겹쳐 놓은
    그림이 거짓말을 한다."""


class GroupOut(BaseModel):
    """묶음 하나 — **재료 + 시험종류 + 방향.**"""

    test_type_key: str
    test_type_label: str
    orientation: str
    sample_count: int
    skipped_unadopted: int
    """채택되지 않아 빠진 시험 수. **조용히 빼면 n 이 왜 이 수인지 모른다.**"""
    test_run_ids: list[uuid.UUID]
    record_names: list[str]
    scalars: list[ScalarStatsOut]
    curve: CurveStatsOut | None
    notes: list[str]
    """왜 여기까지인지, 무엇이 어긋났는지. 곡선이 없으면 이유가 여기 있다."""


class MaterialStatisticsOut(BaseModel):
    material_id: uuid.UUID
    material_name: str
    groups: list[GroupOut]


class EnsembleSaveRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str


class EnsembleResultOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    sample_count: int
    test_run_ids: list[uuid.UUID]
    created_at: datetime


class ObservationOut(BaseModel):
    """값 하나가 어떻게 됐는가. **없는 것과 못 쓰는 것을 가른다.**"""

    specimen_label: str
    status: str
    """`observed` · `missing` · `non_finite` · `censored`"""
    value: float | None


class DistributionCandidateOut(BaseModel):
    """분포 하나를 맞춰 본 결과. **실패한 것도 목록에 남는다.**"""

    key: str
    label: str
    status: str
    """`succeeded` · `not_eligible` · `failed`.

    **셋을 한 칸에 넣지 않는다.** `not_eligible` 은 표본이 모자라 물음이 성립하지
    않는 것이고 `failed` 는 물었는데 답이 안 나온 것이다 — 섞으면 "와이블이 안
    맞는 재료" 와 "시편이 모자란 재료" 가 같은 색으로 보인다."""
    reason: str | None
    parameters: list[float]
    parameter_names: list[str]
    parameter_labels: list[str]
    log_likelihood: float | None
    aicc: float | None
    """유한표본 보정 AIC. **작을수록 낫다.** 후보끼리만 뜻이 있다 — 전부 안 맞아도
    하나는 1등이 된다."""
    delta_aicc: float | None
    """1등과의 차이. 2 미만이면 이 데이터로는 구별되지 않는다."""
    anderson_darling: float | None
    p_value: float | None
    """모수 부트스트랩 p. **작으면 이 분포가 아니라는 뜻이다.** 큰 p 가 "맞다" 는
    증명은 아니다 — 표본이 작으면 무엇으로도 안 갈린다."""
    quantiles: dict[str, float]
    """`p05`·`p50`·`p95`. **이 응답의 쓸모가 여기 있다** — 설계가 묻는 것은
    파라미터가 아니라 하위 5% 다."""


class EmpiricalOut(BaseModel):
    """**분포를 가정하지 않은** 요약. n 이 몇이든 나온다.

    적합이 하나도 못 돌 때(n < 8) 화면이 빈손이 되지 않게 하는 것이 첫 목적이다.
    전에는 「표본 모자람」 배지 셋만 떴고, 그것은 막다른 길이었다 — 사람이 할 수
    있는 판단이 아무것도 없었다.
    """

    count: int
    minimum: float | None
    q1: float | None
    median: float | None
    q3: float | None
    maximum: float | None

    covered_quantile: float | None
    """관측 **최소값**이 덮는 분위수(순서통계량). n=3 이면 0.63 이다.

    **작은 표본이 꼬리를 못 본다는 사실 자체를 수로 보여 준다.** 「데이터가
    모자랍니다」 보다 「최소값으로 63% 분위수까지 말할 수 있습니다」 가 판단할
    거리를 준다."""
    needed_for_design: int | None
    """하위 5% 를 **분포 없이** 말하려면 필요한 표본 수. 95% 신뢰로 59개."""
    confidence: float


class DistributionReportOut(BaseModel):
    """한 항목에 대한 분포 적합 한 벌."""

    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    scalar_key: str
    scalar_label: str
    si_unit: str
    count: int
    """실제로 쓴 값의 개수. 시편 수가 아니다."""
    observations: list[ObservationOut]
    candidates: list[DistributionCandidateOut]
    best: str | None
    empirical: EmpiricalOut | None
    """**적합이 하나도 못 돌아도 이것은 있다.**"""
    notes: list[str]


class DistributableKeyOut(BaseModel):
    """분포를 물어볼 수 있는 항목 하나."""

    key: str
    label: str
    si_unit: str
    count: int
    """값이 있는 시편 수. **`MIN_ELIGIBLE` 미만이면 화면이 미리 말해 준다** —
    눌러 보고 나서 "모자랍니다" 를 받는 것보다 낫다."""


class TallyOut(BaseModel):
    """이름 하나와 개수. 분류·시험 종류처럼 **무엇이 몇 건인가** 를 담는다."""

    key: str
    label: str
    count: int


class AnalysisScalarOut(BaseModel):
    """고를 수 있는 물성 항목. **실제로 값이 있는 것만** — 건수를 함께 준다."""

    key: str
    label: str
    si_unit: str
    count: int


class SpreadOut(BaseModel):
    """상자그림 한 칸. 2건 미만이면 상자를 못 그리므로 없다."""

    count: int
    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    mean: float
    outliers: list[float]


class CompareCellOut(BaseModel):
    scalar_key: str
    scalar_label: str
    si_unit: str
    count: int
    mean: float
    sample_sd: float | None
    """흩어짐. **1건이면 없다** — 0 이 아니라 없는 것이다(ADR 0008 과 같은 규칙)."""
    minimum: float
    maximum: float


class CompareMaterialOut(BaseModel):
    material_id: uuid.UUID
    material_name: str
    family: str
    scalars: list[CompareCellOut]


class CompareOut(BaseModel):
    materials: list[CompareMaterialOut]
    scalars: list[AnalysisScalarOut]
    """고른 재료들이 **함께 가진** 항목이 앞에 온다 — 비교표의 열이 된다."""
    skipped_unadopted: int


class DistributionGroupOut(BaseModel):
    group: str
    cells: dict[str, SpreadOut | None]
    """항목 키 → 흩어짐. **2건 미만이면 `null`** — 화면이 「상자를 못 그린다」 고 적는다.
    항목을 여럿 고르면 열이 여럿이 된다."""


class AnalysisDistributionOut(BaseModel):
    group_by: str
    selected: list[AnalysisScalarOut]
    """고른 항목들 — **열의 차례가 이것이다.** 안 고르면 가장 많은 하나."""
    groups: list[DistributionGroupOut]
    scalars: list[AnalysisScalarOut]
    skipped_unadopted: int


class MaterialChoiceOut(BaseModel):
    """비교에 담을 수 있는 재료 — **채택된 물성이 있는 것만.**

    전체 목록에서 고르게 하면 물성이 없는 재료를 담고 빈 줄을 본다. 무엇을 몇 건
    갖고 있는지 함께 줘서 담기 전에 보이게 한다.
    """

    material_id: uuid.UUID
    material_name: str
    family: str
    category: str
    scalar_count: int
    """항목 수 — 「인장강도·탄성계수 …」 몇 가지를 갖고 있나."""
    run_count: int
    """그 재료에서 채택된 시험 수."""


class SpecGapOut(BaseModel):
    """선언한 값과 잰 값. **차이가 큰 것이 위로 온다.**"""

    material_id: uuid.UUID
    material_name: str
    item: str
    declared_si: float
    declared_source: str | None
    declared_reference: str | None
    measured_mean: float
    measured_count: int
    si_unit: str
    gap_ratio: float
    """(잰 값 - 선언값) / 선언값. 부호가 방향을 말한다."""


class AnalysisSpecGapOut(BaseModel):
    rows: list[SpecGapOut]
    unmatched_items: list[str]
    """선언은 있는데 잰 값이 없어 못 견준 항목. **숨기면 「없다」 로 읽힌다.**"""


class TrendPointOut(BaseModel):
    period: str
    """해. 시험일 기준 — 옛 시험을 오늘 올리면 등록일은 거짓말을 한다."""
    count: int
    mean: float
    minimum: float
    maximum: float


class TrendSeriesOut(BaseModel):
    key: str
    label: str
    points: list[TrendPointOut]


class AnalysisTrendOut(BaseModel):
    scalar_key: str
    scalar_label: str
    si_unit: str
    group_by: str
    series: list[TrendSeriesOut]
    scalars: list[AnalysisScalarOut]
    skipped_unadopted: int


class CoverageCellOut(BaseModel):
    run_count: int
    adopted_count: int
    """채택까지 간 수. **올리기만 한 것과 물성이 나온 것은 다르다** — 그 차이가 남은 일."""
    material_count: int = 0
    """그 분류에서 이 시험을 해 본 재료 수. 분류에 재료가 10개인데 1개만 쟀으면
    「쟀다」 로 읽히면 안 된다."""


class CoverageGroupOut(BaseModel):
    """재료 분류 한 칸 — **재료가 아니라 분류가 행이다.**

    재료마다 한 줄이면 94줄이 되고, 그 표에서 「무엇을 안 쟀나」 를 읽을 수 없다.
    분류로 접으면 「Metal/Steel 은 인장은 했고 점탄성은 안 했다」 가 한 줄에 온다.
    """

    family: str
    category: str
    material_count: int
    cells: dict[str, CoverageCellOut]


class CoverageTypeOut(BaseModel):
    key: str
    label: str


class AnalysisCoverageOut(BaseModel):
    test_types: list[CoverageTypeOut]
    groups: list[CoverageGroupOut]


class DivisionTallyOut(BaseModel):
    """사업부 하나의 현황 — 그 사업부의 시험이 걸친 재료·시료·시편과 시험 수.

    **사업부는 시험에만 붙는다**(ADR 0010 의 축). 재료·시편에는 사업부 칸이 없다 —
    같은 재료를 두 사업부가 시험하는 것이 정상이라, 여기의 재료 수는 「그 사업부
    시험이 걸친 재료」 이고 사업부끼리 합치면 전체보다 클 수 있다.
    """

    division: str
    """`미지정` 은 사업부를 안 적은 시험 — 0 이 아니라면 채울 일이 남은 것이다."""
    run_count: int
    specimen_count: int
    sample_count: int
    material_count: int


class YearTallyOut(BaseModel):
    """한 해 · 한 사업부의 시험 수. 그래프가 그린다. 해는 시험일(없으면 등록일)."""

    year: int
    division: str
    run_count: int


class DivisionOverviewOut(BaseModel):
    divisions: list[DivisionTallyOut]
    """**순서는 서버가 정한다** — MX · VD · DA · NW · 의료기기(실사용 요청으로 고정),
    모르는 값은 그 뒤, 「미지정」 은 맨 뒤. 화면이 다시 정렬하지 않는다."""
    yearly: list[YearTallyOut]


class OverviewOut(BaseModel):
    """홈에 뿌리는 요약.

    **세는 일을 서버가 한다.** 재료 94개를 세려고 94행을 화면으로 보낼 이유가
    없다 — 목록 엔드포인트만 있으면 그렇게 된다.

    부서 범위는 **각 항목이 원래 따르는 규칙 그대로**다. 시험은 부서 것이고
    재료·카드는 전사 카탈로그다(ADR 0004: 남의 부서가 잰 물성도 보라고 만든
    자리다). 여기서 규칙을 새로 만들면 홈의 숫자와 목록 화면의 숫자가 갈린다.
    """

    material_count: int
    families: list[TallyOut]
    """재료의 재료군 분포. **잘못 만든 분류가 여기서 드러난다** — 개발 DB 에
    `Family` 라는 재료군의 재료가 1건 있었고, 요약을 만들고 나서 보였다."""

    sample_count: int
    specimen_count: int
    run_count: int
    test_types: list[TallyOut]
    """시험 종류 분포. 새로 붙인 장비가 안 쓰이고 있으면 여기서 드러난다."""

    card_total: int
    card_published: int
    card_draft: int
    card_deprecated: int
    materials_with_card: int
    """카드가 하나라도 있는 재료 수. `material_count` 와 견주면 **덮인 정도**다."""

    waiting_to_process: int
    """읽혔는데 아직 채택된 처리 결과가 없는 시험. **2단계에 남은 일이다.**"""
    parse_failed: int
    """읽기에 실패한 시험. 0 이면 화면이 안 보인다 — 0을 보이면 그것도 상태처럼
    읽힌다."""
    inbox_waiting: int
    """장비가 보냈는데 **사람이 붙여야** 하는 파일. 시편을 못 정한 것과 후보가
    정해져 승인을 기다리는 것을 함께 센다 — 둘 다 사람이 한 번 봐야 한다.

    **이것이 홈에 있어야 하는 이유:** 수집함은 「데이터 수집 체계」 안쪽에 있어
    매일 여는 자리가 아니다. 장비는 매일 파일을 보내는데 아무도 안 열면 쌓인 줄도
    모른다 — 「처리 대기」 와 같은 성격이고, 그래서 같은 줄에 선다."""
