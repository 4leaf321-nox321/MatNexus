"""전체 검색 API — **한 칸, 세 모드, 열세 종류.**

로직은 없다. 판정은 `shared/entity_search.py`(찾기)와 `shared/graph.py`(권한)에
있고 여기는 HTTP 로 옮기기만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs import kinds, queue
from app.jobs.models import Job
from app.modules.accounts.models import User
from app.modules.search.schemas import (
    SearchGroupOut,
    SearchHitOut,
    SearchOut,
    SemanticReindexOut,
    SemanticStatusOut,
)
from app.shared import embeddings, entity_search, relations, semantic
from app.shared.auth import current_user, require_system_admin
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

    **의미 검색이 켜져 있으면** `similar` 에 뜻이 가까운 것까지 얹힌다(RRF 융합).
    응답의 `meaning` 이 그것을 말한다 — 꺼져 있어도 검색은 그대로 돈다.
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
        meaning=mode == "similar" and semantic.available(db),
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


# --- 의미 검색 현황 ---------------------------------------------------------------


def _indexing(db: Session) -> bool:
    """색인 작업이 큐에 있거나 도는 중인가 — 「지금 색인」 을 두 번 누르지 않게."""
    found = db.scalar(
        select(Job.id)
        .where(Job.kind == kinds.SEARCH_REINDEX, Job.status.in_(("queued", "running")))
        .limit(1)
    )
    return found is not None


@router.get("/semantic", response_model=SemanticStatusOut)
def semantic_status(
    user: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> SemanticStatusOut:
    """의미 검색이 켜져 있나 — **꺼졌으면 왜, 그리고 무엇을 하면 되나.**

    「비슷」 이 글자만 보고 있는데 화면이 조용하면 사람은 「그런 자료가 없다」 로 읽는다
    (계획서가 「가장 큰 구멍」 이라 적은 자리). 시스템 관리자만 — 모델·차원·경로는
    운영 정보다.
    """
    return SemanticStatusOut(**semantic.stats(db), running=_indexing(db))


@router.post("/semantic/reindex", response_model=SemanticReindexOut, status_code=202)
def semantic_reindex(
    user: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> SemanticReindexOut:
    """산문을 전부 다시 색인한다 — **워커가 뒤에서.**

    요청 안에서 돌리면 조각 수천 개의 임베딩 왕복을 누른 사람이 기다린다(그리고 프록시가
    먼저 끊는다). 모델·차원이 바뀌었으면 작업이 표를 다시 만들고 채운다.
    """
    if not embeddings.enabled():
        raise AppError(
            "MNX-SEARCH-0003",
            "임베딩 엔진이 꺼져 있습니다 — `EMBEDDING_BACKEND` 를 켜고 다시 띄우세요.",
            status=409,
        )
    if _indexing(db):
        raise AppError(
            "MNX-SEARCH-0004",
            "색인이 이미 돌고 있습니다 — 끝나면 현황이 바뀝니다.",
            status=409,
        )
    job = queue.enqueue(db, kind=kinds.SEARCH_REINDEX)
    db.commit()
    return SemanticReindexOut(job_id=job.id, chunks=int(semantic.stats(db)["chunks"]))
