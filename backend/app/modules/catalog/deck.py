"""카탈로그 → 솔버 덱 — **BOM 붙여넣기의 서버 절반** (MaterialTwin 이식 2단계).

문헌 카탈로그의 대표값을 렌더러 틀의 `Deck` 으로 조립한다. 흐름:

    재료명 목록 붙여넣기 → 후보 매칭(사람이 확정) → 대표값 조립 → 렌더러

값은 SI 그대로 흐르고(단위 등가는 `mapping.SI_UNIT_EQUIV` 계약 테스트가 지킨다),
**쓰인 값마다 출처 각주가 덱 머리의 `$` 주석으로 들어간다** — 덱만 받은 사람이
숫자의 무게(실측인지 추정인지, 어느 논문인지)를 되짚을 수 있어야 한다. tier4 도
똑같이 실리고 각주로 구별된다(2026-09-06 사용자 결정).

카탈로그 재료는 스칼라뿐이라(소성 표 없음) 낼 수 있는 형식은 스칼라 렌더러
(`dyna_elastic`·`dyna_thermal`)다. 곡선이 필요한 덱(*MAT_024)은 시험→카드
경로의 것이다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog import representative
from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from matcore import export
from matcore.export import dyna as _dyna  # noqa: F401  (스칼라 렌더러를 등록시킨다)

#: MT 물성 키 → Deck 블록 자리. 매핑에 없는 값은 덱에 안 실린다.
DECK_SLOTS: dict[str, tuple[str, str]] = {
    "mechanical.youngs_modulus": ("elastic", "youngs_modulus"),
    "mechanical.poisson_ratio": ("elastic", "poisson_ratio"),
    "physical.density": ("elastic", "density"),
    "thermal.specific_heat": ("thermal", "specific_heat"),
    "thermal.conductivity": ("thermal", "thermal_conductivity"),
}

#: 카탈로그에서 낼 수 있는 형식 — 스칼라 렌더러만.
FORMATS = ("dyna_elastic", "dyna_thermal")

#: 한 번에 받는 줄 수 상한. BOM 은 수십 줄이지 수천 줄이 아니다.
MAX_LINES = 200


@dataclass(frozen=True)
class Line:
    """붙여넣은 한 줄 — `MID, 이름` 또는 `이름`."""

    query: str
    mid: int | None = None


def parse_lines(text: str) -> list[Line]:
    """`101, SUS304` · `SUS304` 꼴을 읽는다. 빈 줄은 건너뛴다."""
    out: list[Line] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        matched = re.match(r"^(\d+)\s*[,\t]\s*(.+)$", stripped)
        if matched:
            out.append(Line(query=matched.group(2).strip(), mid=int(matched.group(1))))
        else:
            out.append(Line(query=stripped))
    if len(out) > MAX_LINES:
        raise export.ExportError(f"{len(out)}줄입니다 — 한 번에 {MAX_LINES}줄까지 받습니다.")
    return out


def candidates(
    db: Session, query: str, limit: int = 5
) -> list[tuple[CatalogMaterial, int, int]]:
    """이름으로 후보를 찾는다 — (재료, 물성값 수, 적합도).

    적합도는 정확 일치(3) > 앞부분 일치(2) > 포함(1). 같은 급에서는 물성 많은
    순 — 쓸 것이 많은 재료가 먼저다. 고르는 것은 사람이다.
    """
    value_count = (
        select(func.count())
        .select_from(CatalogValue)
        .where(CatalogValue.material_id == CatalogMaterial.id)
        .scalar_subquery()
    )
    rows = db.execute(
        select(CatalogMaterial, value_count.label("value_count"))
        .where(CatalogMaterial.name.ilike(f"%{query}%"))
        .order_by(value_count.desc())
        .limit(25)
    ).all()
    lowered = query.lower()

    def score(name: str) -> int:
        low = name.lower()
        if low == lowered:
            return 3
        if low.startswith(lowered):
            return 2
        return 1

    ranked = sorted(
        ((one, count, score(one.name)) for one, count in rows),
        key=lambda item: (-item[2], -item[1], item[0].name),
    )
    return ranked[:limit]


@dataclass
class Assembled:
    blocks: dict[str, dict[str, object]] = field(default_factory=dict)
    provenance: list[str] = field(default_factory=list)


def assemble(db: Session, material: CatalogMaterial) -> Assembled:
    """대표값을 Deck 블록으로 — **쓰인 값마다 각주 한 줄.**

    같은 물성에 후보가 여럿이면 대표값 선택기(고체상→등급→기준온도 근접)가
    고른 것을 쓴다 — 화면 상세가 보여 주는 그 대표와 같은 값이다.
    """
    rows = list(
        db.execute(
            select(CatalogValue, CatalogSource)
            .outerjoin(CatalogSource, CatalogSource.id == CatalogValue.source_id)
            .where(
                CatalogValue.material_id == material.id,
                CatalogValue.property_key.in_(DECK_SLOTS),
                CatalogValue.value_num.is_not(None),
            )
        )
    )
    marks = representative.annotate([value for value, _ in rows])
    out = Assembled(provenance=[f"문헌 카탈로그: {material.name}"])
    for value, source in rows:
        if not marks[value.id].representative:
            continue
        block, key = DECK_SLOTS[value.property_key]
        out.blocks.setdefault(block, {"values": {}})["values"][key] = value.value_num  # type: ignore[index]
        cite_parts = [
            part
            for part in (
                source.title if source else None,
                str(source.year) if source and source.year else None,
                f"doi:{source.doi}" if source and source.doi else None,
                value.source_detail,
            )
            if part
        ]
        tier = QUALITY_TIERS.get(value.quality_tier, str(value.quality_tier))
        out.provenance.append(
            f"{key} = {value.value_num:.6E} — {' · '.join(cite_parts) or '출처 미상'} "
            f"[tier {value.quality_tier}: {tier}]"
        )
        if marks[value.id].n_candidates > 1:
            out.provenance.append(
                f"  ({key}: 후보 {marks[value.id].n_candidates}개 중 대표값 — "
                f"화면의 같은 선택입니다)"
            )
    return out


@dataclass(frozen=True)
class Skipped:
    mid: int
    name: str
    missing: tuple[str, ...]


@dataclass(frozen=True)
class Built:
    text: str
    skipped: tuple[Skipped, ...]
    notes: tuple[str, ...]
    material_count: int


def _combine(rendered: list[str]) -> str:
    """재료별 덱을 한 파일로 — *KEYWORD/*END 는 한 번만."""
    bodies: list[str] = []
    for text in rendered:
        lines = text.rstrip("\n").split("\n")
        assert lines[0] == "*KEYWORD" and lines[-1] == "*END"
        bodies.append("\n".join(lines[1:-1]))
    return "*KEYWORD\n" + "\n$\n".join(bodies) + "\n*END\n"


def build(
    db: Session,
    items: list[tuple[int, uuid.UUID]],
    format_key: str,
    units_key: str | None,
) -> Built:
    """확정된 (MID, 카탈로그 재료) 목록 → 덱 한 파일.

    모자란 재료는 **거르지 않고 알린다** — 조용히 빠진 재료는 해석에서 갑자기
    없는 재료다. MID 는 덱 안에서 유일해야 한다(솔버는 중복을 조용히 덮는다).
    """
    if format_key not in FORMATS:
        raise export.ExportError(
            f"카탈로그에서 낼 수 있는 형식이 아닙니다: {format_key}. "
            f"있는 것: {', '.join(FORMATS)} — 곡선이 필요한 덱은 시험→카드 경로로 만드세요."
        )
    try:
        system = export.systems.get(units_key)
    except KeyError:
        raise export.ExportError(f"모르는 단위계입니다: {units_key}") from None

    seen: set[int] = set()
    for mid, _ in items:
        if not 1 <= mid <= export.MAX_SOLVER_ID:
            raise export.ExportError(f"MID {mid} — 1~{export.MAX_SOLVER_ID} 이어야 합니다.")
        if mid in seen:
            raise export.ExportError(
                f"MID {mid} 가 두 번 있습니다 — 솔버는 중복 MID 를 조용히 덮습니다."
            )
        seen.add(mid)

    rendered: list[str] = []
    skipped: list[Skipped] = []
    notes: list[str] = []
    for mid, material_id in items:
        material = db.get(CatalogMaterial, material_id)
        if material is None:
            raise export.ExportError(f"카탈로그에 없는 재료입니다: {material_id}")
        made = assemble(db, material)
        deck = export.Deck(
            name=export.sanitize_name(material.grade or material.name, fallback="MAT"),
            solver_id=mid,
            blocks=made.blocks,
            provenance=tuple(made.provenance),
        )
        missing = export.missing_for(deck, format_key)
        if missing:
            skipped.append(Skipped(mid=mid, name=material.name, missing=tuple(missing)))
            continue
        result = export.render(format_key, deck, system)
        rendered.append(result.text)
        notes.extend(result.notes)
    if not rendered:
        raise export.ExportError(
            "덱에 실을 수 있는 재료가 없습니다 — 전부 필요한 물성이 모자랍니다. "
            "아래 목록에서 무엇이 없는지 확인하세요: "
            + "; ".join(f"{one.name}({', '.join(one.missing)})" for one in skipped)
        )
    return Built(
        text=_combine(rendered),
        skipped=tuple(skipped),
        notes=tuple(dict.fromkeys(notes)),
        material_count=len(rendered),
    )
