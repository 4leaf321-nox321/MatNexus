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


class TermCreateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    parent_value: str | None = Field(default=None, max_length=200)
    """상위 축의 값. 주면 새 값이 그 아래로 들어간다."""


class TermUpdateRequest(BaseModel):
    """표기 고치기와 감추기. **관리자만.**

    값을 지우는 길은 없다 — 지우면 그것을 가리키던 시료가 무엇이었는지 알 수
    없게 된다. `deprecated` 로 감추면 피커에서만 사라진다.
    """

    value: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|deprecated)$")
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
