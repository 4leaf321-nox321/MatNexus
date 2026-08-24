"""기준정보 API — 피커가 부르는 것.

**전체를 주지 않는다.** 기준정보가 수만 개가 되면 브라우저로 다 보낼 수 없고, 보내
봐야 화면은 60개만 그린다. 검색어를 받아 상한을 걸어 돌려준다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.vocabulary import services, standards
from app.modules.vocabulary.models import (
    SpecimenField,
    Vocabulary,
    VocabularyAlias,
    VocabularyDriftCheck,
    VocabularyTerm,
)
from app.modules.vocabulary.normalize import clean, compare_key, split_row
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
    StandardImportRequest,
    StandardTemplateOut,
    TermAliasCreateRequest,
    TermAliasOut,
    TermCreateRequest,
    TermOut,
    TermUpdateRequest,
    VocabularyOut,
)
from app.shared import audit
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


@router.get("/specimen-standards/catalog", response_model=list[StandardTemplateOut])
def list_standard_catalog(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[StandardTemplateOut]:
    """가져올 수 있는 표준 규격. **치수 값은 없다.**

    근거 문서가 2차 출처라(본문이 유료다) 숫자를 심으면 검증 안 된 값이 시스템의
    정본이 된다 — 실제로 출처끼리 어긋난 곳이 있다. 칸과 기호는 판이 바뀌어도
    그대로이므로 구조만 깔고 숫자는 사람이 규격서를 보고 넣는다.
    """
    axis = services.get_vocabulary(db, "specimen_standard")
    taken = {
        row
        for row in db.scalars(
            select(VocabularyTerm.normalized).where(VocabularyTerm.vocabulary_id == axis.id)
        )
    }
    return [
        StandardTemplateOut(
            key=str(item["key"]),
            value=str(item["value"]),
            category=str(item["category"]),
            family=str(item["family"]),
            fields=[SpecimenFieldOut(**one) for one in item["fields"]],
            cross_section=item.get("cross_section"),
            attributes=dict(item.get("attributes") or {}),
            ratio_checks=[RatioCheckOut(**one) for one in item.get("ratio_checks", [])],
            help=item.get("help"),
            taken=compare_key(str(item["value"])) in taken,
        )
        for item in standards.CATALOG
    ]


@router.post("/specimen-standards/import", response_model=list[TermOut])
def import_standards(
    payload: StandardImportRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> list[TermOut]:
    """고른 표준 규격을 값으로 만든다.

    **이름을 바꿔 한 벌 더 만들 수 있다.** 이 기능이 가장 값을 하는 때가 그때다 —
    같은 규격을 부서가 자기 치수로 쓰는 경우다. 규격서가 범위나 최소만 주는 칸이
    많아서(`R >= 25`, `폭 5~25.4`) 실제 값은 부서마다 갈린다.

    **이미 있는 이름은 건너뛴다.** 덮어쓰면 사람이 넣어 둔 치수가 사라진다.

    분류가 없으면 그 항목은 만들지 않는다. 분류가 칸을 정하는 쪽이라, 없는 채로
    만들면 `게이지 길이` 같은 기본 칸이 안 붙는다.
    """
    axis = services.get_vocabulary(db, "specimen_standard")
    category_axis = services.get_vocabulary(db, "specimen_category")
    templates = {str(one["key"]): one for one in standards.CATALOG}
    made: list[VocabularyTerm] = []

    for wanted in payload.items:
        item = templates.get(wanted.key)
        if item is None:
            raise AppError(
                "MNX-VOCABULARY-0029", f"모르는 표준 규격입니다: {wanted.key}", status=422
            )
        # **이름을 바꿔 한 벌 더 만들 수 있다.** 같은 규격을 부서가 자기 치수로
        # 쓰는 경우가 이 기능이 가장 값을 하는 자리다.
        name = clean(wanted.value) if wanted.value else clean(str(item["value"]))
        normalized = compare_key(name)
        if db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == axis.id,
                VocabularyTerm.normalized == normalized,
            )
        ):
            continue
        category = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == category_axis.id,
                VocabularyTerm.normalized == compare_key(str(item["category"])),
            )
        )
        if category is None:
            raise AppError(
                "MNX-VOCABULARY-0028",
                f"시편 분류 '{item['category']}' 가 없습니다. 분류를 먼저 만드세요 — "
                "분류가 기본 칸을 정합니다.",
                status=422,
            )
        term = VocabularyTerm(
            vocabulary_id=axis.id,
            value=name,
            normalized=normalized,
            parent_term_id=category.id,
            created_by_id=user.id,
        )
        db.add(term)
        db.flush()

        # **위가 이미 주는 칸은 다시 선언하지 않는다.** 축이 판을, 분류가 게이지
        # 길이를 준다 — 같은 키가 둘이면 어느 쪽이 이기는지 사람이 알 수 없다.
        # 다만 **글자는 규격마다 다르므로** 그것만 덮어쓴다(E8 은 G, ISO 는 L₀).
        above = {field.key for field in services.attribute_fields(db, axis, term)}
        term.extra_fields = services.check_extra_fields(
            db, term, [one for one in item["fields"] if one["key"] not in above]
        )
        term.field_symbols = {
            str(one["key"]): str(one["symbol"])
            for one in item["fields"]
            if one["key"] in above and one.get("symbol")
        }
        if item.get("cross_section"):
            term.cross_section = str(item["cross_section"])
        # **규격이 딱 정해 둔 값만 온다.** 최소값·범위·근사·재료가 정하는 것은
        # 카탈로그에 없다 — 그런 칸은 빈 채로 와서 사람이 채운다.
        if item.get("attributes"):
            term.attributes = services.check_attributes(db, axis, term, item["attributes"])
        db.flush()
        if item.get("ratio_checks"):
            term.ratio_checks = services.check_ratio_checks(
                db, axis, term, item["ratio_checks"]
            )
        made.append(term)

    db.commit()
    return [_term_out(db, term) for term in made]


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
        description="상위 축의 값으로 좁힌다. 'Steel' 을 주면 그 아래 Grade 만",
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
        # **새 값이 부모를 물려받는다.** Steel 을 고른 상태에서 Grade 를 추가하면
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
    before = term.value
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

    # **이름 하나가 수천 건을 바꾼다.** 외래키라 참조가 저절로 따라오고, Grade 면
    # 재료 이름까지 다시 만들어진다(ADR 0004). 그렇게 넓게 퍼지는 변경이 아무
    # 흔적 없이 일어나면, 나중에 "이 재료 이름이 왜 이렇죠" 에 답할 근거가 없다.
    #
    # 감춤(`status`)은 남기지 않는다 — 피커에서만 사라지고 자료는 그대로다.
    if before != term.value:
        audit.record(
            db,
            action=audit.VOCABULARY_RENAMED,
            actor=user,
            target_table="vocabulary_terms",
            target_id=term.id,
            target_label=f"{vocabulary.label} · {term.value}",
            changes={"value": {"before": before, "after": term.value}},
        )

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


def _add_aliases(db: Session, term: VocabularyTerm, aliases: list[str]) -> list[str]:
    """붙여넣은 줄의 별칭 열을 이 값에 단다. **새로 단 것만 돌려준다.**

    별칭은 사후 병합보다 싸다 — 등록해 두면 값을 만들 때 게이트가 별칭까지 뒤져서
    애초에 중복이 안 생긴다. 그런데 지금까지는 값을 넣고 나서 하나씩 달아야 해서,
    엑셀에 이미 적혀 있어도 옮길 길이 없었다.

    **이미 달린 것은 조용히 지나간다.** 같은 표를 두 번 붙여넣는 일이 흔한데,
    그때마다 실패로 세면 결과가 붉게 뒤덮인다.
    """
    added: list[str] = []
    for alias in aliases:
        if services.add_alias(db, term, alias) is not None:
            added.append(alias)
    return added


@dataclass(frozen=True)
class _Planned:
    """붙여넣은 한 줄을 **가르기만** 한 결과.

    **있는 값인지는 여기서 정하지 않는다.** 같은 요청 안에서 `SECC` 와 `secc `
    를 함께 보내면 뒤엣것은 **방금 만들어진 것**을 가리켜야 하는데, 앞에서 한꺼번에
    조회해 두면 그 사실을 못 본다.
    """

    raw: str
    parent: VocabularyTerm | None
    parent_label: str | None
    cleaned: str | None
    aliases: list[str]
    reason: str | None
    attributes: dict[str, float | str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _declared(payload: BulkTermCreateRequest) -> list[services.Field]:
    """이 붙여넣기가 **선언하겠다는 칸**. 축·분류가 안 주는 것들이다."""
    return [
        services.Field(
            key=one.key,
            label=one.label,
            dimension=one.dimension,
            si_unit=one.si_unit,
            is_required=one.is_required,
            help=one.help,
            inherited=False,
            kind=one.kind,
            choices=tuple(one.choices),
            symbol=one.symbol,
        )
        for one in payload.columns
    ]


def _by_header(
    raw: str, header: list[str], *, has_parent: bool
) -> tuple[str | None, str, list[str]]:
    """헤더가 있을 때 값·상위·별칭을 **열 이름**으로 찾는다.

    자리로 읽으면 열 순서를 바꾼 표에서 조용히 어긋난다 — 엑셀에서 열을 옮기는
    일은 흔하다.
    """
    cells = [part.strip() for part in raw.split("\t")]
    names = [compare_key(one) for one in header]

    def pick(candidates: tuple[str, ...]) -> str:
        wanted = {compare_key(one) for one in candidates}
        for index, name in enumerate(names):
            if name in wanted and index < len(cells):
                return cells[index]
        return ""

    value = pick(services.HEADER_VALUE)
    parent = pick(services.HEADER_PARENT) if has_parent else ""
    aliases_cell = pick(services.HEADER_ALIAS)
    aliases = [
        part.strip() for part in aliases_cell.replace(",", ";").split(";") if part.strip()
    ]
    return parent or None, value, aliases


def _fields_for(
    db: Session, vocabulary: Vocabulary, parent: VocabularyTerm | None
) -> list[services.Field]:
    """아직 안 만든 값이 가질 칸. **축의 칸 + 그 상위(분류)의 기본 칸.**

    자기만의 칸(`extra_fields`)은 아직 없다 — 값이 생긴 뒤에 더하는 것이다.
    """
    return services.attribute_fields(
        db,
        vocabulary,
        VocabularyTerm(
            vocabulary_id=vocabulary.id,
            parent_term_id=parent.id if parent else None,
            extra_fields=[],
            field_symbols={},
        ),
    )


def _plan_bulk(
    db: Session,
    vocabulary: Vocabulary,
    values: list[str],
    fallback_parent: str | None,
    *,
    has_header: bool = False,
    declared: list[services.Field] | None = None,
) -> list[_Planned]:
    """줄들을 상위·값·별칭으로 가른다. **아무것도 쓰지 않는다.**

    미리보기와 실제 추가가 **같은 코드로 답해야 한다.** 화면이 규칙을 다시
    구현하면 두 구현이 갈라지고, 그러면 미리보기가 거짓말을 한다 — 이름을 화면이
    만들던 시절에 이미 겪은 실패다(ADR 0004).
    """
    fallback = services.parent_of(db, vocabulary, fallback_parent)
    # 같은 상위를 줄마다 다시 조회하지 않는다 — 500줄이면 그만큼 왕복한다.
    resolved: dict[str, VocabularyTerm | None] = {}

    # **헤더는 상위마다 다르게 읽힌다.** 시편 규격의 칸은 분류가 정하므로,
    # `인장` 줄과 `DMA` 줄에서 같은 열 이름이 다른 칸일 수 있다.
    header: list[str] = []
    columns_for: dict[uuid.UUID | None, list[services.Column]] = {}
    body = list(values)
    if has_header:
        while body and not (body[0] or "").strip():
            body.pop(0)  # 붙여넣기 앞에 빈 줄이 섞이는 일이 흔하다
        if body:
            header = [part.strip() for part in body.pop(0).split("\t")]

    rows: list[_Planned] = []
    for raw in body:
        # **부모가 있는 축에서만 가른다.** 제조사 값에 `>` 가 들어 있을 수 있는데
        # 부모 없는 축에서 갈라 버리면 멀쩡한 값이 반토막 난다.
        if header:
            line_parent, body_text, aliases = _by_header(
                raw, header, has_parent=bool(vocabulary.parent_slug)
            )
        else:
            line_parent, body_text, aliases = split_row(
                raw, has_parent=bool(vocabulary.parent_slug)
            )
        cleaned = clean(body_text)
        if cleaned is None:
            # 빈 줄. 붙여 넣기에는 늘 섞여 있다 — 오류로 만들지 않는다.
            rows.append(_Planned(raw, None, None, None, [], None))
            continue

        parent = fallback
        if line_parent:
            if line_parent not in resolved:
                resolved[line_parent] = services.parent_of(db, vocabulary, line_parent)
            parent = resolved[line_parent]
            if parent is None:
                # **말없이 버리지 않는다.** 상위를 못 찾았는데 그냥 만들면 그
                # 값이 어디 속하는지 아무도 모르는 채로 목록에 남는다.
                rows.append(
                    _Planned(
                        raw,
                        None,
                        line_parent,
                        cleaned,
                        aliases,
                        f"상위 '{line_parent}' 를 찾을 수 없습니다.",
                    )
                )
                continue

        attributes: dict[str, float | str] = {}
        warnings: list[str] = []
        if header:
            key = parent.id if parent else None
            if key not in columns_for:
                # **선언할 칸도 후보다.** 안 그러면 값이 있는데 갈 곳이 없다고
                # 떨어뜨리고, 사람은 규격마다 창을 열어 칸부터 만들어야 한다.
                available = _fields_for(db, vocabulary, parent)
                known = {item.key for item in available}
                available += [item for item in (declared or []) if item.key not in known]
                columns_for[key] = services.read_header(header, available)
            cells = [part.strip() for part in raw.split("\t")]
            for index, column in enumerate(columns_for[key]):
                cell = cells[index] if index < len(cells) else ""
                if column.kind == "unknown":
                    # **말없이 버리지 않는다.** 값이 있는데 갈 곳이 없으면 말한다.
                    if cell and column.reason and column.reason not in warnings:
                        warnings.append(column.reason)
                    continue
                if column.kind != "field":
                    continue
                value = services.read_cell(column, cell)
                if value is not None and column.field is not None:
                    attributes[column.field.key] = value

        rows.append(
            _Planned(
                raw,
                parent,
                parent.value if parent else None,
                cleaned,
                aliases,
                None,
                attributes,
                warnings,
            )
        )
    return rows


@router.get("/{slug}/paste-columns", response_model=list[SpecimenFieldOut])
def list_paste_columns(
    slug: str,
    parent_value: str | None = Query(default=None),
    like: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SpecimenFieldOut]:
    """표로 붙여넣을 때 **쓸 수 있는 열**. 값·상위·표기 말고 속성 쪽이다.

    **사용자가 무엇을 적어야 하는지 몰랐다.** 헤더에 칸 이름을 적으라고만 하면
    그 이름이 무엇인지 알 방법이 없다 — 규격의 칸은 분류가 정하고, 분류마다
    다르다. 화면이 실제 목록을 보여 주고 고르게 해야 한다.

    상위(분류)에 따라 답이 달라진다 — `인장` 과 `DMA` 의 기본 칸이 다르다.

    `like` 를 주면 **그 값이 가진 칸까지** 낸다. 환봉 규격을 여러 개 만들 때
    `직경` 을 매번 손으로 만들지 않아도 된다 — 이미 만들어 둔 규격에서 가져온다.
    그 칸은 분류가 주는 것이 아니라 **그 값만의 칸**이라 `inherited` 가 거짓으로
    오고, 새로 만드는 값에는 함께 **선언**해 줘야 값이 들어간다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    parent = services.parent_of(db, vocabulary, parent_value)
    fields = _fields_for(db, vocabulary, parent)
    if like:
        template = services.resolve(db, vocabulary, like)
        if template is not None:
            known = {item.key for item in fields}
            fields += [
                item
                for item in services.attribute_fields(db, vocabulary, template)
                if item.key not in known
            ]
    return [
        SpecimenFieldOut(
            key=item.key,
            label=item.label,
            kind=item.kind,
            choices=list(item.choices),
            symbol=item.symbol,
            dimension=item.dimension,
            si_unit=item.si_unit,
            is_required=item.is_required,
            help=item.help,
            inherited=item.inherited,
        )
        for item in fields
    ]


