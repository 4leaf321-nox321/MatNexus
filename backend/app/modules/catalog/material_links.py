"""사내 재료 ↔ 문헌 재료 **연결 후보**. 잇지는 않는다 — 사람이 누른다.

## 왜 필요한가

사내 재료가 문헌 재료와 이어져 있어야 BOM 덱 · 선언 물성 받아오기 · 비교가 그 재료의
문헌 값을 쓴다(`CatalogLink`). 그런데 잇는 길이 재료 상세에서 이름을 쳐서 찾는 것
하나뿐이라, 개발 DB 사내 재료 135개 중 이어진 것이 9개였다(2026-10-08). 문헌 재료는
2,663종이라 사람이 재료마다 찾아 훑을 수는 없다.

## 무엇을 후보로 올리나 — **눌러도 되는 것만**

사내 재료의 **등급**(`grade`)과 **별칭**(`alias`)을 문헌 재료의 코드 · 등급 · 이름과
견준다. 대소문자와 기호(`-` · `_` · 빈칸 · 괄호)는 무시한다 — `Al5052-H32` 와
`AL5052H32` 는 같은 글이다.

    code    문헌 재료의 코드나 등급과 같다             (`PKG-SAC` · `SUS304`)
    name    문헌 재료의 이름 전체와 같다               (`SAC305 Solder Alloy`)
    prefix  이름이 **그 낱말들로 시작한다**            (`SUS304` → `SUS304_annealed Bilinear`)

**닮기만 한 것은 올리지 않는다.** `SGARC440` 과 `SGARC340` 은 trigram 으로 아주
닮았지만 다른 재료다 — 이어 두면 그 재료의 덱이 다른 강도로 나간다. 물성 항목 연결
후보(`property_names.suggest_links`)가 「이름이 겹치기만 하는 것」 을 안 올리는 것과
같은 판단이다. `prefix` 도 낱말 단위라 `SUS304` 가 `SUS304L` 에 걸리지 않는다.

**이름 가운데의 낱말은 안 본다**(2026-10-08 개발 DB 로 견줘 봄). 처음에는 이름 어디든
이어진 낱말이 같으면 올렸는데 `PC` 에 `LEXAN 3412R (PC-GF20)` 이, `PET` 에 `Double-Sided
PET Tape` 가 걸렸다 — 그 재료를 **쓴** 다른 재료다. 시작하더라도 바로 뒤가 `/` · `+`
면 블렌드라 뺀다(`PC` 에 `PC/ABS Blend`). `prefix` 에는 열처리 · 충전재 꼬리가 다른
재료가 남는다(`AL6063` 에 `Al6063-T6` 과 `-T5`) — 그래서 근거를 함께 주고 사람이 고른다.

**분류가 어긋나면 뺀다** — 금속 재료에 고분자 문헌 재료를 올리지 않는다(`FAMILY_CATEGORIES`).
사내 분류를 모르면 거르지 않는다. 원본에서 사라진 문헌 재료(`source_missing_at`)도 뺀다.

## 확정은 운영에서

후보는 그 서버의 재료로 그 자리에서 계산한다 — 저장하지 않는다. 개발 DB 에는 시험용
재료가 섞여 있어 거기서 이은 것은 운영에 가지 않는다(가서도 안 된다). 잇는 일은 재료를
고칠 수 있는 사람이 운영에서 한다(`PUT /catalog/links/{id}`, ADR 0035).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogMaterial, CatalogValue
from app.modules.materials.models import Material
from app.shared.text import compare_key

#: 사내 분류(`family`) → 이어도 되는 문헌 분류. 비교는 `compare_key` 로 접은 글이다.
#:
#: 고분자에 복합재가 드는 것은 유리섬유 강화 PC(`PC-GF30`)처럼 사내에서는 고분자로,
#: 문헌에서는 복합재로 둔 재료가 실재해서다. `molecular`(용매 · 단분자)는 어느 사내
#: 분류에도 넣지 않는다 — 부품 재료가 아니다. **여기 없는 분류는 거르지 않는다.**
FAMILY_CATEGORIES: dict[str, frozenset[str]] = {
    "metal": frozenset({"metal"}),
    "금속": frozenset({"metal"}),
    "polymer": frozenset({"polymer", "rubber", "foam", "composite"}),
    "plastic": frozenset({"polymer", "rubber", "foam", "composite"}),
    "고분자": frozenset({"polymer", "rubber", "foam", "composite"}),
    "수지": frozenset({"polymer", "rubber", "foam", "composite"}),
    "rubber": frozenset({"rubber", "polymer", "foam"}),
    "elastomer": frozenset({"rubber", "polymer", "foam"}),
    "고무": frozenset({"rubber", "polymer", "foam"}),
    "foam": frozenset({"foam", "polymer", "rubber"}),
    "폼": frozenset({"foam", "polymer", "rubber"}),
    "ceramic": frozenset({"ceramic"}),
    "glass": frozenset({"ceramic"}),
    "세라믹": frozenset({"ceramic"}),
    "유리": frozenset({"ceramic"}),
    "composite": frozenset({"composite", "polymer"}),
    "복합재": frozenset({"composite", "polymer"}),
}

#: 이름에서 낱말 몇 개까지 이어 붙여 견주나. 등급은 길어야 서너 낱말이다
#: (`Al5052 H32` · `SUS 304 L`) — 끝없이 붙이면 색인만 커진다.
MAX_RUN = 6

#: 재료 하나에 올리는 후보 수. 같은 등급의 열처리 · 모델(`Bilinear`)만 다른 문헌
#: 재료가 여럿일 수 있다 — 값이 많은 것부터.
PER_MATERIAL = 5

#: 왜 걸렸나 — 강한 것부터. 정렬이 이 차례를 쓴다.
MATCH_ORDER = ("code", "name", "prefix")

_WORD = re.compile(r"[^\W_]+")

#: 낱말 바로 뒤에 오면 **블렌드 · 적층**이라는 표지. `PC/ABS` 는 PC 가 아니다.
_BLEND = re.compile(r"\s*[/+]")


def words(text: str | None) -> list[str]:
    """견줄 낱말 — 대소문자 · 기호를 버린다. `Al5052-H32 (O)` → `al5052 · h32 · o`."""
    return _WORD.findall((text or "").casefold())


def needle(text: str | None) -> str:
    """견줄 글 하나 — 낱말을 붙인 것. **너무 짧으면 비운다**(한 글자 · 두 자리 숫자는
    낱말 하나로 수십 재료에 걸린다)."""
    joined = "".join(words(text))
    if len(joined) < 2 or (joined.isdigit() and len(joined) < 3):
        return ""
    return joined


@dataclass(frozen=True)
class Candidate:
    """사내 재료 하나에 **이을 만한 문헌 재료** 하나."""

    catalog_material_id: uuid.UUID
    name: str
    category: str
    manufacturer: str | None
    subsystem: str | None
    role: str | None
    value_count: int
    #: `code` · `name` · `prefix` — 왜 걸렸나.
    matched_by: str
    #: 사내 재료의 어느 칸이 걸렸나 — `grade` · `alias`.
    matched_on: str
    #: 그 칸의 글. 화면이 「등급 SUS304 가 이름의 낱말과 같다」 로 말한다.
    matched_text: str


@dataclass
class Index:
    """문헌 재료 전부를 **한 번 읽어** 견줄 글 → 재료로 접은 것. 재료마다 표를 훑지
    않는다 — 사내 재료가 수천이어도 한 재료는 사전 찾기 몇 번이다."""

    rows: dict[uuid.UUID, CatalogMaterial]
    counts: dict[uuid.UUID, int]
    by_code: dict[str, set[uuid.UUID]]
    by_name: dict[str, set[uuid.UUID]]
    by_prefix: dict[str, set[uuid.UUID]]

    @classmethod
    def load(cls, db: Session) -> Index:
        rows = {
            one.id: one
            for one in db.scalars(
                select(CatalogMaterial).where(CatalogMaterial.source_missing_at.is_(None))
            )
        }
        counts = {
            material_id: count
            for material_id, count in db.execute(
                select(CatalogValue.material_id, func.count()).group_by(
                    CatalogValue.material_id
                )
            ).all()
        }
        index = cls(rows=rows, counts=counts, by_code={}, by_name={}, by_prefix={})
        for one in rows.values():
            for code in (one.material_code, one.grade):
                key = needle(code)
                if key:
                    index.by_code.setdefault(key, set()).add(one.id)
            key = "".join(words(one.name))
            if key:
                index.by_name.setdefault(key, set()).add(one.id)
            for run in _prefixes(one.name):
                index.by_prefix.setdefault(run, set()).add(one.id)
        return index

    def candidates(self, material: Material, *, limit: int = PER_MATERIAL) -> list[Candidate]:
        allowed = FAMILY_CATEGORIES.get(compare_key(material.family))
        best: dict[uuid.UUID, tuple[int, str, str, str]] = {}
        for field, text in (("grade", material.grade), ("alias", material.alias)):
            key = needle(text)
            if not key:
                continue
            for rank, (how, table) in enumerate(
                (("code", self.by_code), ("name", self.by_name), ("prefix", self.by_prefix))
            ):
                for found in table.get(key, ()):
                    if found not in best or rank < best[found][0]:
                        best[found] = (rank, how, field, (text or "").strip())
        made = []
        for found, (_rank, how, field, text) in best.items():
            row = self.rows[found]
            if allowed is not None and row.category not in allowed:
                continue
            made.append(
                Candidate(
                    catalog_material_id=row.id,
                    name=row.name,
                    category=row.category,
                    manufacturer=row.manufacturer,
                    subsystem=row.subsystem,
                    role=row.role,
                    value_count=self.counts.get(row.id, 0),
                    matched_by=how,
                    matched_on=field,
                    matched_text=text,
                )
            )
        # 강한 근거 → 실제 제품(근거용 · 범위 밖보다) → 값이 많은 것 → 이름.
        made.sort(
            key=lambda one: (
                MATCH_ORDER.index(one.matched_by),
                one.role != "product",
                -one.value_count,
                one.name,
            )
        )
        return made[:limit]


def _prefixes(name: str) -> list[str]:
    """이름 앞에서부터 낱말을 붙여 간 것 — `Al6063-T6 Bilinear` → `al6063` · `al6063t6` ….
    **바로 뒤가 블렌드 표지인 자리에서는 끊지 않는다** — `PC/ABS Blend` 는 `pc` 로 안 걸리고
    `pcabs` 로는 걸린다."""
    folded = name.casefold()
    out: list[str] = []
    run = ""
    for at, found in enumerate(_WORD.finditer(folded)):
        if at >= MAX_RUN:
            break
        run += found.group()
        if not _BLEND.match(folded, found.end()):
            out.append(run)
    return out


def for_materials(
    db: Session, materials: Iterable[Material], *, limit: int = PER_MATERIAL
) -> dict[uuid.UUID, list[Candidate]]:
    """재료마다 후보 — 색인은 한 번만 만든다."""
    index = Index.load(db)
    return {one.id: index.candidates(one, limit=limit) for one in materials}
