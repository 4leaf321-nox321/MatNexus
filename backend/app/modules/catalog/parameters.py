"""문헌 물성의 **변수**를 드러낸다 — 한 키에 여러 변수가 들어 있다.

전수 조사(2026-09-08): 271개 정의 중 **52개 · 값 4,453건**이 파라미터 묶음이었다.
`mechanical.anand_constant` 하나에 Anand 모델의 9개 상수가 다 들어 있다:

    a=1.72 [1] · A=2800 [1/s] · h0=150000 [MPa] · Q/R=9380 [K] · …

값의 정체는 `conditions.term` 이 들고, 한 재료의 한 벌은 `conditions.set_id` 로
묶인다. **정의는 `si_unit = "1"` 하나만 말하지만** 진짜 단위는 항마다 다르고
(`conditions.unit_of_term`), `value_num` 은 **SI 가 아니라 그 항의 원래 단위**다.

## 그래서 이 모듈이 하는 일

    is_parameterized(key)   이 키가 변수 묶음인가
    terms(key)              그 변수들이 무엇인가 — 사람에게 되물을 목록
    label(정의, term)       표시 이름 — 「Anand 점소성 상수 · A」
    sets(재료, key)         한 벌씩 묶어 준다 — 채택의 단위(ADR 0029 D3)

**정의 표를 고치지 않는다.** 이관물이라 배포마다 원본으로 덮인다(ADR 0027) —
읽는 층에서 드러내는 것이 유일하게 안 지워지는 길이다.

## 캐시를 두는 이유

「이 키가 파라미터형인가」 는 검색 한 번에 열세 번 넘게 묻는다. 카탈로그는 이관
때만 바뀌므로 프로세스 수명 동안 캐시해도 안전하다 — 이관 뒤에는 앱이 다시 뜬다.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogValue

#: `conditions` 에서 변수를 가리키는 칸.
TERM = "term"
MODEL = "model"
SET_ID = "set_id"
UNIT_OF_TERM = "unit_of_term"

#: 파라미터형으로 볼 최소 변수 수. 하나뿐이면 그냥 그 물성이다.
MIN_TERMS = 2

#: 벌을 가르는 축을 찾을 때 **거들떠보지 않는 조건 칸.**
#:
#: 벌의 이름표(`term`·`model`·`set_id`·`unit_of_term`)와, 이관하며 붙인 기록
#: (`*_before_correction`·`correction_*`·`verdict_*`)이다. 뒤엣것을 축으로 쓰면
#: 「고친 이력이 다르다」 는 이유로 벌이 갈린다 — 물성과 아무 상관이 없다.
_NOT_AN_AXIS = frozenset({TERM, MODEL, SET_ID, UNIT_OF_TERM})

#: 한 벌을 가르는 데 쓸 축을 몇 개까지 겹쳐 볼까. 둘이면 「온도와 계열」 까지
#: 짚는다. 셋부터는 조합이 빠르게 늘고, 그쯤 되면 자료 쪽을 고치는 게 맞다.
MAX_AXES = 2


_cache: dict[str, list[str]] | None = None


@dataclass(frozen=True)
class Term:
    """한 변수. **단위가 항마다 다르다** — 그것이 이 표의 존재 이유다."""

    name: str
    unit: str
    count: int


@dataclass(frozen=True)
class ParameterSet:
    """한 벌. **채택의 단위다** — `A` 만 떼어 가면 뜻이 없다."""

    key: str
    model: str
    set_id: str
    material_id: uuid.UUID
    material_name: str
    terms: list[dict[str, Any]] = field(default_factory=list)
    source: str | None = None
    quality_tier: int | None = None
    distinguishing: dict[str, Any] = field(default_factory=dict)
    """이 벌을 **형제 벌과 가르는 조건.** 안 갈렸으면 비어 있다.

    출처 하나가 한 `set_id` 아래 여러 벌을 담는 일이 흔하다 — 온도를 바꿔 가며
    잰 것, 인장(E)과 전단(G) 계열, 노화 시간별. 그것을 안 가르면 **한 벌 안에
    같은 항이 여러 번** 들어간다(실측 2026-09-10: 재료 25종·벌 61개·값 435건.
    NBR 씰 고무는 노화 8조건이 한 벌로 뭉쳐 `C01` 이 8번이었다).
    """

    duplicated: list[str] = field(default_factory=list)
    """그래도 남은 겹친 항 이름. **비어 있어야 정상이다.**

    가를 축을 못 찾았다는 뜻이라, 이 벌은 그대로 받아 가면 안 된다 — 화면과
    도구가 그 사실을 말해야 한다.
    """

    @property
    def variant(self) -> str:
        """형제 벌과 가르는 이름표. `온도=200 · 계열=shear` 처럼.

        **채택할 때 이것으로 고른다.** `set_id` 만으로는 갈린 벌을 못 집는다.
        """
        return " · ".join(
            f"{key}={value}" for key, value in sorted(self.distinguishing.items())
        )


def _load(db: Session) -> dict[str, list[str]]:
    """키별 변수 목록. **한 번만 훑는다.**"""
    global _cache
    if _cache is not None:
        return _cache
    rows = db.execute(
        text(f"""
        SELECT property_key, conditions->>'{TERM}' AS term, count(*)
        FROM catalog_values
        WHERE conditions ? '{TERM}' AND conditions->>'{TERM}' IS NOT NULL
        GROUP BY 1, 2
        """)
    ).all()
    found: dict[str, list[str]] = {}
    for key, term, _count in rows:
        found.setdefault(key, []).append(term)
    # 변수가 하나뿐인 키는 파라미터형이 아니다 — 조건을 적어 뒀을 뿐이다.
    _cache = {key: sorted(terms) for key, terms in found.items() if len(terms) >= MIN_TERMS}
    return _cache


def forget() -> None:
    """캐시를 버린다. 이관·시험이 부른다."""
    global _cache
    _cache = None


def is_parameterized(db: Session, key: str) -> bool:
    """이 키 하나에 여러 변수가 들어 있나."""
    return key in _load(db)


def parameterized_keys(db: Session) -> list[str]:
    return sorted(_load(db))


def terms(db: Session, key: str, *, limit: int = 40) -> list[Term]:
    """그 키의 변수들 — **사람에게 되물을 목록.**

    개수가 많은 것부터 준다. Prony 완화시간처럼 85종인 것도 있어서, 앞의 몇 개만
    봐도 무엇을 고르는 자리인지 알 수 있어야 한다.
    """
    if not is_parameterized(db, key):
        return []
    rows = db.execute(
        text(f"""
        SELECT conditions->>'{TERM}' AS term,
               coalesce(conditions->>'{UNIT_OF_TERM}', '') AS unit,
               count(*) AS n
        FROM catalog_values
        WHERE property_key = :key AND conditions ? '{TERM}'
        GROUP BY 1, 2 ORDER BY n DESC, term LIMIT :limit
        """),
        {"key": key, "limit": limit},
    ).all()
    return [Term(name=row[0], unit=row[1], count=int(row[2])) for row in rows]


def label(definition: CatalogDefinition, term: str | None = None) -> str:
    """표시 이름. **이름만으로는 무엇인지 모른다.**

    항복강도 (Rp0.2)             기호가 있으면 함께
    Anand 점소성 상수 · A        변수가 있으면 그것까지
    """
    name = definition.name
    if term:
        return f"{name} · {term}"
    if definition.symbol:
        return f"{name} ({definition.symbol})"
    return name


def unit_of(db: Session, key: str, term: str | None) -> str:
    """그 변수의 진짜 단위. **정의가 말하는 단위가 아니다.**

    파라미터형에서 정의는 대개 `1`(무차원)이라고 적혀 있는데, 실제로는 항마다
    `MPa`·`1/s`·`K` 로 다르다.
    """
    if term and is_parameterized(db, key):
        found = db.execute(
            text(f"""
            SELECT coalesce(conditions->>'{UNIT_OF_TERM}', '') FROM catalog_values
            WHERE property_key = :key AND conditions->>'{TERM}' = :term
              AND conditions->>'{UNIT_OF_TERM}' IS NOT NULL LIMIT 1
            """),
            {"key": key, "term": term},
        ).scalar()
        if found:
            return str(found)
    definition = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
    return (definition.si_unit or "") if definition else ""


def _mark(conditions: dict[str, Any], axes: tuple[str, ...]) -> str:
    """이 값이 어느 벌에 속하는지 나타내는 표.

    **「없음」 을 값으로 적지 않는다.** 어떤 표를 쓰든 진짜 값과 겹칠 수 있어서,
    있고 없음을 값과 **따로** 싣는다 — `mode` 가 어떤 벌에만 붙어 있으면 그
    있고 없음이 곧 두 벌을 가르는 축이다(실측 2026-09-10: Ogden 벌 넷).
    """
    return json.dumps(
        [[axis in conditions, conditions.get(axis)] for axis in axes],
        ensure_ascii=False,
        sort_keys=True,
    )


def _axis_candidates(rows: list[dict[str, Any]]) -> list[str]:
    """벌을 가를 후보 축. **값이 갈리는 조건 칸만** 남긴다.

    이관 기록(`*_before_correction`·`correction_*`·`verdict_*`)은 뺀다 — 그것으로
    가르면 「고친 이력이 다르다」 는 이유로 벌이 쪼개진다.
    """
    names: set[str] = set()
    for row in rows:
        for key in row.get("conditions") or {}:
            if key in _NOT_AN_AXIS or key == "corrected_by":
                continue
            if key.endswith("_before_correction") or key.startswith(
                ("correction_", "verdict_")
            ):
                continue
            names.add(key)

    # **없는 것도 값이다.** 어떤 벌에만 `mode` 가 붙어 있으면 그 있고 없음이
    # 곳 두 벌을 가르는 축이다 — 있는 행끼리만 보면 값이 한 가지라 축이 아닌 줄
    # 안다(실측 2026-09-10: Ogden 벌 넯이 그래서 안 갈렸다).
    found: list[str] = []
    for key in sorted(names):
        marks = {_mark(row.get("conditions") or {}, (key,)) for row in rows}
        if len(marks) > 1:
            found.append(key)
    return found


def _grouped_by(
    rows: list[dict[str, Any]], axes: tuple[str, ...]
) -> dict[str, list[dict[str, Any]]]:
    made: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        conditions = row.get("conditions") or {}
        made.setdefault(_mark(conditions, axes), []).append(row)
    return made


def _split_axes(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    """이 무리를 가를 **가장 성긴 축**을 고른다. 못 고르면 빈 것.

    ## 왜 「가장 성긴」 인가

    항마다 달라지는 칸(`term_index`·`relaxation_time_s`)으로 가르면 **항 하나에
    벌 하나**가 되어 버린다 — 갈린 것이 아니라 흩어진 것이다. 실제로 가르는 축은
    항을 한 벌씩 통째로 되풀이시키는 것이므로, 조건이 만족되는 것 중 **묶음이
    가장 적은** 축이 답이다.

    같은 묶음 수면 **네모반듯한 쪽**(묶음마다 값 수가 같은 것)을 고른다. 온도
    7가지에 항 4개면 7개씩 4줄로 반듯한데, 우연히 같은 수로 갈리는 다른 칸은 대개
    들쭉날쭉하다.
    """
    counted = Counter(str(row.get("term")) for row in rows)
    if not counted or max(counted.values()) <= 1:
        return ()

    candidates = _axis_candidates(rows)
    tries: list[tuple[str, ...]] = [(one,) for one in candidates]
    if len(candidates) <= 8:
        tries += [
            (first, second)
            for index, first in enumerate(candidates)
            for second in candidates[index + 1 :]
        ]

    best: tuple[tuple[int, int, tuple[str, ...]], tuple[str, ...]] | None = None
    for axes in tries:
        if len(axes) > MAX_AXES:
            continue
        groups = _grouped_by(rows, axes)
        if len(groups) < 2:
            continue
        if any(
            max(Counter(str(row.get("term")) for row in group).values()) > 1
            for group in groups.values()
        ):
            continue  # 갈라도 여전히 같은 항이 겹친다
        sizes = {len(group) for group in groups.values()}
        score = (0 if len(sizes) == 1 else 1, len(groups), axes)
        if best is None or score < best[0]:
            best = (score, axes)
    return best[1] if best else ()


def sets(
    db: Session,
    *,
    key: str,
    material_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[ParameterSet]:
    """한 벌씩 묶어 준다 — **채택의 단위**(ADR 0029).

    `set_id` 가 없는 값도 있다(원본이 안 준 것). 그때는 재료+모델로 묶는다 — 한
    재료에 같은 모델이 두 벌이면 섞이지만, 안 묶어서 낱개로 흩는 것보다 낫다.
    """
    query = (
        select(
            CatalogValue.material_id,
            func.coalesce(CatalogValue.conditions[MODEL].astext, ""),
            func.coalesce(CatalogValue.conditions[SET_ID].astext, ""),
        )
        .where(CatalogValue.property_key == key, CatalogValue.conditions.has_key(TERM))
        .group_by(CatalogValue.material_id, text("2"), text("3"))
        .limit(limit)
    )
    if material_id is not None:
        query = query.where(CatalogValue.material_id == material_id)

    made: list[ParameterSet] = []
    for owner, model, set_id in db.execute(query).all():
        found = (
            db.execute(
                text(f"""
            SELECT v.conditions->>'{TERM}' AS term, v.value_num, v.value_text,
                   coalesce(v.conditions->>'{UNIT_OF_TERM}', '') AS unit, v.quality_tier,
                   left(coalesce(v.source_detail, ''), 160) AS source, m.name AS material,
                   v.conditions, v.source_id,
                   left(coalesce(s.title, ''), 60) AS source_title
            FROM catalog_values v
            JOIN catalog_materials m ON m.id = v.material_id
            LEFT JOIN catalog_sources s ON s.id = v.source_id
            WHERE v.property_key = :key AND v.material_id = :owner
              AND coalesce(v.conditions->>'{MODEL}', '') = :model
              AND coalesce(v.conditions->>'{SET_ID}', '') = :set_id
              -- **항 이름이 있는 값만 벌에 넣는다.** 없으면 벌의 구성원이 아니다 —
              -- 모델·set_id 가 둘 다 빈 값끼리 묶이면서 이름 없는 값이 남의 벌에
              -- 딸려 들어왔다(실측 2026-09-10).
              AND v.conditions ? '{TERM}'
            ORDER BY 1
            """),
                {"key": key, "owner": owner, "model": model, "set_id": set_id},
            )
            .mappings()
            .all()
        )
        if not found:
            continue

        # **한 `set_id` 아래 여러 벌이 들어 있을 수 있다.** 갈라 줄 축이 조건에
        # 있으면 갈라서 낸다 — 안 가르면 같은 항이 여러 번 든 벌이 나가고, 그것을
        # 그대로 받아 가면 `C01` 이 8개인 Mooney-Rivlin 이 재료에 담긴다.
        rows = [dict(one) for one in found]

        # **한 벌은 한 출처에서 온다.** 논문이 다르면 같은 모델이라도 다른 벌이다 —
        # 실측(2026-09-10): Ecoflex 00-30 의 Yeoh-3 에 두 논문이 한 벌로 있었는데,
        # 한쪽은 항을 `C10·C20·C30` 으로 다른 쪽은 `C1·C2·C3` 으로 적어 **이름이
        # 안 겹치는 바람에** 아래 겹침 검사에 안 걸렸다. 값은 30배 달랐다.
        # 이름 표기에 기대지 않으려면 출처로 먼저 가른다.
        by_source: dict[Any, list[dict[str, Any]]] = {}
        for row in rows:
            by_source.setdefault(row.get("source_id"), []).append(row)
        papers = list(by_source.values()) if len(by_source) > 1 else [rows]

        parts: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for paper in papers:
            head: dict[str, Any] = {}
            if len(by_source) > 1:
                head["source"] = paper[0].get("source_title") or "(제목 없음)"
            axes = _split_axes(paper)
            for part in (_grouped_by(paper, axes) if axes else {"": paper}).values():
                marks = dict(head)
                marks.update(
                    {axis: (part[0].get("conditions") or {}).get(axis) for axis in axes}
                )
                parts.append((marks, part))

        for marks, part in parts:
            counted = Counter(str(one["term"]) for one in part)
            made.append(
                ParameterSet(
                    key=key,
                    model=model,
                    set_id=set_id,
                    material_id=owner,
                    material_name=part[0]["material"] or "",
                    quality_tier=part[0]["quality_tier"],
                    source=part[0]["source"] or None,
                    distinguishing=marks,
                    # 갈랐는데도 남았으면 **그 사실을 들고 다닌다.** 조용히 두면
                    # 받는 쪽은 항이 왜 여러 번인지 모른 채 채택한다.
                    duplicated=sorted(name for name, times in counted.items() if times > 1),
                    terms=[
                        {
                            "term": one["term"],
                            "value": one["value_num"],
                            "text": one["value_text"],
                            "unit": one["unit"],
                        }
                        for one in part
                    ],
                )
            )
    return made
