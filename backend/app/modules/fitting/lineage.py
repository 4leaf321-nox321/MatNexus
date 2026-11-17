"""덱의 값이 **어디서 왔나** — 카드 → 재료 · 근거 시험 · 처리 결과 · 문헌 재료(2026-11-17).

실측(HWAX 연결): 덱 값의 출처를 거꾸로 찾을 길이 없었다. 덱 MID 는 카드 UUID 를 줄인 해시라
(`export.solver_id_from`) 거꾸로 셀 수 없고, 덱 머리에는 카드 번호만 있고 재료 · 시험 id 가
없었다. 「탄성계수: 이 시험들에서 잰 값」 의 「이 시험들」 이 어느 것인지는 덱만 봐서는 몰랐다.

그래서 두 길을 둔다.

    card_origin     카드 하나 → 재료 · 근거 시험(id · 코드) — BOM 덱의 줄 · 카드 덱의 머리
    deck_sources    덱 글자 → MID 마다 머리의 「카드 C-… · <id>」 · 「문헌 카탈로그: … · <id>」

**전역 MID 를 관리하지 않는다**(`solver_id_from` 의 결정). 덱 글자가 출처를 들고 다니고, 그
글자에서 거꾸로 읽는다 — 우리가 「어느 덱에 어느 번호를 썼나」 를 따로 적기 시작하면 그
기록도 관리해야 한다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material
from app.modules.tests.models import TestRun

#: 덱 머리에 적는 근거 시험 코드의 최대 수 — 넘으면 「외 n건」.
HEADER_RUNS = 12


@dataclass(frozen=True)
class Origin:
    card_id: uuid.UUID
    card_code: str
    card_status: str
    material_id: uuid.UUID | None
    material_code: str | None
    material_name: str | None
    test_run_ids: list[uuid.UUID] = field(default_factory=list)
    test_run_codes: list[str] = field(default_factory=list)


def _run_ids(card: PropertyCard) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for raw in (card.source or {}).get("test_run_ids") or []:
        try:
            out.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    return out


def card_origin(db: Session, card: PropertyCard) -> Origin:
    """카드 → 재료 · 근거 시험. 지워진 시험은 id 만 남는다(코드는 못 찾는다)."""
    material = db.get(Material, card.material_id) if card.material_id else None
    ids = _run_ids(card)
    codes = (
        {
            run_id: code
            for run_id, code in db.execute(
                select(TestRun.id, TestRun.code).where(TestRun.id.in_(ids))
            ).tuples()
        }
        if ids
        else {}
    )
    return Origin(
        card_id=card.id,
        card_code=card.code,
        card_status=card.status,
        material_id=material.id if material else None,
        material_code=material.code if material else None,
        material_name=material.record_name if material else None,
        test_run_ids=ids,
        test_run_codes=[codes[one] for one in ids if one in codes],
    )


def header_line(origin: Origin) -> str:
    """덱 머리의 근거 한 줄 — 「근거: 재료 M-000123 · 시험 T-000001, T-000002」."""
    material = f"재료 {origin.material_code}" if origin.material_code else "재료 ?"
    if not origin.test_run_ids:
        return f"근거: {material} — 시험 없음(재료에 적힌 값)"
    shown = origin.test_run_codes[:HEADER_RUNS]
    rest = len(origin.test_run_ids) - len(shown)
    tail = f" 외 {rest}건" if rest > 0 else ""
    return f"근거: {material} · 시험 {', '.join(shown) or '(지워짐)'}{tail}"


# ── 덱 글자에서 거꾸로 ─────────────────────────────────────────────────────

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
#: 카드 덱 머리 — `export_card` · BOM 의 카드 줄(`_deck_for_card` 의 「카드 {code} · {id}」).
_CARD = re.compile(rf"카드\s+(C-\d+)\s+·\s+({_UUID})")
#: 문헌 줄 머리 — `literature_material.virtual` 의 「문헌 카탈로그: {이름} · {id}」.
_CATALOG = re.compile(rf"문헌 카탈로그:\s*(.+?)\s+·\s+({_UUID})")
#: 주석 줄의 머리 — LS-DYNA `$` · Abaqus `**` · Radioss `#` · 그 밖의 `//`.
_COMMENT = ("$", "**", "#", "//")


@dataclass
class Found:
    """덱 안의 재료 하나 — 머리 주석에서 찾은 출처와, LS-DYNA 면 그 재료 카드의 MID."""

    mid: int | None = None
    keyword: str | None = None
    card_id: uuid.UUID | None = None
    card_code: str | None = None
    catalog_material_id: uuid.UUID | None = None
    catalog_material_name: str | None = None

    @property
    def empty(self) -> bool:
        return self.card_id is None and self.catalog_material_id is None


def _mid_of(lines: list[str], start: int) -> int | None:
    """`*MAT…` 다음의 첫 자료 줄의 첫 칸. `_TITLE` 이면 그다음 줄."""
    titled = lines[start].split()[0].upper().rstrip("+-").endswith("_TITLE")
    seen = 0
    for line in lines[start + 1 :]:
        if line.startswith("*"):
            return None
        if line.startswith("$") or not line.strip():
            continue
        seen += 1
        if titled and seen == 1:
            continue
        head = line.split(",")[0] if "," in line else line[:10]
        try:
            return int(float(head.strip()))
        except ValueError:
            return None
    return None


def deck_sources(text: str) -> list[Found]:
    """덱 글자 → 재료마다 출처. 머리 주석이 없는 재료(손으로 고친 덱)는 MID 만 있다.

    LS-DYNA 는 `*MAT` 카드마다 바로 앞 머리 주석의 출처를 그 MID 에 묶는다. 다른 솔버는 MID
    없이 출처만.
    """
    lines = text.splitlines()
    out: list[Found] = []
    pending = Found()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(_COMMENT):
            card = _CARD.search(stripped)
            if card:
                pending.card_code, pending.card_id = card.group(1), uuid.UUID(card.group(2))
            catalog = _CATALOG.search(stripped)
            if catalog:
                pending.catalog_material_name = catalog.group(1)
                pending.catalog_material_id = uuid.UUID(catalog.group(2))
            continue
        if stripped.upper().startswith("*MAT"):
            pending.keyword = stripped.split()[0]
            pending.mid = _mid_of(lines, index)
            out.append(pending)
            pending = Found()
    if not pending.empty:
        # LS-DYNA 가 아닌 덱 — 재료 카드를 못 찾았어도 머리의 출처는 돌려준다.
        out.append(pending)
    return out


def describe(db: Session, card: PropertyCard) -> dict[str, Any]:
    """카드의 계보 전부 — `GET /fitting/cards/{id}/lineage` 의 몸통(스키마는 라우트가)."""
    origin = card_origin(db, card)
    runs = (
        list(db.scalars(select(TestRun).where(TestRun.id.in_(origin.test_run_ids))))
        if origin.test_run_ids
        else []
    )
    by_id = {run.id: run for run in runs}
    source = card.source or {}
    basis = {
        key: source[key]
        for key in (
            "group_result_id",
            "plugin_id",
            "master_curve_id",
            "prony_fit_id",
            "modulus_table_ids",
            "parameter_set_ids",
        )
        if source.get(key)
    }
    return {
        "origin": origin,
        "runs": [
            {
                "id": one,
                "code": by_id[one].code if one in by_id else None,
                "name": by_id[one].record_name if one in by_id else None,
                "adopted_result_id": by_id[one].adopted_result_id if one in by_id else None,
                "deleted": one not in by_id or by_id[one].deleted_at is not None,
            }
            for one in origin.test_run_ids
        ],
        "basis": basis,
        "sample_count": source.get("sample_count"),
        "declared_only": bool(source.get("declared_only")),
    }
