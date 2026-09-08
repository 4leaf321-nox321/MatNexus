"""물성 이름 해소 — **「항복응력」이 어느 물성인가.**

MCP/AI 가 값을 묻기 전에 반드시 거치는 자리다. 여러 모듈(catalog·vocabulary·
processing)을 가로지르므로 `shared` 에 있다(AGENTS.md: 로직 공유는 shared 를 거친다).

## 고르지 않는다 — 후보를 준다

이 저장소의 규율이다(경화식을 나란히 주는 것과 같다). 「항복」 하나로 후보가 일곱인데
하나를 골라 주면 **왜 그것인지 부르는 쪽이 알 수 없다.** 특히:

    rheological.yield_stress    「항복응력」      9건   8 ~ 20 Pa
    mechanical.yield_strength   「항복강도」    486건   0.1 ~ 2310 MPa

이름이 정확히 「항복응력」인 것은 **유변학** 물성이다. 사람이 「항복응력 200MPa」
라고 물으면 십중팔구 금속의 항복강도를 뜻하는데, 이름만 맞춰 하나를 고르면
**9건짜리 엉뚱한 물성**을 준다. 그래서 후보를 도메인·단위·값 개수와 함께 돌려주고,
**갈리면 부르는 쪽이 되묻게** 한다.

## 순위는 근거를 갖는다

    1. 별칭·이름·기호가 **정확히** 맞나        exact
    2. 사내 물성 항목과 이어져 있나            linked   — 우리가 실제로 쓰는 물성
    3. 값이 몇 건이나 있나                     values   — 0건짜리를 1등으로 주면 안 된다
    4. 이름이 부분적으로 맞나                  partial

**값 개수를 쓰는 이유**: 「고를 수는 있는데 결과가 0건인 값이 목록에 있으면 사람은
필터를 의심한다」 — 기준정보 피커가 개수를 함께 보여 주는 것과 같은 판단이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogValue
from app.modules.catalog.ontology_models import PropertyAlias, PropertyLink
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared.text import compare_key

#: 사내 물성 항목이 사는 축.
ITEM_AXIS = "property_item"

#: 한 번에 돌려주는 후보 수. **넘으면 몇 개가 더 있는지 말한다** — 조용히 자르지
#: 않는다(`OptionPicker` 와 같은 규칙).
MAX_CANDIDATES = 12


@dataclass(frozen=True)
class Candidate:
    """물성 하나. **값을 묻기 전에 필요한 것을 다 들고 있다.**"""

    key: str
    name: str
    domain: str
    si_unit: str
    symbol: str | None
    #: 값이 몇 건인가. 0이면 이 물성으로는 아무것도 못 찾는다.
    value_count: int
    #: 사내 물성 항목 이름들(이어져 있으면). 「우리가 실제로 쓰는 물성인가」.
    items: tuple[str, ...] = ()
    #: 왜 걸렸나 — `alias` · `name` · `symbol` · `key` · `partial`.
    matched_by: str = "partial"
    #: 걸린 그 문자열. 별칭으로 걸렸으면 그 별칭을 보여 준다.
    matched_text: str | None = None
    score: float = 0.0
    notes: tuple[str, ...] = field(default=())


def _counts(db: Session, keys: list[str]) -> dict[str, int]:
    """물성별 값 개수. **한 번에 센다** — 후보마다 세면 12번 돈다."""
    if not keys:
        return {}
    rows = db.execute(
        select(CatalogValue.property_key, func.count())
        .where(CatalogValue.property_key.in_(keys))
        .group_by(CatalogValue.property_key)
    ).all()
    return {row[0]: row[1] for row in rows}


def _items(db: Session, keys: list[str]) -> dict[str, list[str]]:
    """물성별로 이어진 사내 물성 항목 이름."""
    if not keys:
        return {}
    rows = db.execute(
        select(PropertyLink.property_key, VocabularyTerm.value)
        .join(VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id)
        .where(PropertyLink.property_key.in_(keys))
    ).all()
    found: dict[str, list[str]] = {}
    for key, value in rows:
        found.setdefault(key, []).append(value)
    return found


def _alias_hits(db: Session, needle: str) -> dict[str, tuple[str, str]]:
    """별칭으로 걸린 것 — `{키: (걸린 방식, 별칭)}`.

    정확 일치를 먼저 보고, 없으면 부분 일치를 본다. **정확 일치가 있으면 부분은
    안 본다** — 「항복강도」를 정확히 아는데 「항복」이 든 것을 더 얹으면 후보가
    흐려진다.
    """
    exact = db.execute(
        select(PropertyAlias.property_key, PropertyAlias.alias).where(
            PropertyAlias.normalized == needle
        )
    ).all()
    if exact:
        return {key: ("alias", alias) for key, alias in exact}
    rough = db.execute(
        select(PropertyAlias.property_key, PropertyAlias.alias)
        .where(PropertyAlias.normalized.ilike(f"%{needle}%"))
        .limit(MAX_CANDIDATES * 2)
    ).all()
    return {key: ("alias_partial", alias) for key, alias in rough}


def resolve(db: Session, text: str, *, limit: int = MAX_CANDIDATES) -> list[Candidate]:
    """사람이 부르는 이름 → 물성 후보들. **비면 빈 목록이고, 하나를 지어내지 않는다.**"""
    needle = compare_key(text)
    if not needle:
        return []

    aliases = _alias_hits(db, needle)

    # 정의 자체의 이름·키·기호로도 찾는다. 별칭이 아직 안 붙은 물성이 271개 중
    # 대부분이라, 이것이 없으면 씨앗을 넣기 전까지 아무것도 안 찾힌다.
    found = db.scalars(
        select(CatalogDefinition).where(
            or_(
                func.lower(CatalogDefinition.name).contains(needle),
                func.lower(CatalogDefinition.key).contains(needle),
                func.lower(func.coalesce(CatalogDefinition.symbol, "")) == needle,
                CatalogDefinition.key.in_(list(aliases)),
            )
        )
    ).all()

    keys = [one.key for one in found]
    counts = _counts(db, keys)
    items = _items(db, keys)

    made: list[Candidate] = []
    for one in found:
        alias_hit = aliases.get(one.key)
        name_key = compare_key(one.name)
        symbol_key = compare_key(one.symbol)

        if alias_hit and alias_hit[0] == "alias":
            matched, text_hit, base = "alias", alias_hit[1], 100.0
        elif name_key == needle:
            matched, text_hit, base = "name", one.name, 100.0
        elif symbol_key and symbol_key == needle:
            matched, text_hit, base = "symbol", one.symbol or "", 90.0
        elif compare_key(one.key) == needle:
            matched, text_hit, base = "key", one.key, 90.0
        elif alias_hit:
            matched, text_hit, base = "alias_partial", alias_hit[1], 40.0
        else:
            matched, text_hit, base = "partial", one.name, 30.0

        linked = tuple(sorted(items.get(one.key, ())))
        count = counts.get(one.key, 0)
        notes: list[str] = []
        if not count:
            notes.append("값이 없습니다 — 이 물성으로는 아무것도 못 찾습니다.")
        if linked:
            notes.append("사내 물성 항목: " + " · ".join(linked))

        made.append(
            Candidate(
                key=one.key,
                name=one.name,
                domain=one.domain,
                # **단위가 비어 있는 정의가 있다** — 원본 taxonomy 를 그대로
                # 나른 결과다(ADR 0027). 빈 문자열로 두고 화면·AI 가 「모른다」
                # 로 읽게 한다 — 「1」 로 채우면 무차원이라고 거짓말하는 것이다.
                si_unit=one.si_unit or "",
                symbol=one.symbol,
                value_count=count,
                items=linked,
                matched_by=matched,
                matched_text=text_hit,
                # 사내에서 쓰는 물성이면 올린다. 값 개수는 로그로 눌러 — 486건과
                # 9건의 차이는 중요하지만 486 대 4가 50배 차이로 벌어지면 안 된다.
                score=base + (15.0 if linked else 0.0) + min(count, 500) ** 0.5,
                notes=tuple(notes),
            )
        )

    made.sort(key=lambda one: (-one.score, one.key))
    return made[:limit]


def ambiguous(candidates: list[Candidate]) -> bool:
    """되물어야 하는가.

    **점수가 비슷한 것이 둘 이상이면 갈린 것이다.** 「항복」 처럼 도메인이 다른
    물성이 나란히 서는 경우가 여기 걸린다 — 그때 하나를 고르면 조용히 틀린다.
    """
    if len(candidates) < 2:
        return False
    top = candidates[0].score
    close = [one for one in candidates if one.score >= top * 0.8]
    if len(close) < 2:
        return False
    # 도메인이 같고 값 개수가 압도적으로 차이 나면 갈린 것이 아니다 —
    # 「항복강도」와 「변형률속도별 항복강도」 는 사람이 전자를 뜻한다.
    return len({one.domain for one in close}) > 1 or close[1].value_count > 0


def describe(candidates: list[Candidate]) -> dict[str, Any]:
    """MCP 가 그대로 실어 보낼 모양. **값과 단위를 함께 싣는다.**

    필드 이름에 단위를 박지 않는다 — 알루미늄 밀도가 `2.68e-09 kg/m3` 로 나간
    적이 있다(MCP 안내서).
    """
    return {
        "ambiguous": ambiguous(candidates),
        "candidates": [
            {
                "key": one.key,
                "name": one.name,
                "domain": one.domain,
                "si_unit": one.si_unit,
                "symbol": one.symbol,
                "value_count": one.value_count,
                "internal_items": list(one.items),
                "matched_by": one.matched_by,
                "matched_text": one.matched_text,
                "notes": list(one.notes),
            }
            for one in candidates
        ],
    }


def item_terms(db: Session) -> list[VocabularyTerm]:
    """사내 물성 항목(기준정보 `property_item` 축)의 값들."""
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == ITEM_AXIS))
    if axis is None:
        return []
    return list(
        db.scalars(
            select(VocabularyTerm)
            .where(VocabularyTerm.vocabulary_id == axis.id)
            .order_by(VocabularyTerm.value)
        ).all()
    )
