"""어휘를 찾고 만든다 — **게이트가 하나여야 한다.**

값이 만들어지는 경로가 여럿이면(단건 폼·일괄 등록·이관 스크립트) 그 경로마다
중복 판정이 갈린다. 그래서 모두 `resolve_or_create` 하나를 지난다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.materials.models import Sample
from app.modules.vocabulary.models import Vocabulary, VocabularyAlias, VocabularyTerm
from app.modules.vocabulary.normalize import clean, compare_key
from app.shared.errors import AppError, NotFound


def get_vocabulary(db: Session, slug: str) -> Vocabulary:
    found = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
    if found is None:
        raise NotFound("MNX-VOCABULARY-0001", f"어휘를 찾을 수 없습니다: {slug}")
    return found


def resolve(db: Session, vocabulary: Vocabulary, value: str) -> VocabularyTerm | None:
    """이미 있는 값인가. **정규 값과 별칭을 모두 본다.**

    별칭까지 보는 것이 요점이다. `'포스코(주)'` 가 `'포스코'` 의 별칭으로 등록돼
    있으면 새 값을 안 만들고 `'포스코'` 를 돌려준다 — 사후에 합치는 것보다 싸고,
    사용자는 중복을 만들려 했다는 사실조차 모른다.
    """
    key = compare_key(value)
    if not key:
        return None

    found = db.scalar(
        select(VocabularyTerm).where(
            VocabularyTerm.vocabulary_id == vocabulary.id,
            VocabularyTerm.normalized == key,
        )
    )
    if found is not None:
        return found

    alias = db.scalar(
        select(VocabularyAlias).where(
            VocabularyAlias.vocabulary_id == vocabulary.id,
            VocabularyAlias.normalized == key,
        )
    )
    return db.get(VocabularyTerm, alias.term_id) if alias else None


def resolve_or_create(
    db: Session,
    vocabulary: Vocabulary,
    value: str | None,
    *,
    created_by_id: uuid.UUID | None = None,
) -> VocabularyTerm | None:
    """값 하나를 어휘로 바꾼다. **순서가 중요하다.**

    1. 기존 값·별칭으로 찾아지면 **그것을 돌려준다.** 409 를 내지 않는다 —
       피커가 낙관적으로 보내도 정규 행이 돌아와야 화면이 안 멈춘다.
    2. `closed` 축이면 사용자 추가를 막는다.
    3. 만든다. **승인 대기 상태는 없다**(모델 주석 참고).

    비어 있으면 `None`. 값을 지운 것과 안 건드린 것은 호출부가 구분한다.
    """
    cleaned = clean(value)
    if cleaned is None:
        return None

    found = resolve(db, vocabulary, cleaned)
    if found is not None:
        return found

    if vocabulary.entry_policy == "closed":
        raise AppError(
            "MNX-VOCABULARY-0002",
            f"'{vocabulary.label}' 은(는) 관리자가 등록한 값만 고를 수 있습니다. "
            f"'{cleaned}' 는 목록에 없습니다.",
            status=422,
        )

    term = VocabularyTerm(
        vocabulary_id=vocabulary.id,
        value=cleaned,
        normalized=compare_key(cleaned),
        created_by_id=created_by_id,
    )
    db.add(term)
    db.flush()  # 같은 요청 안에서 뒤이어 참조할 수 있게
    return term


def search(
    db: Session,
    vocabulary: Vocabulary,
    *,
    q: str | None,
    limit: int,
    include_hidden: bool = False,
) -> list[VocabularyTerm]:
    """피커가 부르는 검색. **별칭으로도 찾힌다.**

    `'포스코(주)'` 를 쳤는데 `'포스코'` 가 나오는 것이 정상이다 — 화면이 그
    결과를 다시 거르면 안 되는 이유가 이것이다.
    """
    query: Select[tuple[VocabularyTerm]] = select(VocabularyTerm).where(
        VocabularyTerm.vocabulary_id == vocabulary.id
    )
    # 피커는 활성만 본다. 관리 화면은 감춘 것도 봐야 한다 — **되돌릴 길이 없으면
    # 감추기도 막다른 길이다.**
    if not include_hidden:
        query = query.where(VocabularyTerm.status == "active")
    key = compare_key(q)
    if key:
        by_alias = select(VocabularyAlias.term_id).where(
            VocabularyAlias.vocabulary_id == vocabulary.id,
            VocabularyAlias.normalized.ilike(f"%{key}%"),
        )
        query = query.where(
            or_(
                VocabularyTerm.normalized.ilike(f"%{key}%"),
                VocabularyTerm.id.in_(by_alias),
            )
        )
    # 많이 쓰이는 것이 위로. 검색이 붙어 있으므로 가나다순보다 이쪽이 쓸모 있다.
    query = query.order_by(VocabularyTerm.usage_count.desc(), VocabularyTerm.value)
    return list(db.scalars(query.limit(limit)))


def bump_usage(db: Session, term_id: uuid.UUID | None, delta: int) -> None:
    """`usage_count` 를 옮긴다. **참조가 바뀌는 자리에서 부른다.**

    매번 `count(join)` 으로 세면 어휘가 커질수록 느려지고, 그 비용이 화면을 열
    때마다 든다. 캐시가 어긋나면 재계산하면 되지만 — 어긋난 채로 오래 두면
    "쓰이지 않는 값" 이 피커에 남는다.
    """
    if term_id is None:
        return
    db.execute(
        update(VocabularyTerm)
        .where(VocabularyTerm.id == term_id)
        .values(usage_count=func.greatest(VocabularyTerm.usage_count + delta, 0))
    )


def rename(db: Session, term: VocabularyTerm, value: str) -> None:
    """값의 표기를 바꾼다. **가리키는 쪽도 함께 맞춘다.**

    외래키라서 참조는 저절로 따라온다. 그런데 지금은 Expand 단계라 쓰는 쪽이
    문자열 컬럼도 들고 있고(`samples.manufacturer`), 화면은 그쪽을 읽는다 —
    안 맞추면 어휘와 화면이 어긋난다.

    Contract 단계에서 문자열을 지우면 이 함수의 절반이 사라진다.
    """
    cleaned = clean(value)
    if cleaned is None:
        raise AppError("MNX-VOCABULARY-0003", "값이 비어 있습니다.", status=422)

    key = compare_key(cleaned)
    if key != term.normalized:
        clash = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == term.vocabulary_id,
                VocabularyTerm.normalized == key,
                VocabularyTerm.id != term.id,
            )
        )
        if clash is not None:
            # **말없이 합치지 않는다.** 두 값을 하나로 만드는 것은 병합이고,
            # 그건 어느 쪽이 살아남는지·참조를 어떻게 옮길지를 정해야 하는 일이다.
            raise AppError(
                "MNX-VOCABULARY-0005",
                f"'{clash.value}' 가 이미 있습니다. 합치려면 병합을 쓰세요.",
                status=409,
            )

    old_value = term.value
    term.value = cleaned
    term.normalized = key

    # Expand 단계의 문자열 컬럼 맞추기. 축이 늘어나면 여기도 늘어난다 —
    # Contract 에서 통째로 사라질 코드다.
    slug = db.scalar(select(Vocabulary.slug).where(Vocabulary.id == term.vocabulary_id))
    if slug == "manufacturer" and old_value != cleaned:
        db.execute(
            update(Sample)
            .where(Sample.manufacturer_term_id == term.id)
            .values(manufacturer=cleaned)
        )


def recount(db: Session, vocabulary: Vocabulary) -> int:
    """`usage_count` 를 다시 센다. 고친 값 수를 돌려준다.

    **캐시는 어긋난다.** 참조가 생기고 사라지는 자리를 하나라도 빠뜨리면 그때부터
    조용히 벌어지고, 벌어진 캐시는 피커 정렬과 "쓰는 곳 N건" 을 거짓말로 만든다.
    실제로 개발 중에 생성 경로의 증가를 늦게 붙여 3 대 5 로 벌어졌다.

    그래서 **고칠 길을 함께 둔다.** 매번 세지 않는 이유는 성능이고(ADR 0010),
    성능 때문에 둔 캐시라면 틀렸을 때 바로잡는 버튼이 있어야 한다.

    지운 시료는 안 센다 — 피커의 "쓰는 곳" 은 지금 쓰이는 수다.
    """
    slug = vocabulary.slug
    if slug != "manufacturer":
        # 축이 늘어나면 여기도 늘어난다. 참조하는 컬럼이 축마다 다르므로
        # 자동으로 못 한다 — Contract 뒤에는 한 줄씩 이 표에 적힌다.
        return 0

    db.execute(
        update(VocabularyTerm)
        .where(VocabularyTerm.vocabulary_id == vocabulary.id)
        .values(
            usage_count=(
                select(func.count())
                .select_from(Sample)
                .where(
                    Sample.manufacturer_term_id == VocabularyTerm.id,
                    Sample.deleted_at.is_(None),
                )
                .scalar_subquery()
            )
        )
    )
    return int(
        db.scalar(
            select(func.count()).select_from(
                select(VocabularyTerm)
                .where(VocabularyTerm.vocabulary_id == vocabulary.id)
                .subquery()
            )
        )
        or 0
    )
