"""기준정보 API — 피커가 부르는 것.

**전체를 주지 않는다.** 기준정보가 수만 개가 되면 브라우저로 다 보낼 수 없고, 보내
봐야 화면은 60개만 그린다. 검색어를 받아 상한을 걸어 돌려준다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.vocabulary import services
from app.modules.vocabulary.models import (
    SpecimenField,
    Vocabulary,
    VocabularyAlias,
    VocabularyDriftCheck,
    VocabularyTerm,
)
from app.modules.vocabulary.normalize import clean, split_parent
from app.modules.vocabulary.schemas import (
    BulkDeleteItemOut,
    BulkDeleteOut,
    BulkDeleteRequest,
    BulkTermCreateRequest,
    BulkTermItemOut,
    BulkTermOut,
    CrossSectionNeedOut,
    CrossSectionOut,
    DismissRequest,
    DriftOut,
    DriftReportOut,
    MergeRequest,
    RatioCheckOut,
    SpecimenFieldOut,
    SpecimenFieldsSaveRequest,
    TermAliasCreateRequest,
    TermAliasOut,
    TermCreateRequest,
    TermOut,
    TermUpdateRequest,
    VocabularyOut,
)
from app.shared.auth import current_user, require_system_admin
from app.shared.errors import AppError, NotFound
from app.shared.pagination import MAX_LIMIT, Page, clamp_limit
from matcore import specimen as specimen_kit

router = APIRouter(prefix="/vocabularies", tags=["vocabulary"])

#: 한 번에 돌려주는 최대. 화면이 60개를 그리므로 그보다 조금 넉넉하게.
#: **상한을 서버가 건다** — 화면이 정하게 두면 "전체 주세요" 가 언젠가 온다.
SEARCH_LIMIT = 100


def _term_out(db: Session, item: VocabularyTerm, field_count: int | None = None) -> TermOut:
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
        attributes=dict(item.attributes or {}),
        field_symbols=dict(item.field_symbols or {}),
        ratio_checks=[RatioCheckOut(**row) for row in (item.ratio_checks or [])],
        cross_section=item.cross_section,
        # **이 값이 직접 선언한 칸 수.** 분류 축에서 "이 분류는 칸이 몇 개" 를
        # 말한다 — 0 이면 그 분류의 규격은 치수를 하나도 못 갖는다.
        field_count=field_count
        if field_count is not None
        else db.scalar(
            select(func.count())
            .select_from(SpecimenField)
            .where(SpecimenField.category_term_id == item.id)
        )
        or 0,
        extra_fields=[
            SpecimenFieldOut(
                key=str(field.get("key", "")),
                label=str(field.get("label", "")),
                kind=str(field.get("kind") or "number"),
                choices=[str(one) for one in (field.get("choices") or [])],
                symbol=field.get("symbol"),
                dimension=str(field.get("dimension", "length")),
                si_unit=str(field.get("si_unit", "m")),
                is_required=bool(field.get("is_required", False)),
                help=field.get("help"),
                inherited=False,
            )
            for field in (item.extra_fields or [])
        ],
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
            parent_slug=item.parent_slug,
            entry_policy=item.entry_policy,
            attribute_source=item.attribute_source,
            term_count=counts.get(item.id, 0),
        )
        for item in rows
    ]


def _report(db: Session, row: VocabularyDriftCheck) -> DriftReportOut:
    since, checks = services.clean_run(db)
    return DriftReportOut(
        total=row.total,
        items=[DriftOut(**item) for item in row.detail],
        checked_at=row.checked_at,
        clean_since=since,
        clean_checks=checks,
    )


@router.get("/drift", response_model=DriftReportOut)
def check_drift(
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> DriftReportOut:
    """문자열 컬럼과 기준정보 값이 어긋난 행. **0 이어야 한다.**

    **`/{slug}/...` 보다 먼저 선언한다.** FastAPI 는 선언 순서대로 맞춰 보므로,
    뒤에 두면 `drift` 가 축 이름 자리에 들어간다(`/classifications` 에서 겪었다).

    ## 왜 이게 있어야 하나

    지금은 같은 사실을 두 벌로 들고 있다(ADR 0010 Expand) — `materials.family`
    문자열과 `family_term_id`. Contract 에서 문자열을 지우려면 **두 벌이 같다는
    것을 한 릴리스 동안 봐야 한다.** 볼 도구가 없으면 "지켜봤다" 가 말이 안 된다.

    만들자마자 개발 DB 에서 2건을 찾았고, 그것이 결함 하나를 드러냈다 — 기준정보 값
    이름을 고치면 재료·시료·시편·시험 이름 넷은 전부 따라 바뀌는데 정작 그 값
    자신은 옛 표기 그대로였다. API 는 200 을 냈다.
    """
    row = services.latest_check(db)
    if row is None:
        # 처음 열었을 때. 한 번은 재야 보여 줄 것이 있다.
        row = services.record_check(db, source="manual")
        db.commit()
    return _report(db, row)


@router.post("/drift", response_model=DriftReportOut)
def measure_drift(
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> DriftReportOut:
    """지금 다시 잰다. **읽기와 가른다** — `GET` 은 기록을 보여 주기만 한다.

    화면을 열 때마다 새로 재면 이력이 사람이 창을 연 횟수가 된다. 게이트가 묻는
    것은 "저절로 돌 때도 계속 0 이었나" 이므로 그 이력이 더러우면 안 된다.
    """
    row = services.record_check(db, source="manual")
    db.commit()
    return _report(db, row)


@router.post("/repair", response_model=DriftReportOut)
def repair_drift(
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> DriftReportOut:
    """어긋난 칸을 바로잡는다. **기준정보가 정본이다.**

    자동으로 안 돈다. 방향을 정해야 하는 일이라(문자열을 고칠 것인가, 기준정보를
    고칠 것인가) 사람이 점검을 보고 누른다.

    **이력에 두 줄이 남는다.** 고치기 전과 후다. 고친 뒤만 남기면 무엇이 있었는지
    사라지고, 고치기 전만 남기면 "언제부터 0" 이 틀린다.

    돌려주는 것은 **고친 뒤** 상태다 — 화면이 그것을 그대로 그리므로, 고치기 전
    목록을 주면 눌렀는데 아무 일도 안 일어난 것처럼 보인다.
    """
    before = services.repair(db, created_by_id=user.id)
    services.record_check(db, source="manual", found=before)
    row = services.record_check(db, source="manual")
    db.commit()
    return _report(db, row)


@router.get("/cross-sections", response_model=list[CrossSectionOut])
def list_cross_sections(user: User = Depends(current_user)) -> list[CrossSectionOut]:
    """고를 수 있는 단면적 식. **목록을 화면에 적지 않는다.**

    식이 늘면(관·육각봉…) 화면이 따라온다 — 처리 단계의 `ParamSpec` 과 같은
    자리다(D7).
    """
    return [
        CrossSectionOut(
            key=item.key,
            label=item.label,
            needs=[
                CrossSectionNeedOut(
                    key=need.key,
                    label=need.label,
                    dimension=need.dimension,
                    si_unit=need.si_unit,
                )
                for need in item.needs
            ],
            help=item.help,
        )
        for item in specimen_kit.CROSS_SECTIONS.values()
    ]


@router.get("/{slug}/terms/{term_id}/fields", response_model=list[SpecimenFieldOut])
def list_term_fields(
    slug: str,
    term_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SpecimenFieldOut]:
    """이 값이 가질 수 있는 치수 칸 — **분류의 기본 + 이 값의 추가.**

    화면이 이 응답만으로 입력 폼을 그린다. 목록을 프론트에 적으면 분류를
    추가할 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다(D7).
    """
    vocabulary = services.get_vocabulary(db, slug)
    term = db.get(VocabularyTerm, term_id)
    if term is None or term.vocabulary_id != vocabulary.id:
        raise NotFound("MNX-VOCABULARY-0004", "값을 찾을 수 없습니다.")
    return [
        SpecimenFieldOut(
            key=field.key,
            label=field.label,
            kind=field.kind,
            choices=list(field.choices),
            symbol=field.symbol,
            dimension=field.dimension,
            si_unit=field.si_unit,
            is_required=field.is_required,
            help=field.help,
            inherited=field.inherited,
        )
        for field in services.attribute_fields(db, vocabulary, term)
    ]


@router.put("/{slug}/terms/{term_id}/fields", response_model=list[SpecimenFieldOut])
def save_category_fields(
    slug: str,
    term_id: uuid.UUID,
    payload: SpecimenFieldsSaveRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[SpecimenFieldOut]:
    """**시편 분류**가 갖는 기본 칸을 정한다. 통째로 바꾼다.

    이 분류에 속한 규격 **전부**가 이 칸을 갖는다. 그래서 최소로 둔다 — 그
    분류의 규격이면 대개 갖는 것만. 인장 환봉에는 폭·두께가 없고 DMA 인장
    필름에는 지지 간격이 없다. 그런 것은 규격이 자기 칸으로 더한다
    (`PATCH .../terms/{id}` 의 `extra_fields`).

    **필수로 두는 것은 신중하게.** "그 분류면 예외 없이 갖는다" 가 생각보다 잘
    깨진다 — D3039 계열 인장은 게이지 길이를 시편에 새기지 않고(그립 간 거리가
    곧 게이지), DMA 는 자유길이·폭·두께를 다 갖는 파트가 ISO 6721-4 하나뿐이다.
    필수로 두면 그런 규격은 저장 자체가 안 된다.

    ## 이미 쓰이는 키를 지우면

    그 키로 저장된 치수는 **스키마 밖이 되어 화면에서 사라진다.** 지우지는
    않는다 — 칸을 되살리면 다시 보인다. 지워 버리면 되살릴 방법이 없다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    term = db.get(VocabularyTerm, term_id)
    if term is None or term.vocabulary_id != vocabulary.id:
        raise NotFound("MNX-VOCABULARY-0004", "값을 찾을 수 없습니다.")

    # **기본 칸을 선언하는 쪽인지는 축이 정한다.**
    #
    # `attribute_source="parent"` 는 "이 축의 값은 기본 칸을 상위에서 받는다" 는
    # 뜻이다 — 그런 값은 기본 칸을 선언하지 않는다. 화면이 그것을 값의 상태로
    # 가늠하다가(상위가 비었으면 분류로 봤다) **분류를 아직 안 정한 규격**에
    # 칸을 만들어 넣었고, 그 칸은 규격의 칸도 아니고 지울 수도 없었다.
    if vocabulary.attribute_source == "parent":
        raise AppError(
            "MNX-VOCABULARY-0025",
            f"'{vocabulary.label}' 의 값은 기본 칸을 선언하지 않습니다 — "
            "상위 분류에서 받습니다. 이 값만의 칸은 값 수정의 '이 규격만의 칸' 으로 "
            "더하세요.",
            status=422,
        )

    keys = [item.key for item in payload.fields]
    if len(keys) != len(set(keys)):
        raise AppError("MNX-VOCABULARY-0016", "칸 이름이 겹칩니다.", status=422)

    existing = {
        row.key: row
        for row in db.scalars(
            select(SpecimenField).where(SpecimenField.category_term_id == term.id)
        )
    }
    # **있던 것은 고쳐 쓴다.** 지우고 새로 만들면 id 가 바뀐다.
    for order, item in enumerate(payload.fields):
        row = existing.pop(item.key, None)
        if row is None:
            row = SpecimenField(category_term_id=term.id, key=item.key)
            db.add(row)
        row.label = item.label
        for name, value in services.check_kind(item.model_dump()).items():
            setattr(row, name, value)
        row.is_required = item.is_required
        row.help = item.help
        row.sort_order = order * 10
    for leftover in existing.values():
        db.delete(leftover)

    db.commit()
    return [
        SpecimenFieldOut(
            key=field.key,
            label=field.label,
            kind=field.kind,
            choices=list(field.choices),
            symbol=field.symbol,
            dimension=field.dimension,
            si_unit=field.si_unit,
            is_required=field.is_required,
            help=field.help,
            inherited=True,
        )
        for field in services.category_fields(db, term.id)
    ]


