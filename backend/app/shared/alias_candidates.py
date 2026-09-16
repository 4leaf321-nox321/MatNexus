"""별칭 후보 — **못 푼 이름을 쌓는다.** 사전은 쓰다 보면 자란다.

이름 해소(`property_names.resolve`)가 빈손이면 여기 한 줄 남긴다. 같은 말이 다시 오면
횟수만 오른다. 관리자가 후보 목록에서 「이 물성의 별칭으로」 를 누르면 `PropertyAlias`
가 생기고 다음부터 찾힌다 — AI 는 후보를 만들 뿐 사전을 고치지 못한다(2026-09-16,
[계획] 온톨로지 고도화 §2-F).

## 조용히 실패한다

이것은 부수 효과다. 후보를 적다 실패해도 **검색 자체가 실패하면 안 된다** — 검색이
먼저고 기록은 덤이다. 그래서 예외를 삼키고 로그만 남긴다. 트랜잭션도 부르는 쪽 것에
얹지 않고 여기서 따로 commit 한다 — 검색은 읽기라 커밋할 것이 없고, 후보는 남아야 한다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.ontology_models import AliasCandidate
from app.shared.text import compare_key

log = logging.getLogger(__name__)

#: 후보로 남길 최소 길이. 「a」 같은 오타 한 글자는 사전 후보가 아니다.
MIN_LENGTH = 2
#: 저장 길이 상한 — 붙여 넣은 문단이 후보로 들어오지 않게.
MAX_LENGTH = 200

SOURCES = ("search", "resolve", "import")


def record(db: Session, text: str, *, source: str, kind: str = "property") -> None:
    """못 푼 이름 하나. 있으면 횟수를 올리고, 없으면 새로 적는다."""
    cleaned = " ".join(text.split())
    if not (MIN_LENGTH <= len(cleaned) <= MAX_LENGTH):
        return
    normalized = compare_key(cleaned)
    if not normalized:
        return
    try:
        found = db.scalar(
            select(AliasCandidate).where(
                AliasCandidate.kind == kind, AliasCandidate.normalized == normalized
            )
        )
        if found is None:
            db.add(
                AliasCandidate(
                    kind=kind, text=cleaned, normalized=normalized, source=source, count=1
                )
            )
        else:
            # 이미 판정한 말이 다시 와도 횟수는 오른다 — 받아들인 것이면 사전에 있어야
            # 하는데 빈손이라면 별칭이 지워졌거나 다른 종류의 이름이다. 사람이 보게 한다.
            found.count += 1
            found.last_seen_at = datetime.now(UTC)
        db.commit()
    except Exception:
        log.exception("별칭 후보를 적지 못했습니다: %r", cleaned)
        db.rollback()


def open_count(db: Session, *, kind: str = "property") -> int:
    return int(
        db.scalar(
            select(func.count(AliasCandidate.id)).where(
                AliasCandidate.kind == kind, AliasCandidate.status == "open"
            )
        )
        or 0
    )
