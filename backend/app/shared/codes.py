"""고유 번호 — 재료 `M` · 시료 `S` · 시편 `P` · 시험 `T`(2026-09-30, ADR 0043).

이름(`SECC_MDOI_1.0__01__MD_01__TEN_01`)은 밑줄로 엮여 길고, 기준정보 개명 · 다른 두께로
옮기기에 따라 바뀐다. 말 · 문서 · 라벨로 가리킬 **짧고 안 바뀌는 손잡이**가 번호다. DB
시퀀스가 매기고(server default — 만드는 코드가 몰라도 붙는다), 지워도 재사용하지 않는다.
재료 번호(2026-09-05)를 넷으로 넓혔다 — 머리글자는 사용자가 골랐다(2026-09-30).

## 사람은 번호를 여러 꼴로 친다

`T-000203` · `T-203` · `t203` 은 같은 번호다. 여기서 한 꼴로 맞춘다 — 정확 일치라 유니크
색인을 그대로 탄다(재료 목록이 전부터 `M-140` 을 이렇게 맞춰 왔다).

## 번호로 사슬을 찾는다

시험 목록에 **시편 번호**를 쳐도 그 시편의 시험이 나와야 한다 — 사람은 손에 든 라벨의
번호를 친다. `chain` 이 번호 하나를 재료 · 시료 · 시편 · 시험 id 로 푼다(아래 것은 비어
있다). 목록마다 그 사슬에서 자기 칸을 골라 건다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import TestRun

#: 온톨로지 종류 → 머리글자. **바꾸지 않는다** — 문서 · 라벨에 이미 적혀 나간다.
PREFIXES = {"material": "M", "sample": "S", "specimen": "P", "test_run": "T"}
_KINDS = {prefix: kind for kind, prefix in PREFIXES.items()}

#: 자릿수. `lpad` 는 넘으면 **조용히 자르므로** 시퀀스에 maxvalue 를 같이 둔다(models).
DIGITS = 6

_SHAPE = re.compile(r"([MSPTmspt])-?(\d{1,6})")


@dataclass(frozen=True)
class Code:
    kind: str
    """`material` · `sample` · `specimen` · `test_run`."""
    value: str
    """맞춘 꼴 — `T-000203`."""


def parse(text: str) -> Code | None:
    """번호 꼴이면 맞춘 번호, 아니면 `None`. 앞뒤 공백은 본다 — 복사해 붙이면 붙어 온다."""
    shape = _SHAPE.fullmatch(text.strip())
    if shape is None:
        return None
    prefix = shape.group(1).upper()
    return Code(kind=_KINDS[prefix], value=f"{prefix}-{int(shape.group(2)):0{DIGITS}d}")


def of_kind(text: str, kind: str) -> str | None:
    """이 종류의 번호 꼴이면 맞춘 번호."""
    code = parse(text)
    return code.value if code is not None and code.kind == kind else None


@dataclass(frozen=True)
class Chain:
    """번호 하나가 가리키는 사슬. **번호의 종류보다 아래는 비어 있다.**"""

    material_id: uuid.UUID
    sample_id: uuid.UUID | None = None
    specimen_id: uuid.UUID | None = None
    test_run_id: uuid.UUID | None = None


def chain(db: Session, text: str) -> Chain | None:
    """번호 → 사슬. 번호 꼴이 아니거나 없는 번호면 `None`. **지운 것도 푼다** — 가시 범위와
    지움은 목록의 거르기가 따로 건다(여기서 거르면 규칙이 두 벌이 된다)."""
    code = parse(text)
    if code is None:
        return None
    if code.kind == "material":
        found = db.scalar(select(Material.id).where(Material.code == code.value))
        return Chain(material_id=found) if found else None
    if code.kind == "sample":
        sample = db.execute(
            select(Sample.id, Sample.material_id).where(Sample.code == code.value)
        ).first()
        return Chain(material_id=sample[1], sample_id=sample[0]) if sample else None
    if code.kind == "specimen":
        specimen = db.execute(
            select(Specimen.id, Sample.id, Sample.material_id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Specimen.code == code.value)
        ).first()
        if specimen is None:
            return None
        return Chain(material_id=specimen[2], sample_id=specimen[1], specimen_id=specimen[0])
    run = db.execute(
        select(TestRun.id, Specimen.id, Sample.id, Sample.material_id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(TestRun.code == code.value)
    ).first()
    if run is None:
        return None
    return Chain(material_id=run[3], sample_id=run[2], specimen_id=run[1], test_run_id=run[0])


def specimen_ids(db: Session, found: Chain) -> list[uuid.UUID]:
    """사슬 아래의 시편들 — 시험 목록이 재료 · 시료 번호로 거를 때. **값이 박힌 `IN`** 으로
    걸려고 먼저 푼다(`IN (SELECT …)` 은 `OR` 가지에서 trgm 색인까지 무의미하게 만든다)."""
    if found.specimen_id is not None:
        return [found.specimen_id]
    query = select(Specimen.id).join(Sample, Sample.id == Specimen.sample_id)
    if found.sample_id is not None:
        query = query.where(Specimen.sample_id == found.sample_id)
    else:
        query = query.where(Sample.material_id == found.material_id)
    return list(db.scalars(query))
