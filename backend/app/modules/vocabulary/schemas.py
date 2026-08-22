"""기준정보 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

#: 한 번에 받는 최대 줄 수. **상한을 서버가 건다** — 화면이 정하게 두면
#: 언젠가 "엑셀 통째로" 가 온다.
BULK_MAX = 500


class VocabularyOut(BaseModel):
    slug: str
    label: str
    parent_slug: str | None = None
    """상위 축. 화면이 "상위 분류" 칸을 보여 줄지 정하는 데 쓴다 — 부모가 없는
    축에 그 칸을 두면 적어 봐야 아무 데도 안 간다."""
    entry_policy: str
    """`open` 이면 화면이 '새로 추가' 를 보여 줘도 된다. `closed` 면 감춘다 —
    눌러 봐야 서버가 거절하는 버튼은 두지 않는다."""
    term_count: int
    attribute_source: str | None = None
    """이 축의 값이 속성을 갖는가. `test_type` 이면 값마다 시험 종류를 고르고,
    그 종류가 선언한 시편 규격 칸이 속성 스키마다. 화면이 그 칸을 그린다."""


class TermOut(BaseModel):
    id: uuid.UUID
    value: str
    parent_value: str | None = None
    """상위 축의 값. 화면이 "이 강종은 Metal/Steel 아래 있습니다" 를 말하는 데 쓴다."""
    usage_count: int
    """피커가 많이 쓰는 것을 위로 올린다. 개수가 보이면 고르기 전에 안다.

    **이름을 고칠 때 몇 건이 따라오는지**이기도 하다. 외래키라 한 행을 고치면
    이 수만큼이 함께 바뀐다."""
    status: str = "active"
    attributes: dict[str, float | str] = {}
    """이 값의 속성. 숫자 치수는 **SI 다**(화면이 mm 로 바꿔 보여 준다). 판
    (edition) 처럼 문자인 것과, 모드처럼 목록에서 고르는 것도 함께 담긴다."""
    field_symbols: dict[str, str] = {}
    """이 규격이 그 칸을 **어느 글자로 부르는가.** 위에서 온 칸의 글자를 덮는다."""
    extra_fields: list[SpecimenFieldOut] = []
    """이 값만 갖는 칸. 상위 분류의 기본 칸에 더해진다."""
    cross_section: str | None = None
    """이 규격의 시편은 단면적을 어떻게 내는가(`matcore.specimen`)."""
    ratio_checks: list[RatioCheckOut] = []
    """이 규격이 요구하는 비율 조건. **어겨도 막지 않는다** — 보이게만 한다."""
    field_count: int = 0
    """이 값이 **직접 선언한** 칸 수. 분류 축에서 쓴다 — 0 이면 그 분류의
    규격은 치수를 하나도 못 갖는다."""


class RatioCheckOut(BaseModel):
    """비율 조건 하나 — `분자 / 분모` 가 `[최소, 최대]` 안에 있어야 한다.

    **규격이 치수를 안 주고 비만 주는 일이 흔하다.** DMA 는 숫자를 실제로 주는
    파트가 셋뿐이고 나머지는 비율이거나 장비 위임이다.
    """

    numerator: str
    denominator: str
    minimum: float | None = None
    maximum: float | None = None
    help: str | None = None


class CrossSectionNeedOut(BaseModel):
    """식이 요구하는 칸 하나. **화면이 이것으로 칸을 대신 만들어 준다.**"""

    key: str
    label: str
    dimension: str = "length"
    si_unit: str = "m"


class CrossSectionOut(BaseModel):
    """고를 수 있는 단면적 식 하나.

    **키가 아니라 이름을 함께 준다** — `rectangle` 은 사람이 읽는 말이 아니다.
    """

    key: str
    label: str
    needs: list[CrossSectionNeedOut]
    """이 식이 요구하는 치수 칸. **키만이 아니라 어떤 칸인지까지 준다** — 화면이
    "직경 칸이 없습니다" 라고 말하는 대신 그 칸을 만들어 줄 수 있다."""
    help: str | None = None


class SpecimenFieldOut(BaseModel):
    """치수 칸 하나.

    **분류가 준 것과 이 규격이 더한 것을 함께 낸다** — `inherited` 로 가른다.
    화면이 이 응답만으로 입력 폼을 그린다.
    """

    key: str
    label: str
    kind: str = "number"
    """담는 것 — `number` · `text` · `choice`. 치수만 있는 것이 아니다."""
    choices: list[str] = []
    """`choice` 일 때 고를 수 있는 값."""
    symbol: str | None = None
    """그 규격의 도면이 쓰는 글자(`G`·`W`·`D`). **뜻이 아니라 글자다** — 같은
    `D` 가 E8 에서는 직경, D638 에서는 그립 간 거리다."""
    dimension: str
    si_unit: str
    is_required: bool
    help: str | None = None
    inherited: bool = False
    """위(축·분류)가 준 칸인가. 그렇다면 이 값에서는 못 지운다."""


class StandardTemplateOut(BaseModel):
    """가져올 수 있는 표준 규격 하나.

    **치수 값은 없다.** 근거 문서가 2차 출처라 숫자는 사람이 규격서를 보고 넣는다 —
    칸과 기호는 판이 바뀌어도 그대로지만 값은 바뀐다.
    """

    key: str
    value: str
    """만들어질 값 이름. `ASTM E8/E8M 박판형`."""
    category: str
    """어느 시편 분류 아래로 들어가는가."""
    family: str
    """화면이 묶어 보여 주는 갈래. `금속 인장`."""
    fields: list[SpecimenFieldOut]
    cross_section: str | None = None
    ratio_checks: list[RatioCheckOut] = []
    help: str | None = None
    taken: bool = False
    """이미 그 이름의 값이 있는가. **덮어쓰지 않는다** — 있으면 건너뛴다."""


class StandardImportRequest(BaseModel):
    """고른 것만 만든다. **안 쓰는 규격이 목록을 채우면 피커가 무거워진다.**"""

    keys: list[str] = Field(min_length=1, max_length=100)


class SpecimenFieldSaveRequest(BaseModel):
    """칸 하나를 저장할 때의 모양. **키는 계약이다.**

    이미 저장된 규격의 속성이 이 키로 들어 있으므로, 키를 바꾸면 그 값들이 갈
    곳을 잃는다. 이름(`label`)은 얼마든지 고쳐도 된다 — `TestType.key`/`label`
    을 나눈 것과 같은 관계다.
    """

    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="number", max_length=10)
    choices: list[str] = []
    symbol: str | None = Field(default=None, max_length=20)
    dimension: str = Field(default="length", max_length=20)
    si_unit: str = Field(default="m", max_length=20)
    is_required: bool = False
    help: str | None = None


class SpecimenFieldsSaveRequest(BaseModel):
    """칸 목록 **전체**. 분류의 기본 칸이든 규격의 추가 칸이든 같은 모양이다.

    부분 갱신이 아니라 통째로 바꾼다 — 순서가 곧 화면의 순서라, 부분으로 두면
    "3번을 지우고 5번을 2번으로" 같은 것을 표현할 수가 없다.
    """

    fields: list[SpecimenFieldSaveRequest]


class TermCreateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    parent_value: str | None = Field(default=None, max_length=200)
    """상위 축의 값. 주면 새 값이 그 아래로 들어간다."""
    attributes: dict[str, float] = {}
    """치수 등 속성. SI 로 보낸다."""


class TermUpdateRequest(BaseModel):
    """표기 고치기와 감추기. **관리자만.**

    값을 지우는 길은 없다 — 지우면 그것을 가리키던 시료가 무엇이었는지 알 수
    없게 된다. `deprecated` 로 감추면 피커에서만 사라진다.
    """

    value: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|deprecated)$")
    attributes: dict[str, float | str] | None = None
    field_symbols: dict[str, str] | None = None
    ratio_checks: list[RatioCheckOut] | None = None
    """주면 통째로 바꾼다. 빠뜨린 칸은 지워진다 — 부분 갱신은 "빈 칸으로 고쳤다"
    와 "안 보냈다" 를 구별할 수 없다."""
    cross_section: str | None = Field(default=None, max_length=20)
    """단면적 식. **빈 문자열이면 뗀다.** 그 식이 요구하는 치수 칸이 이 규격에
    있어야 고를 수 있다 — 없는 칸을 요구하는 식은 늘 실패한다."""
    extra_fields: list[SpecimenFieldSaveRequest] | None = None
    """이 값**만** 갖는 치수 칸. 상위 분류의 기본 칸에 더해진다.

    `ASTM E8 R1` 은 환봉이라 직경이 필요하고 `JIS 5호` 는 평판이라 필요 없다.
    **분류의 기본 칸과 같은 키는 못 쓴다** — 어느 쪽이 이기는지 알 방법이 없다."""
    parent_value: str | None = Field(default=None, max_length=200)
    """상위 축의 값. **빈 문자열이면 부모를 뗀다** — `None` 은 "안 건드림" 이라
    둘을 구분할 자리가 필요하다.

    백필이 못 이은 값(부모가 갈렸던 것)을 사람이 정하는 자리다. 그 길이 없으면
    로그만 남기고 아무도 못 고친다."""


class TermAliasOut(BaseModel):
    """값의 다른 표기.

    이름에 `Term` 을 붙인 이유: 단위 모듈에도 `AliasOut` 이 있어서 FastAPI 가
    생성 스키마 이름을 `app__modules__vocabulary__schemas__AliasOut` 으로 늘렸다.
    프론트 타입이 그 이름을 달면 읽을 수 없다."""

    id: uuid.UUID
    alias: str


class TermAliasCreateRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=200)


class MergeRequest(BaseModel):
    into_id: uuid.UUID
    """살아남을 값. **없어지는 쪽이 URL 에 있다** — 무엇이 사라지는지가 주어다."""


class DismissRequest(BaseModel):
    """ "이 둘은 다른 값이다" 를 기억한다."""

    first_id: uuid.UUID
    second_id: uuid.UUID


class BulkTermCreateRequest(BaseModel):
    """여러 값을 한 번에. **줄 단위로 붙여 넣는 것이 자연스럽다.**

    상한을 서버가 건다 — 화면이 정하게 두면 언젠가 "엑셀 통째로" 가 온다.
    """

    values: list[str] = Field(min_length=1, max_length=BULK_MAX)
    parent_value: str | None = Field(default=None, max_length=200)
    """줄에 상위가 없을 때 쓸 기본값. 줄이 적은 것이 이긴다."""


class BulkTermItemOut(BaseModel):
    """한 줄의 결과. **무엇이 새로 생겼는지 건별로 말한다.**

    개수만 주면 "50개 중 12개가 새로 생겼습니다" 로 끝나는데, 사람이 알고 싶은
    것은 **어느 것이** 안 생겼고 왜인지다.
    """

    input: str
    status: str
    """`created` | `existing` | `skipped` | `rejected`."""
    value: str | None = None
    """정규 값. 별칭이나 표기 차이로 기존 값에 붙으면 친 것과 다르다."""
    parent_value: str | None = None
    """이 줄에 붙은 상위. 줄마다 다를 수 있다."""
    reason: str | None = None
    """`rejected` 인 이유. **말없이 버리지 않는다.**"""


class BulkTermOut(BaseModel):
    created: int
    existing: int
    skipped: int
    rejected: int = 0
    items: list[BulkTermItemOut]


class BulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)


class BulkDeleteItemOut(BaseModel):
    id: uuid.UUID
    value: str
    deleted: bool
    reason: str | None = None
    """못 지운 이유. **무엇이 막는지 말하는 것이 요점이다** — "지울 수 없습니다"
    만 주면 사람은 왜인지 알아내려고 목록을 뒤진다."""


class BulkDeleteOut(BaseModel):
    deleted: int
    blocked: int
    items: list[BulkDeleteItemOut]


class DriftOut(BaseModel):
    """문자열과 기준정보가 벌어진 한 칸."""

    table: str
    field: str
    label: str
    """어느 축인가."""
    count: int
    examples: list[str]
    """`문자열 ↔ 기준정보 값` 몇 개. **수만 주면 무엇이 벌어졌는지 알 수 없다.**"""


class DriftReportOut(BaseModel):
    """어긋남 점검 결과. **0 이어야 한다.**

    문자열 컬럼을 지우기(Contract) 전에 한 릴리스 동안 0 이어야 한다. 0 이 아닌
    채로 지우면 어느 쪽이 맞았는지 영영 알 수 없다.

    그래서 "지금 0" 만으로는 부족하다 — `clean_since` 가 진짜 답이다.
    """

    total: int
    items: list[DriftOut]
    checked_at: datetime | None = None
    """이 결과를 잰 시각."""
    clean_since: datetime | None = None
    """**이때부터 지금까지 계속 0 이었다.** 한 번이라도 벌어졌으면 거기서 다시
    센다 — 고쳤더라도 "내내 0 이었다" 는 더 이상 참이 아니다."""
    clean_checks: int = 0
    """그동안 몇 번 쟀나. 시각만 주면 두 번 재고 이틀이 지난 것과 구분이 안 된다."""