def _terms_out(db: Session, items: list[VocabularyTerm]) -> list[TermOut]:
    """목록용. **칸 수를 한 번에 센다** — 줄마다 세면 N+1 이다."""
    if not items:
        return []
    counts = {
        term_id: count
        for term_id, count in db.execute(
            select(SpecimenField.category_term_id, func.count())
            .where(SpecimenField.category_term_id.in_([item.id for item in items]))
            .group_by(SpecimenField.category_term_id)
        )
    }
    return [_term_out(db, item, counts.get(item.id, 0)) for item in items]


@router.get("/{slug}/terms", response_model=Page[TermOut])
def search_terms(
    slug: str,
    q: str | None = Query(default=None, description="부분 일치. 별칭으로도 찾는다"),
    limit: int | None = Query(default=None, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
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
) -> Page[TermOut]:
    vocabulary = services.get_vocabulary(db, slug)
    # 값이 아니라 **표기**를 받는다 — 화면은 id 를 모르고 사람이 고른 글자만
    # 안다. 상위 축에서 그 표기를 찾는 것은 서버의 일이다.
    parent = services.parent_of(db, vocabulary, parent_value)
    size = clamp_limit(limit)
    found = services.search(
        db,
        vocabulary,
        q=q,
        limit=size,
        offset=offset,
        include_hidden=include_hidden,
        least_used=least_used,
        parent=parent,
    )
    return Page(
        items=_terms_out(db, found),
        total=services.count(
            db, vocabulary, q=q, include_hidden=include_hidden, parent=parent
        ),
        limit=size,
        offset=offset,
    )


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

    # **속성은 새로 만들 때, 그것도 실제로 보냈을 때만 받는다.**
    #
    # 이미 있는 값을 골랐을 때 조용히 덮어쓰면 피커에서 이름만 친 사람이 남의
    # 규격 치수를 지운다. 그리고 **안 보낸 것을 검사하면 안 된다** — 치수를
    # 모른 채 규격 이름부터 적는 일이 실제로 있고, 그때 필수 칸을 요구하면
    # 피커가 막힌다.
    if payload.attributes and not term.attributes:
        term.attributes = services.check_attributes(db, vocabulary, term, payload.attributes)
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
    준다 — 안 하면 화면(문자열을 읽는다)과 기준정보가 어긋난다.

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
    if "parent_value" in data:
        # 빈 문자열이면 뗀다. `exclude_unset` 이 "안 보냄" 을 이미 걸러 냈으므로
        # 여기 온 것은 사람이 명시한 것이다.
        parent = services.parent_of(db, vocabulary, data["parent_value"])
        if data["parent_value"] and parent is None:
            raise AppError(
                "MNX-VOCABULARY-0006",
                f"상위 축에서 '{data['parent_value']}' 를 찾을 수 없습니다.",
                status=422,
            )
        term.parent_term_id = parent.id if parent else None

    # 분류(상위 값)를 바꾸면 기본 칸이 바뀐다. 예전 분류의 칸으로 채워진 값은
    # 그 자리에서 거절되어야 한다 — 남겨 두면 화면이 못 보여 주는 유령이 된다.
    if "extra_fields" in data:
        term.extra_fields = services.check_extra_fields(db, term, data["extra_fields"])
    if "field_symbols" in data:
        term.field_symbols = {
            str(key): str(value).strip()
            for key, value in (data["field_symbols"] or {}).items()
            if str(value).strip()
        }
    if "ratio_checks" in data:
        term.ratio_checks = services.check_ratio_checks(
            db, vocabulary, term, data["ratio_checks"] or []
        )
    if "cross_section" in data:
        term.cross_section = services.check_cross_section(
            db, vocabulary, term, data["cross_section"] or None
        )
    if "attributes" in data or "parent_value" in data:
        attributes = data.get("attributes")
        if attributes is None:
            attributes = dict(term.attributes or {})
        term.attributes = services.check_attributes(db, vocabulary, term, attributes)

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
    found = services.search(db, vocabulary, q=None, limit=MAX_LIMIT, include_hidden=True)
    return _terms_out(db, found)


def _term_or_404(db: Session, vocabulary: Vocabulary, term_id: uuid.UUID) -> VocabularyTerm:
    term = db.get(VocabularyTerm, term_id)
    if term is None or term.vocabulary_id != vocabulary.id:
        raise NotFound("MNX-VOCABULARY-0004", "값을 찾을 수 없습니다.")
    return term


@router.get("/{slug}/terms/{term_id}/aliases", response_model=list[TermAliasOut])
def list_aliases(
    slug: str,
    term_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TermAliasOut]:
    vocabulary = services.get_vocabulary(db, slug)
    term = _term_or_404(db, vocabulary, term_id)
    rows = db.scalars(
        select(VocabularyAlias)
        .where(VocabularyAlias.term_id == term.id)
        .order_by(VocabularyAlias.alias)
    )
    return [TermAliasOut(id=row.id, alias=row.alias) for row in rows]


@router.post("/{slug}/terms/{term_id}/aliases", response_model=TermAliasOut, status_code=201)
def create_alias(
    slug: str,
    term_id: uuid.UUID,
    payload: TermAliasCreateRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TermAliasOut:
    """다른 표기를 이 값에 잇는다. **사후 병합보다 싸다.**

    등록해 두면 값을 만들 때 게이트가 별칭까지 뒤져서 애초에 중복이 안 생긴다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    term = _term_or_404(db, vocabulary, term_id)
    created = services.add_alias(db, term, payload.alias)
    db.commit()
    if created is None:
        # 이미 이 값의 표기다 — 만들지 않았지만 실패도 아니다.
        raise AppError("MNX-VOCABULARY-0009", "이미 이 값의 표기입니다.", status=409)
    return TermAliasOut(id=created.id, alias=created.alias)


@router.delete("/{slug}/terms/{term_id}/aliases/{alias_id}", status_code=204)
def delete_alias(
    slug: str,
    term_id: uuid.UUID,
    alias_id: uuid.UUID,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    vocabulary = services.get_vocabulary(db, slug)
    term = _term_or_404(db, vocabulary, term_id)
    row = db.get(VocabularyAlias, alias_id)
    if row is None or row.term_id != term.id:
        raise NotFound("MNX-VOCABULARY-0010", "표기를 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{slug}/merge-candidates", response_model=list[list[TermOut]])
def merge_candidates(
    slug: str,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[list[TermOut]]:
    """합칠 만한 값 묶음. **탐지만 한다.**

    구두점·공백까지 지운 키로 묶으므로 `'ASTM E8'` 과 `'astm-e8'` 이 함께 뜬다.
    오탐도 뜬다 — `'포스코'` 와 `'포스코특수강'` 은 다른 회사다. 그래서 합치는
    것은 사람이 누르고, 아니라고 판정한 쌍은 기억한다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    return [
        [_term_out(db, term) for term in group]
        for group in services.merge_candidates(db, vocabulary)
    ]


@router.post("/{slug}/terms/{term_id}/merge", response_model=TermOut)
def merge_term(
    slug: str,
    term_id: uuid.UUID,
    payload: MergeRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> TermOut:
    """이 값을 다른 값으로 합친다. **없어진 표기는 별칭으로 남는다.**

    그래야 다음에 누가 옛 표기를 쳐도 자동으로 흡수된다 — 병합이 일회성 청소가
    아니라 규칙이 되는 지점이다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    source = _term_or_404(db, vocabulary, term_id)
    target = _term_or_404(db, vocabulary, payload.into_id)
    services.merge(db, source, target, merged_by_id=user.id)
    db.commit()
    return _term_out(db, target)


@router.post("/{slug}/dismissals", status_code=204)
def dismiss_pair(
    slug: str,
    payload: DismissRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    """ "이 둘은 다른 값이다" 를 기억한다 — 안 기억하면 매번 다시 묻는다."""
    vocabulary = services.get_vocabulary(db, slug)
    first = _term_or_404(db, vocabulary, payload.first_id)
    second = _term_or_404(db, vocabulary, payload.second_id)
    services.dismiss(db, first, second, dismissed_by_id=user.id)
    db.commit()
    return Response(status_code=204)


@router.post("/{slug}/terms/bulk", response_model=BulkTermOut)
def create_terms_bulk(
    slug: str,
    payload: BulkTermCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BulkTermOut:
    """여러 값을 한 번에 더한다. **건별로 결과를 돌려준다.**

    개수만 주면 "50개 중 12개가 새로 생겼습니다" 로 끝나는데, 사람이 알고 싶은
    것은 어느 것이 안 생겼고 왜인지다 — 특히 **친 것과 다른 값에 붙은 경우**.
    `'PRE-8382'` 가 `'PRE8382'` 의 별칭이면 그리로 붙는데, 말 안 하면 목록에서
    못 찾고 다시 친다.

    같은 요청 안의 중복도 정직하게 처리된다. `'SECC'` 와 `'secc '` 를 함께
    보내면 앞은 `created`, 뒤는 `existing` 이다 — 방금 만들어진 것을 가리킨다.

    ## 줄마다 상위가 다를 수 있다

    창에서 고른 상위 하나를 전 줄에 붙이면 **분류가 섞인 목록을 못 넣는다.**
    줄에 `Steel<TAB>SECC` 나 `Steel > SECC` 로 적으면 그 줄만 그 상위 아래로
    간다 — 엑셀에서 두 열을 복사하면 탭으로 붙는다.

    상위를 못 찾으면 그 줄만 `rejected` 다. 그냥 만들면 그 값이 어디 속하는지
    아무도 모르는 채로 목록에 남는다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    fallback = services.parent_of(db, vocabulary, payload.parent_value)
    # 같은 상위를 줄마다 다시 조회하지 않는다 — 500줄이면 그만큼 왕복한다.
    resolved_parents: dict[str, VocabularyTerm | None] = {}

    items: list[BulkTermItemOut] = []
    for raw in payload.values:
        # **부모가 있는 축에서만 가른다.** 제조사 값에 `>` 가 들어 있을 수 있는데
        # 부모 없는 축에서 갈라 버리면 멀쩡한 값이 반토막 난다.
        line_parent, body = split_parent(raw) if vocabulary.parent_slug else (None, raw)
        cleaned = clean(body)
        if cleaned is None:
            # 빈 줄. 붙여 넣기에는 늘 섞여 있다 — 오류로 만들지 않는다.
            items.append(BulkTermItemOut(input=raw, status="skipped"))
            continue

        parent = fallback
        if line_parent:
            if line_parent not in resolved_parents:
                resolved_parents[line_parent] = services.parent_of(db, vocabulary, line_parent)
            parent = resolved_parents[line_parent]
            if parent is None:
                # **말없이 버리지 않는다.** 상위를 못 찾았는데 그냥 만들면 그
                # 값이 어디 속하는지 아무도 모르는 채로 목록에 남는다.
                items.append(
                    BulkTermItemOut(
                        input=raw,
                        status="rejected",
                        parent_value=line_parent,
                        reason=f"상위 '{line_parent}' 를 찾을 수 없습니다.",
                    )
                )
                continue

        found = services.resolve(db, vocabulary, cleaned)
        if found is not None:
            items.append(
                BulkTermItemOut(
                    input=raw,
                    status="existing",
                    value=found.value,
                    parent_value=parent.value if parent else None,
                )
            )
            continue
        created = services.resolve_or_create(
            db, vocabulary, cleaned, created_by_id=user.id, parent=parent
        )
        items.append(
            BulkTermItemOut(
                input=raw,
                status="created",
                value=created.value if created else None,
                parent_value=parent.value if parent else None,
            )
        )

    db.commit()
    return BulkTermOut(
        created=sum(1 for item in items if item.status == "created"),
        existing=sum(1 for item in items if item.status == "existing"),
        skipped=sum(1 for item in items if item.status == "skipped"),
        rejected=sum(1 for item in items if item.status == "rejected"),
        items=items,
    )


@router.post("/{slug}/terms/delete", response_model=BulkDeleteOut)
def delete_terms(
    slug: str,
    payload: BulkDeleteRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> BulkDeleteOut:
    """고른 값들을 지운다. **못 지운 것은 이유를 돌려준다.**

    ## 왜 다 못 지우나

    참조가 있으면 안 지운다. 지우면서 참조를 끊으면 그 시료가 어느 제조사였는지
    영영 알 수 없게 되는데, 그건 값을 정리하는 것과 전혀 다른 일이다. 쓰이고 있는
    값을 목록에서 치우고 싶으면 **감추기**를, 다른 값으로 흡수하려면 **병합**을
    쓴다.

    하위 값이 있어도 안 지운다 — 지우면 그것들이 고아가 된다.

    ## 요청 전체를 실패시키지 않는다

    50개를 골랐는데 3개가 막힌다고 나머지 47개를 못 지울 이유가 없다. 대신
    **막힌 것마다 무엇이 막았는지** 말한다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    items: list[BulkDeleteItemOut] = []
    for term_id in payload.ids:
        term = db.get(VocabularyTerm, term_id)
        if term is None or term.vocabulary_id != vocabulary.id:
            items.append(
                BulkDeleteItemOut(
                    id=term_id, value="?", deleted=False, reason="값을 찾을 수 없습니다."
                )
            )
            continue
        value = term.value
        reason = services.delete_term(db, term)
        items.append(
            BulkDeleteItemOut(id=term_id, value=value, deleted=reason is None, reason=reason)
        )

    db.commit()
    return BulkDeleteOut(
        deleted=sum(1 for item in items if item.deleted),
        blocked=sum(1 for item in items if not item.deleted),
        items=items,
    )
