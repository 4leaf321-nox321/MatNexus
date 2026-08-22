"""시험 요약표 흡수 — **곡선 없이 값만 들어온다.**

기존 앱이 내보낸 `tensile-test-for-multiple-data_*.csv` 는 **한 줄 = 시험 하나**인
넓은 요약표다(입력파일명·시편번호·장비·속도·항복점·최대하중·치수 …). 곡선이 없다.

곡선이 없다고 못 쓰는 데이터가 아니다. **낼 수 있는 물성의 범위가 다를 뿐이다** —
통계도 되고 카드의 근거도 된다. 안 되는 것은 곡선을 다시 처리하는 일뿐이다.

## 시편을 어떻게 찾는가

표에는 `시편번호` 가 있고 재료 이름은 없다 — 한 파일이 대개 한 시료 분이기
때문이다. 그래서 **어느 시료의 표인지는 사람이 고르고**, 줄은 그 안에서 시편을
가리킨다.

    시편 열이 `MD-1` 이거나 `1`      →  그 시료의 그 시편
    없으면                            →  옵션에 따라 거절하거나 만든다

**없는 시편을 만들지 말지를 옵션으로 둔다.** 만들면 편하지만 오타 하나가 유령
시편을 만든다 — 기준정보에서 겪은 것과 같은 병이다. 그래서 기본은 끔이다.

## 같은 표를 두 번 붙여도 두 배가 되지 않는다

`원본 파일명` 열이 있으면 그것으로 이미 들어온 줄을 알아본다. 시험은 같은 시편에
여러 번 있을 수 있어서(seq_no) **시편만으로는 중복을 알 수 없다.**
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.materials.models import Sample, Specimen
from app.modules.tests.models import TestConditionField, TestRun, TestSummary, TestType
from app.shared.errors import AppError
from matcore import naming, units

#: 열 이름이 이 뜻을 가리킨다. 나머지는 조건이거나 요약값이다.
HEADER_SPECIMEN = ("시편", "시편번호", "specimen")
HEADER_ORIENTATION = ("방향", "orientation")
HEADER_SOURCE = ("원본 파일명", "입력파일명", "파일명", "source", "file")

#: `항복강도 (MPa)` 에서 단위를 떼는 자리. 기준정보 붙여넣기와 같은 규칙이다.
_UNIT = re.compile(r"^(?P<name>.+?)\s*[(\[](?P<unit>[^)\]]+)[)\]]\s*$")

#: 요약값 키로 쓸 수 있는 글자. 나머지는 밑줄로 바꾼다.
_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(label: str) -> str:
    """사람이 적은 이름을 키로. **키는 저장되는 계약이다.**

    영문 이름은 소문자·밑줄로 정리하고, **한글 이름은 그대로 쓴다.** 65 가 내보낸
    표의 열 이름이 한글이라, 여기서 거절하면 이 기능이 통째로 쓸모없어진다.
    `field_1` 처럼 **지어낸 키**를 쌓지 않는다는 것이 원래 규칙인데, 사람이 적은
    이름을 그대로 쓰는 것은 지어내는 것이 아니다.

    ## 파서가 낸 키와는 안 맞는다

    `.tra` 파서는 `tensile_strength` 로 적고 표는 `인장강도` 로 적는다. 같은
    물성인데 키가 달라 **통계가 한 묶음으로 못 본다.** 지금은 열 이름을
    영문 키로 바꿔 적는 것이 유일한 길이다 — 매핑은 형식 프로파일의 일이다.
    """
    ascii_key = _SLUG.sub("_", label.strip().lower()).strip("_")
    return ascii_key or " ".join(label.split())


@dataclass(frozen=True)
class Column:
    """열 하나가 무엇을 가리키는가."""

    kind: str
    """`specimen` · `orientation` · `source` · `condition` · `summary` · `unknown`."""
    key: str = ""
    label: str = ""
    unit: str | None = None
    reason: str | None = None


@dataclass
class Row:
    """표 한 줄이 어떤 시험이 될지. **아무것도 쓰지 않고** 만든다."""

    raw: str
    status: str
    """`new` · `existing` · `rejected` · `skipped`."""
    specimen_label: str = ""
    specimen: Specimen | None = None
    creates_specimen: bool = False
    conditions: dict[str, float] = field(default_factory=dict)
    condition_units: dict[str, str] = field(default_factory=dict)
    summaries: list[tuple[str, str, float | None, str | None, str]] = field(
        default_factory=list
    )
    """`(key, label, value_num, value_text, si_unit)`."""
    origin: str | None = None
    run_name: str | None = None
    """만들어진 시험 이름. **미리보기에서는 비어 있다.**"""
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def read_header(header: list[str], conditions: list[TestConditionField]) -> list[Column]:
    """헤더 줄을 열 뜻으로 바꾼다.

    **조건은 시험 종류가 선언한 것만** 조건으로 본다. 나머지 숫자 열은 요약값이다 —
    표마다 열이 다르고, 그걸 미리 알 방법이 없다.
    """
    by_name: dict[str, tuple[str, str]] = {}
    for spec in conditions:
        for name in (spec.label, spec.key):
            if name:
                by_name[name.strip().casefold()] = (spec.key, spec.si_unit or "1")

    columns: list[Column] = []
    for raw in header:
        text = raw.strip()
        folded = text.casefold()
        if folded in {one.casefold() for one in HEADER_SPECIMEN}:
            columns.append(Column("specimen"))
            continue
        if folded in {one.casefold() for one in HEADER_ORIENTATION}:
            columns.append(Column("orientation"))
            continue
        if folded in {one.casefold() for one in HEADER_SOURCE}:
            columns.append(Column("source"))
            continue

        unit: str | None = None
        matched = _UNIT.match(text)
        name = text
        if matched:
            name = matched.group("name").strip()
            unit = matched.group("unit").strip()

        condition = by_name.get(name.casefold())
        if condition is not None:
            columns.append(
                Column("condition", key=condition[0], label=name, unit=unit or condition[1])
            )
            continue

        key = _slug(name)
        if not key:
            columns.append(
                Column("unknown", label=name, reason=f"'{name}' 은(는) 이름이 비어 있습니다.")
            )
            continue
        columns.append(Column("summary", key=key, label=name, unit=unit))
    return columns


def _si(value: str, unit: str | None) -> tuple[float | None, str]:
    """숫자와 단위를 SI 로. 단위가 없으면 무차원으로 둔다."""
    number = float(value)
    if not unit:
        return number, "1"
    symbol = units.canonical(unit) or unit
    return units.to_si(number, symbol), units.SI_UNITS[units.unit_of(symbol).dimension]


def plan(
    db: Session,
    *,
    sample: Sample,
    definition: TestType,
    lines: list[str],
    create_missing: bool,
) -> list[Row]:
    """표를 읽어 **어떤 시험이 될지** 만든다. 아무것도 쓰지 않는다.

    미리보기와 실제 흡수가 같은 코드로 답해야 한다 — 두 곳에 두면 갈라지고,
    그러면 미리보기가 거짓말을 한다.
    """
    body = [one for one in lines]
    while body and not body[0].strip():
        body.pop(0)
    if not body:
        return []
    conditions_of = list(
        db.scalars(
            select(TestConditionField).where(TestConditionField.test_type_id == definition.id)
        )
    )
    columns = read_header([part.strip() for part in body.pop(0).split("\t")], conditions_of)

    known = {
        specimen.record_name: specimen
        for specimen in db.scalars(
            select(Specimen).where(
                Specimen.sample_id == sample.id, Specimen.deleted_at.is_(None)
            )
        )
    }
    seen_origins = {
        str((run.source_metadata or {}).get("origin_name"))
        for run in db.scalars(
            select(TestRun).where(
                TestRun.specimen_id.in_([one.id for one in known.values()] or [uuid.uuid4()]),
                TestRun.deleted_at.is_(None),
            )
        )
    }

    rows: list[Row] = []
    for raw in body:
        if not raw.strip():
            rows.append(Row(raw, "skipped"))
            continue
        cells = [part.strip() for part in raw.split("\t")]

        label = ""
        orientation = ""
        origin: str | None = None
        conditions: dict[str, float] = {}
        condition_units: dict[str, str] = {}
        summaries: list[tuple[str, str, float | None, str | None, str]] = []
        warnings: list[str] = []

        for index, column in enumerate(columns):
            cell = cells[index] if index < len(cells) else ""
            if column.kind == "specimen":
                label = cell
            elif column.kind == "orientation":
                orientation = cell.upper()
            elif column.kind == "source":
                origin = cell or None
            elif column.kind == "unknown":
                if cell and column.reason and column.reason not in warnings:
                    warnings.append(column.reason)
            elif not cell:
                continue
            elif column.kind == "condition":
                try:
                    value, _ = _si(cell, column.unit)
                except (ValueError, units.UnknownUnit):
                    warnings.append(f"'{column.label}' 값을 못 읽었습니다: {cell}")
                    continue
                if value is not None:
                    conditions[column.key] = value
                    condition_units[column.key] = column.unit or "1"
            else:
                try:
                    # **저장은 SI 다.** 헤더가 MPa 라도 담기는 것은 Pa 이고,
                    # 단위 칸에 MPa 를 적으면 화면이 10^6 배로 읽는다.
                    value, si_unit = _si(cell, column.unit)
                    summaries.append((column.key, column.label, value, None, si_unit))
                except (ValueError, units.UnknownUnit):
                    # **숫자가 아닌 요약값이 있다.** 장비가 "Unknown" 을 적기도 하고
                    # 시험자 이름 같은 글자 열도 섞인다 — 버리지 않고 글자로 담는다.
                    summaries.append((column.key, column.label, None, cell, "1"))

        if not label:
            rows.append(
                Row(raw, "rejected", reason="시편 칸이 비어 있습니다.", warnings=warnings)
            )
            continue

        specimen = known.get(label)
        seq = _seq(label)
        if specimen is None and seq is not None:
            # `MD-3` 이나 `3` 으로 적힌 줄. 시편 이름은 시료·방향·번호로 만들어진다.
            specimen = known.get(
                naming.specimen_name(
                    sample=sample.record_name,
                    orientation=_orientation_of(label, orientation),
                    seq_no=seq,
                )
            )
        if specimen is None and not create_missing:
            rows.append(
                Row(
                    raw,
                    "rejected",
                    specimen_label=label,
                    reason=f"'{label}' 시편이 이 시료에 없습니다. "
                    "'없는 시편 만들기' 를 켜거나 시편을 먼저 등록하세요.",
                    warnings=warnings,
                )
            )
            continue

        if origin and origin in seen_origins:
            # **같은 표를 두 번 붙여도 두 배가 되지 않는다.**
            rows.append(
                Row(
                    raw,
                    "existing",
                    specimen_label=label,
                    specimen=specimen,
                    origin=origin,
                    reason=f"'{origin}' 은(는) 이미 들어왔습니다.",
                    warnings=warnings,
                )
            )
            continue

        rows.append(
            Row(
                raw,
                "new",
                specimen_label=label,
                specimen=specimen,
                creates_specimen=specimen is None,
                conditions=conditions,
                condition_units=condition_units,
                summaries=summaries,
                origin=origin,
                warnings=warnings,
            )
        )
    return rows


def _seq(label: str) -> int | None:
    """`MD-3` · `3` 에서 번호만. 못 읽으면 `None`."""
    found = re.findall(r"\d+", label)
    return int(found[-1]) if found else None


def _orientation_of(label: str, given: str) -> str:
    if given:
        return given
    head = re.match(r"^([A-Za-z]+)", label.strip())
    return head.group(1).upper() if head else "NA"


def apply(
    db: Session,
    *,
    sample: Sample,
    definition: TestType,
    rows: list[Row],
    user_id: uuid.UUID | None,
) -> list[Row]:
    """계획대로 시험을 만든다. **곡선은 없다.**"""
    for row in rows:
        if row.status != "new":
            continue
        specimen = row.specimen
        if specimen is None:
            orientation = _orientation_of(row.specimen_label, "")
            seq_no = _seq(row.specimen_label) or _next_specimen_seq(db, sample, orientation)
            specimen = Specimen(
                workspace_id=sample.workspace_id,
                sample_id=sample.id,
                seq_no=seq_no,
                orientation=orientation,
                record_name=naming.specimen_name(
                    sample=sample.record_name, orientation=orientation, seq_no=seq_no
                ),
                registered_by_id=user_id,
            )
            db.add(specimen)
            db.flush()
            row.specimen = specimen

        seq_no = (
            db.scalar(
                select(func.coalesce(func.max(TestRun.seq_no), 0)).where(
                    TestRun.specimen_id == specimen.id, TestRun.test_type_id == definition.id
                )
            )
            or 0
        ) + 1
        run = TestRun(
            workspace_id=specimen.workspace_id,
            specimen_id=specimen.id,
            test_type_id=definition.id,
            seq_no=seq_no,
            record_name=naming.test_run_name(
                specimen=specimen.record_name, type_abbr=definition.abbr, seq_no=seq_no
            ),
            conditions=row.conditions,
            input_units=row.condition_units,
            # **파일 처리 상태가 아니다.** 원본이 없으므로 읽을 것도 없다.
            status="imported",
            source_metadata={"origin": "summary_import", "origin_name": row.origin},
            registered_by_id=user_id,
        )
        db.add(run)
        db.flush()
        row.run_name = run.record_name

        for key, label, value_num, value_text, si_unit in row.summaries:
            db.add(
                TestSummary(
                    test_run_id=run.id,
                    key=key[:50],
                    label=label[:100],
                    # **장비가 계산한 값이다.** 표로 받았을 뿐이라 출처는 장비다.
                    source="instrument",
                    value_num=value_num,
                    value_text=value_text,
                    si_unit=si_unit,
                )
            )
    return rows


def _next_specimen_seq(db: Session, sample: Sample, orientation: str) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.max(Specimen.seq_no), 0)).where(
                Specimen.sample_id == sample.id, Specimen.orientation == orientation
            )
        )
        or 0
    ) + 1


def require_columns(rows: list[Row]) -> None:
    """넣을 것이 하나도 없으면 말한다."""
    if not any(row.status == "new" for row in rows):
        raise AppError(
            "MNX-TESTS-0032",
            "넣을 줄이 없습니다. 미리보기에서 이유를 확인하세요.",
            status=422,
        )
