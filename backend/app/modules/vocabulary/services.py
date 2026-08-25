"""기준정보를 찾고 만든다 — **게이트가 하나여야 한다.**

값이 만들어지는 경로가 여럿이면(단건 폼·일괄 등록·이관 스크립트) 그 경로마다
중복 판정이 갈린다. 그래서 모두 `resolve_or_create` 하나를 지난다.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Select, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import (
    SpecimenField,
    Vocabulary,
    VocabularyAlias,
    VocabularyDismissal,
    VocabularyDriftCheck,
    VocabularyMerge,
    VocabularyTerm,
)
from app.shared import vocabulary_hooks
from app.shared.errors import AppError, NotFound
from app.shared.text import clean, compare_key
from matcore import units as unit_kit

logger = logging.getLogger(__name__)


def get_vocabulary(db: Session, slug: str) -> Vocabulary:
    found = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
    if found is None:
        raise NotFound("MNX-VOCABULARY-0001", f"기준정보를 찾을 수 없습니다: {slug}")
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


def parent_of(db: Session, vocabulary: Vocabulary, value: str | None) -> VocabularyTerm | None:
    """상위 축에서 이 표기를 찾는다. 축에 부모가 없거나 못 찾으면 `None`.

    **부모를 못 찾아도 실패하지 않는다.** 좁히기가 안 될 뿐이고, 값은 그대로
    만들어진다 — 부모를 모르는 값이 있어도 시스템이 멈추면 안 된다.
    """
    if not vocabulary.parent_slug or not value:
        return None
    parent_vocabulary = db.scalar(
        select(Vocabulary).where(Vocabulary.slug == vocabulary.parent_slug)
    )
    return resolve(db, parent_vocabulary, value) if parent_vocabulary else None


def resolve_or_create(
    db: Session,
    vocabulary: Vocabulary,
    value: str | None,
    *,
    created_by_id: uuid.UUID | None = None,
    parent: VocabularyTerm | None = None,
) -> VocabularyTerm | None:
    """값 하나를 기준정보로 바꾼다. **순서가 중요하다.**

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

    # **새 값이 부모를 물려받는다.** Metal/Steel 을 고른 상태에서 `DP980` 을
    # 추가하면 부모가 `Steel` 로 붙는다 — 계층이 쓰면서 저절로 만들어진다.
    # 관리자가 수만 개를 미리 이어 놓을 필요가 없다.
    term = VocabularyTerm(
        vocabulary_id=vocabulary.id,
        value=cleaned,
        normalized=compare_key(cleaned),
        parent_term_id=parent.id if parent else None,
        created_by_id=created_by_id,
    )
    db.add(term)
    db.flush()  # 같은 요청 안에서 뒤이어 참조할 수 있게
    return term


def _filtered(
    db: Session,
    vocabulary: Vocabulary,
    *,
    q: str | None,
    include_hidden: bool,
    parent: VocabularyTerm | None,
) -> Select[tuple[VocabularyTerm]]:
    """거르는 조건만. **목록과 개수가 같은 필터를 써야 한다** — 갈리면 "3건 중
    5건" 같은 것이 나온다."""
    query: Select[tuple[VocabularyTerm]] = select(VocabularyTerm).where(
        VocabularyTerm.vocabulary_id == vocabulary.id
    )
    # 피커는 활성만 본다. 관리 화면은 감춘 것도 봐야 한다 — **되돌릴 길이 없으면
    # 감추기도 막다른 길이다.**
    if not include_hidden:
        query = query.where(VocabularyTerm.status == "active")
    if parent is not None:
        # **부모로 좁힌다.** Grade 가 수만 개일 때 Steel 을 골랐으면 후보가 수천으로
        # 줄어야 한다 — 규모에서 가장 큰 이득이다.
        #
        # 부모가 안 붙은 값도 함께 보여 준다. 계층은 쓰면서 채워지므로 초기에는
        # 대부분 비어 있고, 그것들을 감추면 아무것도 안 보인다.
        query = query.where(
            or_(
                VocabularyTerm.parent_term_id == parent.id,
                VocabularyTerm.parent_term_id.is_(None),
            )
        )

    key = compare_key(q)
    if key:
        # **`OR` 로 묶으면 인덱스를 못 탄다.**
        #
        # 별칭 가지는 `t` 의 인덱스로 좁힐 수 없어서, `OR` 하나 때문에 값 표
        # 전체를 훑는다(실측 23만 개: 97ms vs 0.4ms). 0단계에서 재료 검색이
        # 같은 이유로 208ms 였다 — 같은 함정을 두 번 밟았다.
        #
        # `UNION` 으로 나누면 **가지마다 자기 trigram 인덱스를 탄다.**
        pattern = f"%{key}%"
        by_value = select(VocabularyTerm.id).where(
            VocabularyTerm.vocabulary_id == vocabulary.id,
            VocabularyTerm.normalized.ilike(pattern),
        )
        by_alias = select(VocabularyAlias.term_id).where(
            VocabularyAlias.vocabulary_id == vocabulary.id,
            VocabularyAlias.normalized.ilike(pattern),
        )
        query = query.where(VocabularyTerm.id.in_(by_value.union(by_alias)))
    return query


def search(
    db: Session,
    vocabulary: Vocabulary,
    *,
    q: str | None,
    limit: int,
    include_hidden: bool = False,
    least_used: bool = False,
    parent: VocabularyTerm | None = None,
    offset: int = 0,
) -> list[VocabularyTerm]:
    """피커가 부르는 검색. **별칭으로도 찾힌다.**

    `'포스코(주)'` 를 쳤는데 `'포스코'` 가 나오는 것이 정상이다 — 화면이 그
    결과를 다시 거르면 안 되는 이유가 이것이다.
    """
    query = _filtered(db, vocabulary, q=q, include_hidden=include_hidden, parent=parent)
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
    return list(db.scalars(query.limit(limit).offset(offset)))


