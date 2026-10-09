"""문헌 카탈로그 → 솔버 덱 — **BOM 붙여넣기의 서버 절반** (MaterialTwin 이식 2단계).

`shared` 에 사는 이유: 카탈로그의 문헌 덱과 워크벤치의 혼합 덱(사내 카드 우선 +
문헌 보충)이 같은 조립 부품을 쓰는데, 모듈끼리는 직접 못 부른다(경계 규칙).

    재료명 목록 붙여넣기 → 후보 매칭(사람이 확정) → 가상 사내 재료 → 선언 카드 조립기 → 렌더러

## 사내 물성 매핑을 거친다 (2026-09-28)

문헌 값은 **「사내 재료에 반영했다면 적혔을」 선언 물성**으로 옮긴 뒤(저장은 안 한다,
`shared/literature_material`) 선언 물성 카드의 조립기(`shared/declared_card`)로 블록이
된다. 전에는 문헌 키를 블록 칸으로 바로 옮기는 표(`DECK_SLOTS`, 다섯 줄)가 따로 있었고,
그 표가 사내 매핑과 어긋나 선팽창계수가 문헌에 있어도 안 실렸다. 덱 각주도 사내 항목
이름(「선팽창계수(CTE)」)으로 적는다.

**쓰인 값마다 출처 각주가 덱 머리에 들어간다** — 덱만 받은 사람이 숫자의 무게(실측인지
추정인지, 어느 논문인지)를 되짚을 수 있어야 한다. tier4 도 똑같이 실리고 각주로
구별된다(2026-09-06 사용자 결정).

## 형식은 판정한다

전에는 `dyna_elastic`·`dyna_thermal` 둘이 고정이었다. 지금은 **카드 내보내기와 같은
형식 목록**(코드판 + 해석용 물성 정의, 사용 중단 제외)에서, 문헌이 채울 수 있는 블록만
요구하는 형식을 고른다(`literature_formats`). 곡선이 필요한 형식은 「곡선 합성」 을 켤 때만.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.shared import (
    deckmap,
    declared_card,
    declared_slots,
    hyperelastic_sets,
    literature_material,
    moisture,
    representative,
    unit_systems,
)
from matcore import cards, export, synth

#: 한 번에 받는 줄 수 상한. BOM 은 수십 줄이지 수천 줄이 아니다.
MAX_LINES = 200

#: 문헌이 채우는 블록 — 선언 물성 카드가 짓는 것과 같다. 「곡선 합성」 을 켜면 소성 표도.
#: 문헌 재료로 짓는 블록 — 사내 매핑을 거치는 값의 각주는 `literature_material.DECK_BLOCKS`
#: 가 정본이다. 흡습은 그 길을 안 거친다 — 확산 종과 환경을 골라야 해서 `shared/moisture` 가
#: 바로 읽고 각주도 거기서 단다(2026-10-08).
LITERATURE_BLOCKS = (*literature_material.DECK_BLOCKS, moisture.BLOCK)
SYNTHETIC_BLOCK = "table"
#: 탄성 · 열 말고 문헌이 짓는 블록 — **형식이 읽을 때만, 채울 값이 있을 때만** 붙는다
#: (2026-10-08). 주파수 · 파장 표는 선언 물성과 같은 길(`declared_slots.fill`)로 편다.
AXIS_BLOCKS = ("electrical", "optical")
#: 변형률 속도 — 문헌에는 곡선이 없고 Cowper-Symonds 의 C · p 만 있다(99종, 2026-10-08).
#: 속도별 표 없이 요약만 싣고, 단일 곡선 덱이 그 비로 곡선을 늘린다(`cowper_symonds_summary`).
RATE_BLOCK = "rate_table"
CS_KEYS = ("mechanical.cowper_symonds_c", "mechanical.cowper_symonds_p")


def rate_summary(
    db: Session, material: CatalogMaterial
) -> tuple[dict[str, Any] | None, list[str]]:
    """문헌 Cowper-Symonds 짝 → 속도 블록 — `(블록 또는 None, 각주)`.

    **C 와 p 는 같은 출처 · 같은 조건의 짝만 쓴다.** 물성마다 대표값을 따로 고르면 다른 논문의
    C 와 p 가 섞인다 — 둘은 한 번의 적합에서 함께 나온 값이라 섞으면 속도 효과가 자릿수째
    틀린다. 짝이 여럿이면 등급이 좋은 쪽, 나머지는 각주로 말한다.
    """
    values = db.scalars(
        select(CatalogValue).where(
            CatalogValue.material_id == material.id,
            CatalogValue.property_key.in_(CS_KEYS),
            CatalogValue.value_num.is_not(None),
            CatalogValue.source_missing_at.is_(None),
        )
    ).all()
    groups: dict[tuple[Any, str], dict[str, CatalogValue]] = {}
    for value in values:
        semantic = representative.semantic_conditions(value.conditions)
        key = (value.source_id, json.dumps(semantic, sort_keys=True, default=str))
        groups.setdefault(key, {})[value.property_key] = value
    pairs = [group for group in groups.values() if set(CS_KEYS) <= set(group)]
    if not pairs:
        return None, []
    pairs.sort(key=lambda group: max(one.quality_tier for one in group.values()))
    chosen = pairs[0]
    c, p = chosen[CS_KEYS[0]], chosen[CS_KEYS[1]]
    conditions = representative.semantic_conditions(c.conditions)
    reference = conditions.get("reference_strain_rate_s")
    block: dict[str, Any] = {
        "values": {
            "model": "cowper_symonds",
            "cs_d": float(c.value_num or 0.0),
            "cs_p": float(p.value_num or 0.0),
            **(
                {"reference_rate": float(reference)}
                if isinstance(reference, int | float)
                else {}
            ),
        }
    }
    source = db.get(CatalogSource, c.source_id) if c.source_id else None
    tier = max(c.quality_tier, p.quality_tier)
    basis = conditions.get("basis")
    said = [
        f"Cowper-Symonds D = {float(c.value_num or 0.0):.6g} 1/s · "
        f"p = {float(p.value_num or 0.0):.4g} — "
        f"{literature_material.cite_of(c, source) or '출처 미상'} "
        f"[tier {tier}: {QUALITY_TIERS.get(tier, str(tier))}]"
        + (f" · 기준: {basis}" if basis else "")
        + (f" · 기준 속도 {reference:g} 1/s" if isinstance(reference, int | float) else "")
    ]
    if len(pairs) > 1:
        said.append(f"다른 Cowper-Symonds 짝 {len(pairs) - 1}개는 안 썼습니다.")
    return block, said


#: 모델 파라미터 — Anand 9항처럼 한 벌이어야 뜻이 있는 값(ADR 0029). 사내 카드가 재료의 벌을
#: 인용하듯, 문헌 덱은 카탈로그의 벌을 그대로 싣는다(`catalog.parameters.sets`).
PARAMS_BLOCK = "model_params"


def parameter_rows(
    db: Session, material: CatalogMaterial
) -> tuple[list[dict[str, Any]], list[str]]:
    """카탈로그 재료의 파라미터 벌 전부 → 블록 행과 각주. **값은 환산하지 않는다** — 항마다
    단위가 다르고 블록이 그렇게 정했다(`matcore.cards.model_params`). 덱이 단위를 읽어 옮긴다.

    같은 항이 두 번 든 벌은 싣지 않고 말한다 — 가를 축을 못 찾은 벌이라 어느 값이 이길지
    모른다(`ParameterSet.duplicated`).
    """
    rows: list[dict[str, Any]] = []
    said: list[str] = []
    for key in parameters.parameterized_keys(db):
        for found in parameters.sets(db, key=key, material_id=material.id):
            label = f"{found.model or key.rsplit('.', 1)[-1]}/{found.set_id or '-'}"
            if found.variant:
                label += f" ({found.variant})"
            if found.duplicated:
                said.append(
                    f"파라미터 벌 {label} 은 같은 항({', '.join(found.duplicated)})이 두 번 "
                    "있어 싣지 않았습니다."
                )
                continue
            for term in found.terms:
                if not isinstance(term.get("value"), int | float):
                    continue
                rows.append(
                    {
                        "set": label,
                        # 벌을 가르는 열쇠 — 모델 글자만 다른 두 벌(한 출처의 상수가 갈려
                        # 들어온 것)을 덱이 합칠 때 쓴다. 조건으로 갈린 벌은 다른 열쇠다.
                        "group": (found.set_id or label)
                        + (f" ({found.variant})" if found.variant else ""),
                        "name": term["term"],
                        "value": float(term["value"]),
                        # 항 단위 칸이 비면 정의의 단위 — 초탄성 계수는 Pa 다(빈 칸을 「1」 로
                        # 읽으면 그 값이 무차원이 된다).
                        "unit": term.get("unit") or parameters.unit_of(db, key, term["term"]),
                    }
                )
            tier = QUALITY_TIERS.get(found.quality_tier or 0, str(found.quality_tier))
            said.append(
                f"파라미터 벌 {label} = {len(found.terms)}항 — {found.source or '출처 미상'} "
                f"[tier {found.quality_tier}: {tier}]"
            )
    return rows, said


def deck_blocks(target: export.Renderer | None) -> tuple[str, ...]:
    """이 형식이 읽는 문헌 블록 — 각주를 그 블록의 값에만 단다. 형식을 모르면 전부."""
    if target is None:
        return LITERATURE_BLOCKS
    needed = {need.block for need in target.needs}
    return tuple(block for block in LITERATURE_BLOCKS if block in needed)


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


# ── 형식 ──────────────────────────────────────────────────────────────────

#: key 앞부분이 곧 솔버인 이름들 — 코드판의 규약(`<솔버>[_<변형>]`).
SOLVERS = ("dyna", "openradioss", "abaqus", "ansys", "nastran", "optistruct")

#: 확장자 → 솔버. 화면에서 만든 정의는 key 가 `deck_1a2b3c4d` 라 앞부분이 솔버가 아니다.
SOLVER_OF_EXTENSION = {
    "k": "dyna",
    "key": "dyna",
    "dyn": "dyna",
    "rad": "openradioss",
    "inp": "abaqus",
    "mac": "ansys",
    "cdb": "ansys",
    "bdf": "nastran",
    "nas": "nastran",
    "dat": "nastran",
    "fem": "optistruct",
}


def solver_of(target: export.Renderer) -> str:
    """이 형식의 솔버 — 한 파일에는 한 솔버만 선다.

    정의가 적은 `solver` 가 이기고, 없으면 key 앞부분(코드판의 규약), 그것도 아니면
    확장자다. **이름 규약만 믿으면** 화면에서 만든 LS-DYNA 정의가 합칠 때 `*KEYWORD` 를
    재료마다 되풀이한다.
    """
    if target.solver:
        return target.solver
    head = target.key.split("_", 1)[0]
    if head in SOLVERS:
        return head
    return SOLVER_OF_EXTENSION.get(target.extension.lower().lstrip("."), head)


def find_format(db: Session, key: str) -> export.Renderer:
    """형식 하나 — **카드 내보내기와 같은 목록**(코드판 + 해석용 물성 정의)에서.

    멈춘 형식이면 멈춘 이유로 거절한다 — 전에는 코드판 key 를 박아 두고 불러서 정의를
    못 썼고, 사용 중단도 따로 막아야 했다.
    """
    deckmap.ensure_usable(db, key)
    for one in deckmap.all_renderers(db):
        if one.key == key:
            return one
    raise export.ExportError(f"모르는 형식입니다: {key}")


def _fillable(block: str) -> set[str]:
    """문헌(선언 물성)으로 채울 수 있는 칸 — 문헌 키를 든 칸, 그리고 밀도·푸아송비."""
    try:
        spec = cards.block(block)
    except KeyError:
        return set()
    found = {slot.key for slot in spec.produces if slot.property_key}
    if block == "elastic":
        found |= set(declared_card.FROM_RECORD)
    if block == RATE_BLOCK:
        # 문헌 Cowper-Symonds 짝(`rate_summary`) — 속도별 표는 없고 요약만 선다.
        found |= {"cs_d", "cs_p", "model", "reference_rate"}
    if block == moisture.BLOCK:
        # 문헌 흡습 셋(`moisture.from_catalog`) — 포화 농도 칸은 물성 키가 없어도 선다.
        found |= {slot.key for slot in spec.produces}
    return found


def takes_literature(target: export.Renderer, *, synthesize: bool = False) -> bool:
    """이 형식을 문헌 재료로 낼 수 있나 — **요구하는 것을 문헌이 다 채울 수 있나**로 판정.

    곡선(소성 표)을 요구하면 합성을 켤 때만. 여러 재료를 한 파일로 합칠 수 없는 형식
    (JSON)은 뺀다. 값이 실제로 있는지는 재료마다 다르다 — 그것은 덱을 낼 때 본다.
    """
    if "json" in target.media_type:
        return False
    cards.load_builtin()
    allowed = {*LITERATURE_BLOCKS, *((SYNTHETIC_BLOCK,) if synthesize else ())}
    for need in target.needs:
        if need.optional:
            continue
        if need.block not in allowed:
            return False
        if need.block == SYNTHETIC_BLOCK:
            continue
        if need.at_least or not set(need.values) <= _fillable(need.block):
            return False
    return True


def literature_formats(db: Session, *, synthesize: bool = False) -> list[export.Renderer]:
    """문헌 재료로 낼 수 있는 형식 — 카드 내보내기와 같은 목록에서, 사용 중단 제외."""
    return [
        one
        for one in deckmap.all_renderers(db)
        if takes_literature(one, synthesize=synthesize)
    ]


def default_literature_format(
    db: Session, solver: str, *, curve: bool = False
) -> export.Renderer | None:
    """솔버 하나의 문헌 형식 기본값. `curve` 면 곡선 형식(합성 곡선 줄).

    구조 형식(탄성계수를 요구하는 것)이 열 형식보다 앞선다 — 부품표는 대개 구조 해석이다.
    같으면 목록 차례(코드판이 등록된 차례)다.
    """
    pool = [
        one
        for one in literature_formats(db, synthesize=curve)
        if solver_of(one) == solver
        and (not curve or any(need.block == SYNTHETIC_BLOCK for need in one.needs))
    ]

    def structural(one: export.Renderer) -> int:
        wants = any(
            need.block == "elastic" and "youngs_modulus" in need.values for need in one.needs
        )
        return 0 if wants else 1

    pool.sort(key=structural)
    return pool[0] if pool else None


# ── 조립 ──────────────────────────────────────────────────────────────────


@dataclass
class Assembled:
    blocks: dict[str, Any] = field(default_factory=dict)
    provenance: list[str] = field(default_factory=list)


def assemble(
    db: Session,
    material: CatalogMaterial,
    *,
    synthesize: bool = False,
    target: export.Renderer | None = None,
) -> Assembled | str:
    """문헌 재료 하나를 블록으로 — **선언 물성 카드와 같은 조립기**. 못 지으면 이유 글자.

    가상 사내 재료(`literature_material`)를 선언 카드가 짓는 대로 짓는다: 탄성·열 블록,
    온도별 표, 사내 항목 연결로 빈 칸 채우기(카드를 내보낼 때와 같다), 합성 소성 표.
    `target` 이 전기 · 광학 블록을 읽으면 그 블록도(주파수 · 파장 표까지) 짓는다.
    """
    cards.load_builtin()
    wanted = deck_blocks(target)
    virtual = literature_material.virtual(db, material, synthesize=synthesize, blocks=wanted)
    stand_in = virtual.material
    elastic, thermal, _ = declared_card.declared_blocks(db, stand_in, None, None)
    elastic_rows = declared_card.declared_table(
        stand_in,
        declared_card.table_items("elastic"),
        constants=declared_card.constants(elastic),
    )
    thermal_rows = declared_card.declared_table(stand_in, declared_card.table_items("thermal"))
    blocks: dict[str, Any] = {
        **declared_card.temperature_aware("elastic", elastic, elastic_rows),
        **declared_card.temperature_aware("thermal", thermal, thermal_rows),
        # 빈 채로 올려 두면 `fill` 이 채운다 — 사내 선언 카드의 「항목란 고르기」 와 같다.
        **{key: {"values": {}} for key in AXIS_BLOCKS if key in wanted},
    }
    declared_slots.fill(db, stand_in, blocks)
    for key in AXIS_BLOCKS:
        # 채울 값이 없으면 내린다 — 빈 블록이 서면 「이 재료는 유전율이 있다」 고 말하게 된다.
        if key in blocks and not blocks[key].get("values") and not blocks[key].get("rows"):
            del blocks[key]
    provenance = list(virtual.provenance)
    if RATE_BLOCK in wanted and RATE_BLOCK not in blocks:
        rate, said = rate_summary(db, material)
        if rate is not None:
            blocks[RATE_BLOCK] = rate
        provenance.extend(said)
    if moisture.BLOCK in wanted:
        # 확산 종이 물인 값만 · 한 환경(온도 · 습도)의 셋으로(2026-10-08).
        wet, said = moisture.from_catalog(db, material.id)
        if wet is not None:
            blocks[moisture.BLOCK] = wet
        provenance.extend(said)
    if hyperelastic_sets.BLOCK in wanted:
        # 문헌 초탄성 벌 → 초탄성 블록(2026-10-08). 여럿이면 정한 차례로 하나, 나머지는 각주.
        hyper, said = hyperelastic_sets.from_catalog(db, material.id)
        if hyper is not None:
            blocks[hyperelastic_sets.BLOCK] = hyper
        provenance.extend(said)
    if PARAMS_BLOCK in wanted:
        rows, said = parameter_rows(db, material)
        if rows:
            models = sorted({str(row["set"]).split("/", 1)[0] for row in rows})
            blocks[PARAMS_BLOCK] = {
                "values": {
                    "sets": len({row["set"] for row in rows}),
                    "models": ", ".join(models),
                },
                "rows": rows,
            }
        provenance.extend(said)
    if synthesize:
        made = declared_card.synthetic_plastic(stand_in, elastic)
        if isinstance(made, str):
            if made.startswith("소성 표가"):
                return made
            # 선언 카드의 말(「선언 물성에 적으세요」)은 문헌 재료에 안 맞는다.
            return SYNTH_MISSING
        rows, notes = made
        blocks[SYNTHETIC_BLOCK] = {"rows": rows}
        provenance.extend(notes)
    return Assembled(blocks=blocks, provenance=provenance)


#: 합성할 스칼라가 모자랄 때 — 덱과 미리보기가 같은 말을 한다.
SYNTH_MISSING = (
    "곡선을 합성할 스칼라가 모자랍니다 — 탄성계수와 항복강도(또는 인장강도)가 있어야 "
    "합니다. 문헌 값은 사내 물성 항목과 이어져 있어야 실립니다."
)


@dataclass(frozen=True)
class SyntheticPreview:
    """문헌 재료의 합성 곡선 — **덱이 지을 것과 같은 곡선**을 그림으로 보려고."""

    curve: synth.SyntheticCurve
    youngs_modulus: float
    inputs: list[tuple[str, float, str, str]]
    """곡선을 지은 스칼라 — (사내 항목 이름, SI 값, 출처 한 줄, SI 단위)."""
    notes: list[str]
    """정합 조정(항복 > 인장) · 안 이어져 못 쓴 값 — 곡선이 왜 이 모양인지."""


def synthetic_preview(db: Session, material: CatalogMaterial) -> SyntheticPreview | str:
    """「곡선 합성」 을 켜고 덱을 지을 때와 **같은 길**로 곡선을 짓는다. 못 지으면 이유 글자.

    가상 사내 재료 → 탄성 블록의 E → `declared_card.synthetic_curve` — `assemble` 과 같다.
    다른 길로 지으면 미리 본 곡선과 덱의 표가 갈리고, 사람은 미리 본 것을 믿는다.
    """
    cards.load_builtin()
    virtual = literature_material.virtual(db, material, synthesize=True)
    stand_in = virtual.material
    elastic, _, _ = declared_card.declared_blocks(db, stand_in, None, None)
    made = declared_card.synthetic_curve(stand_in, elastic)
    if isinstance(made, str):
        return SYNTH_MISSING
    curve, scalars = made
    # 단위는 정의에서 읽는다 — 화면이 이름(「연신율」)으로 짐작하지 않게.
    keys = dict(zip(declared_card.synth_items(), declared_card.SYNTH_KEYS, strict=True))
    si_units: dict[str, str | None] = {
        key: unit
        for key, unit in db.execute(
            select(CatalogDefinition.key, CatalogDefinition.si_unit).where(
                CatalogDefinition.key.in_(declared_card.SYNTH_KEYS)
            )
        )
    }
    inputs: list[tuple[str, float, str, str]] = []
    for item, one in scalars.items():
        if one.value is None:
            continue
        row = declared_card.declared_row(stand_in, item) or {}
        inputs.append(
            (
                item,
                float(one.value),
                str(row.get("reference") or one.source),
                si_units.get(keys.get(item, "")) or "",
            )
        )
    notes = [virtual.adjusted] if virtual.adjusted else []
    if virtual.unmapped:
        notes.append(
            "사내 물성 항목과 이어지지 않아 못 쓴 문헌 값: "
            + ", ".join(sorted(set(virtual.unmapped)))
        )
    return SyntheticPreview(
        curve=curve,
        youngs_modulus=float(elastic["youngs_modulus"]),
        inputs=inputs,
        notes=notes,
    )


def literature_deck(
    db: Session,
    material: CatalogMaterial,
    mid: int,
    *,
    synthesize: bool = False,
    target: export.Renderer | None = None,
) -> export.Deck | str:
    """문헌 재료 하나 → 덱 재료 하나. 못 지으면 이유 글자(합성할 스칼라가 모자라다 등).

    `target` 을 주면 그 형식이 읽는 블록만 각주를 단다(`deck_blocks`)."""
    made = assemble(db, material, synthesize=synthesize, target=target)
    if isinstance(made, str):
        return made
    return export.Deck(
        name=export.sanitize_name(material.grade or material.name, fallback="MAT"),
        solver_id=mid,
        blocks=made.blocks,
        provenance=tuple(made.provenance),
    )


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
    target: export.Renderer | None = None


# ── 합치기 ─────────────────────────────────────────────────────────────────


def combine(rendered: list[str]) -> str:
    """LS-DYNA — 재료별 덱을 한 파일로, `*KEYWORD`/`*END` 는 한 번만.

    LS-DYNA 는 한 파일에 서로 다른 *MAT_ 카드가 섞이는 것이 정상이라(재료마다 다른 법칙)
    텍스트 합본으로 된다. 정의가 머리·끝 줄을 안 적었어도 받는다.
    """
    bodies: list[str] = []
    for text in rendered:
        lines = text.rstrip("\n").split("\n")
        if lines and lines[0].strip().upper() == "*KEYWORD":
            lines = lines[1:]
        if lines and lines[-1].strip().upper() == "*END":
            lines = lines[:-1]
        bodies.append("\n".join(lines))
    return "*KEYWORD\n" + "\n$\n".join(bodies) + "\n*END\n"


def _radioss_body(lines: list[str], first: bool) -> list[str]:
    """Radioss 재료 하나의 줄 — 끝 `/END` 는 떼고, 둘째부터는 머리와 `/UNIT/1` 도 뗀다.

    **`/END` 는 파일 끝에 하나만.** Starter 는 첫 `/END` 에서 읽기를 멈춘다 — 재료마다
    남겨 두면 첫 재료 뒤는 통째로 안 읽힌다(2026-09-28, OpenRadioss 로 확인: 둘째 재료를
    가리키는 부품이 「MATERIAL ID DOES NOT EXIST」). `/UNIT/1` 은 한 파일이 한 계라 첫
    재료의 것 하나면 되고, 같은 번호를 둘 두면 번호가 겹친다.
    """
    if lines and lines[-1] == "/END":
        lines = lines[:-1]
    if first:
        return lines
    out: list[str] = []
    skip = 0
    for line in lines:
        if skip:
            skip -= 1
            continue
        if line == "#RADIOSS STARTER":
            continue
        if line.startswith("/UNIT/"):
            # 번호 줄 · 이름 · 머리 주석 · 코드 줄 — 넷이 한 블록이다(`_unit_block`).
            skip = 3
            continue
        out.append(line)
    return out


def combine_family(rendered: list[str], family: str) -> str:
    """재료별 덱을 **그 솔버의 규약으로** 한 파일로.

    LS-DYNA 는 `*KEYWORD`/`*END` 를 한 번만, Radioss 는 머리·`/UNIT`·`/END` 를 한 번만,
    Abaqus·ANSYS·Nastran 은 재료 묶음이 이어 서면 그대로 성립한다. 모르는 솔버도 잇는다.
    """
    if family == "dyna":
        return combine(rendered)
    if family == "openradioss":
        lines: list[str] = []
        for index, text in enumerate(rendered):
            lines.extend(_radioss_body(text.rstrip("\n").split("\n"), first=index == 0))
        return "\n".join([*lines, "/END"]) + "\n"
    return "\n".join(text.rstrip("\n") for text in rendered) + "\n"


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
    # 블록의 단위 선언이 있어야 to_system 이 환산한다 — 없으면 mm 계 덱이
    # **오류 없이 SI 숫자로** 나간다(2026-09-06 실측). 멱등이라 매번 불러도 된다.
    cards.load_builtin()
    target = find_format(db, format_key)
    if not takes_literature(target):
        known = ", ".join(one.key for one in literature_formats(db))
        raise export.ExportError(
            f"문헌 재료로 낼 수 없는 형식입니다: {format_key} — 문헌이 채우지 못하는 물성"
            f"(곡선 등)을 요구합니다. 있는 것: {known}. 곡선이 필요한 덱은 시험→카드 경로나 "
            f"BOM 덱의 「곡선 합성」 으로 만드세요."
        )
    # **비우면 mm·N·tonne**(ADR 0036) — 계를 고르는 자리는 `unit_systems` 하나다. 전에는
    # 여기서 붙박이만 찾아서, 비우면 SI 였고 사용자 계는 「모르는 단위계」 였다.
    system = unit_systems.resolve(db, units_key, code="MNX-CATALOG-0005")

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
        deck = literature_deck(db, material, mid, target=target)
        assert not isinstance(deck, str)  # 합성을 안 켜면 늘 덱이 선다
        missing = export.missing_for(deck, target)
        if missing:
            skipped.append(Skipped(mid=mid, name=material.name, missing=tuple(missing)))
            continue
        result = export.render(target, deck, system)
        rendered.append(result.text)
        notes.extend(result.notes)
    if not rendered:
        raise export.ExportError(
            "덱에 실을 수 있는 재료가 없습니다 — 전부 필요한 물성이 모자랍니다. "
            "아래 목록에서 무엇이 없는지 확인하세요: "
            + "; ".join(f"{one.name}({', '.join(one.missing)})" for one in skipped)
        )
    return Built(
        text=combine_family(rendered, solver_of(target)),
        skipped=tuple(skipped),
        notes=tuple(dict.fromkeys(notes)),
        material_count=len(rendered),
        target=target,
    )
