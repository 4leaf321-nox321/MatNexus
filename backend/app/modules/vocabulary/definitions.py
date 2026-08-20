"""기본 어휘 축.

**축은 데이터가 아니라 스키마에 가깝다.** 축이 하나 늘어난다는 것은 어딘가의
컬럼이 어휘를 가리키게 된다는 뜻이고, 그건 코드가 바뀌는 일이다. 그래서 API 로
만들지 않고 여기 적는다 — 시험 종류의 `BUILTIN_TEST_TYPES` 와 같은 자리다.

마이그레이션도 같은 것을 심지만 거기 있는 것은 **그때의 스냅샷**이다. 이 파일은
새 DB(테스트·개발 초기화)를 위한 것이라 둘 다 필요하다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import Vocabulary

#: (slug, label, entry_policy, sort_order)
#:
#: `open` 은 사용자가 피커에서 즉석 추가할 수 있다. `closed` 는 관리자가 등록한
#: 값만 고른다 — 미리 정해야 하는 분류다.
BUILTIN_VOCABULARIES: list[tuple[str, str, str, int]] = [
    ("manufacturer", "제조사", "open", 10),
]


def ensure_builtin_vocabularies(db: Session) -> list[str]:
    """기본 축을 보장한다. 새로 만든 것의 slug 를 돌려준다.

    **이미 있는 축은 손대지 않는다.** 운영 중에 관리자가 라벨이나 정책을 바꿨을
    수 있고, 그것을 배포가 되돌리면 안 된다(시험 종류와 같은 판단).
    """
    existing = set(db.scalars(select(Vocabulary.slug)))
    created: list[str] = []
    for slug, label, policy, order in BUILTIN_VOCABULARIES:
        if slug in existing:
            continue
        db.add(
            Vocabulary(slug=slug, label=label, entry_policy=policy, sort_order=order)
        )
        created.append(slug)
    if created:
        db.flush()
    return created
