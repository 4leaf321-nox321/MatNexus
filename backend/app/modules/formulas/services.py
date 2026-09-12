"""계산식 — 표와 레지스트리 사이 (ADR 0030 D3·D4)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import PropertyCard
from app.modules.formulas.models import KINDS, Formula
from app.modules.processing.models import ProcessingRecipe, ProcessingResult
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.text import clean
from matcore import formulas as kit
from matcore import units
from matcore.registry import Produced

logger = logging.getLogger(__name__)


def spec_of(row: Formula) -> kit.FormulaSpec:
    """행 → 계산 커널이 아는 모양."""
    result = row.result or None
    return kit.FormulaSpec(
        key=row.key,
        kind=row.kind,
        label=row.label,
        expression=row.expression,
        variables=tuple(
            kit.Variable(
                name=str(one["name"]), unit=str(one.get("unit") or "1"), label=one.get("label")
            )
            for one in row.variables or []
        ),
        parameters=tuple(
            kit.Parameter(
                name=str(one["name"]),
                unit=str(one.get("unit") or "1"),
                initial=float(one.get("initial", 1.0)),
                lower=float(one["lower"]) if one.get("lower") is not None else float("-inf"),
                upper=float(one["upper"]) if one.get("upper") is not None else float("inf"),
            )
            for one in row.parameters or []
        ),
        result=(
            Produced(
                key=str(result["key"]),
                label=str(result.get("label") or result["key"]),
                si_unit=str(result.get("si_unit") or "1"),
            )
            if result
            else None
        ),
        x_column=row.x_column or "strain_true_plastic",
        y_column=row.y_column or "stress_true",
        block=row.block or "hardening",
        applies_to=tuple(row.applies_to or []),
        describe=row.describe or "",
        version=str(row.version),
    )


def validate(row: Formula) -> None:
    """읽히는지, 자리에 맞는지, 단위가 표에 있는지. **저장 전에** 부른다."""
    if row.kind not in KINDS:
        raise AppError(
            "MNX-FORMULAS-0001", f"자리는 {', '.join(KINDS)} 중 하나입니다.", status=422
        )
    try:
        kit.validate(spec_of(row))
    except kit.FormulaSpecError as exc:
        raise AppError("MNX-FORMULAS-0002", str(exc), status=422) from exc
    for one in [
        *(row.variables or []),
        *(row.parameters or []),
        *([row.result] if row.result else []),
    ]:
        unit = str(one.get("unit") or one.get("si_unit") or "1")
        if units.canonical(unit) is None:
            raise AppError(
                "MNX-FORMULAS-0003",
                f"'{one.get('name') or one.get('key')}' 의 단위 '{unit}' 가 "
                "단위표에 없습니다 — SI 정본(Pa · 1 · K …)으로 적으세요.",
                status=422,
            )


# ── 레지스트리 ───────────────────────────────────────────────────────────────


def sync(db: Session) -> list[str]:
    """표의 켜진 식을 전부 레지스트리에 넣고, 꺼진·지운 것은 뺀다. 넣은 키를 돌려준다.

    기동 때와 저장할 때 부른다. 멱등이다 — 같은 판이면 같은 것으로 바뀔 뿐이다.
    **한 식이 잘못돼도 나머지는 산다** — 확장 로더와 같은 판단.
    """
    rows = db.scalars(select(Formula)).all()
    wanted: set[str] = set()
    for row in rows:
        if not row.enabled:
            continue
        try:
            wanted.add(kit.install(spec_of(row)))
        except kit.FormulaSpecError as exc:
            logger.error("계산식 '%s' 를 등록하지 못했습니다 — %s", row.key, exc)
    for key in kit.installed():
        if key not in wanted:
            kit.uninstall(key)
    return sorted(wanted)


# ── 쓰기 ─────────────────────────────────────────────────────────────────────


def create(db: Session, payload: dict[str, Any], user: User) -> Formula:
    key = clean(str(payload.get("key") or ""))
    if not key:
        raise AppError("MNX-FORMULAS-0004", "key 가 비었습니다.", status=422)
    if db.scalar(select(Formula).where(Formula.key == key)) is not None:
        raise Conflict("MNX-FORMULAS-0005", f"이미 있는 계산식 키입니다: {key}")
    row = Formula(
        key=key,
        kind=str(payload.get("kind") or ""),
        label=clean(str(payload.get("label") or "")) or key,
        expression=str(payload.get("expression") or ""),
        describe=clean(str(payload.get("describe") or "")) or None,
        variables=list(payload.get("variables") or []),
        parameters=list(payload.get("parameters") or []),
        result=payload.get("result") or None,
        x_column=payload.get("x_column") or None,
        y_column=payload.get("y_column") or None,
        block=payload.get("block") or None,
        applies_to=list(payload.get("applies_to") or []),
        created_by_id=user.id,
    )
    validate(row)
    db.add(row)
    db.flush()
    return row


#: 바꾸면 판이 오르는 것 — 계산이 달라지는 칸.
EDITABLE = (
    "expression",
    "variables",
    "parameters",
    "result",
    "x_column",
    "y_column",
    "block",
    "applies_to",
)
#: 바꿔도 판이 안 오르는 것 — 라벨 하나 바꿨다고 리비전이 찍히면 안 된다.
COSMETIC = ("label", "describe")


def update(db: Session, row: Formula, payload: dict[str, Any]) -> Formula:
    """고친다. **판이 오른다** — 저장된 결과는 옛 판을 든 채 그대로다(D4).

    라벨·설명·`enabled` 는 판을 안 올린다 — 이름을 고치거나 끄고 켜는 것은 식이
    바뀐 게 아니다."""
    bumped = False
    for field in (*EDITABLE, *COSMETIC):
        if field not in payload or payload[field] is None:
            continue
        value = payload[field]
        if isinstance(value, str):
            value = clean(value) or None
        if getattr(row, field) != value:
            setattr(row, field, value)
            bumped = bumped or field in EDITABLE
    if "enabled" in payload and payload["enabled"] is not None:
        row.enabled = bool(payload["enabled"])
    if bumped:
        row.version = int(row.version) + 1
    validate(row)
    db.flush()
    return row


def references(db: Session, row: Formula) -> dict[str, int]:
    """이 식을 가리키는 것 — 레시피·처리 결과·카드. 지우기를 막는 근거다."""
    key = row.registry_key
    quoted = f'"{key}"'
    recipes = db.scalar(
        select(func.count())
        .select_from(ProcessingRecipe)
        .where(cast(ProcessingRecipe.steps, String).contains(quoted))
    )
    results = db.scalar(
        select(func.count())
        .select_from(ProcessingResult)
        .where(cast(ProcessingResult.steps_snapshot, String).contains(quoted))
    )
    cards = db.scalar(
        select(func.count())
        .select_from(PropertyCard)
        .where(or_(cast(PropertyCard.blocks, String).contains(quoted)))
    )
    return {
        "recipes": int(recipes or 0),
        "results": int(results or 0),
        "cards": int(cards or 0),
    }


def delete(db: Session, row: Formula) -> None:
    held = {label: count for label, count in references(db, row).items() if count}
    if held:
        shown = " · ".join(
            f"{ {'recipes': '레시피', 'results': '처리 결과', 'cards': '카드'}[k] } {v}건"
            for k, v in held.items()
        )
        raise AppError(
            "MNX-FORMULAS-0006",
            f"이 식을 {shown}이 쓰고 있어 못 지웁니다 — "
            "대신 끄세요(옛 결과는 그대로 읽힙니다).",
            status=409,
        )
    db.delete(row)
    db.flush()


def get(db: Session, formula_id: uuid.UUID) -> Formula:
    row = db.get(Formula, formula_id)
    if row is None:
        raise NotFound("MNX-FORMULAS-0007", "없는 계산식입니다.")
    return row
