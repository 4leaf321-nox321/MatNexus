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
    # **유통사와 주 벤더가 한 축을 공유한다.** 같은 회사가 어떤 로트에서는
    # 유통사고 다른 로트에서는 주 벤더다. 축을 나누면 같은 회사가 두 목록에
    # 따로 쌓이고, 그 둘을 합칠 방법도 없다.
    ("vendor", "거래처", "open", 20),
    ("sales_type", "판매 유형", "open", 30),
    ("specimen_standard", "시편 규격", "open", 40),
    ("instrument", "장비", "open", 50),
    # **가장 큰 축이고 이득도 가장 크다.** 지금은 SECC/secc/S.E.C.C 가 서로
    # 다른 재료 셋을 만든다. 다만 강종은 재료 이름을 만드는 값이라(ADR 0004)
    # 값 이름을 고치면 재료·시료·시편·시험 이름이 전부 따라 바뀐다.
    ("grade", "강종", "open", 5),
]

#: **전부 `open` 이다.** `closed` 는 만들어 두고 안 켠다.
#:
#: 막았을 때 사람이 어디로 가는지가 문제다. 첫 발포재를 등록하려는데 `Foam` 이
#: 목록에 없으면 관리자를 찾아가거나 — 더 흔하게는 **`Metal` 로 대충 고르고
#: 넘어간다.** 그러면 분류가 지켜진 것이 아니라 조용히 틀린 것이다.
#:
#: `closed` 가 값을 하는 자리는 **외부 시스템이 정본을 주는 축**이다(ReportArchive
#: 는 모델·BOM 코드에 쓴다). 거기서는 정본에 없는 값을 만드는 것 자체가 오류다.
#: MatNexus 에는 아직 그런 축이 없다 — 모든 값을 사람이 친다. Phase 6 에서 장비
#: 커넥터가 붙으면 그때 켠다.


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
        db.add(Vocabulary(slug=slug, label=label, entry_policy=policy, sort_order=order))
        created.append(slug)
    if created:
        db.flush()
    return created