def count(
    db: Session,
    vocabulary: Vocabulary,
    *,
    q: str | None,
    include_hidden: bool = False,
    parent: VocabularyTerm | None = None,
) -> int:
    """같은 조건의 전체 수. **화면이 "몇 건 중 몇 건" 을 말하려면 필요하다.**"""
    query = _filtered(db, vocabulary, q=q, include_hidden=include_hidden, parent=parent)
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def bump_usage(db: Session, term_id: uuid.UUID | None, delta: int) -> None:
    """`usage_count` 를 옮긴다. **참조가 바뀌는 자리에서 부른다.**

    매번 `count(join)` 으로 세면 기준정보가 커질수록 느려지고, 그 비용이 화면을 열
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


def _resync(db: Session) -> None:
    """원시 SQL 뒤에 세션을 맞춘다. **버리기 전에 먼저 쓴다.**

    두 가지가 겹쳐 있어서 순서가 있다.

    1. 원시 SQL 은 ORM 을 우회한다 — 세션이 들고 있던 객체는 옛 값을 그대로
       갖고 있어서 바로 뒤에 읽으면 고치기 전 숫자가 나온다.
    2. 이 세션은 `autoflush=False` 다(`app/database.py`). **아직 안 쓴 변경이
       세션에 남아 있고, `expire_all()` 은 그것을 버린다.**

    그래서 `flush()` 없이 `expire_all()` 만 하면 조용히 지워진다. 실제로 그랬다 —
    기준정보 값 이름을 고치면 재료·시료·시편·시험 이름 넷은 전부 따라 바뀌는데
    **정작 그 값 자신은 옛 표기 그대로**였다. API 는 200 을 냈다. 이름 연쇄만
    보던 시험이 못 잡았고, 어긋남 점검(`drift`)이 개발 DB 에서 2건을 찾아내
    드러났다.
    """
    db.flush()
    db.expire_all()


def rename(db: Session, term: VocabularyTerm, value: str) -> None:
    """값의 표기를 바꾼다. **가리키는 쪽도 함께 맞춘다.**

    외래키라서 참조는 저절로 따라온다. 그런데 지금은 Expand 단계라 쓰는 쪽이
    문자열 컬럼도 들고 있고(`samples.manufacturer`), 화면은 그쪽을 읽는다 —
    안 맞추면 기준정보와 화면이 어긋난다.

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
    # 있고 화면은 그쪽을 읽는다. 안 맞추면 기준정보와 화면이 어긋난다.
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
    _resync(db)

    # **쓰는 쪽이 자기 뒤처리를 한다.** Grade 가 바뀌면 재료 이름을 다시
    # 만들어야 하는데(ADR 0004), 그것을 여기서 하면 기준정보가 재료를 알게 된다.
    vocabulary_hooks.fire_rename(db, slug or "", term.id)


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
        f"(SELECT count(*) FROM {table} WHERE {binding.column} = vocabulary_terms.id"
        f"{deleted.format(t=table)})"
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
    _resync(db)


