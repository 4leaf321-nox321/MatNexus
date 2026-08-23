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


class FitPreviewRequest(BaseModel):
    material_id: uuid.UUID
    test_type_key: str
    orientation: str
    families: list[str] = []
    """비우면 등록된 식 전부를 견준다."""


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
    test_type_key: str
    orientation: str
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
    published_at: datetime | None
    created_at: datetime


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
