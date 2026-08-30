"""시험 종류가 가진 채널 — **누가 어떤 계산을 쓸 수 있는지의 근거.**

레지스트리는 계산마다 필요한 채널을 선언한다(`Plugin.requires_channels`). 그것을
실제 시험 종류와 맞춰 보려면 그 종류의 채널 키가 있어야 하는데, 그 표를 들고 있는
것은 `tests` 모듈이다.

**모듈의 `services` 를 부르지 않는다**(경계 검사). 모델을 읽는 것은 그 모듈의
로직이 아니라 저장소 조회이므로 `shared` 에 둔다 — `curvedata` 가 파케이를 읽는
것과 같은 자리다.

## 왜 키만으로 거르면 안 되나

`applies_to=("dma_sweep",)` 는 **키**를 본다. 부서가 자기 DMA 종류를 만들면(정의는
데이터다) 키가 달라서 DMA 단계와 Prony 묶음이 목록에서 사라진다. 막히는 것이 아니라
**안 보이는** 것이라 사람은 「이 기능이 없구나」 로 읽는다. 실측(2026-08-31): 운영에
`dma_sweep` 이 없을 수 있다는 것을 사람이 먼저 물었다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import TestChannel, TestType


def channels_of(db: Session, key: str | None) -> list[str] | None:
    """그 시험 종류의 채널 키. 종류를 못 찾으면 `None`.

    **빈 목록과 `None` 은 다르다.** 빈 목록은 「채널이 없는 종류」 이고 `None` 은
    「무슨 종류인지 모른다」 이다 — 뒤쪽에서는 채널로 거르는 판단 자체를 하면 안 된다.
    """
    if not key:
        return None
    found = db.scalar(select(TestType).where(TestType.key == key))
    if found is None:
        return None
    return list(
        db.scalars(select(TestChannel.key).where(TestChannel.test_type_id == found.id))
    )


def channels_by_key(db: Session) -> dict[str, list[str]]:
    """모든 시험 종류의 채널. **한 번에 읽는다** — 종류마다 조회하면 N+1 이다."""
    rows = db.execute(
        select(TestType.key, TestChannel.key).join(
            TestChannel, TestChannel.test_type_id == TestType.id
        )
    )
    found: dict[str, list[str]] = {}
    for type_key, channel_key in rows:
        found.setdefault(str(type_key), []).append(str(channel_key))
    # 채널이 하나도 없는 종류도 목록에는 있어야 한다 — 없으면 「모르는 종류」 로
    # 취급되어 채널 판별을 건너뛴다.
    for type_key in db.scalars(select(TestType.key)):
        found.setdefault(str(type_key), [])
    return found