@dataclass(frozen=True)
class Binding:
    """기준정보를 가리키는 컬럼 하나. **축이 늘어나도 코드가 안 늘어나게.**

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
    parent_field: str | None = None
    """부모가 될 값이 어느 필드에 있는가. `grade` 의 부모는 `category` 다.

    **순서가 중요하다** — 부모가 먼저 해석돼야 자식이 그것을 물려받는다. 그래서
    바인딩 표는 부모부터 적는다."""


#: 표별 바인딩. **여기 한 줄을 더하면 저장·수정·집계가 함께 따라온다.**
#: **부모부터 적는다.** family → category → grade 순으로 해석돼야 자식이 부모를
#: 물려받는다.
MATERIAL_BINDINGS = (
    Binding("family", "family", "family_term_id"),
    Binding("category", "category", "category_term_id", parent_field="family"),
    Binding("grade", "grade", "grade_term_id", parent_field="category"),
    # 용도(적용 제품·부위)는 여기 없다. 재료의 칸이 아니라 `material_uses` 의
    # 줄이라서다(v1.89.0) — 한 재료가 여러 제품에 들어간다. 세는 것과 어긋남
    # 검사는 아래 `_COUNT_SOURCES` 가 그 표를 직접 본다.
)
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
    """주어진 값들을 기준정보로 바꿔 행에 넣는다. **`usage_count` 도 여기서 옮긴다.**

    `values` 에 없는 필드는 안 건드린다 — 수정에서 "안 보낸 것" 과 "지운 것" 을
    구분해야 한다.

    문자열 컬럼도 함께 채운다. 아직 Expand 단계라 읽는 쪽이 문자열을 본다;
    Contract 에서 그 줄만 지우면 된다.
    """
    resolved: dict[str, VocabularyTerm | None] = {}
    for binding in bindings:
        if binding.field not in values:
            # 이 요청이 안 건드린 필드다. 다만 **자식의 부모로는 쓰인다** —
            # Grade 만 고치는 수정에서도 부모(Category)는 행에 있는 값을 봐야 한다.
            if binding.parent_field is None:
                resolved[binding.field] = _term_on(db, row, binding)
            continue

        bump_usage(db, getattr(row, binding.column), -1)
        parent = (resolved.get(binding.parent_field) if binding.parent_field else None) or (
            _parent_on(db, row, bindings, binding)
        )
        term = resolve_or_create(
            db,
            get_vocabulary(db, binding.slug),
            values[binding.field],
            created_by_id=created_by_id,
            parent=parent,
        )
        resolved[binding.field] = term
        setattr(row, binding.field, term.value if term else None)
        setattr(row, binding.column, term.id if term else None)
        bump_usage(db, term.id if term else None, 1)


def _term_on(db: Session, row: object, binding: Binding) -> VocabularyTerm | None:
    """행이 이미 가리키고 있는 값."""
    term_id = getattr(row, binding.column, None)
    return db.get(VocabularyTerm, term_id) if term_id else None


def _parent_on(
    db: Session, row: object, bindings: Iterable[Binding], binding: Binding
) -> VocabularyTerm | None:
    """이 바인딩의 부모를 행에서 찾는다. 이번 요청이 부모를 안 보냈을 때 쓴다."""
    if binding.parent_field is None:
        return None
    for other in bindings:
        if other.field == binding.parent_field:
            return _term_on(db, row, other)
    return None


def release_bindings(db: Session, row: object, bindings: Iterable[Binding]) -> None:
    """행이 사라질 때 `usage_count` 를 되돌린다.

    안 빼면 피커에 "쓰이지 않는 값" 이 남고, 관리 화면의 '쓰는 곳' 이 거짓말을
    한다.
    """
    for binding in bindings:
        bump_usage(db, getattr(row, binding.column), -1)


#: 용도 표를 볼 때 쓰는 바인딩. 축은 줄마다 다르지만(`product`·`part`) 세는
#: 일과 어긋남 검사에는 상관없다 — 둘 다 「문자열이 term 과 같은가」만 본다.
USE_BINDINGS = (Binding("product", "value", "term_id"), Binding("part", "value", "term_id"))

#: 어느 표의 어느 바인딩을 세는가. **소프트 삭제된 행은 빼야 한다** — 지운 시료가
#: 기준정보를 붙들고 있으면 "쓰는 곳" 이 실제보다 커진다.
#:
#: 세 번째 칸은 WHERE 조각이고 `{t}` 가 그 표를 가리킨다. 표를 별칭으로 읽는
#: 자리가 있어서(`drift`) 이름을 박아 둘 수 없다.
_COUNT_SOURCES: tuple[tuple[str, tuple[Binding, ...], str], ...] = (
    ("materials", MATERIAL_BINDINGS, " AND {t}.deleted_at IS NULL"),
    ("samples", SAMPLE_BINDINGS, " AND {t}.deleted_at IS NULL"),
    ("specimens", SPECIMEN_BINDINGS, " AND {t}.deleted_at IS NULL"),
    ("test_runs", TEST_RUN_BINDINGS, " AND {t}.deleted_at IS NULL"),
    # 용도는 재료에 매달려 있다. **지운 재료의 용도가 남으면** 「쓰는 곳」 이
    # 실제보다 커지고, 안 쓰는 용어가 피커 위쪽에 계속 앉아 있다.
    (
        "material_uses",
        USE_BINDINGS,
        " AND EXISTS (SELECT 1 FROM materials AS m"
        " WHERE m.id = {t}.material_id AND m.deleted_at IS NULL)",
    ),
)


@dataclass(frozen=True)
class Drift:
    """문자열과 기준정보가 벌어진 한 칸."""

    table: str
    field: str
    label: str
    count: int
    examples: list[str]


def drift(db: Session) -> list[Drift]:
    """문자열 컬럼과 기준정보 값이 어긋난 행을 센다. **Contract 의 검증 도구다.**

    지금은 같은 사실을 두 벌로 들고 있다 — `materials.family` 문자열과
    `family_term_id`. 쓰는 경로는 `apply_bindings` 하나지만 그 밖으로 새는 길이
    있으면(일괄 등록·이관·마이그레이션·DB 직접 수정) 조용히 벌어진다. **조용한
    것이 문제다** — 오늘 0 인 것을 스크립트를 따로 써서야 알았다.

    문자열 컬럼을 지우기 전에 이 수가 한 릴리스 동안 0 이어야 한다. 0 이 아닌
    채로 지우면 어느 쪽이 맞았는지 영영 알 수 없다.

    빈 문자열은 NULL 과 같게 본다 — `''` 와 `NULL` 이 둘로 갈리면 "없음" 이 두
    종류가 되는데, 그건 어긋남이 아니라 표기 문제다(`clean()` 이 이미 막는다).
    """
    found: list[Drift] = []
    # 한 표의 같은 칸을 두 축이 함께 가리킬 수 있다(용도의 제품·부위는 같은
    # `value`·`term_id` 를 본다). 그대로 두면 **같은 어긋남이 두 번 실린다** —
    # 목록의 수를 믿을 수 없게 된다.
    seen: set[tuple[str, str, str]] = set()
    for table, bindings, deleted in _COUNT_SOURCES:
        for binding in bindings:
            if (table, binding.field, binding.column) in seen:
                continue
            seen.add((table, binding.field, binding.column))
            where = (
                f" FROM {table} AS x"
                f" LEFT JOIN vocabulary_terms AS t ON t.id = x.{binding.column}"
                f" WHERE NULLIF(x.{binding.field}, '') IS DISTINCT FROM t.value"
                f"{deleted.format(t='x')}"
            )
            count = db.scalar(text("SELECT count(*)" + where)) or 0
            if not count:
                continue
            rows = db.execute(
                text(
                    f"SELECT coalesce(NULLIF(x.{binding.field}, ''), '(빈 값)'),"
                    f"       coalesce(t.value, '(안 이어짐)')" + where + " LIMIT 5"
                )
            ).all()
            found.append(
                Drift(
                    table=table,
                    field=binding.field,
                    label=binding.slug,
                    count=count,
                    examples=[
                        f"{text_value} ↔ {term_value}" for text_value, term_value in rows
                    ],
                )
            )
    return found


#: 점검 기록을 며칠 들고 있나. 6시간마다 돌면 90일이 360행이다 — 작지만
#: 무한히 쌓게 두지 않는다.
DRIFT_HISTORY_DAYS = 90


def record_check(
    db: Session, *, source: str = "worker", found: list[Drift] | None = None
) -> VocabularyDriftCheck:
    """어긋남을 재고 **남긴다.**

    "지금 0" 과 "언제부터 0" 은 다른 질문이고, Contract 가 묻는 것은 뒤쪽이다.
    남기지 않으면 일주일 뒤에 답할 수 없다.

    `found` 를 주면 그것을 남긴다 — 고치기가 **고치기 전 상태**를 남길 때 쓴다.
    다시 재면 이미 고쳐진 뒤라 무엇이 있었는지가 이력에서 사라진다.
    """
    found = drift(db) if found is None else found
    row = VocabularyDriftCheck(
        total=sum(item.count for item in found),
        detail=[
            {
                "table": item.table,
                "field": item.field,
                "label": item.label,
                "count": item.count,
                "examples": item.examples,
            }
            for item in found
        ],
        source=source,
    )
    db.add(row)
    db.execute(
        text(
            "DELETE FROM vocabulary_drift_checks"
            " WHERE checked_at < now() - :days * interval '1 day'"
        ),
        {"days": DRIFT_HISTORY_DAYS},
    )
    db.flush()
    return row


def latest_check(db: Session) -> VocabularyDriftCheck | None:
    """마지막 점검 기록. 없으면 None(아직 한 번도 안 쟀다)."""
    return db.scalar(
        select(VocabularyDriftCheck).order_by(VocabularyDriftCheck.checked_at.desc()).limit(1)
    )


def clean_run(db: Session) -> tuple[datetime | None, int]:
    """언제부터 계속 0 이었나, 그동안 몇 번 쟀나.

    **끊긴 지점을 찾는다.** 마지막으로 0 이 아니었던 점검보다 뒤에 있는 것들이
    지금 이어지고 있는 구간이다. 한 번이라도 벌어졌으면 거기서 다시 센다 —
    고쳤더라도 "내내 0 이었다" 는 더 이상 참이 아니다.
    """
    broke = db.scalar(
        select(func.max(VocabularyDriftCheck.checked_at)).where(VocabularyDriftCheck.total > 0)
    )
    query = select(func.min(VocabularyDriftCheck.checked_at), func.count()).where(
        VocabularyDriftCheck.total == 0
    )
    if broke is not None:
        query = query.where(VocabularyDriftCheck.checked_at > broke)
    since, count = db.execute(query).one()
    return since, count


def repair(db: Session, *, created_by_id: uuid.UUID | None = None) -> list[Drift]:
    """어긋난 칸을 바로잡는다. **기준정보가 정본이다.**

    방향을 정해야 하는 일이라 자동으로 돌지 않는다 — 사람이 점검을 보고 누른다.
    두 가지 어긋남이 있고 고치는 방향이 반대다.

    * **기준정보는 있는데 문자열이 다르다** — 문자열을 기준정보 값으로 다시 쓴다. 문자열은
      Contract 전까지의 캐시이고, 캐시가 틀렸으면 원본에서 다시 만드는 것이 유일한
      방향이다(`recount` 와 같은 판단).
    * **문자열은 있는데 기준정보가 없다** — 백필이 못 이은 행이다. 여기서 문자열을
      지우면 그 재료가 무엇이었는지 사라진다. 반대로 **문자열을 기준정보로 올린다.**

    고친 뒤 이름 훅을 때린다 — Grade 가 바뀌면 재료 이름이 다시 만들어져야 한다.
    """
    before = drift(db)
    touched: dict[str, set[uuid.UUID]] = {}

    # `drift` 와 같은 이유로 중복을 건너뛴다 — 한 표의 같은 칸을 두 축이 함께
    # 가리킬 수 있다. 두 번 고치면 두 번째는 **엉뚱한 축의 사전**을 들고 온다.
    seen: set[tuple[str, str, str]] = set()
    for table, bindings, deleted in _COUNT_SOURCES:
        for binding in bindings:
            if (table, binding.field, binding.column) in seen:
                continue
            seen.add((table, binding.field, binding.column))
            where = (
                f" FROM {table} AS x"
                f" LEFT JOIN vocabulary_terms AS t ON t.id = x.{binding.column}"
                f" WHERE NULLIF(x.{binding.field}, '') IS DISTINCT FROM t.value"
                f"{deleted.format(t='x')}"
            )
            rows = db.execute(
                text(f"SELECT x.id, x.{binding.field}, x.{binding.column}" + where)
            ).all()
            if not rows:
                continue

            vocabulary = get_vocabulary(db, binding.slug)
            for row_id, text_value, term_id in rows:
                if term_id is not None:
                    # 기준정보가 정본 — 문자열을 다시 쓴다.
                    term = db.get(VocabularyTerm, term_id)
                    if term is None:
                        continue
                    db.execute(
                        text(f"UPDATE {table} SET {binding.field} = :v WHERE id = :i"),
                        {"v": term.value, "i": row_id},
                    )
                    touched.setdefault(binding.slug, set()).add(term.id)
                    continue

                # 안 이어진 행 — 문자열을 기준정보로 올린다. **지우지 않는다.**
                term = resolve_or_create(
                    db, vocabulary, text_value, created_by_id=created_by_id
                )
                if term is None:
                    continue
                db.execute(
                    text(
                        f"UPDATE {table} SET {binding.field} = :v, {binding.column} = :t"
                        f" WHERE id = :i"
                    ),
                    {"v": term.value, "t": term.id, "i": row_id},
                )
                touched.setdefault(binding.slug, set()).add(term.id)

    _resync(db)
    for slug, term_ids in touched.items():
        for term_id in term_ids:
            vocabulary_hooks.fire_rename(db, slug, term_id)
    for slug in touched:
        recount(db, get_vocabulary(db, slug))
    return before


def term_ids_matching(db: Session, slugs: Sequence[str], word: str) -> list[uuid.UUID]:
    """주어진 축들에서 낱말이 걸리는 값의 id. **축으로 좁히는 것이 요점이다.**

    `materials.family` 는 5만 행인데 값은 5가지다. 기준정보 쪽 `family` 축은 5행이다
    — 5행을 훑는 것이 정규화의 이득 전부인데, 축을 안 좁히면 기준정보 23만 행을
    훑어서 도로 잃는다. 실측: 2글자 검색어(trgm 을 못 탄다)에서 79ms 대 0.02ms.
    """
    key = compare_key(word)
    if not key:
        return []
    # **축 id 를 먼저 받는다.** `vocabularies` 와 조인해서 `slug IN (...)` 로 쓰면
    # 플래너가 축 제한을 나중에 걸고 기준정보 23만 행을 훑는다 — 좁히려고 넣은 조건이
    # 안 듣는다. 실측: 2글자 검색어에서 조인 84ms 대 축 id 0.02ms.
    axis_ids = list(db.scalars(select(Vocabulary.id).where(Vocabulary.slug.in_(slugs))))
    if not axis_ids:
        return []
    return list(
        db.scalars(
            select(VocabularyTerm.id).where(
                VocabularyTerm.vocabulary_id.in_(axis_ids),
                VocabularyTerm.normalized.ilike(f"%{key}%"),
            )
        )
    )


def add_alias(db: Session, term: VocabularyTerm, alias: str) -> VocabularyAlias | None:
    """다른 표기를 정규 값에 잇는다. **예방이다.**

    `'POSCO'` 를 `'포스코'` 의 별칭으로 등록해 두면 값을 만들 때 게이트가 그것까지
    뒤져서 애초에 중복이 안 생긴다 — 사후에 합치는 것보다 싸다.

    이미 그 표기가 쓰이고 있으면(정규 값이거나 다른 별칭) 만들지 않는다.
    """
    key = compare_key(alias)
    cleaned = clean(alias)
    if not key or cleaned is None:
        raise AppError("MNX-VOCABULARY-0003", "값이 비어 있습니다.", status=422)

    taken = resolve(db, _vocabulary_of(db, term), cleaned)
    if taken is not None:
        if taken.id == term.id:
            return None  # 이미 이 값이다 — 조용히 넘어간다
        raise AppError(
            "MNX-VOCABULARY-0007",
            f"'{cleaned}' 는 이미 '{taken.value}' 를 가리킵니다.",
            status=409,
        )

    row = VocabularyAlias(
        vocabulary_id=term.vocabulary_id,
        term_id=term.id,
        alias=cleaned,
        normalized=key,
    )
    db.add(row)
    db.flush()
    return row


def merge(
    db: Session,
    source: VocabularyTerm,
    target: VocabularyTerm,
    *,
    merged_by_id: uuid.UUID | None = None,
) -> int:
    """`source` 를 `target` 으로 합친다. 옮긴 참조 수를 돌려준다.

    ## 참조 옮기기가 한 문장이다

    외래키로 간 이유가 이것이다(ADR 0010). 문자열이었으면 전 행을 훑어 글자를
    고쳐야 했고, 그건 병합이 아니라 일괄 치환이다.

    ## 없어진 표기가 별칭으로 남는다

    **병합이 일회성 청소가 아니라 규칙이 되는 지점이다.** `'포스코(주)'` 를
    `'포스코'` 로 합치면 그 표기가 별칭으로 남아서, 다음에 누가 또 치면 새 값이
    안 생기고 `'포스코'` 로 해석된다. ReportArchive 가 같은 판단을 했다 —
    *"이후 옛 표기 입력이 자동으로 into 로 빨려 들어간다."*

    ## 같은 축 안에서만

    축을 넘는 병합은 값을 합치는 것이 아니라 **뜻을 바꾸는 것**이다. 제조사를
    거래처로 옮기는 일은 병합이 아니라 이관이고, 그건 다른 기능이다.
    """
    if source.id == target.id:
        return 0
    if source.vocabulary_id != target.vocabulary_id:
        raise AppError(
            "MNX-VOCABULARY-0008",
            "같은 축의 값끼리만 합칠 수 있습니다.",
            status=422,
        )

    moved = 0
    for table, bindings, _deleted in _COUNT_SOURCES:
        for binding in bindings:
            if binding.slug != _slug_of(db, source):
                continue
            result = db.execute(
                text(
                    f"UPDATE {table} SET {binding.column} = :target,"
                    f" {binding.field} = :value WHERE {binding.column} = :source"
                ),
                {"target": target.id, "value": target.value, "source": source.id},
            )
            # `Result` 의 선언 타입에는 `rowcount` 가 없다 — UPDATE 를 돌린
            # 결과에는 실제로 있다.
            moved += max(cast("Any", result).rowcount or 0, 0)

    # 자식들의 부모를 옮긴다 — 부모가 사라지면 계층이 끊긴다.
    db.execute(
        update(VocabularyTerm)
        .where(VocabularyTerm.parent_term_id == source.id)
        .values(parent_term_id=target.id)
    )

    # `source` 의 별칭을 흡수하고, `source` 의 표기 자체도 별칭으로 남긴다.
    db.execute(
        update(VocabularyAlias)
        .where(VocabularyAlias.term_id == source.id)
        .values(term_id=target.id)
    )
    if source.normalized != target.normalized:
        db.add(
            VocabularyAlias(
                vocabulary_id=target.vocabulary_id,
                term_id=target.id,
                alias=source.value,
                normalized=source.normalized,
            )
        )

    db.add(
        VocabularyMerge(
            vocabulary_id=source.vocabulary_id,
            source_value=source.value,
            target_term_id=target.id,
            target_value=target.value,
            moved_count=moved,
            merged_by_id=merged_by_id,
        )
    )
    target.usage_count += source.usage_count
    db.delete(source)
    _resync(db)
    return moved


def _vocabulary_of(db: Session, term: VocabularyTerm) -> Vocabulary:
    found = db.get(Vocabulary, term.vocabulary_id)
    if found is None:  # pragma: no cover — FK 가 막는다
        raise NotFound("MNX-VOCABULARY-0001", "기준정보를 찾을 수 없습니다.")
    return found


def _slug_of(db: Session, term: VocabularyTerm) -> str:
    return _vocabulary_of(db, term).slug


#: 후보 그룹핑용 **강한 정규화**.
#:
#: 저장값의 비교키(`compare_key`)보다 공격적이다 — 공백·하이픈·괄호·점을 다
#: 떼서 `'ASTM E8'`·`'astm-e8'`·`'ASTM(E8)'` 을 한 키로 만든다.
#:
#: 이것을 **저장에 쓰지 않는 이유**: `'포스코(주)'` 가 계열사 구분일 수 있다.
#: 여기서는 후보로 올려 **사람에게 묻고**, 합치는 것은 사람이 정한다.
_LOOSE = re.compile(r"[^0-9a-z가-힣]+")


def loose_key(value: str) -> str:
    return _LOOSE.sub("", compare_key(value))


def merge_candidates(db: Session, vocabulary: Vocabulary) -> list[list[VocabularyTerm]]:
    """합칠 만한 값 묶음. **탐지만 한다** — 합치는 것은 사람이 누른다.

    ReportArchive 는 여기에 임베딩 유사도(L1)를 한 층 더 얹어 한글↔라틴 교차까지
    건진다. 여기서는 **L0(결정적 정규화 그룹핑)만** 쓴다 — 임베딩 인프라가 없고,
    그거 하나 때문에 들일 값은 아니다.

    기각한 쌍은 뺀다. 안 빼면 같은 것을 매번 다시 묻게 되고, 그러면 목록을
    아무도 안 본다.
    """
    terms = list(
        db.scalars(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == vocabulary.id,
                VocabularyTerm.status == "active",
            )
        )
    )
    groups: dict[str, list[VocabularyTerm]] = {}
    for term in terms:
        groups.setdefault(loose_key(term.value), []).append(term)

    dismissed = {
        (row.low_term_id, row.high_term_id)
        for row in db.scalars(
            select(VocabularyDismissal).where(
                VocabularyDismissal.low_term_id.in_([t.id for t in terms])
            )
        )
    }

    found: list[list[VocabularyTerm]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # 묶음 안의 **모든 쌍**이 기각됐으면 뺀다. 셋 중 둘만 기각했으면 남는
        # 쌍이 있으므로 계속 보여 준다.
        pairs = [(a, b) for index, a in enumerate(members) for b in members[index + 1 :]]
        if all(_pair_key(a.id, b.id) in dismissed for a, b in pairs):
            continue
        # 많이 쓰이는 것이 앞으로 — 화면이 생존값으로 추천한다.
        found.append(sorted(members, key=lambda item: -item.usage_count))
    return found


def _pair_key(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """쌍을 정렬한다 — (a,b) 와 (b,a) 가 다른 행이 되면 유니크가 무의미하다."""
    return (a, b) if str(a) < str(b) else (b, a)


def dismiss(
    db: Session,
    first: VocabularyTerm,
    second: VocabularyTerm,
    *,
    dismissed_by_id: uuid.UUID | None = None,
) -> None:
    """ "이 둘은 다른 값이다" 를 기억한다."""
    low, high = _pair_key(first.id, second.id)
    exists = db.scalar(
        select(VocabularyDismissal).where(
            VocabularyDismissal.low_term_id == low,
            VocabularyDismissal.high_term_id == high,
        )
    )
    if exists is None:
        db.add(
            VocabularyDismissal(
                low_term_id=low, high_term_id=high, dismissed_by_id=dismissed_by_id
            )
        )


def references_to(db: Session, term: VocabularyTerm) -> int:
    """이 값을 실제로 가리키는 행 수. **캐시를 안 믿는다.**

    `usage_count` 는 캐시고 어긋날 수 있다(실제로 3 대 5 로 벌어진 적이 있다).
    지우기는 되돌릴 수 없으므로 여기서는 세어 본다 — 캐시가 0 이라고 해서 지웠는데
    참조가 남아 있으면 외래키가 막고 요청 전체가 500 으로 죽는다.
    """
    slug = _slug_of(db, term)
    total = 0
    for table, bindings, deleted in _COUNT_SOURCES:
        for binding in bindings:
            if binding.slug != slug:
                continue
            found = db.execute(
                text(
                    f"SELECT count(*) FROM {table} WHERE {binding.column} = :term_id"
                    f"{deleted.format(t=table)}"
                ),
                {"term_id": term.id},
            ).scalar()
            total += int(found or 0)
    return total


def child_count(db: Session, term: VocabularyTerm) -> int:
    """이 값을 상위로 삼는 값 수. 지우면 그것들이 고아가 된다."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(VocabularyTerm)
            .where(VocabularyTerm.parent_term_id == term.id)
        )
        or 0
    )


