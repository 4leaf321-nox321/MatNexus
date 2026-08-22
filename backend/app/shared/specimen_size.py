"""시편의 실효 치수 — **규격에서 물려받되, 잰 값을 덮지 않는다.**

## 왜 필요한가

시편 41개 중 치수가 있는 것이 3개뿐이라 처리가 첫 단계에서 막혔다. 규격서에는
`ASTM E8 subsize = 게이지 길이 25 mm` 라고 적혀 있는데, 그 값이 시스템 어디에도
없어서 사람이 시편마다 옮겨 적어야 했다.

이제 규격이 자기 치수를 갖는다(ADR 0010). 시편은 **잰 것만 적고 나머지는 규격에서
읽는다.**

## 규칙 — 빈 칸만 채운다

    시편에 값이 있다   그 값을 쓴다        ← 사람이 실제로 잰 것
    시편이 비었다      규격의 공칭을 쓴다

**규격이 잰 값을 조용히 덮으면 안 된다.** 장비 파일의 치수를 시편에 채울 때와
같은 규칙이다 — 덮어쓰면 "이 두께가 실측인가 규격값인가" 를 나중에 답할 수 없다.

그래서 **규격의 공칭을 시편 행에 복사해 두지도 않는다.** 복사하면 그 순간 둘이
같아 보이고, 규격을 고쳐도 시편은 옛 값을 든 채 남는다.

## 어디서 오는 값인지 함께 낸다

`measured` 는 사람이 잰 것, `nominal` 은 규격에서 온 것. 화면이 "이건 규격값
입니다" 를 말할 수 있어야 한다 — 그러지 않으면 사람은 전부 실측으로 읽는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Specimen
from app.modules.vocabulary.models import VocabularyTerm

# **`Field` 를 여기서 다시 내보낸다.** 모듈은 다른 모듈의 `services` 를 직접
# import 하지 않는다(경계 검사) — 시편 치수를 다루는 다리가 이 파일이므로,
# 그 타입도 여기를 거쳐 간다.
from app.modules.vocabulary.services import Field as Field
from app.modules.vocabulary.services import attribute_fields, get_vocabulary
from matcore import ratio as ratio_kit
from matcore import specimen as specimen_kit

#: 시편 규격 축. 기준정보 slug 는 저장된 계약이라 코드가 이 이름으로 건다.
STANDARD_SLUG = "specimen_standard"

#: 옛 고정 컬럼 → 치수 칸 이름. **아직 둘 다 들고 있다**(ADR 0010 Expand).
LEGACY_COLUMNS = {
    "gauge_length": "gauge_length_m",
    "width": "width_m",
    "thickness": "thickness_m",
}

#: 옛 컬럼의 이름. **이 셋은 코드가 소유한 개념이라 여기 적어도 된다** — 나머지
#: 칸의 이름은 규격이 정한다. 규격에 없는 칸으로 남았을 때 `width` 라고 그리면
#: 사람은 그것이 무엇인지 묻게 된다.
LEGACY_LABELS = {
    "gauge_length": "게이지 길이",
    "width": "폭",
    "thickness": "두께",
}


def legacy_fields() -> list[Field]:
    """규격을 안 정한 시편이 쓰는 칸. **옛 셋이다.**

    규격이 칸을 정하는 것이 원칙이지만, 규격을 아직 안 붙인 시편이 많다. 그때
    칸이 하나도 없으면 **장비 파일에 값이 있어도 채울 자리가 없다** — 되던 길이
    사라진다. 규격을 정하면 그 규격의 칸이 이것을 대신한다.
    """
    return [
        Field(
            key=key,
            label=label,
            dimension="length",
            si_unit="m",
            is_required=False,
            help=None,
            inherited=False,
        )
        for key, label in LEGACY_LABELS.items()
    ]


@dataclass(frozen=True)
class Size:
    """한 칸의 실효 값과 그 출처."""

    key: str
    label: str
    si_unit: str
    value: float
    #: `measured` 사람이 잰 것 · `nominal` 규격이 정한 것
    source: str


@dataclass(frozen=True)
class Sizes:
    """시편 하나의 치수 한 벌."""

    items: tuple[Size, ...]
    #: 그 규격이 고른 단면적 식. 없으면 단면적을 못 낸다.
    cross_section: str | None
    #: 이 규격이 갖는 칸 전부(값이 없는 것도). 화면이 폼을 그린다.
    fields: tuple[Field, ...]
    #: 규격이 정한 공칭. **시편 행에 복사하지 않는다** — 화면이 흐린 글씨로 보인다.
    nominal: dict[str, float]
    #: 이 시편에서 실제로 잰 값. 옛 고정 컬럼도 여기 섞인다.
    measured: dict[str, float]
    #: 규격 값(`ASTM E8 R1`). 없으면 규격을 안 정한 시편이다.
    standard: str | None
    #: 이 규격이 요구하는 비율 조건. **어겨도 막지 않는다** — 보이게만 한다.
    checks: tuple[ratio_kit.Check, ...] = ()

    def violations(self) -> list[ratio_kit.Violation]:
        """어긴 조건. 잴 수 없는 것(값이 빈 칸)은 건너뛴다."""
        return ratio_kit.violations(self.checks, self.values())

    def label_of(self, key: str) -> str:
        for item in self.fields:
            if item.key == key:
                return item.label
        return key

    def values(self) -> dict[str, float]:
        return {item.key: item.value for item in self.items}

    def get(self, key: str) -> float | None:
        for item in self.items:
            if item.key == key:
                return item.value
        return None


def standard_of(db: Session, specimen: Specimen) -> VocabularyTerm | None:
    if specimen.standard_term_id is None:
        return None
    return db.get(VocabularyTerm, specimen.standard_term_id)


def sizes_of(db: Session, specimen: Specimen) -> Sizes:
    """이 시편의 실효 치수. **잰 값이 이기고, 빈 칸은 규격에서 온다.**"""
    return sizes_for(db, [specimen])[specimen.id]


def sizes_for(db: Session, specimens: Sequence[Specimen]) -> dict[uuid.UUID, Sizes]:
    """여러 시편의 실효 치수를 **한 번에** 읽는다.

    **목록에서 시편마다 읽으면 N+1 이다.** 시편 하나의 치수를 알려면 규격 값과
    그 분류의 기본 칸을 봐야 하는데, 한 시료의 시편들은 대개 **같은 규격**이다 —
    그 한 벌을 한 번만 읽으면 된다.
    """
    if not specimens:
        return {}

    standard_ids = {s.standard_term_id for s in specimens if s.standard_term_id}
    standards: dict[uuid.UUID, VocabularyTerm] = {}
    schema: dict[uuid.UUID, tuple[tuple[Field, ...], dict[str, float]]] = {}
    if standard_ids:
        axis = get_vocabulary(db, STANDARD_SLUG)
        for term in db.scalars(
            select(VocabularyTerm).where(VocabularyTerm.id.in_(standard_ids))
        ):
            standards[term.id] = term
            # **숫자 칸만 치수다.** 규격은 판(문자)·모드(선택)도 갖는데, 그것은
            # 그 규격의 성질이지 이 시편을 잰 값이 아니다 — 시편 화면에 입력
            # 칸으로 나오면 사람은 거기에 무엇을 적어야 하는지 알 수 없다.
            fields = tuple(
                item for item in attribute_fields(db, axis, term) if item.kind == "number"
            )
            keys = {item.key for item in fields}
            schema[term.id] = (
                fields,
                {
                    key: float(value)
                    for key, value in (term.attributes or {}).items()
                    if key in keys and isinstance(value, int | float)
                },
            )

    return {
        specimen.id: _sizes(
            specimen,
            standards.get(specimen.standard_term_id) if specimen.standard_term_id else None,
            *schema.get(specimen.standard_term_id or uuid.UUID(int=0), ((), {})),
        )
        for specimen in specimens
    }


def _sizes(
    specimen: Specimen,
    standard: VocabularyTerm | None,
    fields: tuple[Field, ...],
    nominal: dict[str, float],
) -> Sizes:
    measured = {key: float(value) for key, value in (specimen.dimensions or {}).items()}
    # **옛 컬럼도 실측이다.** 아직 그쪽으로만 채워진 시편이 있다(ADR 0010 Expand).
    for key, column in LEGACY_COLUMNS.items():
        if key in measured:
            continue
        value = getattr(specimen, column, None)
        if value:
            measured[key] = float(value)

    known = {item.key: item for item in fields}
    items: list[Size] = []
    # 규격이 정한 칸 순서를 따른다 — 화면이 그 순서로 그린다.
    for key in [*known, *(k for k in measured if k not in known)]:
        field = known.get(key)
        if key in measured:
            value, source = measured[key], "measured"
        elif key in nominal:
            value, source = nominal[key], "nominal"
        else:
            continue
        items.append(
            Size(
                key=key,
                label=field.label if field else key,
                si_unit=field.si_unit if field else "m",
                value=value,
                source=source,
            )
        )

    return Sizes(
        checks=tuple(
            ratio_kit.Check(
                numerator=str(row.get("numerator")),
                denominator=str(row.get("denominator")),
                minimum=row.get("minimum"),
                maximum=row.get("maximum"),
                help=row.get("help"),
            )
            for row in ((standard.ratio_checks if standard else None) or [])
        ),
        items=tuple(items),
        cross_section=standard.cross_section if standard else None,
        fields=fields,
        nominal=nominal,
        measured=measured,
        standard=standard.value if standard else None,
    )


@dataclass(frozen=True)
class Area:
    """단면적과, 못 냈다면 **그 이유.**

    이유가 없으면 화면은 빈 칸만 보여 주고 사람은 어디를 채워야 하는지 모른다 —
    처리 화면에서 "돌려 보기가 그냥 비활성" 이었을 때와 같은 실패다.
    """

    value: float | None
    problem: str | None


def area_detail(db: Session, specimen: Specimen) -> Area:
    """초기 단면적과 못 낸 이유. **어림값을 만들지 않는다.**

    단면적이 틀리면 응력이 자릿수째로 어긋나는데 숫자는 그럴듯해 보인다 —
    없으면 `@specimen_area` 참조가 실패하고 그게 맞다.
    """
    sizes = sizes_of(db, specimen)
    if sizes.cross_section:
        try:
            return Area(specimen_kit.area(sizes.cross_section, sizes.values()), None)
        except specimen_kit.SpecimenError as exc:
            return Area(None, str(exc))

    # 규격이 식을 안 골랐으면 **옛 규칙**으로 되돌아간다 — 폭 곱하기 두께.
    # 지금까지 이렇게 돌던 시편들이 갑자기 못 돌면 안 된다.
    width = sizes.get("width")
    thickness = sizes.get("thickness")
    if width and thickness:
        return Area(width * thickness, None)
    return Area(
        None,
        "단면적 식을 안 골랐고 폭·두께도 없습니다. "
        "기준정보 > 시편 규격에서 단면 모양을 고르거나 폭·두께를 채우세요.",
    )


def area_of(db: Session, specimen: Specimen) -> float | None:
    """초기 단면적(m²). 낼 수 없으면 `None`."""
    return area_detail(db, specimen).value
