"""적합·물성 카드 API 의 요청·응답 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FamilyOut(BaseModel):
    key: str
    label: str
    describe: str
    parameter_names: list[str]
    parameter_units: list[str]
    block: str = "hardening"
    """적합 결과가 담기는 물성 블록(ADR 0012). 초탄성은 `hyperelastic` 이다."""
    x_label: str = "진소성변형률"
    y_label: str = "진응력"
    """이 식이 맞추는 축의 이름. **고무는 공칭이다** — 화면의 축 라벨이
    "진소성변형률" 이라고 붙으면 그것은 거짓말이다."""


class FittedParameterOut(BaseModel):
    name: str
    value: float
    si_unit: str
    lower: float
    upper: float
    initial: float
    """**경계와 초기값을 함께 준다.** 비선형 적합은 여기에 따라 다른 답에 수렴한다."""


class FitOut(BaseModel):
    family: str
    label: str
    parameters: list[FittedParameterOut]
    rmse: float
    relative_rmse: float
    r_squared: float
    max_residual: float
    point_count: int
    strain_min: float
    strain_max: float
    """**적합 구간.** 이 밖은 외삽이고 식마다 전혀 다른 값이 나온다."""
    notes: list[str]
    curve: list[tuple[float, float]]
    """적합된 식을 그린 것. 데이터와 겹쳐 봐야 맞는지 눈으로 판단할 수 있다."""
    extrapolated_to: float | None = None
    """늘려 그린 한계. **`strain_max` 부터 여기까지가 외삽 구간**이고, 화면은 그
    경계를 표시해야 한다 — 점이 나란히 있으면 어디까지가 시험인지 구별이 안 된다."""
    x_label: str = "진소성변형률"
    y_label: str = "진응력"
    """이 적합이 선 축의 이름. **고무는 공칭이다** — 그래프의 축이 "진소성변형률"
    이라고 붙으면 그것은 거짓말이고, 그 거짓말은 화면에서만 보인다."""
    block: str = "hardening"
    """이 식의 결과가 담기는 물성 블록(ADR 0012).

    **화면이 늘리기 칸을 잠그는 근거다.** 늘리는 것은 소성 표를 만드는 일이라
    `hardening` 에서만 뜻이 있는데, 화면이 그것을 모르면 고무를 고른 사람이
    숫자를 넣고 저장 버튼을 누른 뒤에야 422 를 받는다 — **보고 정하라고 만든
    화면에서 그러면 안 된다.**"""


class FitPreviewRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    families: list[str] = []
    """비우면 등록된 식 전부를 견준다."""
    extrapolate_to: float | None = Field(default=None, gt=0, le=10.0)
    """여기까지 늘려 **그려 준다.** 저장하지 않는다.

    **194 MPa 가 갈리는 결정을 눈으로 못 보고 내리면 안 된다.** 측정 구간에서
    거의 같은 두 식이 외삽에서 갈리는데, 저장 뒤에야 결과를 보면 판단할 자리가
    없다."""
    blend_with: str | None = None
    """`blend_primary` 와 섞어 그릴 두 번째 식."""
    blend_primary: str | None = None
    blend_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    """셋을 함께 줘야 혼합 곡선이 후보에 하나 더 붙는다."""


class InheritedValueOut(BaseModel):
    """카드가 **물려받을** 값 하나.

    화면이 이것을 미리 보여 주지 않으면 사람은 재료·시료에 이미 있는 값을 모달에
    또 적는다. 두 곳이 갈리면 그때 어느 쪽이 맞는지 판정할 근거가 없다.

    적합 응답에 싣는 이유: **카드를 만들 때 실제로 쓰는 계산과 같은 코드**가
    내야 한다. 화면이 재료 API 를 따로 불러 나름대로 판정하면 규칙이 두 벌이
    되고, 둘이 어긋나는 순간 화면이 거짓말을 한다.
    """

    key: str
    label: str
    value: float | None
    source: str
    """`sample` | `material` | `manual` | `conflict` | `missing`."""
    detail: str | None


class FitPreviewOut(BaseModel):
    source_points: list[tuple[float, float]]
    """적합에 쓴 점(소성변형률, 진응력). 대표 곡선에서 왔다."""
    sample_count: int
    fits: list[FitOut]
    elastic: list[InheritedValueOut] = []
    """비워 두면 카드에 들어갈 값들. 사람이 모달에서 덮어쓸 수 있다."""
    notes: list[str]


class PropertyCardSaveRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    label: str = Field(min_length=1, max_length=120)
    family: str | None = None
    """비우면 표만 저장한다 — 식이 안 맞는 재료에서는 표가 더 정확하다."""
    poisson_ratio: float | None = Field(default=None, gt=0, lt=0.5)
    """**인장시험이 주지 않는 값이다.** 없으면 없는 채로 둔다 — 0.3 으로 채우면
    그것이 측정값인지 기본값인지 나중에 알 수 없다."""
    density: float | None = Field(default=None, gt=0)
    blend_with: str | None = None
    """`family` 와 섞을 두 번째 식. **외삽에서 갈리는 구간을 조정한다.**

    측정 구간에서는 두 식이 거의 같은데 외삽에서 크게 갈린다 — Swift 는 과대,
    Voce 는 과소 예측하는 경향이 알려져 있어 이 도메인에서는 둘을 섞어 쓴다.

    **적합을 좋게 하려는 것이 아니다.** 혼합의 RMSE 가 두 식 모두보다 나쁠 수 있고
    그 자체는 문제가 아니다."""
    blend_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    """`family` 쪽 비중. `blend_with` 를 주면 함께 줘야 한다.

    **기본값을 두지 않는다.** 적합 구간에서는 어느 값이든 비슷하게 맞으므로
    데이터가 못 정한다 — 얼마나 보수적으로 볼지가 정하고 그건 해석하는 사람이 안다."""
    extrapolate_to: float | None = Field(default=None, gt=0, le=10.0)
    """소성 표를 어디까지 늘릴까. **비우면 측정 구간 그대로.**

    인장시험은 네킹까지만 준다(강판이면 진소성변형률 0.1~0.25). 충돌 해석은
    0.5~1.5, 성형은 0.3~1.0 을 쓴다 — 그 사이 구멍을 안 채우면 솔버가 자기
    기본값으로 채우고(대개 마지막 응력을 붙들고 간다), **그것도 물리적 주장이다.**

    **기본값을 두지 않는다.** 얼마까지 필요한지는 무슨 해석을 하느냐가 정하고
    그건 해석하는 사람이 안다. 기본값을 두면 그 값이 곧 결정이 되는데, 아무도
    그것을 결정이라고 인식하지 않는다.

    식을 안 골랐으면(`family` 가 비었으면) 늘릴 근거가 없으므로 거절한다."""
    note: str | None = None


class ExportFormatOut(BaseModel):
    key: str
    label: str
    extension: str
    describe: str
    requires: list[str]
    """이 형식에 반드시 있어야 하는 값. **화면이 미리 알려 줄 수 있어야 한다** —
    내려받기를 누른 뒤에 "푸아송비가 없습니다" 를 보는 것은 늦다."""


class CardValueOut(BaseModel):
    """카드에 담기는 값 하나의 이름과 뜻. **화면이 이것만으로 칸을 그린다.**

    `processing` 의 `ProducedOut` 과 같은 것을 담지만 이름을 가른다 — 같은 클래스
    이름이 둘이면 OpenAPI 가 **양쪽 다** 이름을 바꿔 버려서, 손대지 않은 처리
    화면의 타입까지 깨진다. 실제로 한 번 깨뜨리고 알았다.
    """

    key: str
    label: str
    si_unit: str
    """**저장 단위(SI)** 다. 화면은 실무 단위로 바꿔 보여 준다."""
    help: str | None = None


class BlockSpecOut(BaseModel):
    """물성 블록 한 갈래의 선언.

    **화면이 블록 이름을 하나도 모른다.** 그것이 새 물성을 더하는 값을
    마이그레이션 0·화면 0 으로 만드는 자리다.
    """

    key: str
    label: str
    help: str
    produces: list[CardValueOut]
    rows: list[CardValueOut]
    """표의 열 선언. 비어 있으면 이 블록에는 표가 없다."""
    in_deck: bool
    """덱에 실리는가. 경화식은 안 실린다 — 표로 나가고 식은 주석에만 남는다."""


class PropertyCardOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    test_type_key: str | None
    """어느 시험에서 나왔나. **빌 수 있다** — 선언 물성만으로 만든 카드다.

    자리표시를 안 넣는다: 아무 시험종류나 채우면 그 카드가 인장시험에서 나온
    것처럼 보이고, 덱을 받은 사람은 그 숫자를 잰 값으로 읽는다."""
    orientation: str | None
    label: str
    status: str
    """`draft` | `published` | `deprecated`. 전환 권한은 D8·D12 참조."""
    source: dict[str, Any]
    blocks: dict[str, Any]
    """물성 블록 묶음. 무엇이 들어 있는지는 `GET /fitting/blocks` 의 선언이 푼다."""
    available_formats: list[str] = []
    """이 카드로 **지금 낼 수 있는** 형식. 누르기 전에 알아야 한다 —
    내려받기를 누른 뒤에 "푸아송비가 없습니다" 를 보는 것은 늦다."""
    problem: str | None = None
    """이 카드를 풀지 못한 이유. 실린 블록을 만든 계산이 지금 코드에 없을 때
    채워진다 — **목록에서 없던 일로 하지 않는다.**"""
    point_count: int
    note: str | None
    owner_workspace_name: str | None = None
    """재료의 소유 부서. **카드에 따로 안 둔다** — 재료를 따라간다."""
    is_global: bool = False
    published_at: datetime | None
    created_at: datetime


class CardFacetOut(BaseModel):
    """거를 수 있는 값 하나와 **그것이 몇 장인가.**

    화면이 한 페이지에서 세면 안 된다. 50장만 받아 세면 「인장시험 12」라고
    적히는데 실제로는 40장일 수 있고, 그러면 **필터 옆의 숫자가 거짓말을 한다.**
    레시피 필터는 목록을 통째로 받으므로 화면에서 세도 됐지만, 카드는 페이지로
    온다.
    """

    key: str
    label: str
    count: int


class CardFacetsOut(BaseModel):
    """무엇으로 거를 수 있나. **지금 걸린 필터와 무관하게 전체를 센다.**

    「무엇이 있나」를 답하는 자리다 — 필터를 걸 때마다 다른 축의 숫자가 같이
    줄면, 필터를 풀기 전에는 그 축에 무엇이 있는지 알 수 없다.
    """

    statuses: list[CardFacetOut]
    test_types: list[CardFacetOut]
    """`test_type_key`. **시험 없이 만든 카드는 `none` 으로 온다** — 안 그러면
    선언 물성 카드가 어느 필터에도 안 걸려 목록에서 사라진다."""
    owners: list[CardFacetOut]
    """소유 부서. 전역은 `global`."""


class DeclaredCardPreviewOut(BaseModel):
    """적어 둔 값만으로 카드를 만들면 **무엇이 실리는가.**

    화면이 재료 API 를 따로 불러 나름대로 판정하지 않게 하려고 둔다 — 규칙이
    두 벌이 되면 어긋나는 순간 화면이 거짓말을 한다. `FitPreviewOut.elastic` 이
    같은 이유로 있다.

    **누르기 전에 알아야 한다.** 만들기를 누른 뒤에 "적어 둔 물성이 없습니다" 를
    보는 것은 늦다.
    """

    material_name: str
    values: list[InheritedValueOut]
    """실릴 값들. 선언 물성과 물려받은 푸아송비·밀도가 함께 온다."""
    blocks: list[str]
    """생길 블록 이름. 비면 카드를 만들 수 없다."""


class DeclaredCardSaveRequest(BaseModel):
    """**시험 없이** 선언 물성만으로 카드를 만든다(ADR 0016).

    시험이 하나도 없는 재료는 대표 곡선이 없어서 `POST /cards` 를 탈 수 없었다.
    그런데 탄성계수·열물성은 인장시험이 주지 않는 값이고, 그것만으로도 열해석·
    선형 정적 해석의 덱은 나간다.

    **적합이 없으므로 식도 표도 없다.** 여기서 나오는 카드는 `elastic` 과
    `thermal` 블록만 든다 — 소성 표가 필요한 형식은 `available_formats` 에서
    저절로 빠진다(렌더러가 `Need` 로 선언한다).
    """

    material_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    poisson_ratio: float | None = Field(default=None, gt=0, lt=0.5)
    """비우면 재료에 적힌 값을 쓴다. **없으면 없는 채로 둔다.**"""
    density: float | None = Field(default=None, gt=0)
    note: str | None = None


class ViscoelasticCardSaveRequest(BaseModel):
    """Prony 적합에서 점탄성 카드를 만든다.

    **묶음을 받지 않는다.** 경화 카드는 재료+시험종류+방향의 대표 곡선에서
    나오지만 Prony 는 마스터커브 하나에 매달려 있다 — 재료·방향은 그 체인
    (적합 → 마스터커브 → 시험 → 시편 → 시료 → 재료)에서 따라간다.
    """

    prony_fit_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    poisson_ratio: float | None = Field(default=None, gt=0, lt=0.5)
    """**DMA 는 이것을 재지 않는다.** 재료에서 물려받거나 사람이 넣는다 —
    없으면 없는 채로 두고, `*ELASTIC` 을 못 쓴다고 그때 말한다."""
    density: float | None = Field(default=None, gt=0)
    note: str | None = None


class PropertyCardUpdateRequest(BaseModel):
    """**이름과 메모만.** 값은 못 바꾼다.

    카드는 불변이다 — 물성 블록을 고치는 길은 없고, 고치려면
    새로 만든다(ADR 0007 과 같은 모델). 그런데 그 원칙이 **이름 오타까지 못 고치게**
    만들고 있었다. 지우고 다시 만드는 수밖에 없었고, 그러면 적합을 다시 돌린다.

    확정된 카드는 이름도 못 바꾼다. 그 이름으로 덱이 이미 나갔을 수 있다.
    """

    label: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = None
