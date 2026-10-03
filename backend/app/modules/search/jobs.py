"""검색 색인 작업 — **저장 요청 안에서 임베딩하지 않는다.**

핸드북 한 절을 저장할 때 임베딩 왕복(수백 ms)을 요청 안에 끼우면, 글 쓰는 사람이
그 대가를 매번 치른다. 워커가 뒤에서 한다.

주기 작업이기도 하다. 절이 바뀌었는데 색인이 옛 글이면 **검색이 옛 답을 준다** —
그것은 틀렸다는 신호가 어디에도 안 남는 종류의 오류다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import handlers, kinds
from app.shared import embeddings, semantic

logger = logging.getLogger(__name__)


@handlers.handler(kinds.SEARCH_REINDEX)
def reindex(db: Session, payload: dict[str, Any]) -> None:
    """산문을 다시 색인한다.

    **꺼져 있으면 조용히 넘어간다.** 임베딩 백엔드가 `off` 인 것은 고장이 아니라
    설정이고, 실패로 쌓이면 진짜 실패가 묻힌다.
    """
    if not embeddings.enabled():
        logger.info("의미 검색이 꺼져 있습니다 — 색인을 건너뜁니다.")
        return
    try:
        counted = semantic.reindex(db)
        logger.info(
            "색인 완료: 조각 %s개 · 정리 %s개", counted.get("chunks"), counted.get("removed")
        )
    except embeddings.EmbeddingError as failed:
        # 엔진이 잠깐 죽은 것과 설정이 꺼진 것은 다르다 — 이쪽은 재시도할 값이 있다.
        logger.warning("색인 실패: %s", failed)
        raise


@handlers.handler(kinds.SEARCH_INDEX_MATERIALS)
def index_materials(db: Session, payload: dict[str, Any]) -> None:
    """재료 몇 개만 다시 색인한다 — 저장 뒤 곧바로 뜻으로 걸리게(2026-09-29).

    꺼져 있으면 조용히 넘어간다(위와 같은 이유). 실패는 던진다 — 한 번만 돌고, 못 채운 것은
    밤의 전체 색인이 채운다.
    """
    if not embeddings.enabled():
        return
    ids = [str(one) for one in payload.get("material_ids") or []]
    counted = semantic.reindex_materials(db, ids)
    logger.info(
        "재료 색인: %s건 · 조각 %s개 · 정리 %s개",
        len(ids),
        counted.get("chunks"),
        counted.get("removed"),
    )


@handlers.handler(kinds.SEARCH_INDEX_GUIDE)
def index_guide_sections(db: Session, payload: dict[str, Any]) -> None:
    """핸드북 절 몇 개만 다시 색인한다 — 고친 뒤 곧바로 뜻으로 걸리게(2026-10-03).

    재료와 같은 규칙: 꺼져 있으면 넘어가고, 실패는 던진다(못 채운 것은 밤의 전체 색인이
    채운다).
    """
    if not embeddings.enabled():
        return
    ids = [str(one) for one in payload.get("section_ids") or []]
    counted = semantic.reindex_guide_sections(db, ids)
    logger.info(
        "핸드북 절 색인: %s건 · 조각 %s개 · 정리 %s개",
        len(ids),
        counted.get("chunks"),
        counted.get("removed"),
    )
