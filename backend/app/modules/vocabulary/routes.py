"""어휘 API — 피커가 부르는 것.

**전체를 주지 않는다.** 어휘가 수만 개가 되면 브라우저로 다 보낼 수 없고, 보내
봐야 화면은 60개만 그린다. 검색어를 받아 상한을 걸어 돌려준다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.vocabulary import services
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.modules.vocabulary.schemas import (
    TermCreateRequest,
    TermOut,
    TermUpdateRequest,
    VocabularyOut,
)
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, NotFound

router = APIRouter(prefix="/vocabularies", tags=["vocabulary"])

#: 한 번에 돌려주는 최대. 화면이 60개를 그리므로 그보다 조금 넉넉하게.
#: **상한을 서버가 건다** — 화면이 정하게 두면 "전체 주세요" 가 언젠가 온다.
SEARCH_LIMIT = 100


def _term_out(db: Session, item: VocabularyTerm) -> TermOut:
    """값 하나를 응답 모양으로. **한 곳에서만 만든다.**

    네 군데서 손으로 만들고 있었는데, 필드를 하나 더하니 그중 하나를 빠뜨렸다.
    부모 조회도 여기 모아 둔다.
    """
    parent = db.get(VocabularyTerm, item.parent_term_id) if item.parent_term_id else None
    return TermOut(
        id=item.id,
        value=item.value,
        parent_value=parent.value if parent else None,
        usage_count=item.usage_count,
        status=item.status,
    )


@router.get("", response_model=list[VocabularyOut])
def list_vocabularies(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[VocabularyOut]:
    """축 목록. 화면이 '새로 추가' 를 보여 줄지 정하는 데 쓴다."""
    counts: dict[uuid.UUID, int] = {
        vocabulary_id: count
        for vocabulary_id, count in db.execute(
            select(VocabularyTerm.vocabulary_id, func.count())
            .where(VocabularyTerm.status == "active")
            .group_by(VocabularyTerm.vocabulary_id)
        ).all()
    }
    rows = db.scalars(select(Vocabulary).order_by(Vocabulary.sort_order, Vocabulary.slug))
    return [
        VocabularyOut(
            slug=item.slug,
            label=item.label,
            entry_policy=item.entry_policy,
            term_count=counts.get(item.id, 0),
        )
        for item in rows
    ]


@router.get("/{slug}/terms", response_model=list[TermOut])
def search_terms(
    slug: str,
    q: str | None = Query(default=None, description="부분 일치. 별칭으로도 찾는다"),
    limit: int = Query(default=SEARCH_LIMIT, ge=1, le=SEARCH_LIMIT),
    include_hidden: bool = Query(
        default=False, description="감춘 값도 포함. 관리 화면이 쓴다"
    ),
    least_used: bool = Query(
        default=False, description="적게 쓰이는 것부터. 오타를 찾을 때 쓴다"
    ),
    parent_value: str | None = Query(
        default=None,
        description="상위 축의 값으로 좁힌다. 'Steel' 을 주면 그 아래 강종만",
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TermOut]:
    vocabulary = services.get_vocabulary(db, slug)
    found = services.search(
        db,
        vocabulary,
        q=q,
        limit=limit,
        include_hidden=include_hidden,
        least_used=least_used,
        # 값이 아니라 **표기**를 받는다 — 화면은 id 를 모르고 사람이 고른 글자만
        # 안다. 상위 축에서 그 표기를 찾는 것은 서버의 일이다.
        parent=services.parent_of(db, vocabulary, parent_value),
    )
    return [_term_out(db, item) for item in found]


@router.post("/{slug}/terms", response_model=TermOut, status_code=201)
def create_term(
    slug: str,
    payload: TermCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TermOut:
    """값을 더한다. **이미 있으면 그것을 돌려준다** — 409 가 아니다.

    피커는 사람이 엔터를 치는 순간 낙관적으로 보낸다. 그때 409 를 주면 화면이
    오류를 그려야 하는데, 실제로 일어난 일은 "이미 있는 값을 골랐다" 뿐이다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    term = services.resolve_or_create(
        db,
        vocabulary,
        payload.value,
        created_by_id=user.id,
        # **새 값이 부모를 물려받는다.** Steel 을 고른 상태에서 강종을 추가하면
        # 그 아래로 들어간다 — 계층이 쓰면서 저절로 만들어진다.
        parent=services.parent_of(db, vocabulary, payload.parent_value),
    )
    if term is None:
        # `clean` 이 빈 값으로 만든 경우 — 공백만 친 것이다.
        raise AppError("MNX-VOCABULARY-0003", "값이 비어 있습니다.", status=422)
    db.commit()
    db.refresh(term)
    return _term_out(db, term)


@router.patch("/{slug}/terms/{term_id}", response_model=TermOut)
def update_term(
    slug: str,
    term_id: uuid.UUID,
    payload: TermUpdateRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TermOut:
    """값의 표기를 고치거나 감춘다. **관리자만.**

    ## 이름을 고치면 가리키던 것이 전부 따라온다

    외래키라서 그렇다(ADR 0010). `'포스코'` 를 `'포스코(주)'` 로 고치면 그 값을
    가리키는 시료 수천 건이 한 행 수정으로 함께 바뀐다 — 문자열이었으면 전 행을
    훑어야 했다.

    다만 **아직 Expand 단계**라 문자열 컬럼도 함께 들고 있다. 그쪽도 맞춰
    준다 — 안 하면 화면(문자열을 읽는다)과 어휘가 어긋난다.

    ## 지우지 않고 감춘다

    `deprecated` 는 피커에서만 사라진다. 지우면 그 시료가 어느 제조사였는지 알
    수 없게 되는데, 그건 오타를 고치는 것과 전혀 다른 일이다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    term = db.get(VocabularyTerm, term_id)
    if term is None or term.vocabulary_id != vocabulary.id:
        raise NotFound("MNX-VOCABULARY-0004", "값을 찾을 수 없습니다.")

    data = payload.model_dump(exclude_unset=True)
    if "value" in data:
        services.rename(db, term, data["value"])
    if "status" in data:
        term.status = data["status"]

    db.commit()
    db.refresh(term)
    return _term_out(db, term)


@router.post("/{slug}/recount", response_model=list[TermOut])
def recount_terms(
    slug: str,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[TermOut]:
    """`쓰는 곳` 을 다시 센다. **캐시가 어긋났을 때 고치는 자리.**

    평소에는 참조가 바뀌는 지점에서 증감한다(그래야 화면을 열 때마다 전체를
    세지 않는다). 그 지점을 하나 빠뜨리면 조용히 벌어지므로, 바로잡는 길을
    함께 둔다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    services.recount(db, vocabulary)
    db.commit()
    found = services.search(db, vocabulary, q=None, limit=SEARCH_LIMIT, include_hidden=True)
    return [_term_out(db, item) for item in found]
