"""카드 항목란 — 표와 레지스트리 사이 (ADR 0033).

계산식(`app/modules/formulas/services.py`)과 같은 모양이다: 행 → `BlockSpec`,
저장 전 검사, 기동·저장 때 `sync`. 다른 점 하나는 **내장을 못 덮는다**는 것이고,
그 판정은 `matcore.cards.install` 이 한다.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.fitting.models import CardBlock, PropertyCard
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.text import clean
from matcore import cards, units
from matcore.registry import Produced

logger = logging.getLogger(__name__)

#: 키에 쓸 수 있는 글자. **점이 없다** — 덱 정의가 값을 `블록.슬롯` 으로 가리키고
#: 그 해석이 첫 점 기준이라(`path.partition(".")`), 점이 든 키는 가리킬 수가 없다.
KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

#: 한 항목란이 들 수 있는 슬롯 수. 상한이 없으면 화면이 무너지고, 덱 한 줄에
#: 백 칸을 적는 정의가 생긴다.
MAX_SLOTS = 40


def _text(value: object) -> str:
    """다듬은 글자. **`None` 을 안 돌려준다** — 아래 검사들이 전부 문자열을 본다."""
    return clean(str(value or "")) or ""


def _slots(raw: list[dict[str, Any]], where: str) -> tuple[Produced, ...]:
    """선언 목록 하나를 검사해 `Produced` 로. **여기서만 모양을 믿는다.**"""
    if len(raw) > MAX_SLOTS:
        raise AppError(
            "MNX-CARDBLOCK-0002",
            f"{where} 가 {len(raw)}개입니다 — {MAX_SLOTS}개까지입니다.",
            status=422,
        )
    out: list[Produced] = []
    seen: set[str] = set()
    for one in raw:
        key = _text(one.get("key"))
        label = _text(one.get("label"))
        unit = _text(one.get("si_unit")) or "1"
        if not KEY.match(key):
            raise AppError(
                "MNX-CARDBLOCK-0002",
                f"{where} 의 이름 '{key}' 는 쓸 수 없습니다 — 영소문자로 시작하고 "
                "영소문자·숫자·밑줄만, 2~40자입니다(점은 못 씁니다).",
                status=422,
            )
        if not label:
            # **이름 없는 선언을 막는다.** 비면 화면에 키가 그대로 뜨고, 그것이
            # 무엇인지는 만든 사람만 안다.
            raise AppError(
                "MNX-CARDBLOCK-0002", f"{where} '{key}' 에 이름이 없습니다.", status=422
            )
        if key in seen:
            raise AppError(
                "MNX-CARDBLOCK-0002", f"{where} 에 '{key}' 가 두 번 있습니다.", status=422
            )
        if units.canonical(unit) is None:
            raise AppError(
                "MNX-CARDBLOCK-0003",
                f"'{key}' 의 단위 '{unit}' 가 단위표에 없습니다 — "
                "SI 정본(Pa · 1 · K …)으로 적으세요.",
                status=422,
            )
        seen.add(key)
        out.append(
            Produced(
                key=key,
                label=label,
                si_unit=unit,
                help=_text(one.get("help")) or None,
                property_key=_text(one.get("property_key")) or None,
            )
        )
    return tuple(out)


def spec_of(row: CardBlock) -> cards.BlockSpec:
    """행 → 레지스트리가 아는 모양."""
    produces = _slots(list(row.produces or []), "값")
    made_rows = _slots(list(row.rows or []), "표의 열")
    columns = {one.key for one in made_rows}
    curve: tuple[str, str] | None = None
    if row.curve_x and row.curve_y:
        if not {row.curve_x, row.curve_y} <= columns:
            raise AppError(
                "MNX-CARDBLOCK-0004",
                f"곡선 축({row.curve_x} · {row.curve_y})이 표의 열에 없습니다.",
                status=422,
            )
        curve = (row.curve_x, row.curve_y)
    return cards.BlockSpec(
        key=row.key,
        label=row.label,
        help=row.help or "",
        produces=produces,
        rows=made_rows,
        # **컬럼 기본값은 아직 안 채워져 있다.** 저장 전에도 이 함수를 부르는데
        # (`validate`), 그때 행은 파이썬 객체일 뿐이라 `default=` 가 안 돈다.
        order=int(row.sort_order or 200),
        kind_priority=row.kind_priority,
        curve=curve,
        from_tests=tuple(row.from_tests or []),
        # **등급 판정이 읽는다.** 코드의 목록에 이름을 더하러 가지 않게 한다.
        meta={
            "measured": bool(row.measured),
            "origin": "db",
            "version": int(row.version or 1),
        },
    )


def validate(db: Session, row: CardBlock) -> None:
    """저장 전에 부른다 — 키·슬롯·단위·내장 충돌."""
    if not KEY.match(row.key or ""):
        raise AppError(
            "MNX-CARDBLOCK-0001",
            f"키 '{row.key}' 는 쓸 수 없습니다 — 영소문자로 시작하고 영소문자·숫자·"
            "밑줄만, 2~40자입니다. **점은 못 씁니다**(덱 정의가 `블록.슬롯` 으로 가리킵니다).",
            status=422,
        )
    if cards.is_builtin(row.key):
        raise Conflict(
            "MNX-CARDBLOCK-0005",
            f"'{row.key}' 는 내장 항목란입니다 — 덮을 수 없습니다. 다른 키로 만드세요.",
        )
    spec = spec_of(row)
    if not spec.produces and not spec.rows:
        raise AppError(
            "MNX-CARDBLOCK-0006",
            "값도 표도 없는 항목란은 만들지 않습니다 — 담을 것이 없습니다.",
            status=422,
        )
    _known_tests(db, spec.from_tests)


def _known_tests(db: Session, keys: tuple[str, ...]) -> None:
    """`from_tests` 가 실재하는 시험 종류인가. **오타를 여기서 잡는다** —
    안 잡으면 준비도가 「이 시험을 하면 생긴다」 로 없는 시험을 가리킨다."""
    if not keys:
        return
    from app.modules.tests.models import TestType

    found = set(db.scalars(select(TestType.key).where(TestType.key.in_(list(keys)))))
    missing = sorted(set(keys) - found)
    if missing:
        raise AppError(
            "MNX-CARDBLOCK-0007",
            f"그런 시험 종류가 없습니다: {', '.join(missing)}",
            status=422,
        )


# ── 레지스트리 ───────────────────────────────────────────────────────────────


def sync(db: Session) -> list[str]:
    """켜진 항목란을 전부 레지스트리에 얹고, 꺼진·지운 것은 뺀다. 얹은 키를 돌려준다.

    기동 때와 저장할 때 부른다. 멱등이다. **하나가 잘못돼도 나머지는 산다** —
    확장 로더·계산식과 같은 판단이다. 잘못된 항목란 하나 때문에 카드 화면이
    통째로 비면 그게 더 나쁘다.
    """
    cards.load_builtin()
    wanted: set[str] = set()
    for row in db.scalars(select(CardBlock)).all():
        if not row.enabled:
            continue
        try:
            wanted.add(cards.install(spec_of(row)))
        except (cards.CardError, AppError) as exc:
            logger.error("카드 항목란 '%s' 를 얹지 못했습니다 — %s", row.key, exc)
    for key in cards.installed():
        if key not in wanted:
            cards.uninstall(key)
    return sorted(wanted)


# ── 쓰기 ─────────────────────────────────────────────────────────────────────


def create(db: Session, payload: dict[str, Any], user: User) -> CardBlock:
    key = _text(payload.get("key"))
    if db.scalar(select(CardBlock).where(CardBlock.key == key)) is not None:
        raise Conflict("MNX-CARDBLOCK-0008", f"이미 있는 항목란 키입니다: {key}")
    row = CardBlock(
        key=key,
        label=_text(payload.get("label")) or key,
        help=_text(payload.get("help")),
        produces=list(payload.get("produces") or []),
        rows=list(payload.get("rows") or []),
        sort_order=int(payload.get("sort_order") or 200),
        kind_priority=payload.get("kind_priority"),
        curve_x=_text(payload.get("curve_x")) or None,
        curve_y=_text(payload.get("curve_y")) or None,
        from_tests=list(payload.get("from_tests") or []),
        measured=bool(payload.get("measured")),
        created_by_id=user.id,
    )
    validate(db, row)
    db.add(row)
    db.flush()
    return row


#: 바꾸면 판이 오르는 것 — **카드에 담기는 모양이 달라지는 칸.**
EDITABLE = (
    "produces",
    "rows",
    "curve_x",
    "curve_y",
    "from_tests",
    "measured",
)
#: 바꿔도 판이 안 오르는 것 — 이름 하나 고쳤다고 리비전이 찍히면 안 된다.
COSMETIC = ("label", "help", "sort_order", "kind_priority")


def update(db: Session, row: CardBlock, payload: dict[str, Any]) -> CardBlock:
    """고친다. **키는 안 바뀐다** — 카드가 그 키로 값을 들고 있다."""
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
    validate(db, row)
    db.flush()
    return row


def cards_using(db: Session, row: CardBlock) -> int:
    """이 항목란을 담고 있는 카드 수. **지우기를 막는 근거다.**

    JSONB 의 키를 본다 — 값이 비어 있어도 담긴 것은 담긴 것이다.
    """
    count = db.scalar(
        select(func.count())
        .select_from(PropertyCard)
        .where(cast(PropertyCard.blocks, String).contains(f'"{row.key}":'))
    )
    return int(count or 0)


def delete(db: Session, row: CardBlock) -> None:
    held = cards_using(db, row)
    if held:
        raise AppError(
            "MNX-CARDBLOCK-0009",
            f"카드 {held}건이 이 항목란을 담고 있어 못 지웁니다 — 대신 끄세요"
            "(옛 카드의 값은 그대로 남습니다).",
            status=409,
        )
    db.delete(row)
    db.flush()


def get(db: Session, block_id: uuid.UUID) -> CardBlock:
    row = db.get(CardBlock, block_id)
    if row is None:
        raise NotFound("MNX-CARDBLOCK-0010", "없는 카드 항목란입니다.")
    return row
