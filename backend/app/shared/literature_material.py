"""문헌 재료 → **가상 사내 재료** — 문헌 값을 사내 물성 매핑으로 옮긴다, 저장은 안 한다.

문헌 덱과 BOM 덱의 문헌 줄이 이것을 거친다(2026-09-28). 전에는 문헌 값을 덱 블록으로
바로 옮기는 표(`litdeck.DECK_SLOTS`, 코드에 다섯 줄)가 따로 있었다 — 사내 물성 매핑과
같은 일을 하는 **두 번째 표**라 어긋났다: 선팽창계수는 매핑에 이어져 있는데 그 표에
없어서, 문헌에 값이 있어도 덱에 안 실렸다.

## 「반영」 과 같은 번역이다

문헌 재료 화면의 「사내 재료에 반영」(`AdoptDialog`)이 하는 일을 **저장 없이** 한다:

    사내 항목 (선언 물성)    매핑 화면에서 `same_as` 로 이은 것 — 폐기된 키는 뺀다
    재료 기본 칸            밀도 · 포아송비 (`catalog.mapping.PROPERTY_ITEM_MAP` 의 column)
    어느 값을               물성마다 대표값 하나(`shared/representative`) — 화면의 기본 선택
    출처                    literature · datasheet · standard · estimate(등급 4·추정·계산)

그 가상 재료가 선언 물성 카드의 조립기(`shared/declared_card`)를 지난다 — 같은 문헌 값이
반영해서 카드로 갈 때와 덱으로 바로 갈 때 같은 모양이 된다. 덱 각주도 사내 항목 이름으로
적는다(「선팽창계수(CTE)」 — 문헌 키가 아니라).

## 안 이어진 값은 조용히 빠지지 않는다

덱에 쓰일 수 있는 물성(블록 칸이 가리키는 문헌 키)인데 사내 항목과 안 이어져 못 옮긴
값은 이름을 모아 둔다 — 덱 각주와 화면이 그것을 말한다. 이어 달라는 뜻이다.

## 각주는 블록에 실린 값에만

옮기는 것은 이어진 값 전부지만(반영과 같다), **덱 머리 각주는 블록 칸이 가리키는 값에만**
단다. 전부 달았더니 항복강도·경도·융점까지 덱 머리에 「값 = … [tier 1]」 로 섰다 — 덱만
받은 사람은 그것이 덱에 들어간 줄 안다(2026-09-28, MCP 점검에서 AI 가 「각주에만 실린 값」
을 따로 가려 말해야 했다). 합성 곡선의 입력은 합성 쪽이 제 각주를 단다.

## 합성 곡선의 입력은 정합한 짝으로

항복강도·인장강도의 대표값은 물성마다 따로 뽑혀 서로 다른 출처에서 올 수 있다. 그대로
담으면 항복 > 인장인 재료가 되고 곡선이 물리적으로 불가능해진다. 그때는 **등급 합이 가장
좋은 정합 짝**(항복 ≤ 인장)을 담고 그 사실을 각주로 적는다(MT 원본의 판단, 전에는
`litdeck.synthetic_assembly` 가 곡선을 지을 때 했다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog import mapping
from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.materials.models import Material
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import declared_conditions, representative
from matcore import cards

#: 합성 곡선의 두 입력 — 모순(항복 > 인장)이면 정합한 짝으로 바꾼다.
YIELD, TENSILE = "mechanical.yield_strength", "mechanical.tensile_strength"


@dataclass
class Virtual:
    """반영했다면 적혔을 사내 재료 — **DB 에 없다**(세션에 안 넣는다)."""

    material: Material
    provenance: list[str] = field(default_factory=list)
    """값마다 한 줄 — 사내 이름 · 값 · 출처 · 등급. 덱 머리에 그대로 실린다."""
    unmapped: list[str] = field(default_factory=list)
    """덱에 쓰일 수 있는데 사내 항목과 안 이어져 못 옮긴 문헌 물성(이름)."""


def targets(db: Session) -> dict[str, tuple[str, str]]:
    """문헌 키 → `(자리, 이름)`. 자리는 `declared`(사내 항목) · `column`(재료 기본 칸).

    `/catalog/properties/adoptable` 과 같은 규칙이다 — 매핑 화면에서 `same_as` 로 이은 것,
    폐기된 키는 빼고, 한 키에 여럿이면 첫 것(눈금 순). 기본 칸은 코드 표가 정한다.
    """
    retired = set(
        db.scalars(
            select(CatalogDefinition.key).where(CatalogDefinition.deprecated_at.is_not(None))
        )
    )
    out: dict[str, tuple[str, str]] = {}
    for link, item in db.execute(
        select(PropertyLink, VocabularyTerm.value)
        .join(VocabularyTerm, VocabularyTerm.id == PropertyLink.term_id)
        .where(PropertyLink.kind == "same_as", PropertyLink.property_key.not_in(retired))
        .order_by(PropertyLink.property_key, PropertyLink.scale)
    ).all():
        out.setdefault(link.property_key, ("declared", str(item)))
    for key, target in mapping.PROPERTY_ITEM_MAP.items():
        if target.place == "column":
            out[key] = ("column", mapping.COLUMN_TARGETS[target.label])
    return out


#: 합성 곡선의 입력 — 「곡선 합성」 을 켤 때만 덱에 쓰인다(각주는 합성이 단다).
SYNTH_INPUTS = {
    YIELD: "항복강도",
    TENSILE: "인장강도",
    "mechanical.elongation_at_break": "연신율",
}


def deck_keys() -> dict[str, str]:
    """블록 칸이 가리키는 문헌 키 → 사람이 읽는 이름. 이 값들이 덱 블록에 실린다."""
    cards.load_builtin()
    found: dict[str, str] = {}
    for spec in cards.list_blocks():
        for slot in spec.produces:
            if slot.property_key:
                found.setdefault(slot.property_key, slot.label)
    return found


def source_of(value: CatalogValue, source: CatalogSource | None) -> str:
    """선언 물성의 출처 낱말 — 화면의 `adoptionSource` 와 같다."""
    if value.quality_tier == 4 or value.method in ("estimated", "computed"):
        return "estimate"
    if source is not None and source.kind in ("datasheet", "standard"):
        return str(source.kind)
    return "literature"


def cite_of(value: CatalogValue, source: CatalogSource | None) -> str:
    """출처 한 줄 — 제목(또는 발행처) · 연도 · DOI · 세부."""
    parts = [
        part
        for part in (
            (source.title or source.publisher) if source else None,
            str(source.year) if source and source.year else None,
            f"doi:{source.doi}" if source and source.doi else None,
            value.source_detail,
        )
        if part
    ]
    return " · ".join(parts)


def reference_of(value: CatalogValue, source: CatalogSource | None) -> str:
    """근거 문자열 — 화면의 `adoptionReference` 와 같은 모양(출처, 등급)."""
    tier = QUALITY_TIERS.get(value.quality_tier, f"t{value.quality_tier}")
    return f"{cite_of(value, source) or '카탈로그'} (문헌 물성 카탈로그, {tier})"


def _consistent(
    rows: list[tuple[CatalogValue, CatalogSource | None]],
    chosen: dict[str, tuple[CatalogValue, CatalogSource | None]],
) -> str | None:
    """항복 > 인장이면 등급 합이 가장 좋은 정합 짝으로 바꾼다. 바꿨으면 그 말을 돌려준다."""
    if YIELD not in chosen or TENSILE not in chosen:
        return None
    sigy = float(chosen[YIELD][0].value_num or 0.0)
    uts = float(chosen[TENSILE][0].value_num or 0.0)
    if sigy <= uts:
        return None
    yields = [pair for pair in rows if pair[0].property_key == YIELD]
    tensiles = [pair for pair in rows if pair[0].property_key == TENSILE]
    best: tuple[tuple[int, int, int], Any, Any] | None = None
    for one in yields:
        for two in tensiles:
            if float(one[0].value_num or 0.0) <= float(two[0].value_num or 0.0):
                score = (
                    one[0].quality_tier + two[0].quality_tier,
                    one[0].quality_tier,
                    two[0].quality_tier,
                )
                if best is None or score < best[0]:
                    best = (score, one, two)
    if best is None:
        del chosen[TENSILE]
        return (
            f"항복({sigy / 1e6:.0f} MPa)이 인장강도({uts / 1e6:.0f} MPa)보다 커서 "
            "(출처 불일치) 인장강도를 빼고 담았습니다."
        )
    _, one, two = best
    chosen[YIELD], chosen[TENSILE] = one, two
    return (
        f"대표값 조합이 물리적으로 모순(항복 {sigy / 1e6:.0f} > 인장 {uts / 1e6:.0f} MPa)"
        "이라, "
        f"정합한 조합(항복 {float(one[0].value_num) / 1e6:.0f} / 인장 "
        f"{float(two[0].value_num) / 1e6:.0f} MPa)을 담았습니다."
    )


def virtual(db: Session, material: CatalogMaterial, *, synthesize: bool = False) -> Virtual:
    """문헌 재료 하나를 사내 재료의 모양으로. **대표값만**, 매핑된 것만.

    `synthesize` 면 합성 입력(항복·인장·연신율)도 「덱에 쓰일 값」 으로 친다 — 안 이어져
    있으면 그 이름을 말한다.
    """
    rows = list(
        db.execute(
            select(CatalogValue, CatalogSource)
            .outerjoin(CatalogSource, CatalogSource.id == CatalogValue.source_id)
            .where(
                CatalogValue.material_id == material.id, CatalogValue.value_num.is_not(None)
            )
            .order_by(CatalogValue.property_key)
        ).all()
    )
    marks = representative.annotate([value for value, _ in rows])
    chosen: dict[str, tuple[CatalogValue, CatalogSource | None]] = {}
    for value, source in rows:
        if marks[value.id].representative and value.property_key not in chosen:
            chosen[value.property_key] = (value, source)
    fix = _consistent([(value, source) for value, source in rows], chosen)

    places = targets(db)
    # 항목마다 값이 무엇에 따라 변하나 — 유전율이면 주파수를 점에 싣는다.
    axes = declared_conditions.of_items(db)
    slots = deck_keys()
    usable = {**slots, **(SYNTH_INPUTS if synthesize else {})}
    out = Virtual(
        material=Material(record_name=material.name, declared_properties=[]),
        provenance=[f"문헌 카탈로그: {material.name} — 사내 물성 매핑을 거쳐 실었습니다"],
    )
    declared_rows: list[dict[str, Any]] = []
    for key, (value, source) in chosen.items():
        number = float(value.value_num or 0.0)
        place = places.get(key)
        if place is None:
            if key in usable:
                out.unmapped.append(usable[key])
            continue
        kind, name = place
        reference = reference_of(value, source)
        if kind == "column":
            # 기본 칸의 서버 제약 — 화면의 반영과 같다(음의 푸아송비는 못 담는다).
            if name == "poisson_ratio" and not 0.0 <= number < 0.5:
                continue
            if name == "density_si" and number <= 0.0:
                continue
            setattr(out.material, name, number)
            label = "포아송비" if name == "poisson_ratio" else "밀도"
        else:
            # **조건을 항목의 축으로 옮긴다.** 온도는 `temperature_k` 와 `temperature_c` 가
            # 둘 다 있다 — 전에는 앞엣것만 읽어 섭씨로 적힌 값의 온도가 빠졌다.
            condition = axes.get(name, declared_conditions.DEFAULT)
            point: dict[str, Any] = {
                "temperature_k": declared_conditions.from_catalog(
                    value.conditions, declared_conditions.TEMPERATURE
                ),
                "value_si": number,
            }
            if condition is not declared_conditions.TEMPERATURE:
                point[condition.key] = declared_conditions.from_catalog(
                    value.conditions, condition
                )
            declared_rows.append(
                {
                    "item": name,
                    "points": [point],
                    "source": source_of(value, source),
                    "reference": reference,
                    "note": "문헌 물성 카탈로그에서 — 덱에 바로 실었다(반영하지 않음)",
                }
            )
            label = name
        if key not in slots:
            # 옮기되(반영과 같다) 각주는 안 단다 — 블록에 안 실리는 값이다(머리말).
            continue
        # 덱 각주는 전과 같은 모양 — 출처와 `[tier N: 뜻]`. 덱만 받은 사람이 숫자의 무게를
        # 되짚는 자리다. 이름만 사내 항목 이름이 됐다.
        tier = QUALITY_TIERS.get(value.quality_tier, str(value.quality_tier))
        line = (
            f"{label} = {number:.6E} — {cite_of(value, source) or '출처 미상'} "
            f"[tier {value.quality_tier}: {tier}]"
        )
        if marks[value.id].n_candidates > 1:
            line += f" (후보 {marks[value.id].n_candidates}개 중 대표값)"
        out.provenance.append(line)
    out.material.declared_properties = declared_rows
    if fix and synthesize:
        # 항복·인장은 합성 곡선에만 쓰인다 — 탄성 덱 머리에 이 말이 서면 무엇을 바꿨는지
        # 모른다.
        out.provenance.append(fix)
    if out.unmapped:
        out.provenance.append(
            "사내 물성 항목과 이어지지 않아 안 실은 문헌 값: "
            + ", ".join(sorted(set(out.unmapped)))
            + " — 기준정보 > 사내 물성 항목(물성 매핑)에서 이으면 실립니다."
        )
    return out