def delete_term(db: Session, term: VocabularyTerm) -> str | None:
    """지운다. 못 지우면 **이유를 돌려준다**(지웠으면 `None`).

    **무엇이 막는지 말하는 것이 요점이다.** "지울 수 없습니다" 만 주면 사람은
    왜인지 알아내려고 목록을 뒤진다 — 시편 삭제가 "시험 N건이 남아 있어" 라고
    말하는 것과 같은 이유다.

    참조가 있으면 안 지운다. 지우고 참조를 끊으면 그 시료가 어느 제조사였는지
    영영 알 수 없게 되는데, 그건 값을 정리하는 것과 전혀 다른 일이다. 그럴
    때는 **감추기**나 **병합**을 쓴다.
    """
    used = references_to(db, term)
    if used:
        return f"{used}곳에서 쓰고 있습니다. 감추기나 병합을 쓰세요."
    children = child_count(db, term)
    if children:
        return f"하위 값 {children}개가 이 값을 상위로 삼고 있습니다."
    db.delete(term)
    return None


# --- 속성 있는 값 -----------------------------------------------------------
#
# 시편 규격은 이름이 아니라 **치수 한 벌**이다(`ASTM E8 subsize` = 게이지 길이
# 25 mm · 평행부 폭 6 mm …). 그런데 그 칸이 규격마다 다르다 — 인장 안에서도
# 평판은 폭·두께를 갖고 환봉은 직경을 갖는다.
#
# 그래서 두 층으로 나눈다.
#
#   분류의 기본 칸   그 분류의 규격이면 **예외 없이** 갖는 것 (`SpecimenField`)
#   규격의 추가 칸   그 규격만 갖는 것 (`VocabularyTerm.extra_fields`)
#
# 분류는 규격의 **상위 값**이다(`parent_term_id`). 축 계층 기계를 그대로 쓴다 —
# `kind` 같은 컬럼을 따로 두면 같은 것을 두 방식으로 표현하게 된다.


