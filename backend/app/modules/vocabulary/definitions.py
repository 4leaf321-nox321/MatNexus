"""기준정보의 기본 축.

**축은 데이터가 아니라 스키마에 가깝다.** 축이 하나 늘어난다는 것은 어딘가의
컬럼이 기준정보를 가리키게 된다는 뜻이고, 그건 코드가 바뀌는 일이다. 그래서 API 로
만들지 않고 여기 적는다 — 시험 종류의 `BUILTIN_TEST_TYPES` 와 같은 자리다.

마이그레이션도 같은 것을 심지만 거기 있는 것은 **그때의 스냅샷**이다. 이 파일은
새 DB(테스트·개발 초기화)를 위한 것이라 둘 다 필요하다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import Vocabulary

#: (slug, label, entry_policy, sort_order)
#:
#: `open` 은 사용자가 피커에서 즉석 추가할 수 있다. `closed` 는 관리자가 등록한
#: 값만 고른다 — 미리 정해야 하는 분류다.
#: (slug, label, entry_policy, sort_order, parent_slug, attribute_source)
#:
#: **분류는 사슬이다.** Metal → Steel → SECC. 평평하게 두면 Polymer + PP + SECC
#: 같은 조합을 아무도 안 막고, 강종이 수만 개일 때 피커가 전체를 보여 준다.
BUILTIN_VOCABULARIES: list[tuple[str, str, str, int, str | None, str | None]] = [
    ("manufacturer", "제조사", "open", 10, None, None),
    # **유통사와 주 벤더가 한 축을 공유한다.** 같은 회사가 어떤 로트에서는
    # 유통사고 다른 로트에서는 주 벤더다. 축을 나누면 같은 회사가 두 목록에
    # 따로 쌓이고, 그 둘을 합칠 방법도 없다.
    ("vendor", "거래처", "open", 20, None, None),
    ("sales_type", "판매 유형", "open", 30, None, None),
    # **시편 분류가 기본 칸을 갖는다.** "인장 시편이면 늘 게이지 길이가
    # 필요하다" 처럼, 그 분류의 규격 전부가 갖는 치수다(`specimen_fields`).
    ("specimen_category", "시편 분류", "open", 38, None, None),
    # **규격은 분류 아래 산다.** 부모 축 기계를 그대로 쓴다(`grade` 의 부모가
    # `category` 이듯) — `kind` 같은 컬럼을 따로 두면 같은 것을 두 방식으로
    # 표현하게 된다.
    #
    # `attribute_source="parent"` 는 "기본 칸을 상위 값이 갖는다" 는 뜻이다.
    # 규격은 거기에 자기만의 칸을 더한다(`extra_fields`) — `ASTM E8 R1` 은
    # 환봉이라 직경이 필요하고 `JIS 5호` 는 평판이라 필요 없다.
    ("specimen_standard", "시편 규격", "open", 40, "specimen_category", "parent"),
    ("instrument", "장비", "open", 50, None, None),
    # **가장 큰 축이고 이득도 가장 크다.** 지금은 SECC/secc/S.E.C.C 가 서로
    # 다른 재료 셋을 만든다. 다만 강종은 재료 이름을 만드는 값이라(ADR 0004)
    # 값 이름을 고치면 재료·시료·시편·시험 이름이 전부 따라 바뀐다.
    ("family", "Family", "open", 1, None, None),
    ("category", "Category", "open", 2, "family", None),
    ("grade", "강종", "open", 5, "category", None),
    # **용도는 재료의 성질이다**(전에는 시료에 있었다). "도어 이너용 재료가 뭐가
    # 있나" 가 집계 질문이 되려면 자유 문자열이면 안 된다 — `도어`/`Door`/`도어 `
    # 가 갈리면 그 질문에 답이 셋 나온다.
    ("product", "적용 제품", "open", 60, None, None),
    # **부위를 제품 아래에 두지 않는다.** 계층은 값 하나에 부모 하나인데(`grade`
    # 의 부모가 `category` 하나이듯), `이너 패널` 은 도어에도 후드에도 쓰인다.
    # 부모를 붙이면 먼저 들어온 제품이 이기고 나머지는 조용히 틀린 곳에 매달린다.
    ("part", "적용 부위", "open", 70, None, None),
]

#: **전부 `open` 이다.** `closed` 는 만들어 두고 안 켠다.
#:
#: 막았을 때 사람이 어디로 가는지가 문제다. 첫 발포재를 등록하려는데 `Foam` 이
#: 목록에 없으면 관리자를 찾아가거나 — 더 흔하게는 **`Metal` 로 대충 고르고
#: 넘어간다.** 그러면 분류가 지켜진 것이 아니라 조용히 틀린 것이다.
#:
#: `closed` 가 값을 하는 자리는 **외부 시스템이 정본을 주는 축**이다(ReportArchive
#: 는 모델·BOM 코드에 쓴다). 거기서는 정본에 없는 값을 만드는 것 자체가 오류다.
#: MatNexus 에는 아직 그런 축이 없다 — 모든 값을 사람이 친다. Phase 6 에서 장비
#: 커넥터가 붙으면 그때 켠다.


#: 기본 시편 분류와 그 분류의 **기본 치수 칸**.
#:
#: (분류 값, [(키, 이름, 차원, SI 단위, 필수, 도움말)])
#:
#: **최소로 둔다.** 그 분류의 규격이면 **예외 없이** 갖는 것만 기본이다 —
#: 인장 환봉에는 폭·두께가 없고, DMA 인장 필름에는 지지 간격이 없다. 그런
#: 것은 규격이 자기 칸으로 더한다.
BUILTIN_SPECIMEN_CATEGORIES: list[
    tuple[str, list[tuple[str, str, str, str, bool, str | None]]]
] = [
    (
        "인장",
        [
            (
                "gauge_length",
                "게이지 길이",
                "length",
                "m",
                True,
                "변위를 이 길이로 나눠 변형률을 만듭니다. 평판이든 환봉이든 있습니다.",
            ),
            (
                "total_length",
                "전체 길이",
                "length",
                "m",
                False,
                None,
            ),
        ],
    ),
    (
        "DMA",
        [
            (
                "free_length",
                "자유 길이",
                "length",
                "m",
                True,
                "클램프 사이의 길이. 계산에 들어가는 것은 전체 길이가 아니라 이 값입니다.",
            ),
            ("width", "폭", "length", "m", True, None),
            ("thickness", "두께", "length", "m", True, None),
        ],
    ),
]


def ensure_builtin_specimen_categories(db: Session) -> list[str]:
    """기본 분류와 그 기본 칸을 보장한다. 새로 만든 값을 돌려준다.

    **이미 있는 것은 손대지 않는다.** 운영 중에 관리자가 칸을 고쳤을 수 있고,
    배포가 그것을 되돌리면 안 된다(시험 종류·축과 같은 판단).
    """
    from app.modules.vocabulary.models import SpecimenField, VocabularyTerm
    from app.modules.vocabulary.normalize import clean, compare_key

    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "specimen_category"))
    if axis is None:
        return []

    created: list[str] = []
    for value, fields in BUILTIN_SPECIMEN_CATEGORIES:
        term = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == axis.id,
                VocabularyTerm.normalized == compare_key(value),
            )
        )
        if term is None:
            term = VocabularyTerm(
                vocabulary_id=axis.id,
                value=clean(value),
                normalized=compare_key(value),
            )
            db.add(term)
            db.flush()
            created.append(value)
        existing = set(
            db.scalars(
                select(SpecimenField.key).where(SpecimenField.category_term_id == term.id)
            )
        )
        for order, (key, label, dimension, si_unit, required, help_text) in enumerate(fields):
            if key in existing:
                continue
            db.add(
                SpecimenField(
                    category_term_id=term.id,
                    key=key,
                    label=label,
                    dimension=dimension,
                    si_unit=si_unit,
                    is_required=required,
                    help=help_text,
                    sort_order=order * 10,
                )
            )
    return created


def ensure_builtin_vocabularies(db: Session) -> list[str]:
    """기본 축을 보장한다. 새로 만든 것의 slug 를 돌려준다.

    **이미 있는 축은 손대지 않는다.** 운영 중에 관리자가 라벨이나 정책을 바꿨을
    수 있고, 그것을 배포가 되돌리면 안 된다(시험 종류와 같은 판단).
    """
    existing = set(db.scalars(select(Vocabulary.slug)))
    created: list[str] = []
    for slug, label, policy, order, parent, attribute_source in BUILTIN_VOCABULARIES:
        if slug in existing:
            continue
        db.add(
            Vocabulary(
                slug=slug,
                label=label,
                entry_policy=policy,
                sort_order=order,
                parent_slug=parent,
                attribute_source=attribute_source,
            )
        )
        created.append(slug)
    if created:
        db.flush()
    return created
