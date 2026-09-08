"""전체 검색 API — **한 칸, 세 모드, 열세 종류.**

로직은 없다. 판정은 `shared/entity_search.py`(찾기)와 `shared/graph.py`(권한)에
있고 여기는 HTTP 로 옮기기만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.search.schemas import SearchGroupOut, SearchHitOut, SearchOut
from app.shared import entity_search, relations
from app.shared.auth import current_user
from app.shared.errors import AppError

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, description="찾을 말"),
    mode: str = Query(default="contains", description="`exact` · `contains` · `similar`"),
    kind: list[str] | None = Query(default=None, description="이 종류만 — 주면 더 많이 준다"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SearchOut:
    """**한 칸에 치면 무엇이든 찾는다.**

    사람은 「SECC180」 이 재료인지 시료인지 시험 이름인지 모른 채 친다. 대상은
    온톨로지 종류 전부이고, 안 보이는 것은 결과에도 없다 — **검색에 뜨는데 열면
    404** 가 되면 안 되기 때문이다.

    `similar` 는 오타·표기 흔들림까지 본다(`pg_trgm`). 「비슷한 것」이 「그 말이 든
    것」보다 위에 서지 않도록 점수를 눌러 둔다.
    """
    if mode not in entity_search.MODES:
        raise AppError(
            "MNX-SEARCH-0001",
            f"'{mode}' 는 아는 방식이 아닙니다 — {' · '.join(entity_search.MODES)}.",
            status=422,
        )
    unknown = [one for one in (kind or []) if one not in relations.KINDS]
    if unknown:
        raise AppError(
            "MNX-SEARCH-0002",
            f"모르는 종류입니다: {' · '.join(unknown)}. `GET /api/ontology` 로 목록을 보세요.",
            status=422,
        )

    groups = entity_search.search(db, user, needle=q.strip(), mode=mode, only=kind)
    return SearchOut(
        query=q,
        mode=mode,
        total=sum(len(one.hits) for one in groups),
        groups=[
            SearchGroupOut(
                kind=one.kind,
                label=one.label,
                module=one.module,
                truncated=one.truncated,
                hits=[
                    SearchHitOut(
                        kind=hit.kind,
                        id=hit.id,
                        name=hit.name,
                        score=round(hit.score, 4),
                        matched=hit.matched,
                        parent_kind=hit.parent_kind,
                        parent_id=hit.parent_id,
                    )
                    for hit in one.hits
                ],
            )
            for one in groups
        ],
    )