@dataclass(frozen=True)
class Field:
    """칸 하나 — **값이 들어갈 자리의 정의.** 값 자체는 여기 없다.

    축·분류·값 어디서 선언되든 모양이 같아서 한 타입으로 다룬다.
    """

    key: str
    label: str
    dimension: str
    si_unit: str
    is_required: bool
    help: str | None
    #: 상위(축·분류)가 준 칸인가. 화면이 "여기서 못 지운다" 를 말한다.
    inherited: bool
    #: 담는 것 — `number` · `text` · `choice`.
    kind: str = "number"
    #: `choice` 일 때 고를 수 있는 값.
    choices: tuple[str, ...] = ()
    #: 그 규격의 도면이 쓰는 글자(`G`·`W`·`D`). 규격이 덮어쓸 수 있다.
    symbol: str | None = None


def _as_field(row: Any, *, inherited: bool) -> Field:
    return Field(
        key=str(row.key if hasattr(row, "key") else row["key"]),
        label=str(row.label if hasattr(row, "label") else row["label"]),
        dimension=str(
            (row.dimension if hasattr(row, "dimension") else row.get("dimension")) or "length"
        ),
        si_unit=str((row.si_unit if hasattr(row, "si_unit") else row.get("si_unit")) or "m"),
        is_required=bool(
            row.is_required if hasattr(row, "is_required") else row.get("is_required", False)
        ),
        help=(row.help if hasattr(row, "help") else row.get("help")) or None,
        inherited=inherited,
        kind=str((row.kind if hasattr(row, "kind") else row.get("kind")) or "number"),
        choices=tuple(
            str(item)
            for item in (
                (row.choices if hasattr(row, "choices") else row.get("choices")) or ()
            )
        ),
        symbol=(row.symbol if hasattr(row, "symbol") else row.get("symbol")) or None,
    )


