"""정의의 key — **전사에서 하나다**(ADR 0035).

장비 파일 정의(형식 프로파일)·처리 레시피·해석용 물성 정의 셋이 같은 규칙을 쓴다.

## 왜 전사에서 하나인가

전에는 부서 안에서만 하나였다 — 같은 인장이라도 부서마다 따르는 규격이 다르니
`tensile_standard` 를 각자 쓰라는 뜻이었다. 그 규칙은 「남의 부서 것은 안 보인다」
위에 서 있었다. 보기를 전원에게 열자(ADR 0035) 같은 key 가 둘 이상 보이고, key 로
하나를 집는 조회(`/formats/{key}` · `/recipes/{key}` · 덱 형식)가 그중 **아무거나**
집게 된다. 부서를 보고 골라 주던 조건이 사라졌기 때문이다.

## 왜 서버가 짓나

사람에게 key 를 받으면 전사에서 하나라는 규칙이 곧 「옆 부서가 먼저 쓴 이름은 못
쓴다」 가 된다 — 자기와 상관없는 이유로 409 를 본다. 사람이 읽는 것은 이름(label)
이고 key 는 주소다. 그래서 비워 두면 서버가 `fmt_1a2b3c4d` 처럼 짓는다.

key 를 **주는** 길은 남긴다. 파일로 옮겨 오는 정의(개발 서버 → 운영)는 같은 key 로
들어와야 두 번 들여올 때 409 로 막힌다 — 새로 지으면 같은 것이 조용히 둘 생긴다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import ExportProfile
from app.modules.processing.models import ProcessingRecipe
from app.modules.tests.models import FormatProfile
from app.shared.errors import Conflict

Definition = type[FormatProfile] | type[ProcessingRecipe] | type[ExportProfile]

#: 지은 key 의 뒷부분 — 16진 8자리(약 43억 가지). 몇천 건에서 부딪힐 일은 없지만,
#: 부딪히면 다시 짓는다.
_SUFFIX = 8
_TRIES = 5


def resolve(
    db: Session,
    model: Definition,
    requested: str | None,
    *,
    prefix: str,
    what: str,
    code: str,
) -> str:
    """만들 정의의 key. 안 줬으면 짓고, 줬으면 비어 있는지 본다."""
    if requested is None:
        return _generate(db, model, prefix)
    holder = db.scalar(
        select(model.label).where(model.key == requested, model.deleted_at.is_(None))
    )
    if holder is not None:
        # **누가 쓰고 있는지 말한다.** 「이미 있다」 만 적으면 사람은 목록을 뒤져야
        # 하고, 그 목록에서 key 는 작은 회색 글씨다.
        raise Conflict(
            code,
            f"이미 있는 {what}입니다: {requested} ({holder}). "
            f"key 는 전사에서 하나입니다 — 비워 두면 서버가 짓습니다.",
        )
    return requested


def _generate(db: Session, model: Definition, prefix: str) -> str:
    """안 쓰인 key 하나. **지운 것까지 센다** — 휴지통에서 되살릴 때 부딪히지 않게."""
    for _ in range(_TRIES):
        candidate = f"{prefix}_{uuid.uuid4().hex[:_SUFFIX]}"
        if db.scalar(select(model.id).where(model.key == candidate)) is None:
            return candidate
    # 다섯 번 연속으로 부딪히면 우연이 아니다 — 조용히 넘기지 않는다.
    raise RuntimeError(f"{model.__tablename__} 의 key 를 짓지 못했습니다")
