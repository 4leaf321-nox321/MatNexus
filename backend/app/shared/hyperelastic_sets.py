"""파라미터 벌 → **초탄성 블록** — 문헌 덱과 사내 카드가 같은 길로(2026-10-08).

문헌 카탈로그에는 초탄성 벌이 450값 · 52재료 있다(Ecoflex · NBR · EPDM 실 · 폼). 덱 렌더러는
초탄성 블록(`hyperelastic`)을 읽는데, 그 벌은 모델 파라미터(ADR 0029)로만 들어와서 덱까지 가는
길이 없었다. 옮기는 규칙은 `matcore.cards.hyperelastic.from_parameter_set` 하나다 — 항 이름이
출처마다 달라(`C10` · `C1` · `mu`) 그 판단을 두 곳에 두면 갈린다.

## 벌이 여럿이면

문헌 재료 하나에 식 · 맞춘 변형 범위 · 노화 조건이 다른 벌이 여럿인 것이 흔하다. 문헌 덱은
고를 화면이 없어서 **정한 차례로 하나를 고르고 나머지를 각주로 말한다** — 등급이 좋은 것,
조건 없는 것, 항이 많은 식(Yeoh > Mooney-Rivlin > Neo-Hookean, 큰 변형을 더 잘 따른다).
다른 벌을 쓰려면 사내 재료로 받아 카드에서 고른다(사내 카드는 사람이 고른 벌만 쓴다).

**단위**: 벌의 항 단위 칸이 비어 있으면 정의의 단위를 쓴다(`catalog.parameters.unit_of`) —
초탄성 계수는 정의가 Pa 다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import QUALITY_TIERS
from matcore.cards.hyperelastic import FromSet, from_parameter_set
from matcore.export import initial_shear

#: 초탄성 계수가 사는 문헌 키. 지수(`hyperelastic_exponent`)는 Ogden · Arruda-Boyce 의 것이라
#: 덱이 받는 식(Neo-Hookean · Mooney-Rivlin · Yeoh)에는 안 쓰인다.
COEFFICIENT_KEY = "mechanical.hyperelastic_coefficient"
BLOCK = "hyperelastic"

#: 사람이 읽는 식 이름.
FAMILY_LABELS = {
    "neo_hookean": "Neo-Hookean",
    "mooney_rivlin": "Mooney-Rivlin",
    "yeoh": "Yeoh",
    "ogden_1": "Ogden (N=1)",
}
#: 여럿일 때 앞서는 식 — 항이 많은 쪽이 큰 변형을 더 잘 따른다.
RICHNESS = {"yeoh": 0, "mooney_rivlin": 1, "neo_hookean": 2}


@dataclass(frozen=True)
class Candidate:
    label: str
    tier: int | None
    variant: str
    source: str | None
    made: FromSet


def block_of(made: FromSet, *, origin: str) -> dict[str, Any]:
    """옮긴 벌 → 카드 블록. 계수는 SI(Pa), 단위계 환산은 덱이 한다."""
    return {
        "values": {
            "family": made.family,
            "label": f"{FAMILY_LABELS.get(made.family, made.family)} ({origin})",
            "shear_modulus": initial_shear(made.family, made.values),
        },
        "rows": [
            {"name": name, "value": value, "si_unit": "Pa"}
            for name, value in made.values.items()
        ],
    }


def terms_of(
    db: Session, key: str, terms: Iterable[dict[str, Any]]
) -> dict[str, tuple[float, str]]:
    """벌의 항 → (값, 단위). 단위 칸이 비면 정의의 단위."""
    out: dict[str, tuple[float, str]] = {}
    for term in terms:
        value = term.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        name = str(term.get("term") or "")
        out[name] = (
            float(value),
            str(term.get("unit") or "") or parameters.unit_of(db, key, name),
        )
    return out


def from_catalog(
    db: Session, material_id: uuid.UUID
) -> tuple[dict[str, Any] | None, list[str]]:
    """문헌 재료의 초탄성 벌 가운데 하나를 블록으로 — `(블록 또는 None, 각주)`."""
    candidates: list[Candidate] = []
    skipped: list[str] = []
    for found in parameters.sets(db, key=COEFFICIENT_KEY, material_id=material_id):
        label = f"{found.model or '?'}/{found.set_id or '-'}" + (
            f" ({found.variant})" if found.variant else ""
        )
        if found.duplicated:
            skipped.append(f"{label}: 같은 항이 두 번")
            continue
        made = from_parameter_set(found.model, terms_of(db, COEFFICIENT_KEY, found.terms))
        if isinstance(made, str):
            skipped.append(f"{label}: {made}")
            continue
        candidates.append(
            Candidate(label, found.quality_tier, found.variant, found.source, made)
        )
    said: list[str] = []
    if not candidates:
        if skipped:
            said.append("문헌 초탄성 벌을 덱으로 옮기지 못했습니다 — " + " · ".join(skipped))
        return None, said
    candidates.sort(
        key=lambda one: (
            one.tier if one.tier is not None else 9,
            bool(one.variant),
            RICHNESS.get(one.made.family, 9),
            one.label,
        )
    )
    chosen = candidates[0]
    tier = QUALITY_TIERS.get(chosen.tier or 0, str(chosen.tier))
    said.append(
        f"초탄성 = {FAMILY_LABELS.get(chosen.made.family, chosen.made.family)} — 문헌 벌 "
        f"{chosen.label} · {chosen.source or '출처 미상'} [tier {chosen.tier}: {tier}]"
        + (f". {chosen.made.note}" if chosen.made.note else "")
    )
    others = [one.label for one in candidates[1:]]
    if others:
        said.append(
            f"다른 초탄성 벌 {len(others)}개({', '.join(others[:4])}"
            + (" …" if len(others) > 4 else "")
            + ")는 안 썼습니다 — 다른 벌을 쓰려면 사내 재료로 받아 카드에서 고르세요."
        )
    if skipped:
        said.append(
            "덱으로 못 옮긴 초탄성 벌: "
            + " · ".join(skipped[:4])
            + (" …" if len(skipped) > 4 else "")
        )
    return block_of(chosen.made, origin="문헌 벌"), said
