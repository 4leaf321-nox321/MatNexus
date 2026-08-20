"""어휘를 찾고 만든다 — **게이트가 하나여야 한다.**

값이 만들어지는 경로가 여럿이면(단건 폼·일괄 등록·이관 스크립트) 그 경로마다
중복 판정이 갈린다. 그래서 모두 `resolve_or_create` 하나를 지난다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select, text, update
from sqlalchemy.orm import Session

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
    least_used: bool = False,
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
    if least_used:
        # **검토할 것을 위로.** 오타는 늘 `쓰는 곳 1` 로 생기는데, 기본 정렬
        # (많이 쓰는 순)에서는 목록 끝에 묻힌다.
        #
        # `closed` 정책 대신 두는 장치다. 앞에서 막으면 사람이 대충 고르고
        # 넘어가지만, 뒤에서 보이게 하면 관리자가 실제 오염만 골라 낸다.
        query = query.order_by(VocabularyTerm.usage_count, VocabularyTerm.value)
    else:
        # 많이 쓰이는 것이 위로. 검색이 붙어 있으므로 가나다순보다 낫다.
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

    if old_value == cleaned:
        return

    # **Expand 단계의 문자열 컬럼 맞추기.**
    #
    # 외래키라서 참조는 저절로 따라오는데, 지금은 쓰는 쪽이 문자열 컬럼도 들고
    # 있고 화면은 그쪽을 읽는다. 안 맞추면 어휘와 화면이 어긋난다.
    #
    # 바인딩 표를 훑는다 — 축을 더할 때 이 함수를 안 고쳐도 되게. Contract 에서
    # 문자열을 지우면 이 블록이 통째로 사라진다.
    slug = db.scalar(select(Vocabulary.slug).where(Vocabulary.id == term.vocabulary_id))
    for table, bindings, _deleted in _COUNT_SOURCES:
        for binding in bindings:
            if binding.slug != slug:
                continue
            db.execute(
                text(
                    f"UPDATE {table} SET {binding.field} = :value"
                    f" WHERE {binding.column} = :term_id"
                ),
                {"value": cleaned, "term_id": term.id},
            )
    db.expire_all()


def recount(db: Session, vocabulary: Vocabulary) -> None:
    """`usage_count` 를 다시 센다.

    **캐시는 어긋난다.** 참조가 생기고 사라지는 자리를 하나라도 빠뜨리면 그때부터
    조용히 벌어지고, 벌어진 캐시는 피커 정렬과 "쓰는 곳 N건" 을 거짓말로 만든다.
    실제로 개발 중에 생성 경로의 증가를 늦게 붙여 3 대 5 로 벌어졌다.

    매번 세지 않는 이유는 성능이고(ADR 0010), **성능 때문에 둔 캐시라면 틀렸을
    때 바로잡는 버튼이 있어야 한다.**

    한 축을 **여러 컬럼이 가리킬 수 있다**(거래처 = 유통사 + 주 벤더). 그래서
    바인딩 표를 훑어 합산한다 — 축을 더할 때 이 함수를 안 고쳐도 되게.

    지운 행은 안 센다 — "쓰는 곳" 은 지금 쓰이는 수다.
    """
    parts = [
        f"(SELECT count(*) FROM {table} WHERE {binding.column} = vocabulary_terms.id{deleted})"
        for table, bindings, deleted in _COUNT_SOURCES
        for binding in bindings
        if binding.slug == vocabulary.slug
    ]
    if not parts:
        return
    db.execute(
        text(
            f"UPDATE vocabulary_terms SET usage_count = {' + '.join(parts)}"
            f" WHERE vocabulary_id = :vid"
        ),
        {"vid": vocabulary.id},
    )
    # **원시 SQL 은 ORM 을 우회한다.** 세션이 들고 있던 객체는 옛 값을 그대로
    # 갖고 있어서, 바로 뒤에 읽으면 고치기 전 숫자가 나온다(테스트가 잡았다).
    db.expire_all()


@dataclass(frozen=True)
class Binding:
    """어휘를 가리키는 컬럼 하나. **축이 늘어나도 코드가 안 늘어나게.**

    라우트마다 "resolve 하고 문자열 채우고 FK 채우고 usage 증감" 을 베껴 쓰면
    축 열 개에 같은 코드가 열 벌 생기고, 그중 하나만 고쳐지는 날이 온다 —
    시료 폼이 갈렸던 것과 같은 실패다.
    """

    slug: str
    """어느 축인가."""
    field: str
    """요청·모델의 문자열 필드 이름(`manufacturer`)."""
    column: str
    """FK 컬럼 이름(`manufacturer_term_id`)."""


#: 표별 바인딩. **여기 한 줄을 더하면 저장·수정·집계가 함께 따라온다.**
SAMPLE_BINDINGS = (
    Binding("manufacturer", "manufacturer", "manufacturer_term_id"),
    # 유통사와 주 벤더가 **한 축**을 공유한다 — 같은 회사가 로트에 따라 둘 중
    # 어느 쪽도 된다.
    Binding("vendor", "distributor", "distributor_term_id"),
    Binding("vendor", "primary_vendor", "primary_vendor_term_id"),
    Binding("sales_type", "sales_type", "sales_type_term_id"),
)
SPECIMEN_BINDINGS = (Binding("specimen_standard", "standard", "standard_term_id"),)
TEST_RUN_BINDINGS = (Binding("instrument", "instrument", "instrument_term_id"),)


def apply_bindings(
    db: Session,
    row: object,
    bindings: Iterable[Binding],
    values: Mapping[str, str | None],
    *,
    created_by_id: uuid.UUID | None = None,
) -> None:
    """주어진 값들을 어휘로 바꿔 행에 넣는다. **`usage_count` 도 여기서 옮긴다.**

    `values` 에 없는 필드는 안 건드린다 — 수정에서 "안 보낸 것" 과 "지운 것" 을
    구분해야 한다.

    문자열 컬럼도 함께 채운다. 아직 Expand 단계라 읽는 쪽이 문자열을 본다;
    Contract 에서 그 줄만 지우면 된다.
    """
    for binding in bindings:
        if binding.field not in values:
            continue
        bump_usage(db, getattr(row, binding.column), -1)
        term = resolve_or_create(
            db,
            get_vocabulary(db, binding.slug),
            values[binding.field],
            created_by_id=created_by_id,
        )
        setattr(row, binding.field, term.value if term else None)
        setattr(row, binding.column, term.id if term else None)
        bump_usage(db, term.id if term else None, 1)


def release_bindings(db: Session, row: object, bindings: Iterable[Binding]) -> None:
    """행이 사라질 때 `usage_count` 를 되돌린다.

    안 빼면 피커에 "쓰이지 않는 값" 이 남고, 관리 화면의 '쓰는 곳' 이 거짓말을
    한다.
    """
    for binding in bindings:
        bump_usage(db, getattr(row, binding.column), -1)


#: 어느 표의 어느 바인딩을 세는가. **소프트 삭제된 행은 빼야 한다** — 지운 시료가
#: 어휘를 붙들고 있으면 "쓰는 곳" 이 실제보다 커진다.
_COUNT_SOURCES: tuple[tuple[str, tuple[Binding, ...], str], ...] = (
    ("samples", SAMPLE_BINDINGS, " AND deleted_at IS NULL"),
    ("specimens", SPECIMEN_BINDINGS, " AND deleted_at IS NULL"),
    ("test_runs", TEST_RUN_BINDINGS, " AND deleted_at IS NULL"),
)
