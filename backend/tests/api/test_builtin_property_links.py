"""기본 물성 항목의 **연결이 씨앗이다** — 배포가 심는다.

선언 물성이 카드의 빈 칸으로 흐르려면 기준정보 항목이 물성 키에 이어져 있어야
한다. 그 연결은 지금까지 사람이 화면에서만 만들 수 있었고, 그래서 개발 DB 에서
이어 둔 것이 운영에는 없었다 — 같은 코드가 서버마다 다르게 움직였다.

이 시험이 지키는 것:

    있으면 잇는다          항목과 문헌 정의가 다 있을 때
    두 번 돌려도 하나      배포마다 도는 것이라 멱등이어야 한다
    차원이 다르면 안 잇는다 숫자가 다른 단위 자리에 조용히 들어간다
    정의가 없으면 건너뛴다  갓 설치한 서버의 첫 배포가 그렇다
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared import coverage
from app.shared.text import compare_key

#: 시험이 쓰는 한 쌍 — 이름은 기준정보 씨앗이 정한다.
KEY = "thermal.specific_heat"
ITEM = "비열"


def _definition(db: Session, key: str, si_unit: str, name: str) -> None:
    db.add(
        CatalogDefinition(
            key=key, domain=key.split(".")[0], name=name, value_type="numeric", si_unit=si_unit
        )
    )
    db.commit()


def _links(db: Session) -> list[PropertyLink]:
    return list(db.scalars(select(PropertyLink)))


def test_연결_표의_항목이_전부_씨앗에_있다() -> None:
    """**이름을 못 찾으면 그 줄은 조용히 안 심긴다.** 표를 늘릴 때 오타 한 자가
    그렇게 사라지므로, 두 표가 맞는지 여기서 본다."""
    from app.modules.catalog.links import BUILTIN_LINKS
    from app.shared import property_names

    unknown = [
        one for one, _key, _scale in BUILTIN_LINKS if property_names.builtin_item(one) is None
    ]
    assert unknown == []


def test_항목과_정의가_있으면_잇는다(db: Session) -> None:
    ensure_builtin_property_items(db)
    _definition(db, KEY, "J/(kg.K)", "Specific heat")

    made = ensure_builtin_property_links(db)
    db.commit()

    assert any(ITEM in line for line in made)
    # **카드가 읽는 다리가 그대로 선다** — 이 지도가 선언 물성을 칸에 앉힌다.
    assert coverage.item_property_map(db)[ITEM] == KEY


def test_두_번_돌려도_하나다(db: Session) -> None:
    """배포마다 도는 씨앗이다. 두 번째에 또 만들면 같은 연결이 쌓인다."""
    ensure_builtin_property_items(db)
    _definition(db, KEY, "J/(kg.K)", "Specific heat")

    ensure_builtin_property_links(db)
    db.commit()
    again = ensure_builtin_property_links(db)
    db.commit()

    assert again == []
    assert len([one for one in _links(db) if one.property_key == KEY]) == 1


def test_차원이_다르면_안_잇는다(db: Session) -> None:
    """열전도율을 「비열」 에 이어 두면 W/(m·K) 숫자가 J/(kg·K) 자리에 들어간다 —
    숫자는 그럴듯하다. **안 잇는 것이 맞는 결과다.**"""
    ensure_builtin_property_items(db)
    _definition(db, KEY, "W/(m.K)", "Wrong dimension")

    made = ensure_builtin_property_links(db)
    db.commit()

    assert not any(ITEM in line for line in made)
    assert [one for one in _links(db) if one.property_key == KEY] == []


def test_문헌_정의가_없으면_건너뛴다(db: Session) -> None:
    """갓 설치한 서버의 첫 배포가 그렇다 — 카탈로그 적재가 뒤에 온다. 막지 않고
    넘어가고, 배포가 적재 뒤에 한 번 더 부른다."""
    ensure_builtin_property_items(db)

    made = ensure_builtin_property_links(db)
    db.commit()

    assert made == []
    assert _links(db) == []


def test_항목_이름을_고쳐도_이름으로_찾는다(db: Session) -> None:
    """이름의 정본은 기준정보 씨앗이다. 씨앗이 아는 이름이 없으면 안 잇는다 —
    **짐작으로 다른 항목에 붙이지 않는다.**"""
    ensure_builtin_property_items(db)
    _definition(db, KEY, "J/(kg.K)", "Specific heat")
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    assert axis is not None
    term = db.scalar(
        select(VocabularyTerm).where(
            VocabularyTerm.vocabulary_id == axis.id,
            VocabularyTerm.normalized == compare_key(ITEM),
        )
    )
    assert term is not None
    term.value = "비열(고쳐 부른 이름)"
    term.normalized = compare_key(term.value)
    db.commit()

    made = ensure_builtin_property_links(db)
    db.commit()

    assert made == []
    assert _links(db) == []