@router.post("/{slug}/terms/bulk/preview", response_model=BulkTermOut)
def preview_terms_bulk(
    slug: str,
    payload: BulkTermCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BulkTermOut:
    """붙여넣은 줄이 **어떻게 들어갈지** 미리 말한다. 아무것도 쓰지 않는다.

    **보내 봐야 아는 상태였다.** 엑셀에서 복사한 표가 상위·값·별칭으로 어떻게
    갈리는지, 어느 줄이 이미 있는 값에 붙는지, 어느 줄이 상위를 못 찾아 떨어지는지
    누르기 전에는 알 수 없었다.

    **화면이 다시 계산하지 않는다.** 규칙을 두 곳에 두면 갈라지고, 그러면
    미리보기가 거짓말을 한다 — 그건 없는 것보다 나쁘다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    items: list[BulkTermItemOut] = []
    # **앞 줄이 만들 값도 센다.** 같은 표에 같은 값이 두 번 있는 일이 흔한데,
    # 둘 다 '새로' 로 세면 실제로 생길 개수와 어긋난다.
    coming: set[str] = set()

    for row in _plan_bulk(
        db,
        vocabulary,
        payload.values,
        payload.parent_value,
        has_header=payload.has_header,
        declared=_declared(payload),
    ):
        if row.cleaned is None:
            items.append(BulkTermItemOut(input=row.raw, status="skipped"))
            continue
        if row.reason:
            items.append(
                BulkTermItemOut(
                    input=row.raw,
                    status="rejected",
                    parent_value=row.parent_label,
                    reason=row.reason,
                )
            )
            continue

        found = services.resolve(db, vocabulary, row.cleaned)
        key = compare_key(row.cleaned)
        items.append(
            BulkTermItemOut(
                input=row.raw,
                status="existing" if found or key in coming else "new",
                value=found.value if found else row.cleaned,
                parent_value=row.parent_label,
                aliases=row.aliases,
                attributes=row.attributes,
                warnings=row.warnings,
            )
        )
        coming.add(key)
    return BulkTermOut(
        created=sum(1 for item in items if item.status == "new"),
        existing=sum(1 for item in items if item.status == "existing"),
        skipped=sum(1 for item in items if item.status == "skipped"),
        rejected=sum(1 for item in items if item.status == "rejected"),
        items=items,
    )


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

    ## 엑셀에서 복사한 열이 그대로 붙는다

        부모 있는 축   Steel <TAB> SECC <TAB> SECC-1;SECC(주)
        부모 없는 축   포스코 <TAB> POSCO;포스코(주)

    마지막 열은 **별칭**이다. 별칭은 사후 병합보다 싸다 — 등록해 두면 값을 만들
    때 게이트가 별칭까지 뒤져서 애초에 중복이 안 생긴다.

    ## 줄마다 상위가 다를 수 있다

    창에서 고른 상위 하나를 전 줄에 붙이면 **분류가 섞인 목록을 못 넣는다.**
    상위를 못 찾으면 그 줄만 `rejected` 다.

    미리보기(`.../bulk/preview`)가 **같은 해석 코드**를 쓴다 — 두 곳에 두면
    갈라지고, 그러면 미리보기가 거짓말을 한다.
    """
    vocabulary = services.get_vocabulary(db, slug)
    items: list[BulkTermItemOut] = []

    for row in _plan_bulk(
        db,
        vocabulary,
        payload.values,
        payload.parent_value,
        has_header=payload.has_header,
        declared=_declared(payload),
    ):
        if row.cleaned is None:
            items.append(BulkTermItemOut(input=row.raw, status="skipped"))
            continue
        if row.reason:
            items.append(
                BulkTermItemOut(
                    input=row.raw,
                    status="rejected",
                    parent_value=row.parent_label,
                    reason=row.reason,
                )
            )
            continue

        # **그때그때 조회한다.** 앞 줄이 방금 만든 값을 봐야 한다 — 미리
        # 조회해 두면 `SECC` 와 `secc ` 를 둘 다 '새로' 로 세게 된다.
        found = services.resolve(db, vocabulary, row.cleaned)
        term = found or services.resolve_or_create(
            db, vocabulary, row.cleaned, created_by_id=user.id, parent=row.parent
        )
        if term is not None and payload.columns:
            # **값이 들어가려면 칸이 있어야 한다.** 이미 있는 칸은 안 건드린다 —
            # 사람이 고쳐 둔 이름·단위가 붙여넣기 한 번에 되돌아가면 안 된다.
            have = {item.key for item in services.attribute_fields(db, vocabulary, term)}
            missing = [one.model_dump() for one in payload.columns if one.key not in have]
            if missing:
                term.extra_fields = services.check_extra_fields(
                    db, term, [*(term.extra_fields or []), *missing]
                )
                db.flush()

        stored: dict[str, float | str] = {}
        if term is not None and row.attributes:
            # **있는 값의 속성은 안 덮는다.** 사람이 규격서를 보고 고친 값이
            # 붙여넣기 한 번에 되돌아가면 안 된다 — 빈 칸만 채운다.
            merged = {**row.attributes, **dict(term.attributes or {})}
            stored = services.check_attributes(db, vocabulary, term, merged)
            term.attributes = stored
        items.append(
            BulkTermItemOut(
                input=row.raw,
                status="existing" if found else "created",
                value=term.value if term else None,
                parent_value=row.parent_label,
                aliases=_add_aliases(db, term, row.aliases) if term else [],
                attributes=stored,
                warnings=row.warnings,
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
