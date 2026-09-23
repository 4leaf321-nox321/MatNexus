"""기본 물성 항목 ↔ 문헌 물성 키 **연결의 씨앗**.

## 왜 씨앗인가

선언 물성이 카드의 빈 칸으로 흐르려면 다리가 둘 필요하다 — 칸이 드는 물성 키
(`Produced.property_key`)와, 기준정보 항목 ↔ 그 키의 연결(`property_links`).
뒤엣것은 지금까지 **사람이 화면에서만 만들 수 있었다**(문헌 물성의 「사내 항목
연결」). 그래서 개발 DB 에서 이어 둔 것이 운영에는 없었고, 같은 코드가 서버마다
다르게 움직였다 — 값이 조용히 안 실리는 종류다.

기본 항목 아홉은 전사 공통이고 코드가 이름과 키를 다 안다(기준정보 씨앗). 그러면
그 연결도 씨앗이어야 한다. **배포가 매번 맞춘다**(`scripts/refresh_builtins.py`).

## 없는 것을 만든다 — **지운 것도 다시 생긴다**

다른 씨앗(`ensure_builtin_*`)과 같은 규칙이다: 배포마다 「없으면 만든다」. 그래서
관리자가 기본 연결을 끊어도 다음 배포에 되살아난다. 기본 아홉은 전사 공통이고
카드·검색·커버리지가 그 위에 서 있어서, 한 서버에서만 끊겨 있는 상태가 더 나쁘다.

정말 끊어야 하는 연결이 생기면 그것은 **씨앗 표에서 빼는 일**이지 화면에서 지우는
일이 아니다. 부서가 만든 항목의 연결은 여기 없으므로 그대로 사람의 것이다.

## 문헌 정의가 아직 없으면 건너뛴다

연결은 문헌 물성 정의(`catalog_definitions`)를 가리킨다. 그 씨앗은 배포에서 **이
단계보다 뒤에** 돌므로, 갓 설치한 서버의 첫 배포에서는 정의가 없을 수 있다. 그때는
이름을 세어 돌려주고 넘어간다 — 배포 스크립트가 카탈로그를 적재한 뒤 한 번 더
부른다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared import property_names
from app.shared.text import compare_key
from matcore import units

#: `(항목을 가리키는 물성 키, 이을 문헌 물성 키, 눈금)`.
#:
#: 첫 칸이 **항목 이름 대신** 들어가는 이유: 이름의 정본은 기준정보 씨앗 하나이고
#: (`BUILTIN_PROPERTY_ITEMS`), 여기에 한글 이름을 또 적으면 그 순간 정본이 둘이
#: 된다 — 오늘 카드 라우터에서 걷어낸 바로 그 문제다.
#:
#: **경도는 눈금마다 한 줄이다.** `HV 200` 과 `HB 200` 은 다른 값이고 환산식이
#: 없다. 눈금 없이 이으면 서로 다른 뜻의 숫자가 한 칸에 섞인다.
BUILTIN_LINKS: list[tuple[str, str, str | None]] = [
    ("mechanical.youngs_modulus", "mechanical.youngs_modulus", None),
    ("mechanical.shear_modulus", "mechanical.shear_modulus", None),
    ("thermal.expansion_linear", "thermal.expansion_linear", None),
    ("thermal.specific_heat", "thermal.specific_heat", None),
    ("thermal.conductivity", "thermal.conductivity", None),
    ("mechanical.yield_strength", "mechanical.yield_strength", None),
    ("mechanical.tensile_strength", "mechanical.tensile_strength", None),
    ("mechanical.elongation_at_break", "mechanical.elongation_at_break", None),
    ("mechanical.hardness_vickers", "mechanical.hardness_vickers", "HV"),
    ("mechanical.hardness_vickers", "mechanical.hardness_brinell", "HB"),
    ("mechanical.hardness_vickers", "mechanical.hardness_rockwell", "HRC"),
    ("mechanical.hardness_vickers", "mechanical.hardness_rockwell", "HRB"),
]


def dimension_conflict(definition: CatalogDefinition, term: VocabularyTerm) -> str | None:
    """「같은 것」 으로 이을 수 없는 까닭. 이을 수 있으면 `None`.

    **차원이 다르면 못 잇는다.** 이 매핑은 채우기의 정본이고, 채우기는 SI 값을 환산
    없이 옮긴다. 열전도율을 「비열」 에 이어 두면 W/(m·K) 숫자가 J/(kg·K) 자리에
    조용히 들어간다 — 숫자는 그럴듯하다. 표가 모르는 눈금(HV)은 무차원·눈금
    항목(경도)에만 간다.

    화면(연결 만들기)과 씨앗이 **같은 규칙을 쓴다.** 두 벌이면 씨앗이 심은 것을
    화면이 거절하는 상태가 생긴다.
    """
    dimension = str((term.attributes or {}).get("dimension") or "dimensionless")
    has_scales = bool(str((term.attributes or {}).get("scales") or "").strip())
    symbol = definition.si_unit or ""
    found = units.canonical(symbol) if symbol else None
    if found is None:
        if has_scales:
            return None
        return (
            f"'{definition.name}' 의 단위 '{symbol or '(없음)'}' 는 표가 모르는 단위라 "
            f"눈금 있는 항목에만 이을 수 있습니다 — '{term.value}' 은 눈금이 없습니다."
        )
    if not units.same_dimension(units.unit_of(found).dimension, dimension):
        return (
            f"'{definition.name}' 은 {units.unit_of(found).dimension} 인데 '{term.value}' 은 "
            f"{dimension} 입니다 — 차원이 달라 같은 것으로 이을 수 없습니다. 담으면 숫자가 "
            "다른 단위 자리에 그대로 들어갑니다."
        )
    return None


def ensure_builtin_property_links(db: Session) -> list[str]:
    """기본 항목의 연결을 보장한다. **만든 것의 이름을 돌려준다.**

    없는 것만 만든다. 이미 있는 연결은 안 건드린다 — 종류·메모를 사람이 고쳤을 수
    있고, 배포가 그것을 되돌리면 안 된다. 다만 **지워진 것은 다시 생긴다**(위 머리말).
    """
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    if axis is None:
        return []
    terms = {
        one.normalized: one
        for one in db.scalars(
            select(VocabularyTerm).where(VocabularyTerm.vocabulary_id == axis.id)
        )
    }

    made: list[str] = []
    for item_key, property_key, scale in BUILTIN_LINKS:
        item = property_names.builtin_item(item_key)
        if item is None:
            continue
        term = terms.get(compare_key(item))
        if term is None:
            # 항목 자체가 없다 — 앞 단계(`ensure_builtin_property_items`)가 만든다.
            continue
        definition = db.scalar(
            select(CatalogDefinition).where(CatalogDefinition.key == property_key)
        )
        if definition is None:
            # 문헌 카탈로그가 아직 안 적재됐다. 다음 차례에 붙는다.
            continue
        if dimension_conflict(definition, term) is not None:
            # 항목의 차원을 누가 바꿨다. **짐작해서 잇지 않는다.**
            continue
        found = db.scalar(
            select(PropertyLink).where(
                PropertyLink.property_key == property_key,
                PropertyLink.term_id == term.id,
                PropertyLink.scale.is_(None) if scale is None else PropertyLink.scale == scale,
            )
        )
        if found is not None:
            continue
        db.add(
            PropertyLink(
                property_key=property_key,
                term_id=term.id,
                kind="same_as",
                scale=scale,
                note="기본 연결 (씨앗)",
                created_by_id=None,
            )
        )
        made.append(f"{item} ↔ {property_key}" + (f" [{scale}]" if scale else ""))
    return made