def category_fields(db: Session, category_term_id: uuid.UUID) -> list[Field]:
    """이 값이 **직접 선언한** 칸. 분류가 갖는 기본 칸이 이것이다.

    `inherited=False` 로 낸다 — 여기서는 고칠 수 있다는 뜻이다. 그 칸이 규격
    쪽에서 보일 때 `True` 가 된다(`attribute_fields`).
    """
    rows = db.scalars(
        select(SpecimenField)
        .where(SpecimenField.category_term_id == category_term_id)
        .order_by(SpecimenField.sort_order)
    )
    return [_as_field(row, inherited=False) for row in rows]


def axis_fields(vocabulary: Vocabulary) -> list[Field]:
    """**이 축의 값이면 무엇이든 갖는 칸.** 시편 규격의 판(edition) 이 그렇다.

    분류마다 적으면 새 분류를 만들 때 빠뜨린다 — 축에 한 번만 적는다.
    """
    return [_as_field(item, inherited=True) for item in (vocabulary.base_fields or [])]


def attribute_fields(
    db: Session, vocabulary: Vocabulary, term: VocabularyTerm | None
) -> list[Field]:
    """이 값이 가질 수 있는 칸.

    한 규칙으로 네 자리를 다 본다.

        축의 칸  +  이 값이 직접 선언한 칸  +  상위가 선언한 칸  +  이 값의 추가 칸

    **분류**는 자기가 선언한 칸을 갖고(상위가 없다), **규격**은 축과 상위 분류가
    선언한 칸에 자기 칸을 더한다. 규칙을 갈라 두면 "이 값은 어느 쪽이냐" 를
    부르는 곳마다 물어야 한다.

    `inherited` 는 **위에서 온 칸인가**다 — 그렇다면 이 값에서는 못 지운다.

    마지막으로 **규격이 자기 글자를 덮어쓴다**(`field_symbols`). 같은 게이지
    길이라도 E8 은 `G`, ISO 527-2 는 `L₀` 로 적기 때문이다.
    """
    if term is None:
        return []
    own = category_fields(db, term.id)
    parent = (
        [replace(item, inherited=True) for item in category_fields(db, term.parent_term_id)]
        if term.parent_term_id
        else []
    )
    extra = [_as_field(item, inherited=False) for item in (term.extra_fields or [])]
    fields = axis_fields(vocabulary) + own + parent + extra

    overrides = term.field_symbols or {}
    if not overrides:
        return fields
    return [
        replace(item, symbol=str(overrides[item.key])) if item.key in overrides else item
        for item in fields
    ]


#: 칸이 쓸 수 있는 차원 — **단위표에 있는 것 전부.**
#:
#: 처음에는 길이·면적·각도·무차원·질량 다섯으로 좁혔다. 좁힐 근거가 없었다 —
#: 규격표만 봐도 길이(치수)·각도(탭 베벨)·무차원(w/d, 시편 2장)·면적(직접 잰
#: 단면적)·질량(ISO 6721-10 의 시료 3~5 g)이 나오고, 시편에 붙는 값이 그것으로
#: 끝난다는 보장이 없다. 좁혀 두면 필요해질 때마다 코드를 고쳐야 한다.
#:
#: **차원과 저장 단위가 짝이라는 규칙만 지킨다**(`check_dimension`).
SPECIMEN_DIMENSIONS = tuple(unit_kit.SI_UNITS)


#: 칸이 담을 수 있는 것.
FIELD_KINDS = ("number", "text", "choice")


def check_kind(item: Mapping[str, Any]) -> dict[str, Any]:
    """칸의 종류와 그에 딸린 것들을 정리한다.

    **종류마다 뜻이 있는 항목이 다르다.** 문자 칸에 차원·저장 단위는 뜻이 없고,
    선택 칸은 고를 값이 있어야 한다. 뒤섞어 두면 화면이 문자 칸에 mm 를 붙인다.
    """
    kind = str(item.get("kind") or "number")
    if kind not in FIELD_KINDS:
        raise AppError(
            "MNX-VOCABULARY-0023",
            f"칸의 종류는 {', '.join(FIELD_KINDS)} 중 하나여야 합니다: {kind}.",
            status=422,
        )

    choices = [str(one).strip() for one in (item.get("choices") or []) if str(one).strip()]
    if kind == "choice" and not choices:
        raise AppError(
            "MNX-VOCABULARY-0024",
            "선택 칸에는 고를 값을 적어야 합니다. "
            "고를 것이 없으면 문자 칸으로 두세요 — 빈 목록은 아무것도 못 고르게 합니다.",
            status=422,
        )
    if kind != "choice":
        choices = []

    if kind == "number":
        dimension, si_unit = check_dimension(
            str(item.get("dimension") or "length"), str(item.get("si_unit") or "m")
        )
    else:
        # 숫자가 아니면 차원이 뜻이 없다. 자리는 남기되 무차원으로 고정한다 —
        # 빼 버리면 읽는 쪽이 전부 `None` 을 다뤄야 한다.
        dimension, si_unit = "dimensionless", "1"

    symbol = str(item.get("symbol") or "").strip() or None
    return {
        "kind": kind,
        "choices": choices,
        "dimension": dimension,
        "si_unit": si_unit,
        "symbol": symbol,
    }


