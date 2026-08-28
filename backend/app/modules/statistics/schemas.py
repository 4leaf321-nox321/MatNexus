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
