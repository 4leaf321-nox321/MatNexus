"""묶음 — **여러 시험을 묶어 하나를 만든다.**

## 왜 처리도 통계도 아닌가

    처리   시험 하나 안에서 끝난다        곡선 → 곡선·스칼라
    통계   값들을 평균 낸다               스칼라 n개 → 평균·표준편차
    묶음   여러 시험이 있어야 답이 나온다  곡선 n벌 → 곡선 하나 · 계수 한 벌

셋째가 실제로 있었는데 자리가 없었다. 점탄성이 **전용 표(`master_curves`)와 전용
라우트**로 그것을 따로 만들고 있었고, 다음 물성이 오면 또 만들어야 했다 —
피로 S-N 곡선(시편 수십 개를 지나는 회귀), 크리프(조건별 여러 시험)가 전부 같은
모양이다.

**평균이 아니라는 것이 요점이다.** 시편 다섯의 마스터커브를 평균 내는 것과
다섯을 겹쳐 하나로 만드는 것은 다른 계산이고, S-N 은 아예 평균이 뜻이 없다.

## 확장 창구는 넷 그대로다

새 등록 함수를 만들지 않았다. `registry.register(kind="grouping")` 이다 — 확장이
외울 것이 늘지 않는다(AGENTS).

## 계산은 DB 를 모른다

여기 오는 것은 **이미 읽힌 숫자**다. "어느 시험들이 한 묶음인가", "채택된 결과에서
무엇을 꺼내는가" 는 저장소 쪽(`app/`)이 정한다 — 통계가 이미 그렇게 갈려 있다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from matcore.registry import Plugin, get, list_plugins


class GroupError(Exception):
    """묶을 수 없다. 메시지는 **사용자가 읽는다.**"""


@dataclass(frozen=True)
class Member:
    """묶이는 것 하나 — 대개 시편 하나의 채택된 결과.

    **이름을 함께 든다.** 경고에 「셋째 것이 온도가 다릅니다」 라고만 하면 어느
    시편인지 찾아야 한다.
    """

    label: str
    """사람이 읽는 이름(`SECC__01_MD_01`). 경고와 근거에 그대로 실린다."""

    columns: Mapping[str, np.ndarray] = field(default_factory=dict)
    """곡선. 열 이름은 그 물성이 정한다(`frequency_hz`·`storage_pa`…)."""

    values: Mapping[str, float] = field(default_factory=dict)
    """스칼라. 온도·기준온도처럼 묶는 데 필요한 조건이 여기 온다."""

    meta: Mapping[str, Any] = field(default_factory=dict)
    """이미 맞춰 둔 것(Prony 계수 등). 다시 맞추지 않고 고르기만 할 때 쓴다."""


@dataclass(frozen=True)
class GroupOutcome:
    """묶어서 나온 것.

    **처리 결과와 같은 모양이다** — 곡선 하나와 스칼라 한 벌. 그래야 카드·
    내보내기가 묶음인지 한 건인지 몰라도 된다.
    """

    values: dict[str, float] = field(default_factory=dict)
    columns: dict[str, np.ndarray] = field(default_factory=dict)

    detail: dict[str, Any] = field(default_factory=dict)
    """숫자로 안 담기는 것(Prony 항 목록 등). 그대로 저장된다."""

    warnings: list[str] = field(default_factory=list)
    """막지는 않지만 말해야 하는 것. **묶음에서 특히 많다** — 조건이 조금씩
    다른 것을 묶는 일이라, 무엇을 감수하고 묶었는지가 남아야 한다."""

    used: list[str] = field(default_factory=list)
    """실제로 쓴 구성원의 이름. **고른 것과 쓴 것이 다를 수 있다** — 조건이
    안 맞아 빠진 것이 있으면 사람이 그것을 알아야 한다."""


def groupings(
    applies_to: str | None = None, channels: Iterable[str] | None = None
) -> list[Plugin]:
    """등록된 묶음. 화면이 목록을 적어 두지 않게 한다.

    **키가 아니라 채널로도 잡는다** — 부서가 만든 DMA 종류는 키가 다른데 재는
    것은 같다(`registry.fits`).
    """
    return list_plugins(kind="grouping", applies_to=applies_to, channels=channels)


def run_group(
    plugin_id: str, members: Sequence[Member], options: Mapping[str, Any] | None = None
) -> GroupOutcome:
    """묶음 하나를 돌린다.

    **둘 미만이면 막는다.** 하나를 「묶었다」 고 부르면 그 결과가 묶음인지 한
    건인지 나중에 구별할 수 없다 — 대표 하나를 고르는 것도 후보가 여럿일 때
    뜻이 있다.
    """
    try:
        plugin = get(plugin_id)
    except KeyError as exc:
        raise GroupError(f"등록되지 않은 계산입니다: {plugin_id}") from exc
    if plugin.kind != "grouping":
        raise GroupError(
            f"묶음 계산이 아닙니다: {plugin_id} 는 '{plugin.kind}' 입니다. "
            f"갈래를 안 보면 묶음 자리에 아무 계산이나 들어간다."
        )
    if len(members) < 2:
        raise GroupError(
            f"묶으려면 둘 이상이 필요합니다(지금 {len(members)}개). "
            f"하나뿐이면 그 시험의 결과를 그대로 쓰세요."
        )
    outcome = plugin.fn(list(members), **dict(options or {}))
    if not isinstance(outcome, GroupOutcome):
        raise GroupError(f"{plugin_id} 가 GroupOutcome 을 안 돌려줬습니다.")
    return outcome


__all__ = [
    "GroupError",
    "GroupOutcome",
    "Member",
    "groupings",
    "run_group",
]