def check_dimension(dimension: str, si_unit: str) -> tuple[str, str]:
    """차원과 저장 단위가 짝인가. **여기서 안 막으면 조용히 틀린다.**

    단면적 칸을 길이(m)로 만들어 두면 화면이 mm 로 환산해 **10⁶ 배** 어긋난 값이
    저장되고, 숫자는 멀쩡해 보인다. 시험 종류 정의에서 같은 판단을 이미 했다 —
    저장 단위는 고르는 것이 아니라 차원이 정한다.
    """
    if dimension not in SPECIMEN_DIMENSIONS:
        raise AppError(
            "MNX-VOCABULARY-0021",
            f"시편 치수로 쓸 수 없는 차원입니다: {dimension}. "
            f"쓸 수 있는 것: {', '.join(SPECIMEN_DIMENSIONS)}.",
            status=422,
        )
    expected = unit_kit.SI_UNITS[dimension]
    if si_unit != expected:
        raise AppError(
            "MNX-VOCABULARY-0022",
            f"'{dimension}' 의 저장 단위는 {expected} 입니다({si_unit} 이 아니라). "
            "저장은 언제나 SI 이고, 화면 단위는 보여 줄 때 정합니다.",
            status=422,
        )
    return dimension, si_unit


def check_extra_fields(
    db: Session, term: VocabularyTerm, fields: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """이 값만의 칸을 검사한다. **분류의 기본 칸과 겹치면 거절한다.**

    같은 키가 둘이면 어느 쪽이 이기는지를 사람이 알 방법이 없다 — 화면에 칸이
    둘 뜨거나 하나가 조용히 가려진다.
    """
    axis = db.get(Vocabulary, term.vocabulary_id)
    base = {item.key for item in (axis_fields(axis) if axis else [])}
    base |= {
        item.key
        for item in (category_fields(db, term.parent_term_id) if term.parent_term_id else [])
    }
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for item in fields:
        key = str(item.get("key") or "").strip()
        if not key:
            raise AppError("MNX-VOCABULARY-0017", "칸 이름(키)이 비어 있습니다.", status=422)
        if key in base:
            raise AppError(
                "MNX-VOCABULARY-0018",
                f"'{key}' 는 위에서 이미 갖고 있는 칸입니다(축 또는 분류). "
                "다른 이름을 쓰세요.",
                status=422,
            )
        if key in seen:
            raise AppError("MNX-VOCABULARY-0016", f"칸 이름이 겹칩니다: {key}.", status=422)
        seen.add(key)
        cleaned.append(
            {
                "key": key,
                "label": str(item.get("label") or key),
                "is_required": bool(item.get("is_required", False)),
                "help": item.get("help") or None,
                **check_kind(item),
            }
        )
    return cleaned


def _clean_value(field: Field, raw: Any) -> float | str:
    """값 하나를 그 칸의 종류에 맞게 정리한다.

    **치수만 있는 것이 아니다.** 규격은 판(문자)과 모드·단부 형식(선택)도 갖는다.
    숫자 규칙을 문자에 그대로 대면 판 `D638-22` 가 거절된다.
    """
    if field.kind == "text":
        text = str(raw).strip()
        if len(text) > 200:
            raise AppError(
                "MNX-VOCABULARY-0012",
                f"'{field.label}' 이(가) 너무 깁니다(200자까지).",
                status=422,
            )
        return text

    if field.kind == "choice":
        text = str(raw).strip()
        if field.choices and text not in field.choices:
            raise AppError(
                "MNX-VOCABULARY-0012",
                f"'{field.label}' 은(는) {', '.join(field.choices)} 중 하나여야 합니다: "
                f"{text!r}.",
                status=422,
            )
        return text

    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise AppError(
            "MNX-VOCABULARY-0012",
            f"'{field.label}' 은(는) 숫자여야 합니다: {raw!r}.",
            status=422,
        ) from None
    if not math.isfinite(value) or value <= 0:
        raise AppError(
            "MNX-VOCABULARY-0012",
            f"'{field.label}' 은(는) 0 보다 큰 값이어야 합니다.",
            status=422,
        )
    return value


def check_attributes(
    db: Session,
    vocabulary: Vocabulary,
    term: VocabularyTerm | None,
    attributes: Mapping[str, Any],
) -> dict[str, float | str]:
    """속성을 스키마에 견줘 본다. 통과하면 저장할 모양으로 돌려준다.

    세 가지를 본다.

      - **스키마에 없는 키는 거절한다.** 오타 하나가 조용히 새 속성이 되면
        아무도 못 찾는다.
      - **숫자여야 한다.** 값은 그 칸이 선언한 차원의 SI 수치다 — 길이만은
        아니다(탭 베벨각은 각도, w/d 는 무차원, 직접 잰 단면적은 면적).
      - **필수라고 표시한 칸은 비울 수 없다.** 다만 기본 칸을 필수로 두지는
        않는다 — 게이지 길이가 없는 인장 규격이 실제로 여럿이다(D3039 계열은
        그립 간 거리가 곧 게이지다).

    값은 **SI 로 온다.** 규격서가 mm 로 적혀 있어도 화면이 바꿔서 보낸다.
    """
    fields = attribute_fields(db, vocabulary, term)
    if not fields:
        if attributes:
            raise AppError(
                "MNX-VOCABULARY-0010",
                "이 값은 아직 치수 칸이 없습니다. 분류를 고르거나 칸을 먼저 만드세요.",
                status=422,
            )
        return {}

    known = {field.key: field for field in fields}
    # **이미 들어 있던 값은 칸이 없어져도 막지 않는다.** 칸을 빼도 값은 남기기
    # 때문이다(칸을 되살리면 다시 보인다) — 그 값 때문에 다음 저장이 422 가 되면
    # 칸을 지운 사람이 아무것도 못 하게 된다.
    stored = dict((term.attributes if term else None) or {})
    orphans = {
        key: value
        for key, value in attributes.items()
        if key not in known and key in stored and stored[key] == value
    }
    unknown = sorted(set(attributes) - set(known) - set(orphans))
    if unknown:
        raise AppError(
            "MNX-VOCABULARY-0011",
            f"이 규격에 없는 치수입니다: {', '.join(unknown)}.",
            status=422,
        )

    cleaned: dict[str, float | str] = dict(orphans)
    for key, raw in attributes.items():
        if raw is None or raw == "" or key in orphans:
            continue
        cleaned[key] = _clean_value(known[key], raw)

    missing = [
        field.label for field in fields if field.is_required and field.key not in cleaned
    ]
    if missing:
        raise AppError(
            "MNX-VOCABULARY-0013",
            f"필수 치수가 비어 있습니다: {', '.join(missing)}.",
            status=422,
        )
    return cleaned


#: 헤더에서 값·상위·별칭을 가리키는 이름. 나머지 열은 **칸 이름**으로 본다.
HEADER_VALUE = ("값", "이름", "value", "name")
HEADER_PARENT = ("상위", "분류", "상위 분류", "parent")
HEADER_ALIAS = ("표기", "별칭", "다른 표기", "alias", "aliases")

#: `게이지 길이 (mm)` 에서 단위를 떼는 자리.
_HEADER_UNIT = re.compile(r"^(?P<name>.+?)\s*[(\[](?P<unit>[^)\]]+)[)\]]\s*$")


@dataclass(frozen=True)
class Column:
    """헤더 한 칸이 무엇을 가리키는가."""

    kind: str
    """`value` · `parent` · `alias` · `field` · `unknown`."""
    field: Field | None = None
    unit: str | None = None
    """숫자 칸일 때 그 열이 적힌 단위. **헤더에 없으면 `None`.**"""
    reason: str | None = None
    """`unknown` 인 이유. 말없이 버리지 않는다."""


def read_header(header: Sequence[str], fields: Sequence[Field]) -> list[Column]:
    """헤더 줄을 열 뜻으로 바꾼다.

    **숫자 열은 단위를 헤더에 적어야 한다.** `게이지 길이 (mm)` 처럼. 안 적으면
    `50` 이 50 mm 인지 50 m 인지 알 수 없는데, 추측해서 mm 로 치면 m 로 적은 표
    에서 **1000배 틀린 규격**이 만들어지고 그 숫자는 그럴듯해 보인다. 장비 파일
    치수를 읽을 때 이미 같은 판단을 했다 — 단위를 못 찾으면 포기한다.
    """
    by_name: dict[str, Field] = {}
    for item in fields:
        by_name.setdefault(compare_key(item.label), item)
        by_name.setdefault(compare_key(item.key), item)
        # **사람은 괄호까지 안 적는다.** 칸 이름이 `판(edition)` 이어도 헤더에는
        # `판` 이라고 쓴다.
        bare = _HEADER_UNIT.match(item.label)
        if bare:
            by_name.setdefault(compare_key(bare.group("name")), item)

    columns: list[Column] = []
    for raw in header:
        text = clean(raw) or ""
        key = compare_key(text)
        if key in {compare_key(one) for one in HEADER_VALUE}:
            columns.append(Column("value"))
            continue
        if key in {compare_key(one) for one in HEADER_PARENT}:
            columns.append(Column("parent"))
            continue
        if key in {compare_key(one) for one in HEADER_ALIAS}:
            columns.append(Column("alias"))
            continue

        unit: str | None = None
        matched = _HEADER_UNIT.match(text)
        if matched:
            unit = matched.group("unit").strip()
            key = compare_key(matched.group("name"))

        field = by_name.get(key)
        if field is None:
            columns.append(Column("unknown", reason=f"'{text}' 는 이 축의 칸이 아닙니다."))
            continue
        if field.kind == "number":
            if not unit:
                columns.append(
                    Column(
                        "unknown",
                        field=field,
                        reason=f"'{field.label}' 은(는) 단위를 헤더에 적어야 합니다 — "
                        f"`{field.label} (mm)` 처럼.",
                    )
                )
                continue
            try:
                unit_kit.unit_of(unit_kit.canonical(unit) or unit)
            except unit_kit.UnknownUnit:
                columns.append(
                    Column("unknown", field=field, reason=f"모르는 단위입니다: {unit}")
                )
                continue
        columns.append(Column("field", field=field, unit=unit))
    return columns


def read_cell(column: Column, raw: str) -> float | str | None:
    """열 하나의 값을 저장할 모양으로. 빈 칸은 `None`(안 적은 것)."""
    text = (raw or "").strip()
    if not text or column.field is None:
        return None
    if column.field.kind != "number":
        return text
    try:
        value = float(text)
    except ValueError:
        raise AppError(
            "MNX-VOCABULARY-0030",
            f"'{column.field.label}' 은(는) 숫자여야 합니다: {text!r}",
            status=422,
        ) from None
    symbol = unit_kit.canonical(column.unit or "") or (column.unit or "")
    try:
        return unit_kit.to_si(value, symbol)
    except unit_kit.UnknownUnit:
        raise AppError(
            "MNX-VOCABULARY-0030", f"모르는 단위입니다: {column.unit}", status=422
        ) from None


def check_ratio_checks(
    db: Session,
    vocabulary: Vocabulary,
    term: VocabularyTerm,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """비율 조건을 검사한다.

    **두 칸 다 이 규격이 갖는 숫자 칸이어야 한다.** 없는 칸을 가리키면 그 조건은
    영영 판정되지 않고, 사람은 "왜 경고가 안 뜨지" 를 묻게 된다 — 조용한 실패다.
    """
    numbers = {
        field.key: field
        for field in attribute_fields(db, vocabulary, term)
        if field.kind == "number"
    }
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        top = str(row.get("numerator") or "").strip()
        bottom = str(row.get("denominator") or "").strip()
        for key in (top, bottom):
            if key not in numbers:
                raise AppError(
                    "MNX-VOCABULARY-0026",
                    f"'{key}' 는 이 규격의 숫자 칸이 아닙니다. "
                    "비율 조건은 이 규격이 갖는 치수 칸으로만 걸 수 있습니다.",
                    status=422,
                )
        if top == bottom:
            raise AppError(
                "MNX-VOCABULARY-0026",
                "같은 칸끼리는 비를 잴 수 없습니다.",
                status=422,
            )

        minimum = _as_bound(row.get("minimum"))
        maximum = _as_bound(row.get("maximum"))
        if minimum is None and maximum is None:
            raise AppError(
                "MNX-VOCABULARY-0027",
                f"'{numbers[top].label} / {numbers[bottom].label}' 에 최소나 최대 중 "
                "하나는 적어야 합니다 — 둘 다 비면 아무것도 안 재는 조건입니다.",
                status=422,
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise AppError(
                "MNX-VOCABULARY-0027",
                "최소가 최대보다 큽니다.",
                status=422,
            )
        cleaned.append(
            {
                "numerator": top,
                "denominator": bottom,
                "minimum": minimum,
                "maximum": maximum,
                "help": (str(row.get("help")).strip() if row.get("help") else None) or None,
            }
        )
    return cleaned


def _as_bound(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise AppError(
            "MNX-VOCABULARY-0027", f"숫자가 아닙니다: {raw!r}.", status=422
        ) from None
    if not math.isfinite(value) or value <= 0:
        raise AppError("MNX-VOCABULARY-0027", "비율 한계는 0 보다 커야 합니다.", status=422)
    return value


def check_cross_section(
    db: Session, vocabulary: Vocabulary, term: VocabularyTerm, key: str | None
) -> str | None:
    """단면적 식을 고를 수 있는가.

    **그 식이 요구하는 치수 칸이 이 규격에 있어야 한다.** 없으면 그 식은 늘
    실패하고, 사람은 "왜 단면적이 안 나오지" 를 처리 화면에서 만난다 — 고른
    자리에서 거절하는 편이 낫다.
    """
    from matcore import specimen as specimen_kit

    if key is None:
        return None
    shape = specimen_kit.CROSS_SECTIONS.get(key)
    if shape is None:
        raise AppError("MNX-VOCABULARY-0019", f"모르는 단면 모양입니다: {key}", status=422)

    have = {field.key for field in attribute_fields(db, vocabulary, term)}
    missing = [need.label for need in shape.needs if need.key not in have]
    if missing:
        raise AppError(
            "MNX-VOCABULARY-0020",
            f"'{shape.label}' 를 쓰려면 {', '.join(missing)} 칸이 있어야 합니다. "
            f"이 규격의 칸에 먼저 더하세요.",
            status=422,
        )
    return key
