"""묶음 API 의 모양."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

#: 한 번에 묶을 수 있는 시험 수. 시편 수십 장이 정상인 물성이 있다(피로).
MAX_MEMBERS = 200


class GroupingParamOut(BaseModel):
    """조절하는 값 하나. **화면의 폼 필드가 여기서 생긴다.**

    `dict[str, Any]` 로 두면 프론트 타입이 `{}` 가 되어 화면이 아무거나 읽는다 —
    타입을 손으로 적지 않게 하려고 스키마를 내보내는 것인데 그러면 뜻이 없다.
    """

    name: str
    label: str
    type: str
    default: Any = None
    choices: list[str] = Field(default_factory=list)
    choice_labels: dict[str, str] = Field(default_factory=dict)
    choice_help: dict[str, str] = Field(default_factory=dict)
    """고른 값의 설명. **화면은 고른 것만 보인다** — 셋을 한 줄에 이어 적으면
    지금 무엇을 고른 것인지 눈으로 찾아야 한다."""
    help: str | None = None


class GroupingProducedOut(BaseModel):
    """묶음이 내는 값 하나. **단위를 함께 준다** — 라벨에 손으로 안 적는다."""

    key: str
    label: str
    si_unit: str


class GroupingSpecOut(BaseModel):
    """고를 수 있는 묶음 하나. **화면이 목록을 적어 두지 않게 한다.**"""

    id: str
    label: str
    applies_to: list[str]
    """**풀어서 준다** — 지금 이 DB 에서 이 방법을 쓸 수 있는 시험 종류 키 전부.

    선언에 적힌 키만 주면, 부서가 만든 DMA 종류(키가 다르지만 재는 것은 같다)의
    시험이 화면의 후보에서 조용히 사라진다."""
    requires_channels: list[list[str]] = []
    """필요한 채널. **안쪽 묶음은 「그중 하나」.** 시험 종류를 만드는 화면이 이것을
    읽어 「이 채널을 넣으면 무엇이 열리나」 를 보여 준다."""
    needs: str = "master_curve"
    """구성원이 시험에서 갖고 있어야 하는 것 — `master_curve` 또는 `adopted_result`.
    화면이 후보 시험을 이것으로 거른다. 플러그인 id 로 알아맞히면 새 묶음마다 화면을
    고쳐야 한다."""
    params: list[GroupingParamOut]
    makes_values: list[GroupingProducedOut]
    makes_card: bool = False
    """이 묶음 결과로 카드를 만들 수 있는가 — 플러그인이 `card=` 로 블록을 선언했으면.
    화면은 이것을 보고 「카드 생성」 을 세운다(`/fitting/cards/from-group`). 속도·점탄성
    처럼 제 경로가 있는 것은 결과의 모양으로 따로 안다."""


class GroupNoteRequest(BaseModel):
    """묶음 결과에서 고칠 수 있는 것은 메모뿐이다. 값·멤버·옵션은 그때의 계산 그대로 남는다."""

    note: str | None = Field(default=None, max_length=500)


class GroupCreateRequest(BaseModel):
    plugin_id: str
    run_ids: list[uuid.UUID] = Field(min_length=2, max_length=MAX_MEMBERS)
    """**둘 이상이다.** 하나를 「묶었다」 고 부르면 그 결과가 묶음인지 한 건인지
    나중에 구별할 수 없다."""
    options: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class GroupResultOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    plugin_id: str
    plugin_version: str
    options: dict[str, Any]

    members: list[dict[str, Any]]
    used: list[str]
    """**실제로 쓴 것.** 고른 것과 다를 수 있다 — 대표를 고르면 하나만 쓴다."""

    values: dict[str, float]
    detail: dict[str, Any]
    warnings: list[str]
    note: str | None
    created_at: datetime
